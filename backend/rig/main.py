"""FastAPI application — Sprint 1 API surface.

Endpoints are tenant-scoped through the caller's JWT: the DB session for a
request sets `app.tenant_id` from the verified principal, so RLS enforces
isolation below the application layer.
"""

from datetime import date
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from sqlalchemy import text

from . import audit
from .auth import Principal, require
from .db import tenant_session
from .insights import upsert_risk_insight
from .scoring import compute_renewal_risk
from .signals.engine import evaluate_account

app = FastAPI(title="Revenue Intelligence Graph", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/accounts")
def list_accounts(principal: Principal = Depends(require("accounts:read"))):
    with tenant_session(principal.tenant_id) as session:
        rows = session.execute(text(
            "SELECT id, name, segment, tier, arr_cents, renewal_date, lifecycle_stage,"
            " plan_status FROM account WHERE deleted_at IS NULL ORDER BY renewal_date NULLS LAST"
        )).mappings().all()
        return {"accounts": [dict(r) for r in rows]}


@app.get("/v1/accounts/{account_id}")
def get_account(account_id: UUID, principal: Principal = Depends(require("accounts:read"))):
    with tenant_session(principal.tenant_id) as session:
        account = session.execute(
            text("SELECT * FROM account WHERE id = :aid AND deleted_at IS NULL"),
            {"aid": str(account_id)},
        ).mappings().one_or_none()
        if account is None:
            raise HTTPException(status_code=404, detail="account not found")
        signals = session.execute(text(
            "SELECT id, signal_type, detector_class, severity, confidence, rationale,"
            " state, occurrence_count, first_detected_at FROM signal"
            " WHERE account_id = :aid AND state = 'active'"
            " ORDER BY severity DESC, first_detected_at"
        ), {"aid": str(account_id)}).mappings().all()
        audit.record(
            session, tenant_id=principal.tenant_id, actor_type="user",
            actor_id=principal.user_id, action="account.view",
            object_type="account", object_id=str(account_id),
        )
        return {"account": dict(account), "active_signals": [dict(s) for s in signals]}


@app.get("/v1/accounts/{account_id}/risk")
def get_risk(account_id: UUID, principal: Principal = Depends(require("accounts:read"))):
    """Latest renewal-risk score with full component explanation and citations."""
    with tenant_session(principal.tenant_id) as session:
        score = session.execute(text(
            "SELECT id, value, reliability, score_version, as_of, inputs_hash FROM score"
            " WHERE account_id = :aid AND score_type = 'renewal_risk'"
            " ORDER BY as_of DESC LIMIT 1"
        ), {"aid": str(account_id)}).mappings().one_or_none()
        if score is None:
            raise HTTPException(status_code=404, detail="no score computed yet")
        components = session.execute(text(
            "SELECT component, weight, norm_value, contribution, rationale, evidence_ids"
            " FROM score_component WHERE score_id = :sid ORDER BY contribution DESC"
        ), {"sid": str(score["id"])}).mappings().all()

        explained = []
        for c in components:
            signal_ids = [str(x) for x in (c["evidence_ids"] or [])]
            citations = []
            if signal_ids:
                citations = session.execute(text(
                    "SELECT ec.claim_text, ec.claim_class, eo.kind, eo.source_system,"
                    " eo.source_record_id, eo.statement, eo.event_at, eo.freshness_at"
                    " FROM evidence_citation ec JOIN evidence_object eo ON eo.id = ec.evidence_id"
                    " WHERE ec.claim_owner_type = 'signal'"
                    " AND ec.claim_owner_id = ANY(CAST(:sids AS uuid[]))"
                ), {"sids": "{" + ",".join(signal_ids) + "}"}).mappings().all()
            explained.append({**dict(c), "evidence_ids": signal_ids,
                              "citations": [dict(x) for x in citations]})

        return {
            "score": {k: v for k, v in dict(score).items() if k != "id"},
            "direction": "higher_is_riskier",
            "components": explained,
        }


@app.get("/v1/admin/sources")
def list_sources(principal: Principal = Depends(require("sources:manage"))):
    with tenant_session(principal.tenant_id) as session:
        rows = session.execute(text(
            "SELECT ds.id, ds.type, ds.name, ds.status, ds.cursors,"
            " (SELECT row_to_json(sr) FROM (SELECT status, mode, stats, error, started_at,"
            "   finished_at FROM sync_run WHERE data_source_id = ds.id"
            "   ORDER BY started_at DESC LIMIT 1) sr) AS last_run"
            " FROM data_source ds ORDER BY ds.created_at"
        )).mappings().all()
        return {"sources": [dict(r) for r in rows]}


@app.get("/v1/admin/identity/candidates")
def list_identity_candidates(principal: Principal = Depends(require("sources:manage"))):
    with tenant_session(principal.tenant_id) as session:
        rows = session.execute(text(
            "SELECT ic.id, ic.source_system, ic.source_record_id, ic.display,"
            " ic.suggested_entity_id, ic.suggested_confidence, ic.match_method, ic.created_at,"
            " a.name AS suggested_account_name"
            " FROM identity_candidate ic LEFT JOIN account a ON a.id = ic.suggested_entity_id"
            " WHERE ic.status = 'pending' ORDER BY ic.created_at"
        )).mappings().all()
        return {"candidates": [dict(r) for r in rows]}


@app.post("/v1/admin/identity/candidates/{candidate_id}/accept")
def accept_identity_candidate(
    candidate_id: UUID,
    target_account_id: UUID | None = None,
    create_account: bool = False,
    principal: Principal = Depends(require("sources:manage")),
):
    from .resolution import accept_candidate

    with tenant_session(principal.tenant_id) as session:
        try:
            account_id = accept_candidate(
                session, principal.tenant_id, candidate_id,
                resolved_by=principal.user_id,
                target_account_id=target_account_id, create_account=create_account,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        audit.record(session, tenant_id=principal.tenant_id, actor_type="user",
                     actor_id=principal.user_id, action="identity.candidate.accept",
                     object_type="identity_candidate", object_id=str(candidate_id),
                     payload={"account_id": str(account_id), "created": create_account})
        return {"status": "accepted", "account_id": str(account_id)}


@app.post("/v1/admin/identity/candidates/{candidate_id}/reject")
def reject_identity_candidate(
    candidate_id: UUID,
    principal: Principal = Depends(require("sources:manage")),
):
    from .resolution import reject_candidate

    with tenant_session(principal.tenant_id) as session:
        try:
            reject_candidate(session, principal.tenant_id, candidate_id,
                             resolved_by=principal.user_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        audit.record(session, tenant_id=principal.tenant_id, actor_type="user",
                     actor_id=principal.user_id, action="identity.candidate.reject",
                     object_type="identity_candidate", object_id=str(candidate_id))
        return {"status": "rejected"}


@app.post("/v1/admin/accounts/{account_id}/evaluate")
def evaluate(
    account_id: UUID,
    as_of: date | None = Query(default=None),
    principal: Principal = Depends(require("admin:evaluate")),
):
    """Run signal detection + scoring for one account (admin/ops surface)."""
    with tenant_session(principal.tenant_id) as session:
        try:
            summary = evaluate_account(session, principal.tenant_id, account_id, today=as_of)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        score = compute_renewal_risk(session, principal.tenant_id, account_id, as_of=as_of)
        insight_id = upsert_risk_insight(
            session, str(principal.tenant_id), str(account_id), score
        )
        audit.record(
            session, tenant_id=principal.tenant_id, actor_type="user",
            actor_id=principal.user_id, action="signals.evaluate",
            object_type="account", object_id=str(account_id),
            payload={"summary": summary, "score_version": score["score_version"] if score else None},
        )
        return {"evaluation": summary,
                "score": score if score else {"status": "insufficient_data"},
                "insight_id": str(insight_id) if insight_id else None}


# ---------------------------------------------------------------------------
# Workbench: ranked insights, lifecycle, feedback
# ---------------------------------------------------------------------------

@app.get("/v1/workbench")
def get_workbench(
    state: str | None = Query(default=None),
    principal: Principal = Depends(require("accounts:read")),
):
    from .insights import workbench

    with tenant_session(principal.tenant_id) as session:
        return {"insights": workbench(session, state=state),
                "ranking": "urgency = severity_rank × (1 + ARR/$100k) × confidence"}


@app.post("/v1/insights/{insight_id}/transition")
def transition(
    insight_id: UUID,
    to_state: str = Query(...),
    reason: str | None = Query(default=None),
    principal: Principal = Depends(require("accounts:write")),
):
    from .insights import transition_insight

    with tenant_session(principal.tenant_id) as session:
        try:
            result = transition_insight(
                session, str(principal.tenant_id), insight_id, to_state,
                actor_id=principal.user_id, reason=reason,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        audit.record(session, tenant_id=principal.tenant_id, actor_type="user",
                     actor_id=principal.user_id, action="insight.transition",
                     object_type="insight", object_id=str(insight_id),
                     payload={**result, "reason": reason})
        return result


@app.post("/v1/insights/{insight_id}/feedback")
def insight_feedback(
    insight_id: UUID,
    verdict: str = Query(...),
    comment: str | None = Query(default=None),
    principal: Principal = Depends(require("accounts:read")),
):
    valid = {"correct", "incorrect", "useful", "not_useful", "missing_context", "already_known"}
    if verdict not in valid:
        raise HTTPException(status_code=422, detail=f"verdict must be one of {sorted(valid)}")
    with tenant_session(principal.tenant_id) as session:
        exists = session.execute(
            text("SELECT 1 FROM insight WHERE id = :id"), {"id": str(insight_id)}
        ).scalar_one_or_none()
        if not exists:
            raise HTTPException(status_code=404, detail="insight not found")
        session.execute(text(
            "INSERT INTO feedback_event (tenant_id, subject_type, subject_id, verdict,"
            " comment, user_id) VALUES (:tid, 'insight', :sid, :verdict, :comment, :uid)"
        ), {"tid": str(principal.tenant_id), "sid": str(insight_id), "verdict": verdict,
            "comment": comment, "uid": principal.user_id})
        return {"status": "recorded"}


# ---------------------------------------------------------------------------
# Data quality + usage import
# ---------------------------------------------------------------------------

@app.get("/v1/admin/data-quality")
def list_data_quality(principal: Principal = Depends(require("sources:manage"))):
    with tenant_session(principal.tenant_id) as session:
        rows = session.execute(text(
            "SELECT id, issue_class, severity, title, impact, affected_refs, state,"
            " detected_at, resolved_at FROM data_quality_issue"
            " ORDER BY state, severity DESC, detected_at DESC"
        )).mappings().all()
        return {"issues": [dict(r) for r in rows]}


@app.post("/v1/admin/data-quality/run")
def run_data_quality(principal: Principal = Depends(require("sources:manage"))):
    from .data_quality import run_checks

    with tenant_session(principal.tenant_id) as session:
        summary = run_checks(session, str(principal.tenant_id))
        audit.record(session, tenant_id=principal.tenant_id, actor_type="user",
                     actor_id=principal.user_id, action="data_quality.run",
                     payload=summary)
        return summary


@app.post("/v1/admin/usage/import")
async def usage_import(
    request: Request,
    principal: Principal = Depends(require("sources:manage")),
):
    from .usage_import import import_usage_csv

    content = (await request.body()).decode("utf-8", errors="replace")
    if not content.strip():
        raise HTTPException(status_code=422, detail="empty body; POST CSV content")
    with tenant_session(principal.tenant_id) as session:
        report = import_usage_csv(session, str(principal.tenant_id), content)
        audit.record(session, tenant_id=principal.tenant_id, actor_type="user",
                     actor_id=principal.user_id, action="usage.csv_import",
                     payload={"status": report["status"], "imported": report["imported"],
                              "error_count": report.get("error_count", 0)})
        return report

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

# Dev CORS for the Vite frontend; production serves same-origin behind the LB.
import os as _os

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=_os.environ.get("RIG_CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Dev login (ONLY when RIG_DEV_LOGIN=1; production uses OIDC/WorkOS)
# ---------------------------------------------------------------------------

def _dev_login_enabled():
    if _os.environ.get("RIG_DEV_LOGIN") != "1":
        raise HTTPException(status_code=404, detail="not found")


@app.get("/v1/dev/tenants")
def dev_tenants():
    _dev_login_enabled()
    from .migrate import admin_engine

    with admin_engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name FROM tenant ORDER BY created_at")).all()
    return {"tenants": [{"id": str(r[0]), "name": r[1]} for r in rows]}


@app.post("/v1/dev/token")
def dev_token(tenant_id: UUID, role: str = Query(...), user: str = Query(default="dev-user")):
    _dev_login_enabled()
    from .auth import CAPABILITIES, issue_dev_token

    if role not in CAPABILITIES:
        raise HTTPException(status_code=422, detail=f"role must be one of {sorted(CAPABILITIES)}")
    return {"token": issue_dev_token(user, tenant_id, role), "role": role,
            "tenant_id": str(tenant_id)}


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


@app.get("/v1/accounts/{account_id}/timeline")
def get_timeline(account_id: UUID, principal: Principal = Depends(require("accounts:read"))):
    """Unified account timeline: signals, billing, support, score snapshots."""
    with tenant_session(principal.tenant_id) as session:
        exists = session.execute(
            text("SELECT 1 FROM account WHERE id = :aid AND deleted_at IS NULL"),
            {"aid": str(account_id)}).scalar_one_or_none()
        if not exists:
            raise HTTPException(status_code=404, detail="account not found")
        events = session.execute(text(
            "SELECT * FROM ("
            "  SELECT 'signal' AS kind, first_detected_at AS at, rationale AS title,"
            "    severity AS detail, detector_class AS source, state AS status"
            "  FROM signal WHERE account_id = :aid"
            "  UNION ALL"
            "  SELECT 'invoice', due_at::timestamptz, 'Invoice ' || source_record_id ||"
            "    ' due ($' || (amount_cents/100)::text || ')', status, source_system, status"
            "  FROM invoice WHERE account_id = :aid"
            "  UNION ALL"
            "  SELECT 'ticket', opened_at, subject, priority, source_system, status"
            "  FROM support_ticket WHERE account_id = :aid"
            "  UNION ALL"
            "  SELECT 'score', as_of, 'Renewal risk ' || round(value)::text || '/100',"
            "    score_version, 'rig', 'computed'"
            "  FROM score WHERE account_id = :aid AND score_type = 'renewal_risk'"
            ") t ORDER BY at DESC LIMIT 200"
        ), {"aid": str(account_id)}).mappings().all()
        return {"events": [dict(e) for e in events]}


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
        if insight_id is not None:
            from . import notifications

            notifications.notify_insight(
                session, str(principal.tenant_id), str(insight_id),
                notifications.default_slack_client,
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
# LLM signal review, write-backs, generation triggers
# ---------------------------------------------------------------------------

@app.post("/v1/signals/{signal_id}/review")
def review_signal(
    signal_id: UUID,
    outcome: str = Query(...),
    principal: Principal = Depends(require("signals:review")),
):
    if outcome not in ("confirmed", "rejected"):
        raise HTTPException(status_code=422, detail="outcome must be confirmed|rejected")
    with tenant_session(principal.tenant_id) as session:
        updated = session.execute(text(
            "UPDATE signal SET review_outcome = :outcome, reviewed_by = :by,"
            " reviewed_at = now() WHERE id = :id AND requires_review = true"
        ), {"outcome": outcome, "by": principal.user_id, "id": str(signal_id)}).rowcount
        if not updated:
            raise HTTPException(status_code=404, detail="signal not found or not reviewable")
        audit.record(session, tenant_id=principal.tenant_id, actor_type="user",
                     actor_id=principal.user_id, action="signal.review",
                     object_type="signal", object_id=str(signal_id),
                     payload={"outcome": outcome})
        return {"status": outcome}


@app.get("/v1/writebacks")
def list_writebacks(principal: Principal = Depends(require("writeback:approve"))):
    with tenant_session(principal.tenant_id) as session:
        rows = session.execute(text(
            "SELECT id, connector_type, operation, preview, state, proposed_by, approved_by,"
            " error, created_at, executed_at FROM writeback_request"
            " ORDER BY created_at DESC LIMIT 200"
        )).mappings().all()
        return {"writebacks": [dict(r) for r in rows]}


@app.post("/v1/insights/{insight_id}/propose-task")
def propose_insight_task(
    insight_id: UUID,
    title: str = Query(...),
    due_date: str | None = Query(default=None),
    principal: Principal = Depends(require("accounts:write")),
):
    from . import writeback

    with tenant_session(principal.tenant_id) as session:
        try:
            request_id = writeback.propose_task(
                session, str(principal.tenant_id), insight_id=str(insight_id),
                title=title, due_date=due_date, proposed_by=principal.user_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"writeback_request_id": request_id, "state": "proposed",
                "note": "requires approval before anything is written to the CRM"}


@app.post("/v1/writebacks/{request_id}/approve")
def approve_writeback(
    request_id: UUID,
    principal: Principal = Depends(require("writeback:approve")),
):
    from . import writeback

    with tenant_session(principal.tenant_id) as session:
        try:
            writeback.approve(session, str(principal.tenant_id), request_id,
                              approved_by=principal.user_id)
            if writeback.default_write_client is not None:
                result = writeback.execute(session, str(principal.tenant_id), request_id,
                                           writeback.default_write_client,
                                           actor_id=principal.user_id)
                return {"state": "executed", "external_result": result}
        except writeback.WritebackError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"state": "approved",
                "note": "no write client configured; will execute when connector is live"}


@app.post("/v1/writebacks/{request_id}/reject")
def reject_writeback(
    request_id: UUID,
    reason: str | None = Query(default=None),
    principal: Principal = Depends(require("writeback:approve")),
):
    from . import writeback

    with tenant_session(principal.tenant_id) as session:
        try:
            writeback.reject(session, str(principal.tenant_id), request_id,
                             rejected_by=principal.user_id, reason=reason)
        except writeback.WritebackError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"state": "rejected"}


@app.post("/v1/admin/tickets/{ticket_id}/analyze-sentiment")
def analyze_sentiment(
    ticket_id: UUID,
    principal: Principal = Depends(require("admin:evaluate")),
):
    from .llm import gateway as llm_gateway
    from .llm.sentiment import analyze_ticket_sentiment

    if llm_gateway.default_gateway is None:
        raise HTTPException(status_code=503, detail="LLM gateway not configured;"
                            " generative features disabled")
    with tenant_session(principal.tenant_id) as session:
        try:
            return analyze_ticket_sentiment(session, str(principal.tenant_id),
                                            llm_gateway.default_gateway, str(ticket_id))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except llm_gateway.LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/insights/{insight_id}/generate-narrative")
def generate_narrative(
    insight_id: UUID,
    principal: Principal = Depends(require("accounts:write")),
):
    from .llm import gateway as llm_gateway
    from .llm.narrative import generate_insight_narrative

    if llm_gateway.default_gateway is None:
        raise HTTPException(status_code=503, detail="LLM gateway not configured")
    with tenant_session(principal.tenant_id) as session:
        try:
            return generate_insight_narrative(session, str(principal.tenant_id),
                                              llm_gateway.default_gateway, str(insight_id))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except llm_gateway.LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Executive briefs
# ---------------------------------------------------------------------------

@app.post("/v1/briefs/generate")
def create_brief(
    as_of: date | None = Query(default=None),
    principal: Principal = Depends(require("admin:evaluate")),
):
    from .briefing import generate_brief

    with tenant_session(principal.tenant_id) as session:
        brief_id = generate_brief(session, str(principal.tenant_id),
                                  created_by=principal.user_id, as_of=as_of)
        return {"brief_id": brief_id, "state": "draft"}


@app.get("/v1/briefs/{brief_id}")
def get_brief(brief_id: UUID, principal: Principal = Depends(require("accounts:read"))):
    with tenant_session(principal.tenant_id) as session:
        brief = session.execute(text(
            "SELECT * FROM exec_brief WHERE id = :id"
        ), {"id": str(brief_id)}).mappings().one_or_none()
        if brief is None:
            raise HTTPException(status_code=404, detail="brief not found")
        return {"brief": dict(brief)}


@app.post("/v1/briefs/{brief_id}/approve")
def approve_exec_brief(
    brief_id: UUID,
    principal: Principal = Depends(require("admin:evaluate")),
):
    from .briefing import BriefError, approve_brief

    with tenant_session(principal.tenant_id) as session:
        try:
            return approve_brief(session, str(principal.tenant_id), str(brief_id),
                                 approved_by=principal.user_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except BriefError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/briefs/{brief_id}/distribute")
def distribute_exec_brief(
    brief_id: UUID,
    targets: list[dict],
    principal: Principal = Depends(require("admin:evaluate")),
):
    from .briefing import BriefError, distribute_brief

    with tenant_session(principal.tenant_id) as session:
        try:
            return distribute_brief(session, str(principal.tenant_id), str(brief_id),
                                    actor_id=principal.user_id, targets=targets)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except BriefError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


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

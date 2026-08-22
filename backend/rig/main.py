"""FastAPI application — Sprint 1 API surface.

Endpoints are tenant-scoped through the caller's JWT: the DB session for a
request sets `app.tenant_id` from the verified principal, so RLS enforces
isolation below the application layer.
"""

from datetime import date
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import text

from . import audit
from .auth import Principal, require
from .db import tenant_session
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
        audit.record(
            session, tenant_id=principal.tenant_id, actor_type="user",
            actor_id=principal.user_id, action="signals.evaluate",
            object_type="account", object_id=str(account_id),
            payload={"summary": summary, "score_version": score["score_version"] if score else None},
        )
        return {"evaluation": summary,
                "score": score if score else {"status": "insufficient_data"}}

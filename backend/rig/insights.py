"""Insight composition and lifecycle (Workbench backend — docs/06 D).

An insight bundles an account's active signals into one owned, ranked,
workflowed item. Sprint 3 composes narratives deterministically from signal
rationales (LLM contextualization arrives in Sprint 4 behind the same shape).

Lifecycle state machine — transitions are validated, recorded, and audited;
dismissal requires a reason code (feeds FP accounting).
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

TRANSITIONS: dict[str, set[str]] = {
    "detected": {"triaged"},
    "triaged": {"accepted", "dismissed"},
    "accepted": {"in_progress", "dismissed"},
    "in_progress": {"mitigated", "not_mitigated"},
    "mitigated": {"outcome_known"},
    "not_mitigated": {"outcome_known"},
    "dismissed": {"outcome_known"},
}
DISMISS_REASONS = {"incorrect", "already_known", "not_actionable", "duplicate", "data_error"}
RISK_INSIGHT_THRESHOLD = 60.0


def upsert_risk_insight(session: Session, tenant_id: str, account_id: str,
                        score: dict | None) -> UUID | None:
    """Create/update the account's open risk insight from active signals.

    Called after evaluation+scoring. Below threshold (or no score) any open
    detected/triaged insight resolves; human-owned states are never
    auto-closed by the machine.
    """
    open_insight = session.execute(text(
        "SELECT id, state FROM insight WHERE account_id = :aid AND kind = 'risk'"
        " AND state NOT IN ('dismissed','outcome_known')"
    ), {"aid": account_id}).mappings().one_or_none()

    if score is None or score["value"] < RISK_INSIGHT_THRESHOLD:
        if open_insight and open_insight["state"] in ("detected", "triaged"):
            _record_transition(session, tenant_id, open_insight["id"],
                               open_insight["state"], "outcome_known",
                               reason="risk_cleared", actor_id="system")
            session.execute(text(
                "UPDATE insight SET state = 'outcome_known', outcome = 'risk_cleared',"
                " outcome_at = now(), updated_at = now() WHERE id = :id"
            ), {"id": str(open_insight["id"])})
        return None

    signals = session.execute(text(
        "SELECT id, signal_type, severity, confidence, rationale FROM signal"
        " WHERE account_id = :aid AND state = 'active'"
        " ORDER BY confidence * (CASE severity WHEN 'critical' THEN 5 WHEN 'high' THEN 4"
        " WHEN 'medium' THEN 3 WHEN 'low' THEN 2 ELSE 1 END) DESC"
    ), {"aid": account_id}).mappings().all()
    if not signals:
        return None

    account = session.execute(text(
        "SELECT name, arr_cents, renewal_date FROM account WHERE id = :aid"
    ), {"aid": account_id}).mappings().one()

    top_severity = max((s["severity"] for s in signals), key=lambda x: SEVERITY_ORDER[x])
    confidence = round(min(0.99, float(score["reliability"]) *
                           max(float(s["confidence"]) for s in signals)), 2)
    title = f"Renewal at risk: {signals[0]['rationale'][:80]}"
    narrative = (
        f"{account['name']} scores {score['value']:.0f}/100 renewal risk"
        f" ({len(signals)} active signals). "
        + " • ".join(s["rationale"] for s in signals[:5])
    )
    signal_ids = "{" + ",".join(str(s["id"]) for s in signals) + "}"

    if open_insight:
        session.execute(text(
            "UPDATE insight SET title = :title, narrative = :narr, severity = :sev,"
            " confidence = :conf, arr_at_stake_cents = :arr,"
            " signal_ids = CAST(:sids AS uuid[]), score_id = :score_id, updated_at = now()"
            " WHERE id = :id"
        ), {"title": title, "narr": narrative, "sev": top_severity, "conf": confidence,
            "arr": account["arr_cents"], "sids": signal_ids,
            "score_id": score["score_id"], "id": str(open_insight["id"])})
        return open_insight["id"]

    return session.execute(text(
        "INSERT INTO insight (tenant_id, account_id, kind, title, narrative, severity,"
        " confidence, arr_at_stake_cents, signal_ids, score_id)"
        " VALUES (:tid, :aid, 'risk', :title, :narr, :sev, :conf, :arr,"
        " CAST(:sids AS uuid[]), :score_id) RETURNING id"
    ), {"tid": tenant_id, "aid": account_id, "title": title, "narr": narrative,
        "sev": top_severity, "conf": confidence, "arr": account["arr_cents"],
        "sids": signal_ids, "score_id": score["score_id"]}).scalar_one()


def transition_insight(session: Session, tenant_id: str, insight_id: UUID | str,
                       to_state: str, *, actor_id: str, reason: str | None = None,
                       owner_id: str | None = None) -> dict:
    insight = session.execute(text(
        "SELECT id, state FROM insight WHERE id = :id"
    ), {"id": str(insight_id)}).mappings().one_or_none()
    if insight is None:
        raise LookupError("insight not found")
    from_state = insight["state"]
    if to_state not in TRANSITIONS.get(from_state, set()):
        raise ValueError(f"invalid transition {from_state} -> {to_state}")
    if to_state == "dismissed":
        if reason not in DISMISS_REASONS:
            raise ValueError(f"dismissal requires a reason code: {sorted(DISMISS_REASONS)}")

    session.execute(text(
        "UPDATE insight SET state = :state, state_reason = :reason,"
        " owner_id = COALESCE(CAST(:owner AS uuid), owner_id), updated_at = now()"
        " WHERE id = :id"
    ), {"state": to_state, "reason": reason, "owner": owner_id, "id": str(insight_id)})
    _record_transition(session, tenant_id, insight_id, from_state, to_state,
                       reason=reason, actor_id=actor_id)
    return {"from": from_state, "to": to_state}


def _record_transition(session: Session, tenant_id: str, insight_id, from_state: str,
                       to_state: str, *, reason: str | None, actor_id: str) -> None:
    session.execute(text(
        "INSERT INTO insight_transition (tenant_id, insight_id, from_state, to_state,"
        " reason, actor_id) VALUES (:tid, :iid, :f, :t, :r, :a)"
    ), {"tid": tenant_id, "iid": str(insight_id), "f": from_state, "t": to_state,
        "r": reason, "a": actor_id})


def workbench(session: Session, *, state: str | None = None) -> list[dict]:
    """Ranked portfolio: urgency = severity_rank × ARR band × confidence.

    Deterministic and explainable (docs/06 D) — the formula is exposed to the
    UI as a tooltip, not hidden.
    """
    rows = session.execute(text(
        "SELECT i.id, i.account_id, a.name AS account_name, i.kind, i.title, i.severity,"
        " i.confidence, i.arr_at_stake_cents, i.state, i.state_reason, i.owner_id,"
        " a.renewal_date, i.created_at, i.updated_at,"
        " (CASE i.severity WHEN 'critical' THEN 5 WHEN 'high' THEN 4 WHEN 'medium' THEN 3"
        "   WHEN 'low' THEN 2 ELSE 1 END)"
        "  * (1 + COALESCE(i.arr_at_stake_cents, 0) / 10000000.0)"
        "  * i.confidence AS urgency"
        " FROM insight i JOIN account a ON a.id = i.account_id"
        " WHERE (CAST(:state AS text) IS NULL"
        "        AND i.state NOT IN ('dismissed','outcome_known'))"
        "    OR i.state = CAST(:state AS text)"
        " ORDER BY urgency DESC, i.created_at"
    ), {"state": state}).mappings().all()
    return [dict(r) for r in rows]

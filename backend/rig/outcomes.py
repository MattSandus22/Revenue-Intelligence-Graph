"""Outcome capture and learning (docs/15 WF-15, docs/06 E).

Recording a renewal outcome:
- closes the account's open risk insight (outcome_known) with the outcome
- computes the label triple (flagged?, detection lead days, intervention
  level from task completion) — intervention-stratified per docs/09 C so
  successful saves don't teach the model that risk signals are safe
- requires a root cause from the churn taxonomy for churned/downgraded
- feeds the outcomes report: surprise-churn (FN) rate, detection lead time,
  root-cause distribution, and calibration-label progress toward the
  50-outcome gate (docs/09 E cold-start honesty)
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from .insights import _record_transition

OUTCOMES = {"renewed", "churned", "downgraded"}
CHURN_REASONS = {"product_gap", "price", "champion_loss", "unresolved_support",
                 "competitor", "budget", "m_and_a", "other"}
SURPRISE_CHURN_MIN_LEAD_DAYS = 30   # docs/01 §1.5
CALIBRATION_LABELS_REQUIRED = 50    # docs/09 E progressive-calibration gate


def record_outcome(session: Session, tenant_id: str, account_id: str, *,
                   outcome: str, outcome_date: date, recorded_by: str,
                   arr_after_cents: int | None = None,
                   root_cause_primary: str | None = None,
                   root_causes_secondary: list[str] | None = None,
                   notes: str | None = None,
                   next_renewal_date: date | None = None,
                   source: str = "manual") -> dict:
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {sorted(OUTCOMES)}")
    if outcome in ("churned", "downgraded"):
        if root_cause_primary not in CHURN_REASONS:
            raise ValueError(f"{outcome} requires root_cause_primary from the churn"
                             f" taxonomy: {sorted(CHURN_REASONS)}")
        invalid = set(root_causes_secondary or []) - CHURN_REASONS
        if invalid:
            raise ValueError(f"unknown secondary root causes: {sorted(invalid)}")

    account = session.execute(text(
        "SELECT id, name, arr_cents FROM account WHERE id = :aid AND deleted_at IS NULL"
    ), {"aid": str(account_id)}).mappings().one_or_none()
    if account is None:
        raise LookupError("account not found")

    # Was this outcome ever flagged? (high+ risk insight created before the
    # outcome date — the FN test for churn, the TP test for saves)
    flagged = session.execute(text(
        "SELECT id, created_at, state FROM insight WHERE account_id = :aid"
        " AND kind = 'risk' AND severity IN ('high', 'critical')"
        " AND created_at::date <= :od ORDER BY created_at LIMIT 1"
    ), {"aid": str(account_id), "od": outcome_date}).mappings().one_or_none()
    detection_lead_days = (
        (outcome_date - flagged["created_at"].date()).days if flagged else None)

    # Intervention level from the mitigation tasks on the open insight chain.
    task_counts = session.execute(text(
        "SELECT count(*) FILTER (WHERE status = 'done') AS done, count(*) AS total"
        " FROM task t JOIN insight i ON i.id = t.insight_id"
        " WHERE i.account_id = :aid AND i.kind = 'risk' AND t.status != 'cancelled'"
    ), {"aid": str(account_id)}).one()
    if task_counts.total == 0:
        intervention = "none"
    elif task_counts.done == task_counts.total:
        intervention = "completed"
    else:
        intervention = "partial"

    # Close the open risk insight, if any.
    open_insight = session.execute(text(
        "SELECT id, state FROM insight WHERE account_id = :aid AND kind = 'risk'"
        " AND state NOT IN ('dismissed', 'outcome_known')"
    ), {"aid": str(account_id)}).mappings().one_or_none()
    if open_insight is not None:
        _record_transition(session, tenant_id, open_insight["id"], open_insight["state"],
                           "outcome_known", reason=outcome, actor_id=recorded_by)
        session.execute(text(
            "UPDATE insight SET state = 'outcome_known', outcome = :outcome,"
            " outcome_at = now(), updated_at = now() WHERE id = :id"
        ), {"outcome": outcome, "id": str(open_insight["id"])})

    outcome_id = session.execute(text(
        "INSERT INTO renewal_outcome (tenant_id, account_id, outcome, outcome_date,"
        " arr_before_cents, arr_after_cents, source, root_cause_primary,"
        " root_causes_secondary, notes, was_flagged, detection_lead_days, intervention,"
        " insight_id, recorded_by)"
        " VALUES (:tid, :aid, :outcome, :od, :before, :after, :source, :rc,"
        " :rcs, :notes, :flagged, :lead, :intervention, :iid, :by) RETURNING id"
    ), {"tid": tenant_id, "aid": str(account_id), "outcome": outcome, "od": outcome_date,
        "before": account["arr_cents"], "after": arr_after_cents, "source": source,
        "rc": root_cause_primary, "rcs": root_causes_secondary or [],
        "notes": notes, "flagged": flagged is not None, "lead": detection_lead_days,
        "intervention": intervention,
        "iid": str(open_insight["id"]) if open_insight else None,
        "by": recorded_by}).scalar_one()

    # Account state effects.
    if outcome == "churned":
        session.execute(text(
            "UPDATE account SET lifecycle_stage = 'churned', updated_at = now()"
            " WHERE id = :id"), {"id": str(account_id)})
    elif next_renewal_date is not None:
        session.execute(text(
            "UPDATE account SET renewal_date = :next,"
            " arr_cents = COALESCE(:after, arr_cents), updated_at = now() WHERE id = :id"
        ), {"next": next_renewal_date, "after": arr_after_cents, "id": str(account_id)})

    return {
        "outcome_id": str(outcome_id), "outcome": outcome,
        "was_flagged": flagged is not None,
        "detection_lead_days": detection_lead_days,
        "intervention": intervention,
        "surprise_churn": outcome == "churned" and (
            flagged is None
            or (detection_lead_days or 0) < SURPRISE_CHURN_MIN_LEAD_DAYS),
        "insight_closed": str(open_insight["id"]) if open_insight else None,
    }


def get_postmortem(session: Session, account_id: str) -> dict | None:
    """Full replay for the account's latest outcome (docs/06 D postmortems)."""
    outcome = session.execute(text(
        "SELECT ro.*, a.name AS account_name FROM renewal_outcome ro"
        " JOIN account a ON a.id = ro.account_id"
        " WHERE ro.account_id = :aid ORDER BY ro.outcome_date DESC LIMIT 1"
    ), {"aid": str(account_id)}).mappings().one_or_none()
    if outcome is None:
        return None

    signals = session.execute(text(
        "SELECT signal_type, detector_class, severity, state, rationale,"
        " first_detected_at FROM signal WHERE account_id = :aid"
        " ORDER BY first_detected_at"
    ), {"aid": str(account_id)}).mappings().all()
    transitions = []
    if outcome["insight_id"]:
        transitions = session.execute(text(
            "SELECT from_state, to_state, reason, actor_id, occurred_at"
            " FROM insight_transition WHERE insight_id = :iid ORDER BY occurred_at"
        ), {"iid": str(outcome["insight_id"])}).mappings().all()
    tasks = session.execute(text(
        "SELECT title, playbook_key, status, due_date, completed_at FROM task"
        " WHERE account_id = :aid ORDER BY created_at"
    ), {"aid": str(account_id)}).mappings().all()

    return {
        "outcome": {k: v for k, v in dict(outcome).items()},
        "signals": [dict(s) for s in signals],
        "lifecycle": [dict(t) for t in transitions],
        "mitigation_tasks": [dict(t) for t in tasks],
        "attribution_note": "correlational — selection effects possible (docs/01 §1.7)",
    }


def outcomes_report(session: Session) -> dict:
    rows = session.execute(text(
        "SELECT outcome, was_flagged, detection_lead_days, intervention,"
        " root_cause_primary, arr_before_cents FROM renewal_outcome"
    )).mappings().all()

    churned = [r for r in rows if r["outcome"] == "churned"]
    surprise = [r for r in churned if not r["was_flagged"]
                or (r["detection_lead_days"] or 0) < SURPRISE_CHURN_MIN_LEAD_DAYS]
    lead_days = sorted(r["detection_lead_days"] for r in rows
                       if r["detection_lead_days"] is not None)
    root_causes: dict[str, int] = {}
    for row in churned:
        if row["root_cause_primary"]:
            root_causes[row["root_cause_primary"]] = \
                root_causes.get(row["root_cause_primary"], 0) + 1

    labels = len(rows)
    return {
        "outcomes": {o: sum(1 for r in rows if r["outcome"] == o) for o in sorted(OUTCOMES)},
        "churned_arr_cents": sum(r["arr_before_cents"] or 0 for r in churned),
        "surprise_churn": {
            "count": len(surprise), "of_churned": len(churned),
            "rate": round(len(surprise) / len(churned), 3) if churned else None,
            "definition": f"churned without a high+ risk flag >= "
                          f"{SURPRISE_CHURN_MIN_LEAD_DAYS} days before the outcome",
        },
        "detection_lead_days": {
            "median": lead_days[len(lead_days) // 2] if lead_days else None,
            "min": lead_days[0] if lead_days else None,
            "max": lead_days[-1] if lead_days else None,
        },
        "root_causes": dict(sorted(root_causes.items(), key=lambda kv: -kv[1])),
        "interventions": {level: sum(1 for r in rows if r["intervention"] == level)
                          for level in ("none", "partial", "completed")},
        "calibration": {
            "labels": labels,
            "required": CALIBRATION_LABELS_REQUIRED,
            "predictive_mode_active": labels >= CALIBRATION_LABELS_REQUIRED,
            "status": (f"predictive mode not yet active — {labels}/"
                       f"{CALIBRATION_LABELS_REQUIRED} outcomes observed"
                       if labels < CALIBRATION_LABELS_REQUIRED
                       else "calibration gate reached — isotonic calibration eligible"),
        },
    }

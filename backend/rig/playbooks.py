"""Playbooks and tasks (docs/06 module D, WF-4).

Applying a playbook to an accepted risk creates owned, dated tasks and moves
the insight to in_progress — the "% of accepted risks with an active
mitigation" metric is computed from exactly this linkage.
"""

import json
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from .insights import transition_insight

# The three canned MVP playbooks (docs/16); tenants customize via the
# playbook table — these seed only when the key is absent.
DEFAULT_PLAYBOOKS: list[dict] = [
    {
        "key": "renewal_save",
        "name": "Renewal save play",
        "description": "Structured save motion for a high-risk renewal (docs/20 §20.12).",
        "steps": [
            {"title": "Resolve the trust-breaking support issue; daily updates until closed",
             "role": "csm", "sla_days": 2},
            {"title": "Executive re-alignment: book economic-buyer meeting with value recap",
             "role": "leader", "sla_days": 7},
            {"title": "Champion re-engagement working session; reactivate power users",
             "role": "csm", "sla_days": 7},
            {"title": "Commercial options prepared before the notice deadline",
             "role": "leader", "sla_days": 14},
            {"title": "Mutual action plan drafted and reviewed with the champion",
             "role": "csm", "sla_days": 10},
        ],
    },
    {
        "key": "usage_recovery",
        "name": "Usage recovery play",
        "description": "Re-engagement motion for a sustained usage decline.",
        "steps": [
            {"title": "Usage review call: identify which workflows stopped and why",
             "role": "csm", "sla_days": 5},
            {"title": "Targeted enablement session for inactive power users",
             "role": "csm", "sla_days": 10},
            {"title": "30-day usage checkpoint documented on the account",
             "role": "csm", "sla_days": 30},
        ],
    },
    {
        "key": "billing_resolution",
        "name": "Billing resolution play",
        "description": "Decouple payment friction from the renewal conversation.",
        "steps": [
            {"title": "Finance sync: confirm invoice status and dispute state",
             "role": "csm", "sla_days": 3},
            {"title": "Customer AP follow-up with corrected/confirmed invoice",
             "role": "csm", "sla_days": 7},
        ],
    },
]


def ensure_default_playbooks(session: Session, tenant_id: str) -> int:
    created = 0
    for playbook in DEFAULT_PLAYBOOKS:
        result = session.execute(text(
            "INSERT INTO playbook (tenant_id, key, name, description, steps)"
            " VALUES (:tid, :key, :name, :descr, CAST(:steps AS jsonb))"
            " ON CONFLICT (tenant_id, key) DO NOTHING"
        ), {"tid": tenant_id, "key": playbook["key"], "name": playbook["name"],
            "descr": playbook["description"], "steps": json.dumps(playbook["steps"])})
        created += result.rowcount
    return created


def apply_playbook(session: Session, tenant_id: str, insight_id: str, playbook_key: str,
                   *, actor_id: str, today: date | None = None) -> dict:
    today = today or date.today()
    insight = session.execute(text(
        "SELECT id, account_id, state FROM insight WHERE id = :id"
    ), {"id": str(insight_id)}).mappings().one_or_none()
    if insight is None:
        raise LookupError("insight not found")
    if insight["state"] not in ("accepted", "in_progress"):
        raise ValueError(f"playbooks apply to accepted risks; insight is '{insight['state']}'"
                         " — triage and accept it first")
    playbook = session.execute(text(
        "SELECT key, name, steps FROM playbook WHERE key = :key AND enabled"
    ), {"key": playbook_key}).mappings().one_or_none()
    if playbook is None:
        raise LookupError(f"no enabled playbook '{playbook_key}'")

    already = session.execute(text(
        "SELECT count(*) FROM task WHERE insight_id = :iid AND playbook_key = :key"
        " AND status != 'cancelled'"
    ), {"iid": str(insight_id), "key": playbook_key}).scalar_one()
    if already:
        raise ValueError(f"playbook '{playbook_key}' already applied to this insight"
                         f" ({already} tasks)")

    task_ids = []
    for index, step in enumerate(playbook["steps"]):
        task_ids.append(str(session.execute(text(
            "INSERT INTO task (tenant_id, account_id, insight_id, playbook_key, step_index,"
            " title, assignee_role, due_date, created_by)"
            " VALUES (:tid, :aid, :iid, :key, :idx, :title, :role, :due, :by) RETURNING id"
        ), {"tid": tenant_id, "aid": str(insight["account_id"]), "iid": str(insight_id),
            "key": playbook["key"], "idx": index, "title": step["title"],
            "role": step.get("role"), "due": today + timedelta(days=step.get("sla_days", 7)),
            "by": actor_id}).scalar_one()))

    transitioned = None
    if insight["state"] == "accepted":
        transitioned = transition_insight(session, tenant_id, insight_id, "in_progress",
                                          actor_id=actor_id,
                                          reason=f"playbook:{playbook_key}")
    return {"playbook": playbook["key"], "tasks_created": len(task_ids),
            "task_ids": task_ids, "transitioned": transitioned}


def complete_task(session: Session, tenant_id: str, task_id: str, *, actor_id: str) -> dict:
    updated = session.execute(text(
        "UPDATE task SET status = 'done', completed_by = :by, completed_at = now()"
        " WHERE id = :id AND status = 'open' RETURNING insight_id"
    ), {"by": actor_id, "id": str(task_id)}).one_or_none()
    if updated is None:
        raise LookupError("task not found or not open")
    insight_id = updated[0]
    remaining = None
    if insight_id:
        remaining = session.execute(text(
            "SELECT count(*) FROM task WHERE insight_id = :iid AND status = 'open'"
        ), {"iid": str(insight_id)}).scalar_one()
    return {"status": "done", "insight_id": str(insight_id) if insight_id else None,
            "open_tasks_remaining": remaining}


def precision_metrics(session: Session) -> dict:
    """Insight-quality telemetry (docs/06 D feedback, docs/09 F online metrics)."""
    acceptance = session.execute(text(
        "SELECT to_state, count(*) FROM insight_transition"
        " WHERE to_state IN ('accepted', 'dismissed') GROUP BY to_state"
    )).all()
    counts = {row[0]: row[1] for row in acceptance}
    accepted, dismissed = counts.get("accepted", 0), counts.get("dismissed", 0)

    dismissal_reasons = dict(session.execute(text(
        "SELECT COALESCE(reason, 'unspecified'), count(*) FROM insight_transition"
        " WHERE to_state = 'dismissed' GROUP BY 1 ORDER BY 2 DESC"
    )).all())

    feedback = dict(session.execute(text(
        "SELECT verdict, count(*) FROM feedback_event"
        " WHERE subject_type = 'insight' GROUP BY verdict"
    )).all())

    mitigation = session.execute(text(
        "SELECT count(DISTINCT i.id) FILTER (WHERE t.id IS NOT NULL) AS with_tasks,"
        " count(DISTINCT i.id) AS total"
        " FROM insight i LEFT JOIN task t ON t.insight_id = i.id AND t.status != 'cancelled'"
        " WHERE i.state IN ('accepted', 'in_progress')"
    )).one()

    total_triaged = accepted + dismissed
    return {
        "acceptance_rate": round(accepted / total_triaged, 3) if total_triaged else None,
        "accepted": accepted,
        "dismissed": dismissed,
        "dismissal_reasons": dismissal_reasons,
        "feedback_verdicts": feedback,
        "mitigation_coverage": {
            "accepted_or_in_progress": mitigation[1],
            "with_active_tasks": mitigation[0],
            "rate": round(mitigation[0] / mitigation[1], 3) if mitigation[1] else None,
        },
        "note": "acceptance_rate is the docs/01 'insight precision' proxy until "
                "outcome labels accumulate; FN reporting activates with WF-15",
    }

"""Playbooks and tasks: WF-4 mitigation flow + precision metrics."""

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from rig.db import tenant_session
from rig.insights import transition_insight, upsert_risk_insight
from rig.playbooks import (apply_playbook, complete_task,
                           ensure_default_playbooks, precision_metrics)
from rig.scoring import compute_renewal_risk
from rig.signals.engine import evaluate_account

TODAY = date.today()


def _accepted_insight(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        evaluate_account(s, tid, seeded["acme_account"], today=TODAY)
        score = compute_renewal_risk(s, tid, seeded["acme_account"], as_of=TODAY)
        insight_id = upsert_risk_insight(s, tid, seeded["acme_account"], score)
        state = s.execute(text("SELECT state FROM insight WHERE id = :id"),
                          {"id": str(insight_id)}).scalar_one()
        for to_state in {"detected": ["triaged", "accepted"],
                         "triaged": ["accepted"]}.get(state, []):
            transition_insight(s, tid, insight_id, to_state, actor_id="u_csm")
    return insight_id


def test_defaults_seed_once(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        first = ensure_default_playbooks(s, tid)
        second = ensure_default_playbooks(s, tid)
        keys = s.execute(text("SELECT key FROM playbook ORDER BY key")).scalars().all()
    assert first == 3 and second == 0
    assert keys == ["billing_resolution", "renewal_save", "usage_recovery"]


def test_apply_playbook_creates_dated_tasks_and_transitions(seeded):
    tid = seeded["nsc_tenant"]
    insight_id = _accepted_insight(seeded)
    with tenant_session(tid) as s:
        ensure_default_playbooks(s, tid)
        result = apply_playbook(s, tid, str(insight_id), "renewal_save",
                                actor_id="u_csm", today=TODAY)
        assert result["tasks_created"] == 5
        assert result["transitioned"] == {"from": "accepted", "to": "in_progress"}

        tasks = s.execute(text(
            "SELECT title, due_date, assignee_role, status FROM task"
            " WHERE insight_id = :iid ORDER BY step_index"
        ), {"iid": str(insight_id)}).mappings().all()
        assert tasks[0]["due_date"] == TODAY + timedelta(days=2)   # sla_days=2
        assert tasks[1]["assignee_role"] == "leader"
        assert all(t["status"] == "open" for t in tasks)

        # double-apply is rejected
        with pytest.raises(ValueError, match="already applied"):
            apply_playbook(s, tid, str(insight_id), "renewal_save", actor_id="u_csm")

        # completing a task decrements the open count
        task_id = s.execute(text(
            "SELECT id FROM task WHERE insight_id = :iid AND step_index = 0"
        ), {"iid": str(insight_id)}).scalar_one()
        done = complete_task(s, tid, str(task_id), actor_id="u_csm")
        assert done["open_tasks_remaining"] == 4
        with pytest.raises(LookupError):
            complete_task(s, tid, str(task_id), actor_id="u_csm")  # not open anymore


def test_playbook_requires_accepted_state(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        account_id = s.execute(text(
            "INSERT INTO account (tenant_id, name, arr_cents, renewal_date)"
            " VALUES (:tid, 'PlaybookGate Co', 100000, :r) RETURNING id"
        ), {"tid": tid, "r": TODAY}).scalar_one()
        insight_id = s.execute(text(
            "INSERT INTO insight (tenant_id, account_id, kind, title, narrative,"
            " severity, confidence) VALUES (:tid, :aid, 'risk', 't', 'n', 'high', 0.9)"
            " RETURNING id"
        ), {"tid": tid, "aid": str(account_id)}).scalar_one()
        ensure_default_playbooks(s, tid)
        with pytest.raises(ValueError, match="accept"):
            apply_playbook(s, tid, str(insight_id), "renewal_save", actor_id="u_csm")


def test_precision_metrics_math(seeded):
    tid = seeded["nsc_tenant"]
    _accepted_insight(seeded)  # ensures at least one accepted transition exists
    with tenant_session(tid) as s:
        s.execute(text(
            "INSERT INTO feedback_event (tenant_id, subject_type, subject_id, verdict, user_id)"
            " SELECT :tid, 'insight', id, 'correct', 'u_m' FROM insight LIMIT 1"
        ), {"tid": tid})
        metrics = precision_metrics(s)
    assert metrics["accepted"] >= 1
    total = metrics["accepted"] + metrics["dismissed"]
    assert metrics["acceptance_rate"] == round(metrics["accepted"] / total, 3)
    assert metrics["feedback_verdicts"].get("correct", 0) >= 1
    coverage = metrics["mitigation_coverage"]
    assert coverage["with_active_tasks"] <= coverage["accepted_or_in_progress"]
    if coverage["accepted_or_in_progress"]:
        assert coverage["rate"] == round(
            coverage["with_active_tasks"] / coverage["accepted_or_in_progress"], 3)

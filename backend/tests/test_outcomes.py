"""Outcome capture (WF-15): labels, lifecycle closure, FN accounting,
postmortems, calibration progress."""

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from rig.db import tenant_session
from rig.insights import upsert_risk_insight
from rig.outcomes import get_postmortem, outcomes_report, record_outcome
from rig.playbooks import apply_playbook, ensure_default_playbooks
from rig.scoring import compute_renewal_risk
from rig.signals.engine import evaluate_account

TODAY = date.today()


def _open_acme_insight(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        evaluate_account(s, tid, seeded["acme_account"], today=TODAY)
        score = compute_renewal_risk(s, tid, seeded["acme_account"], as_of=TODAY)
        return upsert_risk_insight(s, tid, seeded["acme_account"], score)


def test_renewed_outcome_closes_insight_with_labels(seeded):
    tid = seeded["nsc_tenant"]
    insight_id = _open_acme_insight(seeded)
    with tenant_session(tid) as s:
        # partial intervention: playbook applied, one task done
        from rig.insights import transition_insight

        state = s.execute(text("SELECT state FROM insight WHERE id = :id"),
                          {"id": str(insight_id)}).scalar_one()
        for to_state in {"detected": ["triaged", "accepted"],
                         "triaged": ["accepted"]}.get(state, []):
            transition_insight(s, tid, insight_id, to_state, actor_id="u_csm")
        ensure_default_playbooks(s, tid)
        apply_playbook(s, tid, str(insight_id), "usage_recovery", actor_id="u_csm")
        task_id = s.execute(text(
            "SELECT id FROM task WHERE insight_id = :iid LIMIT 1"
        ), {"iid": str(insight_id)}).scalar_one()
        from rig.playbooks import complete_task

        complete_task(s, tid, str(task_id), actor_id="u_csm")

        # NOTE: no next_renewal_date here — later test modules rely on the
        # seeded 92-day Acme renewal fixture; roll-forward is asserted on a
        # dedicated account below.
        result = record_outcome(
            s, tid, seeded["acme_account"], outcome="renewed",
            outcome_date=TODAY + timedelta(days=92), recorded_by="u_leader",
        )
        assert result["was_flagged"] is True
        assert result["detection_lead_days"] == 92     # flagged today, outcome in 92d
        assert result["intervention"] == "partial"
        assert result["surprise_churn"] is False
        assert result["insight_closed"] == str(insight_id)

        state, outcome = s.execute(text(
            "SELECT state, outcome FROM insight WHERE id = :id"
        ), {"id": str(insight_id)}).one()
        assert (state, outcome) == ("outcome_known", "renewed")


def test_renewed_rolls_renewal_forward_when_asked(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        account_id = s.execute(text(
            "INSERT INTO account (tenant_id, name, arr_cents, renewal_date)"
            " VALUES (:tid, 'RollForward Co', 2400000, :r) RETURNING id"
        ), {"tid": tid, "r": TODAY}).scalar_one()
        record_outcome(s, tid, str(account_id), outcome="renewed",
                       outcome_date=TODAY, recorded_by="u_leader",
                       arr_after_cents=3000000,
                       next_renewal_date=TODAY + timedelta(days=365))
        renewal_date, arr = s.execute(text(
            "SELECT renewal_date, arr_cents FROM account WHERE id = :id"
        ), {"id": str(account_id)}).one()
    assert renewal_date == TODAY + timedelta(days=365)
    assert arr == 3000000  # expansion on renewal reflected


def test_churn_requires_root_cause_and_flags_surprise(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        # an account that was NEVER flagged — churn is a surprise (FN)
        quiet_id = s.execute(text(
            "INSERT INTO account (tenant_id, name, arr_cents, renewal_date)"
            " VALUES (:tid, 'NeverFlagged Inc', 4000000, :r) RETURNING id"
        ), {"tid": tid, "r": TODAY}).scalar_one()

        with pytest.raises(ValueError, match="root_cause_primary"):
            record_outcome(s, tid, str(quiet_id), outcome="churned",
                           outcome_date=TODAY, recorded_by="u_leader")
        with pytest.raises(ValueError, match="churn taxonomy"):
            record_outcome(s, tid, str(quiet_id), outcome="churned",
                           outcome_date=TODAY, recorded_by="u_leader",
                           root_cause_primary="vibes")

        result = record_outcome(
            s, tid, str(quiet_id), outcome="churned", outcome_date=TODAY,
            recorded_by="u_leader", root_cause_primary="competitor",
            root_causes_secondary=["price"], notes="lost to CompetitorX")
        assert result["was_flagged"] is False
        assert result["surprise_churn"] is True
        assert result["intervention"] == "none"
        stage = s.execute(text("SELECT lifecycle_stage FROM account WHERE id = :id"),
                          {"id": str(quiet_id)}).scalar_one()
        assert stage == "churned"


def test_outcomes_report_math(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        report = outcomes_report(s)
    assert report["outcomes"]["renewed"] >= 1
    assert report["outcomes"]["churned"] >= 1
    surprise = report["surprise_churn"]
    assert surprise["count"] >= 1 and surprise["of_churned"] >= surprise["count"]
    assert surprise["rate"] == round(surprise["count"] / surprise["of_churned"], 3)
    assert report["root_causes"].get("competitor", 0) >= 1
    assert report["detection_lead_days"]["median"] is not None
    calibration = report["calibration"]
    assert calibration["predictive_mode_active"] is False
    assert f"{calibration['labels']}/50" in calibration["status"]


def test_postmortem_replays_full_history(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        postmortem = get_postmortem(s, seeded["acme_account"])
    assert postmortem is not None
    assert postmortem["outcome"]["outcome"] == "renewed"
    assert len(postmortem["signals"]) >= 5
    lifecycle_states = [t["to_state"] for t in postmortem["lifecycle"]]
    assert lifecycle_states[-1] == "outcome_known"
    assert "accepted" in lifecycle_states and "in_progress" in lifecycle_states
    assert any(t["status"] == "done" for t in postmortem["mitigation_tasks"])
    assert "correlational" in postmortem["attribution_note"]


def test_duplicate_outcome_same_date_rejected(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        with pytest.raises(Exception) as excinfo:
            record_outcome(s, tid, seeded["acme_account"], outcome="renewed",
                           outcome_date=TODAY + timedelta(days=92),
                           recorded_by="u_leader")
    assert "unique" in str(excinfo.value).lower() or "duplicate" in str(excinfo.value).lower()

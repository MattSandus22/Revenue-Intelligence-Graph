"""Insight lifecycle, workbench ranking, feedback capture (docs/06 D)."""

from datetime import date

import pytest
from sqlalchemy import text

from rig.db import tenant_session
from rig.insights import transition_insight, upsert_risk_insight, workbench
from rig.scoring import compute_renewal_risk
from rig.signals.engine import evaluate_account

TODAY = date.today()


def _make_insight(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        evaluate_account(s, seeded["nsc_tenant"], seeded["acme_account"], today=TODAY)
        score = compute_renewal_risk(s, seeded["nsc_tenant"], seeded["acme_account"], as_of=TODAY)
        insight_id = upsert_risk_insight(s, seeded["nsc_tenant"], seeded["acme_account"], score)
    return insight_id


def test_risk_insight_created_and_idempotent(seeded):
    first = _make_insight(seeded)
    assert first is not None
    second = _make_insight(seeded)
    assert second == first  # updates the open insight, never duplicates
    with tenant_session(seeded["nsc_tenant"]) as s:
        row = s.execute(text(
            "SELECT severity, confidence, arr_at_stake_cents, state,"
            " cardinality(signal_ids) AS n_signals FROM insight WHERE id = :id"
        ), {"id": str(first)}).mappings().one()
    assert row["severity"] in ("high", "critical")
    assert row["arr_at_stake_cents"] == 12000000
    assert row["state"] == "detected"
    assert row["n_signals"] >= 5


def test_lifecycle_happy_path_and_guards(seeded):
    insight_id = _make_insight(seeded)
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        # invalid jump straight to mitigated
        with pytest.raises(ValueError, match="invalid transition"):
            transition_insight(s, tid, insight_id, "mitigated", actor_id="u_csm")
        transition_insight(s, tid, insight_id, "triaged", actor_id="u_csm")
        # dismissal requires a reason code
        with pytest.raises(ValueError, match="reason code"):
            transition_insight(s, tid, insight_id, "dismissed", actor_id="u_csm")
        transition_insight(s, tid, insight_id, "accepted", actor_id="u_csm")
        transition_insight(s, tid, insight_id, "in_progress", actor_id="u_csm")
        transition_insight(s, tid, insight_id, "mitigated", actor_id="u_csm")
        history = s.execute(text(
            "SELECT from_state, to_state FROM insight_transition WHERE insight_id = :id"
            " ORDER BY occurred_at"
        ), {"id": str(insight_id)}).all()
    assert [tuple(h) for h in history] == [
        ("detected", "triaged"), ("triaged", "accepted"),
        ("accepted", "in_progress"), ("in_progress", "mitigated"),
    ]
    # reset for other tests: close it out
    with tenant_session(tid) as s:
        transition_insight(s, tid, insight_id, "outcome_known", actor_id="u_csm")


def test_workbench_ranks_by_urgency(seeded):
    insight_id = _make_insight(seeded)
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        # a second, smaller risk on another account: low ARR, medium severity
        other = s.execute(text(
            "INSERT INTO account (tenant_id, name, arr_cents, renewal_date)"
            " VALUES (:tid, 'Smallco', 1000000, :renewal) RETURNING id"
        ), {"tid": tid, "renewal": TODAY}).scalar_one()
        s.execute(text(
            "INSERT INTO insight (tenant_id, account_id, kind, title, narrative,"
            " severity, confidence, arr_at_stake_cents)"
            " VALUES (:tid, :aid, 'risk', 'small risk', 'n', 'medium', 0.9, 1000000)"
        ), {"tid": tid, "aid": str(other)})
        ranked = workbench(s)
    ids = [r["id"] for r in ranked]
    assert str(insight_id) in [str(i) for i in ids]
    # Acme ($120k, high/critical) outranks Smallco ($10k, medium)
    assert str(ids[0]) == str(insight_id)
    assert all(ranked[i]["urgency"] >= ranked[i + 1]["urgency"] for i in range(len(ranked) - 1))


def test_risk_cleared_auto_resolves_untriaged_insight(seeded):
    tid = seeded["nsc_tenant"]
    insight_id = _make_insight(seeded)
    with tenant_session(tid) as s:
        state = s.execute(text("SELECT state FROM insight WHERE id = :id"),
                          {"id": str(insight_id)}).scalar_one()
        assert state == "detected"
        # simulate risk gone: no score / below threshold
        upsert_risk_insight(s, tid, seeded["acme_account"], {"value": 10, "reliability": 1.0,
                                                             "score_id": None})
        state = s.execute(text("SELECT state, outcome FROM insight WHERE id = :id"),
                          {"id": str(insight_id)}).one()
    assert tuple(state) == ("outcome_known", "risk_cleared")

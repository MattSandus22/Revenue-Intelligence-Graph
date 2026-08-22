"""Signal engine: Acme fixtures must reproduce the docs/20 walkthrough signals,
idempotently, with evidence citations on every signal."""

from datetime import date, timedelta

from sqlalchemy import text

from rig.db import tenant_session
from rig.signals.engine import evaluate_account

TODAY = date.today()


def _evaluate(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        return evaluate_account(s, seeded["nsc_tenant"], seeded["acme_account"], today=TODAY)


def _active_signals(seeded):
    """Engine-managed active signals (LLM signals have a separate lifecycle)."""
    with tenant_session(seeded["nsc_tenant"]) as s:
        return {r["signal_type"]: dict(r) for r in s.execute(text(
            "SELECT * FROM signal WHERE account_id = :aid AND state = 'active'"
            " AND requires_review = false"
        ), {"aid": seeded["acme_account"]}).mappings().all()}


def test_acme_fires_expected_signals(seeded):
    summary = _evaluate(seeded)
    signals = _active_signals(seeded)
    expected = {
        "renewal_no_plan", "notice_period_approaching", "payment_late",
        "critical_ticket_unresolved", "usage_drop_vs_baseline",
    }
    assert expected <= set(signals), f"missing: {expected - set(signals)}"
    assert summary["active"] >= len(expected)

    assert signals["payment_late"]["severity"] == "medium"       # 14 days -> medium
    assert signals["payment_late"]["magnitude"]["days_past_due"] == 14
    assert signals["critical_ticket_unresolved"]["severity"] == "critical"  # Enterprise tier bump
    drop = signals["usage_drop_vs_baseline"]["magnitude"]["drop_pct"]
    assert 25 <= drop <= 38, f"expected ~31% drop, got {drop}"
    assert signals["usage_drop_vs_baseline"]["severity"] == "high"
    # notice deadline = renewal(92d) - 60d = 32 days out
    assert signals["notice_period_approaching"]["magnitude"]["days_to_deadline"] == 32


def test_every_signal_has_evidence_citation(seeded):
    _evaluate(seeded)
    with tenant_session(seeded["nsc_tenant"]) as s:
        uncited = s.execute(text(
            "SELECT sg.signal_type FROM signal sg"
            " WHERE sg.account_id = :aid AND sg.state = 'active'"
            " AND NOT EXISTS (SELECT 1 FROM evidence_citation ec"
            "   WHERE ec.claim_owner_type = 'signal' AND ec.claim_owner_id = sg.id)"
        ), {"aid": seeded["acme_account"]}).scalars().all()
    assert uncited == [], f"signals without evidence: {uncited}"


def test_reevaluation_is_idempotent(seeded):
    _evaluate(seeded)
    before = _active_signals(seeded)
    summary = _evaluate(seeded)
    after = _active_signals(seeded)
    assert set(before) == set(after)
    assert summary["created"] == 0 and summary["updated"] >= len(after)
    for signal_type in after:
        assert after[signal_type]["occurrence_count"] == before[signal_type]["occurrence_count"] + 1
    # citations not duplicated
    with tenant_session(seeded["nsc_tenant"]) as s:
        dupes = s.execute(text(
            "SELECT claim_owner_id, evidence_id, count(*) FROM evidence_citation"
            " GROUP BY claim_owner_id, evidence_id HAVING count(*) > 1"
        )).all()
    assert dupes == []


def test_healthy_account_fires_nothing(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        summary = evaluate_account(s, seeded["nsc_tenant"], seeded["beta_account"], today=TODAY)
        count = s.execute(text(
            "SELECT count(*) FROM signal WHERE account_id = :aid AND state = 'active'"
        ), {"aid": seeded["beta_account"]}).scalar_one()
    assert summary["active"] == 0 and count == 0


def test_resolved_when_condition_clears(seeded):
    """Paying the invoice resolves payment_late on next evaluation (not deleted)."""
    _evaluate(seeded)
    with tenant_session(seeded["nsc_tenant"]) as s:
        s.execute(text(
            "UPDATE invoice SET paid_at = :d, status = 'paid' WHERE source_record_id = 'INV-2214'"
        ), {"d": TODAY})
        evaluate_account(s, seeded["nsc_tenant"], seeded["acme_account"], today=TODAY)
        state = s.execute(text(
            "SELECT state FROM signal WHERE account_id = :aid AND signal_type = 'payment_late'"
        ), {"aid": seeded["acme_account"]}).scalar_one()
        # restore fixture for other tests
        s.execute(text(
            "UPDATE invoice SET paid_at = NULL, status = 'overdue' WHERE source_record_id = 'INV-2214'"
        ))
        evaluate_account(s, seeded["nsc_tenant"], seeded["acme_account"], today=TODAY)
    assert state == "resolved"

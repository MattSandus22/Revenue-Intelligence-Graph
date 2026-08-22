"""Renewal-risk score: explained, reproducible, coverage-aware."""

from datetime import date

from sqlalchemy import text

from rig.db import tenant_session
from rig.scoring import compute_renewal_risk
from rig.signals.engine import evaluate_account

TODAY = date.today()


def _score_acme(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        evaluate_account(s, seeded["nsc_tenant"], seeded["acme_account"], today=TODAY)
        return compute_renewal_risk(s, seeded["nsc_tenant"], seeded["acme_account"], as_of=TODAY)


def test_score_is_explained_and_sums(seeded):
    result = _score_acme(seeded)
    assert result is not None
    assert result["direction"] == "higher_is_riskier"
    assert 50 <= result["value"] <= 100, "Acme should score high-risk"
    total = sum(c["contribution"] for c in result["components"])
    assert abs(total - result["value"]) < 0.05
    weights = sum(c["weight"] for c in result["components"])
    assert abs(weights - 1.0) < 0.001
    for component in result["components"]:
        if component["norm_value"] > 0:
            assert component["evidence_signal_ids"], (
                f"{component['component']} contributes without evidence"
            )


def test_score_is_reproducible(seeded):
    first = _score_acme(seeded)
    second = _score_acme(seeded)
    assert first["value"] == second["value"]
    assert first["inputs_hash"] == second["inputs_hash"]


def test_reliability_reflects_coverage(seeded):
    """Beta account has no invoices/tickets/usage → covered weight below the
    floor → no score emitted (insufficient data beats a fake number)."""
    with tenant_session(seeded["nsc_tenant"]) as s:
        evaluate_account(s, seeded["nsc_tenant"], seeded["beta_account"], today=TODAY)
        result = compute_renewal_risk(s, seeded["nsc_tenant"], seeded["beta_account"], as_of=TODAY)
    assert result is None

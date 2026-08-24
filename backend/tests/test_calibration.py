"""Progressive calibration: PAV correctness, the activation gate, prior
honesty, and end-to-end fitting on a synthetic labeled tenant."""

import random
import uuid
from datetime import date, timedelta

from sqlalchemy import text

from rig.calibration import (apply_knots, brier, fit, pav_isotonic,
                             prior_probability, probability_for)
from rig.db import tenant_session

TODAY = date.today()


def test_pav_monotone_and_pools_violators():
    # y dips at x=30 — PAV must pool it away; result must be non-decreasing
    pairs = [(10, 0.0), (20, 1.0), (30, 0.0), (40, 1.0), (50, 1.0)]
    knots = pav_isotonic(pairs)
    probabilities = [p for _, p in knots]
    assert probabilities == sorted(probabilities)
    # pooled block over the violator averages 0.5 across x=20..30
    assert apply_knots(knots, 25) == 0.5
    # applying beyond the fitted range clamps, never extrapolates certainty
    assert apply_knots(knots, 999) == probabilities[-1]


def test_prior_is_bounded_and_documented():
    assert prior_probability(0) == 0.05
    assert prior_probability(100) == 0.65
    assert prior_probability(74) == 0.494  # docs/20-scale scores stay uncertain


def test_prior_mode_before_labels(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        result = probability_for(s, 74.0)
    assert result["calibration"] == "default_prior"
    assert "not fitted to your outcomes" in result["basis"]
    assert result["p_nonrenewal"] == prior_probability(74.0)


def test_fit_refuses_insufficient_labels(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        result = fit(s, seeded["nsc_tenant"], fitted_by="u_model")
    assert result.status == "insufficient_labels"
    assert result.labels < 50


def _synthetic_labeled_tenant():
    """A dedicated tenant with 60 accounts whose outcomes correlate with
    their scores — enough signal for isotonic to beat the linear prior."""
    tenant_id = uuid.uuid4()
    rng = random.Random(7)
    with tenant_session(tenant_id) as s:
        s.execute(text("INSERT INTO tenant (id, name) VALUES (:id, 'CalibrationCo')"),
                  {"id": str(tenant_id)})
        for i in range(60):
            score_value = rng.uniform(5, 95)
            churn_probability = 0.05 if score_value < 40 else (0.5 if score_value < 70 else 0.95)
            churned = rng.random() < churn_probability
            account_id = s.execute(text(
                "INSERT INTO account (tenant_id, name, arr_cents, renewal_date)"
                " VALUES (:tid, :name, 1000000, :r) RETURNING id"
            ), {"tid": str(tenant_id), "name": f"Synth {i}",
                "r": TODAY - timedelta(days=30)}).scalar_one()
            s.execute(text(
                "INSERT INTO score (tenant_id, account_id, score_type, score_version,"
                " value, reliability, as_of, inputs_hash)"
                " VALUES (:tid, :aid, 'renewal_risk', 'test@v1', :v, 1.0,"
                " :asof, 'synthetic')"
            ), {"tid": str(tenant_id), "aid": str(account_id), "v": round(score_value, 2),
                "asof": TODAY - timedelta(days=40)})
            s.execute(text(
                "INSERT INTO renewal_outcome (tenant_id, account_id, outcome,"
                " outcome_date, was_flagged, intervention, recorded_by,"
                " root_cause_primary)"
                " VALUES (:tid, :aid, :outcome, :od, :flagged, 'none', 'synthetic', :rc)"
            ), {"tid": str(tenant_id), "aid": str(account_id),
                "outcome": "churned" if churned else "renewed",
                "od": TODAY - timedelta(days=30), "flagged": score_value >= 60,
                "rc": "other" if churned else None})
    return tenant_id


def test_end_to_end_fit_activates_and_serves_fitted_probability(seeded):
    tenant_id = _synthetic_labeled_tenant()
    with tenant_session(tenant_id) as s:
        result = fit(s, str(tenant_id), fitted_by="u_model")
        assert result.status == "activated", (result.brier_fitted, result.brier_prior)
        assert result.labels == 60
        assert result.brier_fitted < result.brier_prior

        served = probability_for(s, 85.0)
        assert served["calibration"] == f"isotonic_v{result.version}"
        # fitted high-score probability reflects the ~0.95 churn regime,
        # well above the conservative prior's 0.56 at score 85
        assert served["p_nonrenewal"] > prior_probability(85.0)
        assert served["p_nonrenewal"] > 0.7
        low = probability_for(s, 10.0)
        assert low["p_nonrenewal"] < 0.3

    # the fitted model is tenant-scoped: the demo tenant still runs the prior
    with tenant_session(seeded["nsc_tenant"]) as s:
        assert probability_for(s, 85.0)["calibration"] == "default_prior"


def test_pav_flattens_anticorrelated_labels():
    # labels perfectly ANTI-correlated with score: the monotone-increasing
    # fit must collapse to a single flat pool at the base rate
    pairs = [(float(x), 1.0 if x < 50 else 0.0) for x in range(0, 100, 2)]
    knots = pav_isotonic(pairs)
    assert len(knots) == 1 and knots[0][1] == 0.5
    assert brier(pairs, lambda x: apply_knots(knots, x)) == 0.25


def test_gate_rejects_worse_than_prior_model(seeded, monkeypatch):
    """Force a terrible fitted curve; the gate must store it INACTIVE and
    keep serving the prior."""
    import rig.calibration as calibration_module

    tenant_id = _synthetic_labeled_tenant()
    monkeypatch.setattr(calibration_module, "pav_isotonic",
                        lambda pairs: [(100.0, 0.99)])  # predicts 0.99 for everyone
    with tenant_session(tenant_id) as s:
        result = fit(s, str(tenant_id), fitted_by="u_model")
        assert result.status == "rejected_by_gate"
        assert result.brier_fitted > result.brier_prior
        active = s.execute(text(
            "SELECT active FROM calibration_model WHERE version = :v"
        ), {"v": result.version}).scalar_one()
        assert active is False
        # serving path untouched: still the honest prior
        assert probability_for(s, 85.0)["calibration"] == "default_prior"

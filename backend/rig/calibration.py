"""Progressive score calibration (docs/09 §C, §E).

Cold start: a documented PRIOR maps the 0-100 risk score to a non-renewal
probability, always labeled "default prior calibration — not fitted to your
outcomes". Once >= 50 outcome labels exist, an isotonic (PAV) calibrator can
be fitted per tenant — and it ACTIVATES only if it beats the prior on Brier
score over those labels (the docs/09 backtest gate: never replace an honest
default with a worse model). Fitting is explicit and audited, never silent.
"""

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

MIN_LABELS = 50


def prior_probability(score_value: float) -> float:
    """Documented default prior: linear in score, bounded away from fake
    certainty. score 0 -> 0.05, score 100 -> 0.65 (docs/09 cold-start:
    deliberately conservative; the walkthrough's 74 -> ~0.49)."""
    return round(0.05 + 0.60 * max(0.0, min(100.0, score_value)) / 100.0, 3)


def pav_isotonic(pairs: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Pool-adjacent-violators: non-decreasing fit of y on x.
    Returns step-function knots [(x, p), ...] with p non-decreasing."""
    ordered = sorted(pairs)
    # blocks: [x_last, weight, mean_y]
    blocks: list[list[float]] = []
    for x, y in ordered:
        blocks.append([x, 1.0, float(y)])
        while len(blocks) >= 2 and blocks[-2][2] >= blocks[-1][2]:
            x2, w2, m2 = blocks.pop()
            x1, w1, m1 = blocks.pop()
            blocks.append([max(x1, x2), w1 + w2, (m1 * w1 + m2 * w2) / (w1 + w2)])
    return [(b[0], round(b[2], 4)) for b in blocks]


def apply_knots(knots: list[tuple[float, float]], score_value: float) -> float:
    """Step interpolation: p of the first knot whose x >= score, clamped to
    the fitted range (no extrapolated certainty)."""
    if not knots:
        return prior_probability(score_value)
    for x, p in knots:
        if score_value <= x:
            return p
    return knots[-1][1]


def brier(pairs: list[tuple[float, float]], predict) -> float:
    return round(sum((predict(x) - y) ** 2 for x, y in pairs) / len(pairs), 4)


@dataclass
class FitResult:
    status: str          # activated | rejected_by_gate | insufficient_labels
    labels: int
    version: int | None = None
    brier_fitted: float | None = None
    brier_prior: float | None = None
    knots: list[tuple[float, float]] | None = None


def _label_pairs(session: Session) -> list[tuple[float, float]]:
    """(score at the last pre-outcome computation, y=1 if not renewed)."""
    rows = session.execute(text(
        "SELECT (SELECT s.value FROM score s WHERE s.account_id = ro.account_id"
        "        AND s.score_type = 'renewal_risk' AND s.as_of::date <= ro.outcome_date"
        "        ORDER BY s.as_of DESC LIMIT 1) AS score_value,"
        " (ro.outcome != 'renewed')::int AS y"
        " FROM renewal_outcome ro"
    )).all()
    return [(float(r[0]), float(r[1])) for r in rows if r[0] is not None]


def fit(session: Session, tenant_id: str, *, fitted_by: str,
        min_labels: int = MIN_LABELS) -> FitResult:
    pairs = _label_pairs(session)
    if len(pairs) < min_labels:
        return FitResult(status="insufficient_labels", labels=len(pairs))

    # The gate compares on a HOLDOUT split: an isotonic fit evaluated on its
    # own training data can essentially never lose to the prior (it is the
    # least-squares monotone fit), which would make the gate vacuous.
    # Deterministic shuffle so repeated fits on the same labels agree.
    import random as _random

    shuffled = sorted(pairs)  # canonical order first, then seeded shuffle
    _random.Random(0).shuffle(shuffled)
    split = max(int(len(shuffled) * 0.7), 2)
    train, holdout = shuffled[:split], shuffled[split:] or shuffled[:1]
    train_knots = pav_isotonic(train)
    brier_fitted = brier(holdout, lambda x: apply_knots(train_knots, x))
    brier_prior = brier(holdout, prior_probability)
    active = brier_fitted < brier_prior   # the gate: must beat the prior out-of-sample
    # when activated, the stored curve is refit on ALL labels
    knots = pav_isotonic(pairs) if active else train_knots

    version = (session.execute(text(
        "SELECT COALESCE(max(version), 0) FROM calibration_model"
        " WHERE score_type = 'renewal_risk'"
    )).scalar_one()) + 1
    session.execute(text(
        "INSERT INTO calibration_model (tenant_id, score_type, version, knots,"
        " labels_used, brier_fitted, brier_prior, active, fitted_by)"
        " VALUES (:tid, 'renewal_risk', :v, CAST(:knots AS jsonb), :n, :bf, :bp,"
        " :active, :by)"
    ), {"tid": tenant_id, "v": version, "knots": json.dumps(knots), "n": len(pairs),
        "bf": brier_fitted, "bp": brier_prior, "active": active, "by": fitted_by})
    return FitResult(
        status="activated" if active else "rejected_by_gate",
        labels=len(pairs), version=version,
        brier_fitted=brier_fitted, brier_prior=brier_prior, knots=knots)


def probability_for(session: Session, score_value: float) -> dict:
    """Calibrated probability + provenance for display (docs/06 B: never a
    number without its basis)."""
    model = session.execute(text(
        "SELECT version, knots, labels_used FROM calibration_model"
        " WHERE score_type = 'renewal_risk' AND active"
        " ORDER BY version DESC LIMIT 1"
    )).mappings().one_or_none()
    if model is None:
        return {
            "p_nonrenewal": prior_probability(score_value),
            "calibration": "default_prior",
            "basis": "default prior calibration — not fitted to your outcomes"
                     f" (fits at {MIN_LABELS}+ recorded outcomes)",
        }
    knots = [(float(x), float(p)) for x, p in model["knots"]]
    return {
        "p_nonrenewal": apply_knots(knots, score_value),
        "calibration": f"isotonic_v{model['version']}",
        "basis": f"isotonic calibration fitted on {model['labels_used']}"
                 " recorded outcomes (beat the prior on Brier score)",
    }

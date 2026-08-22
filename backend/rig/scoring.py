"""Renewal-risk score v0: rule-based weighted composite (doc 9 §C).

Deterministic, reproducible (inputs_hash), fully explained: every component
stores weight, normalized value, signed contribution, rationale, and the
evidence ids of the signals that drove it. Higher = riskier.

Missing-data policy: components whose inputs are absent are excluded and the
remaining weights renormalized; reliability decreases accordingly. Below 60%
weight coverage no score is emitted ("insufficient data" — a stale number is
worse than no number).
"""

import hashlib
import json
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

SCORE_VERSION = "renewal_risk@v0.1"

# component -> (weight, contributing signal types)
COMPONENTS: dict[str, tuple[float, list[str]]] = {
    "usage_trajectory": (0.25, ["usage_drop_vs_baseline"]),
    "support_friction": (0.20, ["critical_ticket_unresolved"]),
    "commercial_engagement": (0.25, ["renewal_no_plan", "notice_period_approaching"]),
    "billing_health": (0.15, ["payment_late"]),
    "sentiment_trend": (0.15, ["negative_sentiment"]),
}

SEVERITY_NORM = {"info": 0.1, "low": 0.25, "medium": 0.5, "high": 0.8, "critical": 1.0}
MIN_WEIGHT_COVERAGE = 0.6


def compute_renewal_risk(
    session: Session,
    tenant_id: UUID | str,
    account_id: UUID | str,
    as_of: date | None = None,
) -> dict | None:
    """Compute and persist the score. Returns explanation dict, or None if
    insufficient data coverage."""
    tenant_id, account_id = str(tenant_id), str(account_id)
    as_of_ts = (
        datetime.combine(as_of, datetime.min.time(), tzinfo=timezone.utc)
        if as_of else datetime.now(timezone.utc)
    )

    # LLM-derived signals never affect scores until a human confirms them
    # (docs/07 conventions, docs/09 principle 7).
    signals = session.execute(text(
        "SELECT id, signal_type, severity, confidence, rationale FROM signal"
        " WHERE account_id = :aid AND state = 'active'"
        " AND (requires_review = false OR review_outcome = 'confirmed')"
    ), {"aid": account_id}).mappings().all()
    by_type: dict[str, list] = {}
    for s in signals:
        by_type.setdefault(s["signal_type"], []).append(s)

    # Which data domains have any coverage at all (absence of data != absence of risk)
    has_usage = session.execute(text(
        "SELECT EXISTS (SELECT 1 FROM usage_metric_daily WHERE account_id = :aid)"
    ), {"aid": account_id}).scalar_one()
    has_billing = session.execute(text(
        "SELECT EXISTS (SELECT 1 FROM invoice WHERE account_id = :aid)"
    ), {"aid": account_id}).scalar_one()
    has_support = session.execute(text(
        "SELECT EXISTS (SELECT 1 FROM support_ticket WHERE account_id = :aid)"
    ), {"aid": account_id}).scalar_one()
    coverage = {
        "usage_trajectory": bool(has_usage),
        "support_friction": bool(has_support),
        "commercial_engagement": True,  # CRM fields always present for an account
        "billing_health": bool(has_billing),
        # conversation coverage proxy: support text is the only conversation
        # source until call transcripts land (V2)
        "sentiment_trend": bool(has_support),
    }

    covered_weight = sum(w for name, (w, _) in COMPONENTS.items() if coverage[name])
    if covered_weight < MIN_WEIGHT_COVERAGE:
        return None

    components = []
    raw_total = 0.0
    for name, (weight, signal_types) in COMPONENTS.items():
        if not coverage[name]:
            continue
        matched = [s for t in signal_types for s in by_type.get(t, [])]
        if matched:
            # strongest severity drives the component; confidence attenuates
            norm = max(SEVERITY_NORM[s["severity"]] * float(s["confidence"]) for s in matched)
            rationale = "; ".join(s["rationale"] for s in matched)
        else:
            norm, rationale = 0.0, "no active signals in this dimension"
        renorm_weight = weight / covered_weight
        contribution = 100 * renorm_weight * norm
        raw_total += contribution
        components.append({
            "component": name,
            "weight": round(renorm_weight, 4),
            "norm_value": round(norm, 4),
            "contribution": round(contribution, 3),
            "rationale": rationale,
            "evidence_signal_ids": [str(s["id"]) for s in matched],
        })

    value = round(raw_total, 2)
    reliability = round(covered_weight, 2)
    inputs_hash = hashlib.sha256(json.dumps({
        "version": SCORE_VERSION,
        "signals": sorted((s["signal_type"], s["severity"], str(s["confidence"])) for s in signals),
        "coverage": coverage,
    }, sort_keys=True).encode()).hexdigest()

    score_id = session.execute(text(
        "INSERT INTO score (tenant_id, account_id, score_type, score_version, value,"
        " reliability, as_of, inputs_hash)"
        " VALUES (:tid, :aid, 'renewal_risk', :ver, :val, :rel, :asof, :hash)"
        " ON CONFLICT (tenant_id, account_id, score_type, as_of)"
        " DO UPDATE SET value = EXCLUDED.value, reliability = EXCLUDED.reliability,"
        "   inputs_hash = EXCLUDED.inputs_hash, score_version = EXCLUDED.score_version"
        " RETURNING id"
    ), {"tid": tenant_id, "aid": account_id, "ver": SCORE_VERSION, "val": value,
        "rel": reliability, "asof": as_of_ts, "hash": inputs_hash}).scalar_one()

    session.execute(text("DELETE FROM score_component WHERE score_id = :sid"), {"sid": str(score_id)})
    for c in components:
        session.execute(text(
            "INSERT INTO score_component (tenant_id, score_id, component, weight,"
            " norm_value, contribution, rationale, evidence_ids)"
            " VALUES (:tid, :sid, :name, :w, :n, :c, :r, CAST(:ev AS uuid[]))"
        ), {"tid": tenant_id, "sid": str(score_id), "name": c["component"],
            "w": c["weight"], "n": c["norm_value"], "c": c["contribution"],
            "r": c["rationale"], "ev": "{" + ",".join(c["evidence_signal_ids"]) + "}"})

    return {
        "score_id": str(score_id),
        "score_type": "renewal_risk",
        "score_version": SCORE_VERSION,
        "value": value,
        "direction": "higher_is_riskier",
        "reliability": reliability,
        "inputs_hash": inputs_hash,
        "as_of": as_of_ts.isoformat(),
        "components": components,
    }

"""Claim-verification layer (docs/10 §10.3).

Nothing executive-facing bypasses this. For each claim:

1. Citation existence — every material claim maps to ≥1 evidence_object id
   that exists in this tenant's store (RLS-scoped).
2. Quantitative check — every numeral appearing in the claim text must match
   a value in the claim's declared `numeric_values` allowlist. Generators
   inject numbers from the metrics layer; free-hand arithmetic cannot pass.
3. Class check — claim_class must be a known class.
4. Staleness — cited evidence must be fresh within policy.

Verdict: verified | unsupported (with reasons). Callers decide whether
unsupported claims are dropped (executive surfaces: always) or labeled.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

CLAIM_CLASSES = {"observed_fact", "model_prediction", "ai_interpretation", "recommendation"}
DEFAULT_MAX_EVIDENCE_AGE_DAYS = 14

_NUMERAL = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def _normalize_number(token: str) -> str:
    return token.strip("$%").replace(",", "").rstrip(".")


@dataclass
class Claim:
    text: str
    claim_class: str
    evidence_ids: list[str] = field(default_factory=list)
    numeric_values: list[str] = field(default_factory=list)


def verify_claim(session: Session, claim: Claim,
                 max_evidence_age_days: int = DEFAULT_MAX_EVIDENCE_AGE_DAYS) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if claim.claim_class not in CLAIM_CLASSES:
        reasons.append(f"unknown claim class '{claim.claim_class}'")

    if not claim.evidence_ids:
        reasons.append("no evidence cited")
    else:
        rows = session.execute(text(
            "SELECT id, freshness_at FROM evidence_object WHERE id = ANY(CAST(:ids AS uuid[]))"
        ), {"ids": "{" + ",".join(claim.evidence_ids) + "}"}).mappings().all()
        found = {str(r["id"]) for r in rows}
        missing = [e for e in claim.evidence_ids if e not in found]
        if missing:
            reasons.append(f"cited evidence does not exist: {missing}")
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_evidence_age_days)
        stale = [str(r["id"]) for r in rows if r["freshness_at"] < cutoff]
        if stale:
            reasons.append(f"cited evidence is stale (> {max_evidence_age_days}d): {stale}")

    allowed = {_normalize_number(v) for v in claim.numeric_values}
    for token in _NUMERAL.findall(claim.text):
        if _normalize_number(token) not in allowed:
            reasons.append(f"numeric claim '{token}' not backed by the metrics layer")

    return ("verified" if not reasons else "unsupported"), reasons


def verify_claims(session: Session, claims: list[Claim],
                  max_evidence_age_days: int = DEFAULT_MAX_EVIDENCE_AGE_DAYS) -> list[dict]:
    results = []
    for claim in claims:
        status, reasons = verify_claim(session, claim, max_evidence_age_days)
        results.append({
            "text": claim.text, "claim_class": claim.claim_class,
            "evidence_ids": claim.evidence_ids, "numeric_values": claim.numeric_values,
            "verification": {"status": status, "reasons": reasons},
        })
    return results

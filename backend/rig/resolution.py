"""Identity resolution v1 (doc 6 §A.3).

Resolves source records (CRM companies, billing customers) to canonical
accounts. Match ladder: explicit source_link → domain → fuzzy name.
Confidence bands:
  >= AUTO_LINK   auto-link (source_link created)
  REVIEW..AUTO   human review queue (identity_candidate)
  <  REVIEW      primary sources create a new account; secondary sources queue

The CRM is "primary" (it may mint canonical accounts); billing/support are
"secondary" (they must attach to an existing account or ask a human).
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

AUTO_LINK_CONFIDENCE = 0.95
REVIEW_CONFIDENCE = 0.70

_LEGAL_SUFFIXES = re.compile(
    r"\b(incorporated|corporation|company|limited|holdings|inc|corp|ltd|llc|gmbh|co)\b\.?",
    re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    cleaned = _LEGAL_SUFFIXES.sub("", name.lower())
    return re.sub(r"[^a-z0-9]+", " ", cleaned).strip()


@dataclass
class Resolution:
    outcome: str          # linked | created | queued | already_linked
    account_id: UUID | None
    method: str | None = None
    confidence: float | None = None


def _existing_link(session: Session, source_system: str, source_record_id: str) -> UUID | None:
    return session.execute(text(
        "SELECT entity_id FROM source_link WHERE source_system = :src"
        " AND source_record_id = :rec AND entity_type = 'account' AND status = 'linked'"
    ), {"src": source_system, "rec": source_record_id}).scalar_one_or_none()


def _link(session: Session, tenant_id: str, account_id: UUID, source_system: str,
          source_record_id: str, method: str, confidence: float,
          linked_by: str | None = None) -> None:
    session.execute(text(
        "INSERT INTO source_link (tenant_id, entity_type, entity_id, source_system,"
        " source_record_id, match_method, confidence, linked_by)"
        " VALUES (:tid, 'account', :eid, :src, :rec, :method, :conf, :by)"
        " ON CONFLICT (tenant_id, source_system, source_record_id, entity_type)"
        " DO UPDATE SET entity_id = EXCLUDED.entity_id, match_method = EXCLUDED.match_method,"
        "   confidence = EXCLUDED.confidence, status = 'linked', linked_by = EXCLUDED.linked_by"
    ), {"tid": tenant_id, "eid": str(account_id), "src": source_system,
        "rec": source_record_id, "method": method, "conf": confidence, "by": linked_by})


def _queue_candidate(session: Session, tenant_id: str, source_system: str,
                     source_record_id: str, display: dict,
                     suggested: UUID | None, confidence: float | None, method: str | None) -> None:
    import json
    session.execute(text(
        "INSERT INTO identity_candidate (tenant_id, entity_type, source_system,"
        " source_record_id, display, suggested_entity_id, suggested_confidence, match_method)"
        " VALUES (:tid, 'account', :src, :rec, CAST(:disp AS jsonb), :sug, :conf, :method)"
        " ON CONFLICT (tenant_id, source_system, source_record_id, entity_type) DO NOTHING"
    ), {"tid": tenant_id, "src": source_system, "rec": source_record_id,
        "disp": json.dumps(display), "sug": str(suggested) if suggested else None,
        "conf": confidence, "method": method})


def _best_match(session: Session, name: str | None, domain: str | None):
    """Returns (account_id, method, confidence) for the best candidate, or None."""
    if domain:
        account_id = session.execute(text(
            "SELECT id FROM account WHERE :domain = ANY(domains) AND deleted_at IS NULL LIMIT 1"
        ), {"domain": domain.lower()}).scalar_one_or_none()
        if account_id:
            return account_id, "domain", 0.98
    if name:
        target = normalize_name(name)
        if target:
            best, best_score = None, 0.0
            rows = session.execute(text(
                "SELECT id, name FROM account WHERE deleted_at IS NULL"
            )).all()
            for account_id, account_name in rows:
                score = SequenceMatcher(None, target, normalize_name(account_name)).ratio()
                if score > best_score:
                    best, best_score = account_id, score
            if best and best_score >= REVIEW_CONFIDENCE:
                return best, "fuzzy_name", round(best_score, 2)
    return None


def resolve_account(
    session: Session,
    tenant_id: UUID | str,
    *,
    source_system: str,
    source_record_id: str,
    name: str,
    domain: str | None = None,
    primary: bool = False,
    extra_fields: dict | None = None,
) -> Resolution:
    tenant_id = str(tenant_id)
    existing = _existing_link(session, source_system, source_record_id)
    if existing:
        return Resolution("already_linked", existing)

    match = _best_match(session, name, domain)
    if match:
        account_id, method, confidence = match
        if confidence >= AUTO_LINK_CONFIDENCE:
            _link(session, tenant_id, account_id, source_system, source_record_id,
                  method, confidence)
            if domain:  # enrich canonical domains from newly linked source
                session.execute(text(
                    "UPDATE account SET domains = array_append(domains, :d), updated_at = now()"
                    " WHERE id = :id AND NOT (:d = ANY(domains))"
                ), {"d": domain.lower(), "id": str(account_id)})
            return Resolution("linked", account_id, method, confidence)
        _queue_candidate(session, tenant_id, source_system, source_record_id,
                         {"name": name, "domain": domain}, account_id, confidence, method)
        return Resolution("queued", None, method, confidence)

    if primary:
        extra = extra_fields or {}
        account_id = session.execute(text(
            "INSERT INTO account (tenant_id, name, domains, segment, tier, arr_cents, renewal_date)"
            " VALUES (:tid, :name, :domains, :segment, :tier, :arr, :renewal) RETURNING id"
        ), {"tid": tenant_id, "name": name,
            "domains": [domain.lower()] if domain else [],
            "segment": extra.get("segment"), "tier": extra.get("tier"),
            "arr": extra.get("arr_cents"), "renewal": extra.get("renewal_date")}).scalar_one()
        _link(session, tenant_id, account_id, source_system, source_record_id, "created", 1.0)
        return Resolution("created", account_id, "created", 1.0)

    _queue_candidate(session, tenant_id, source_system, source_record_id,
                     {"name": name, "domain": domain}, None, None, None)
    return Resolution("queued", None)


def accept_candidate(
    session: Session,
    tenant_id: UUID | str,
    candidate_id: UUID | str,
    *,
    resolved_by: str,
    target_account_id: UUID | str | None = None,
    create_account: bool = False,
) -> UUID:
    """Human decision: link to target (or suggestion), or mint a new account."""
    tenant_id = str(tenant_id)
    candidate = session.execute(text(
        "SELECT * FROM identity_candidate WHERE id = :id AND status = 'pending'"
    ), {"id": str(candidate_id)}).mappings().one_or_none()
    if candidate is None:
        raise ValueError("candidate not found or already resolved")

    if create_account:
        display = candidate["display"]
        account_id = session.execute(text(
            "INSERT INTO account (tenant_id, name, domains) VALUES (:tid, :name, :domains)"
            " RETURNING id"
        ), {"tid": tenant_id, "name": display.get("name", "Unnamed"),
            "domains": [display["domain"].lower()] if display.get("domain") else []}).scalar_one()
    else:
        account_id = target_account_id or candidate["suggested_entity_id"]
        if account_id is None:
            raise ValueError("no target account: pass target_account_id or create_account=True")

    _link(session, tenant_id, UUID(str(account_id)), candidate["source_system"],
          candidate["source_record_id"], "human", 1.0, linked_by=resolved_by)
    session.execute(text(
        "UPDATE identity_candidate SET status = 'accepted', resolved_entity_id = :eid,"
        " resolved_by = :by, resolved_at = now() WHERE id = :id"
    ), {"eid": str(account_id), "by": resolved_by, "id": str(candidate_id)})
    return UUID(str(account_id))


def reject_candidate(session: Session, tenant_id: UUID | str, candidate_id: UUID | str,
                     *, resolved_by: str) -> None:
    updated = session.execute(text(
        "UPDATE identity_candidate SET status = 'rejected', resolved_by = :by,"
        " resolved_at = now() WHERE id = :id AND status = 'pending'"
    ), {"by": resolved_by, "id": str(candidate_id)}).rowcount
    if not updated:
        raise ValueError("candidate not found or already resolved")

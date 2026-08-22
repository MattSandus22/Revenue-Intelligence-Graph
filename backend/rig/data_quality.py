"""Data-quality monitoring v0 (docs/06 H): freshness + required fields.

Issues are upserted on a dedupe key, auto-resolve when the condition clears,
and are consumed by scoring (usage staleness suppresses usage signals rather
than firing on dead data — docs/07 U1 FP-prevention).
"""

import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

USAGE_FRESHNESS_SLA_DAYS = 3
SYNC_FRESHNESS_SLA_HOURS = 24
REQUIRED_ACCOUNT_FIELDS = ["renewal_date", "arr_cents"]


def usage_is_fresh(session: Session, account_id: str, today: date | None = None) -> bool:
    today = today or datetime.now(timezone.utc).date()
    latest = session.execute(text(
        "SELECT max(date) FROM usage_metric_daily WHERE account_id = :aid"
    ), {"aid": account_id}).scalar_one()
    return latest is not None and (today - latest).days <= USAGE_FRESHNESS_SLA_DAYS


def run_checks(session: Session, tenant_id: str, today: date | None = None) -> dict:
    """Run all checks; upsert open issues, resolve cleared ones."""
    today = today or datetime.now(timezone.utc).date()
    open_keys: set[str] = set()

    # 1. Usage freshness per account that has ever reported usage.
    rows = session.execute(text(
        "SELECT a.id, a.name, max(u.date) AS latest FROM account a"
        " JOIN usage_metric_daily u ON u.account_id = a.id"
        " WHERE a.deleted_at IS NULL GROUP BY a.id, a.name"
    )).mappings().all()
    for row in rows:
        stale_days = (today - row["latest"]).days
        if stale_days > USAGE_FRESHNESS_SLA_DAYS:
            key = f"freshness:usage:{row['id']}"
            open_keys.add(key)
            _upsert_issue(session, tenant_id, key,
                          issue_class="freshness", severity="high",
                          title=f"Usage data stale for {row['name']} ({stale_days} days)",
                          impact="Usage signals suspended; adoption/risk scores degraded "
                                 "until the feed recovers.",
                          affected={"account_id": str(row["id"]), "stale_days": stale_days})

    # 2. Connector sync freshness.
    rows = session.execute(text(
        "SELECT ds.id, ds.type, ds.name, ds.status,"
        " (SELECT max(finished_at) FROM sync_run sr WHERE sr.data_source_id = ds.id"
        "   AND sr.status = 'succeeded') AS last_ok"
        " FROM data_source ds WHERE ds.status != 'disconnected'"
    )).mappings().all()
    now = datetime.now(timezone.utc)
    for row in rows:
        last_ok = row["last_ok"]
        breached = last_ok is None or (now - last_ok) > timedelta(hours=SYNC_FRESHNESS_SLA_HOURS)
        if breached or row["status"] == "action_required":
            key = f"freshness:sync:{row['id']}"
            open_keys.add(key)
            _upsert_issue(session, tenant_id, key,
                          issue_class="freshness", severity="high",
                          title=f"Connector '{row['name']}' ({row['type']}) is stale or failing",
                          impact="Downstream records may be out of date; dependent insight "
                                 "confidence is reduced.",
                          affected={"data_source_id": str(row["id"]), "status": row["status"]})

    # 3. Required account fields (hygiene).
    for field in REQUIRED_ACCOUNT_FIELDS:
        rows = session.execute(text(
            f"SELECT id, name FROM account WHERE deleted_at IS NULL AND {field} IS NULL"
        )).mappings().all()
        for row in rows:
            key = f"missing_field:account:{row['id']}:{field}"
            open_keys.add(key)
            _upsert_issue(session, tenant_id, key,
                          issue_class="missing_field", severity="medium",
                          title=f"{row['name']}: missing {field}",
                          impact="Renewal signals and forecast coverage are incomplete "
                                 "for this account.",
                          affected={"account_id": str(row["id"]), "field": field})

    # Auto-resolve issues whose condition cleared.
    resolved = 0
    for row in session.execute(text(
        "SELECT id, dedupe_key FROM data_quality_issue WHERE state = 'open'"
    )).mappings().all():
        if row["dedupe_key"] not in open_keys:
            session.execute(text(
                "UPDATE data_quality_issue SET state = 'resolved', resolved_at = now()"
                " WHERE id = :id"
            ), {"id": str(row["id"])})
            resolved += 1

    return {"open": len(open_keys), "resolved": resolved}


def _upsert_issue(session: Session, tenant_id: str, dedupe_key: str, *, issue_class: str,
                  severity: str, title: str, impact: str, affected: dict) -> None:
    session.execute(text(
        "INSERT INTO data_quality_issue (tenant_id, issue_class, severity, dedupe_key,"
        " title, impact, affected_refs)"
        " VALUES (:tid, :cls, :sev, :key, :title, :impact, CAST(:refs AS jsonb))"
        " ON CONFLICT (tenant_id, dedupe_key)"
        " DO UPDATE SET severity = EXCLUDED.severity, title = EXCLUDED.title,"
        "   impact = EXCLUDED.impact, affected_refs = EXCLUDED.affected_refs,"
        "   state = 'open', resolved_at = NULL"
    ), {"tid": tenant_id, "cls": issue_class, "sev": severity, "key": dedupe_key,
        "title": title, "impact": impact, "refs": json.dumps(affected)})

"""CSV usage import (docs/11 Phase 1 — the universal fallback for product data).

Template columns: account_ref, date, metric, value[, user_count]
`account_ref` may be a canonical account id, a domain, or an exact name.

Contract: validate everything first, return a full validation report, and
commit only valid rows (partial commit is deliberate: unmatched accounts are
listed for the admin to fix, matched data starts flowing immediately).
"""

import csv
import io
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

REQUIRED_COLUMNS = {"account_ref", "date", "metric", "value"}


def import_usage_csv(session: Session, tenant_id: str, content: str) -> dict:
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames is None or not REQUIRED_COLUMNS <= set(reader.fieldnames):
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
        return {"status": "rejected", "error": f"missing required columns: {missing}",
                "imported": 0, "errors": []}

    # Build account lookup once: id, domain, exact name (case-insensitive).
    accounts = session.execute(text(
        "SELECT id, name, domains FROM account WHERE deleted_at IS NULL"
    )).mappings().all()
    by_id = {str(a["id"]): a["id"] for a in accounts}
    by_domain = {d.lower(): a["id"] for a in accounts for d in a["domains"]}
    by_name = {a["name"].lower(): a["id"] for a in accounts}

    imported, errors = 0, []
    for line_number, row in enumerate(reader, start=2):
        ref = (row.get("account_ref") or "").strip()
        account_id = by_id.get(ref) or by_domain.get(ref.lower()) or by_name.get(ref.lower())
        if account_id is None:
            errors.append({"line": line_number, "error": f"unmatched account_ref '{ref}'"})
            continue
        try:
            day = date.fromisoformat((row.get("date") or "").strip())
            value = float(row["value"])
            user_count = int(row["user_count"]) if (row.get("user_count") or "").strip() else None
            metric = (row.get("metric") or "").strip()
            if not metric:
                raise ValueError("empty metric")
        except (ValueError, KeyError) as exc:
            errors.append({"line": line_number, "error": f"malformed row: {exc}"})
            continue

        session.execute(text(
            "INSERT INTO usage_metric_daily (tenant_id, account_id, metric, date, value, user_count)"
            " VALUES (:tid, :aid, :metric, :date, :value, :users)"
            " ON CONFLICT (tenant_id, account_id, metric, date)"
            " DO UPDATE SET value = EXCLUDED.value, user_count = EXCLUDED.user_count"
        ), {"tid": tenant_id, "aid": str(account_id), "metric": metric,
            "date": day, "value": value, "users": user_count})
        imported += 1

    return {
        "status": "ok" if not errors else ("partial" if imported else "rejected"),
        "imported": imported,
        "error_count": len(errors),
        "errors": errors[:100],  # cap the report; full count above
    }

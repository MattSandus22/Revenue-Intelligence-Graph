"""Semantic layer: the ONLY path from natural language to the database.

The LLM never emits SQL. It emits filter tuples against this allow-listed
catalog; the compiler turns known (field, op) pairs into parameterized SQL
fragments and returns everything else as `unsupported` — surfaced to the
user, never guessed (docs/06 module J, docs/09 §D.12).
"""

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..signals.registry import load_registry

MAX_LIMIT = 200

# field -> allowed ops. Values are strings from the model; coercion below.
CATALOG: dict[str, set[str]] = {
    "name": {"contains"},
    "arr": {"gte", "lte"},                    # dollars in questions; cents in db
    "renewal_date": {"within_days", "beyond_days"},
    "segment": {"eq"},
    "tier": {"eq"},
    "lifecycle_stage": {"eq"},
    "plan_status": {"eq", "ne"},
    "risk_score": {"gte", "lte"},
    "signal": {"active"},                     # value = signal type from the registry
}


def known_signal_types() -> set[str]:
    return set(load_registry().keys()) | {"negative_sentiment"}


def catalog_description() -> str:
    """Rendered into the parser prompt so the model maps to real fields."""
    lines = [f"- {name}: ops {sorted(ops)}" for name, ops in CATALOG.items()]
    lines.append(f"  signal values must be one of: {sorted(known_signal_types())}")
    return "\n".join(lines)


@dataclass
class CompiledQuery:
    conditions: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)
    applied: list[dict] = field(default_factory=list)
    unsupported: list[dict] = field(default_factory=list)


_RISK_SUBQUERY = ("(SELECT s.value FROM score s WHERE s.account_id = a.id"
                  " AND s.score_type = 'renewal_risk' ORDER BY s.as_of DESC LIMIT 1)")


def compile_filters(filters: list[dict]) -> CompiledQuery:
    compiled = CompiledQuery()
    for i, item in enumerate(filters):
        field_name, op, value = item.get("field"), item.get("op"), item.get("value")
        key = f"p{i}"
        if field_name not in CATALOG or op not in CATALOG.get(field_name, set()):
            compiled.unsupported.append({**item, "reason": "field/op not in the semantic catalog"})
            continue
        try:
            if field_name == "name" and op == "contains":
                compiled.conditions.append(f"a.name ILIKE :{key}")
                compiled.params[key] = f"%{value}%"
            elif field_name == "arr":
                cents = int(float(str(value).replace("$", "").replace(",", "")) * 100)
                compiled.conditions.append(
                    f"a.arr_cents {'>=' if op == 'gte' else '<='} :{key}")
                compiled.params[key] = cents
            elif field_name == "renewal_date":
                days = int(value)
                if op == "within_days":
                    compiled.conditions.append(
                        f"a.renewal_date BETWEEN CURRENT_DATE AND CURRENT_DATE + :{key}")
                else:
                    compiled.conditions.append(f"a.renewal_date > CURRENT_DATE + :{key}")
                compiled.params[key] = days
            elif field_name in ("segment", "tier", "lifecycle_stage", "plan_status"):
                operator = "=" if op == "eq" else "!="
                compiled.conditions.append(f"a.{field_name} {operator} :{key}")
                compiled.params[key] = str(value)
            elif field_name == "risk_score":
                compiled.conditions.append(
                    f"{_RISK_SUBQUERY} {'>=' if op == 'gte' else '<='} :{key}")
                compiled.params[key] = float(value)
            elif field_name == "signal":
                if value not in known_signal_types():
                    compiled.unsupported.append({**item, "reason": "unknown signal type"})
                    continue
                # unconfirmed LLM signals never satisfy queries (review rule)
                compiled.conditions.append(
                    f"EXISTS (SELECT 1 FROM signal sg WHERE sg.account_id = a.id"
                    f" AND sg.signal_type = :{key} AND sg.state = 'active'"
                    f" AND (sg.requires_review = false OR sg.review_outcome = 'confirmed'))")
                compiled.params[key] = value
        except (ValueError, TypeError):
            compiled.unsupported.append({**item, "reason": "value could not be interpreted"})
            continue
        compiled.applied.append(item)
    return compiled


def execute_account_query(session: Session, compiled: CompiledQuery, limit: int) -> list[dict]:
    limit = max(1, min(int(limit or 50), MAX_LIMIT))
    where = " AND ".join(["a.deleted_at IS NULL", *compiled.conditions])
    rows = session.execute(text(
        f"SELECT a.id, a.name, a.arr_cents, a.renewal_date, a.segment, a.tier,"
        f" a.plan_status, a.lifecycle_stage, {_RISK_SUBQUERY} AS risk_score"
        f" FROM account a WHERE {where}"
        f" ORDER BY a.arr_cents DESC NULLS LAST LIMIT {limit}"
    ), compiled.params).mappings().all()
    return [dict(r) for r in rows]

"""Deterministic/statistical signal engine (Sprint 1 detectors).

Every detection returns evidence descriptors; the engine persists
evidence_object rows and binds evidence_citation rows to the signal — a signal
without evidence cannot exist, by construction (doc 10).

Idempotency: signals are keyed on (tenant, account, signal_type, semantic_key).
Re-evaluation updates magnitude/severity and increments occurrence_count;
detections that no longer hold are transitioned to state 'resolved'.
"""

import hashlib
import json
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from .registry import SignalDefinition, load_registry


@dataclass
class EvidenceSpec:
    kind: str
    source_system: str
    source_record_id: str
    statement: str            # rendered claim, always claim_class=observed_fact here
    event_at: datetime
    content_ref: dict = field(default_factory=dict)


@dataclass
class Detection:
    semantic_key: str
    severity: str
    confidence: float
    magnitude: dict
    rationale: str
    evidence: list[EvidenceSpec]


# ---------------------------------------------------------------------------
# Detectors. Each receives (session, account_row, params, today) and returns
# a list of Detection. Account row is a mapping of the account table columns.
# ---------------------------------------------------------------------------

def detect_renewal_no_plan(session: Session, account, params: dict, today: date) -> list[Detection]:
    renewal = account["renewal_date"]
    if renewal is None:
        return []
    days_to_renewal = (renewal - today).days
    if not (0 <= days_to_renewal <= params["window_days"]) or account["plan_status"] == "active":
        return []
    severity = "medium" if account["auto_renew"] else "high"
    return [Detection(
        semantic_key=f"renewal:{renewal.isoformat()}",
        severity=severity,
        confidence=1.0,
        magnitude={"days_to_renewal": days_to_renewal, "plan_status": account["plan_status"]},
        rationale=(
            f"Renewal due {renewal.isoformat()} ({days_to_renewal} days) with no active account plan"
        ),
        evidence=[EvidenceSpec(
            kind="crm_field",
            source_system="crm",
            source_record_id=f"account:{account['id']}:renewal_date",
            statement=f"Renewal date {renewal.isoformat()}; account plan status '{account['plan_status']}'",
            event_at=datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
        )],
    )]


def detect_notice_period_approaching(session: Session, account, params: dict, today: date) -> list[Detection]:
    renewal, notice_days = account["renewal_date"], account["notice_days"]
    if renewal is None or notice_days is None:
        return []
    deadline = renewal - timedelta(days=notice_days)
    days_to_deadline = (deadline - today).days
    if not (0 <= days_to_deadline <= params["window_days"]):
        return []
    return [Detection(
        semantic_key=f"notice:{deadline.isoformat()}",
        severity="high",
        confidence=1.0,
        magnitude={"notice_deadline": deadline.isoformat(), "days_to_deadline": days_to_deadline},
        rationale=f"Contract notice deadline {deadline.isoformat()} is {days_to_deadline} days away",
        evidence=[EvidenceSpec(
            kind="crm_field",
            source_system="crm",
            source_record_id=f"account:{account['id']}:notice_terms",
            statement=(
                f"Contract requires {notice_days}-day notice before renewal {renewal.isoformat()}"
                f" — deadline {deadline.isoformat()}"
            ),
            event_at=datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
        )],
    )]


def detect_payment_late(session: Session, account, params: dict, today: date) -> list[Detection]:
    rows = session.execute(text(
        "SELECT source_system, source_record_id, amount_cents, due_at, status"
        " FROM invoice WHERE account_id = :aid AND paid_at IS NULL AND status IN ('open','overdue')"
    ), {"aid": str(account["id"])}).mappings().all()
    detections = []
    for inv in rows:
        days_past_due = (today - inv["due_at"]).days
        if days_past_due < params["medium_days"]:
            continue
        severity = "high" if days_past_due >= params["high_days"] else "medium"
        detections.append(Detection(
            semantic_key=f"invoice:{inv['source_record_id']}",
            severity=severity,
            confidence=1.0,
            magnitude={"days_past_due": days_past_due, "amount_cents": inv["amount_cents"]},
            rationale=(
                f"Invoice {inv['source_record_id']} (${inv['amount_cents'] / 100:,.0f})"
                f" is {days_past_due} days past due"
            ),
            evidence=[EvidenceSpec(
                kind="billing_event",
                source_system=inv["source_system"],
                source_record_id=inv["source_record_id"],
                statement=(
                    f"Invoice {inv['source_record_id']} due {inv['due_at'].isoformat()},"
                    f" unpaid, {days_past_due} days overdue"
                ),
                event_at=datetime.combine(inv["due_at"], datetime.min.time(), tzinfo=timezone.utc),
            )],
        ))
    return detections


def detect_critical_ticket_unresolved(session: Session, account, params: dict, today: date) -> list[Detection]:
    now = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    rows = session.execute(text(
        "SELECT source_system, source_record_id, subject, priority, opened_at, escalated"
        " FROM support_ticket WHERE account_id = :aid AND resolved_at IS NULL"
        " AND status IN ('open','pending') AND priority IN ('high','critical')"
    ), {"aid": str(account["id"])}).mappings().all()
    detections = []
    for t in rows:
        age_hours = (now - t["opened_at"]).total_seconds() / 3600
        if age_hours <= params["sla_hours"]:
            continue
        severity = "critical" if account["tier"] in ("Strategic", "Enterprise") else "high"
        detections.append(Detection(
            semantic_key=f"ticket:{t['source_record_id']}",
            severity=severity,
            confidence=1.0,
            magnitude={"age_days": round(age_hours / 24, 1), "priority": t["priority"], "escalated": t["escalated"]},
            rationale=(
                f"{t['priority'].capitalize()} ticket '{t['subject']}' open"
                f" {age_hours / 24:.0f} days (SLA {params['sla_hours']}h)"
            ),
            evidence=[EvidenceSpec(
                kind="ticket",
                source_system=t["source_system"],
                source_record_id=t["source_record_id"],
                statement=(
                    f"Ticket {t['source_record_id']} ({t['priority']}) opened"
                    f" {t['opened_at'].date().isoformat()}, still unresolved"
                ),
                event_at=t["opened_at"],
            )],
        ))
    return detections


def detect_usage_drop_vs_baseline(session: Session, account, params: dict, today: date) -> list[Detection]:
    # FP prevention (docs/07 U1): never fire on a stale feed — a drop that is
    # really a broken pipeline is a data-quality issue, not a churn signal.
    from ..data_quality import usage_is_fresh

    if not usage_is_fresh(session, str(account["id"]), today):
        return []
    baseline_start = today - timedelta(days=params["baseline_days"])
    observe_start = today - timedelta(days=params["observe_days"])
    rows = session.execute(text(
        "SELECT metric, date, value FROM usage_metric_daily"
        " WHERE account_id = :aid AND date >= :start ORDER BY metric, date"
    ), {"aid": str(account["id"]), "start": baseline_start}).mappings().all()

    by_metric: dict[str, list] = {}
    for r in rows:
        by_metric.setdefault(r["metric"], []).append(r)

    detections = []
    for metric, series in by_metric.items():
        baseline_vals = [float(r["value"]) for r in series if r["date"] < observe_start]
        observe_vals = [float(r["value"]) for r in series if r["date"] >= observe_start]
        if len(baseline_vals) < params["min_history_days"] or not observe_vals:
            continue
        baseline = statistics.median(baseline_vals)
        if baseline < params["min_baseline_value"]:  # denominator floor
            continue
        current = statistics.fmean(observe_vals)
        drop_pct = (baseline - current) / baseline * 100
        if drop_pct < params["drop_threshold_pct"]:
            continue
        self_severity = "medium"
        severity_cfg = params.get("severity") or {}
        if drop_pct >= severity_cfg.get("critical_below_pct", 50):
            self_severity = "critical"
        elif drop_pct >= severity_cfg.get("high_below_pct", 30):
            self_severity = "high"
        detections.append(Detection(
            semantic_key=f"metric:{metric}",
            severity=self_severity,
            confidence=0.94,
            magnitude={
                "metric": metric,
                "baseline": round(baseline, 1),
                "current_14d_mean": round(current, 1),
                "drop_pct": round(drop_pct, 1),
            },
            rationale=(
                f"{metric} down {drop_pct:.0f}% vs {params['baseline_days']}-day baseline"
                f" ({baseline:.0f} → {current:.0f}/day)"
            ),
            evidence=[EvidenceSpec(
                kind="usage_metric",
                source_system="usage_warehouse",
                source_record_id=f"metric:{metric}:{account['id']}",
                statement=(
                    f"{metric}: trailing {params['observe_days']}d mean {current:.0f}/day vs"
                    f" {params['baseline_days']}d baseline {baseline:.0f}/day ({drop_pct:.0f}% drop)"
                ),
                event_at=datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
                content_ref={"window": f"{params['baseline_days']}d", "observe": f"{params['observe_days']}d"},
            )],
        ))
    return detections


def detect_opp_stage_stalled(session: Session, account, params: dict, today: date) -> list[Detection]:
    """O2 — open opportunity stuck in-stage past the norm (from field history)."""
    now = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    rows = session.execute(text(
        "SELECT o.id, o.name, o.stage, o.amount_cents, o.source_record_id,"
        " o.source_system,"
        " (SELECT max(h.changed_at) FROM opportunity_field_history h"
        "   WHERE h.opportunity_id = o.id AND h.field = 'stage') AS last_stage_change"
        " FROM opportunity o WHERE o.account_id = :aid"
        " AND o.stage IS NOT NULL AND lower(o.stage) NOT LIKE '%closed%'"
    ), {"aid": str(account["id"])}).mappings().all()
    detections = []
    for o in rows:
        anchor = o["last_stage_change"]
        if anchor is None:
            continue                            # no history yet → can't age it
        age_days = (now - anchor).days
        if age_days < params["stalled_days"]:
            continue
        high_value = (o["amount_cents"] or 0) >= params["high_value_cents"]
        severity = "high" if high_value else "medium"
        detections.append(Detection(
            semantic_key=f"opp_stage:{o['source_record_id']}",
            severity=severity, confidence=1.0,
            magnitude={"stage": o["stage"], "days_in_stage": age_days,
                       "amount_cents": o["amount_cents"]},
            rationale=(
                f"Opportunity '{o['name']}' has been in stage '{o['stage']}'"
                f" for {age_days} days (norm {params['stalled_days']})"),
            evidence=[EvidenceSpec(
                kind="crm_field", source_system=o["source_system"],
                source_record_id=f"opportunity:{o['source_record_id']}:stage",
                statement=(f"Opportunity {o['source_record_id']} entered stage"
                           f" '{o['stage']}' on {anchor.date().isoformat()}, unchanged since"),
                event_at=anchor)],
        ))
    return detections


def detect_close_date_slip(session: Session, account, params: dict, today: date) -> list[Detection]:
    """O5 — open opportunity whose close date was pushed out >= min_slips times."""
    now = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    window_start = now - timedelta(days=params["window_days"])
    rows = session.execute(text(
        "SELECT o.id, o.name, o.close_date, o.source_record_id, o.source_system,"
        " (SELECT count(*) FROM opportunity_field_history h"
        "   WHERE h.opportunity_id = o.id AND h.field = 'close_date'"
        "   AND h.changed_at >= :ws"
        "   AND (h.new_value IS NULL OR h.old_value IS NULL"
        "        OR h.new_value > h.old_value)) AS slip_count"   # pushed OUT only
        " FROM opportunity o WHERE o.account_id = :aid"
        " AND o.stage IS NOT NULL AND lower(o.stage) NOT LIKE '%closed%'"
    ), {"aid": str(account["id"]), "ws": window_start}).mappings().all()
    detections = []
    for o in rows:
        if (o["slip_count"] or 0) < params["min_slips"]:
            continue
        detections.append(Detection(
            semantic_key=f"opp_slip:{o['source_record_id']}",
            severity="medium", confidence=1.0,
            magnitude={"slip_count": o["slip_count"],
                       "current_close_date": o["close_date"].isoformat() if o["close_date"] else None},
            rationale=(
                f"Opportunity '{o['name']}' close date pushed out {o['slip_count']} times"
                f" in {params['window_days']} days"),
            evidence=[EvidenceSpec(
                kind="crm_field", source_system=o["source_system"],
                source_record_id=f"opportunity:{o['source_record_id']}:close_date",
                statement=(f"Opportunity {o['source_record_id']} close date moved"
                           f" {o['slip_count']} times (last: {o['close_date']})"),
                event_at=now)],
        ))
    return detections


DETECTORS = {
    "detect_renewal_no_plan": detect_renewal_no_plan,
    "detect_notice_period_approaching": detect_notice_period_approaching,
    "detect_payment_late": detect_payment_late,
    "detect_critical_ticket_unresolved": detect_critical_ticket_unresolved,
    "detect_usage_drop_vs_baseline": detect_usage_drop_vs_baseline,
    "detect_opp_stage_stalled": detect_opp_stage_stalled,
    "detect_close_date_slip": detect_close_date_slip,
}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _upsert_evidence(session: Session, tenant_id: str, account_id: str, spec: EvidenceSpec) -> UUID:
    content_hash = hashlib.sha256(
        f"{spec.statement}|{spec.source_system}|{spec.source_record_id}".encode()
    ).hexdigest()
    row = session.execute(text(
        "INSERT INTO evidence_object"
        " (tenant_id, account_id, kind, source_system, source_record_id, statement,"
        "  content_ref, event_at, hash)"
        " VALUES (:tid, :aid, :kind, :src, :rec, :stmt, CAST(:ref AS jsonb), :at, :hash)"
        " ON CONFLICT (tenant_id, kind, source_system, source_record_id, hash)"
        " DO UPDATE SET freshness_at = now()"
        " RETURNING id"
    ), {
        "tid": tenant_id, "aid": account_id, "kind": spec.kind,
        "src": spec.source_system, "rec": spec.source_record_id,
        "stmt": spec.statement, "ref": json.dumps(spec.content_ref),
        "at": spec.event_at, "hash": content_hash,
    }).scalar_one()
    return row


def evaluate_account(
    session: Session,
    tenant_id: UUID | str,
    account_id: UUID | str,
    today: date | None = None,
    registry: dict[str, SignalDefinition] | None = None,
) -> dict:
    """Run all registered detectors for one account. Returns a summary dict."""
    today = today or datetime.now(timezone.utc).date()
    registry = registry or load_registry()
    tenant_id, account_id = str(tenant_id), str(account_id)

    account = session.execute(
        text("SELECT * FROM account WHERE id = :aid AND deleted_at IS NULL"),
        {"aid": account_id},
    ).mappings().one_or_none()
    if account is None:
        raise ValueError(f"account {account_id} not found in tenant context")

    active_keys: set[tuple[str, str]] = set()
    created, updated = 0, 0

    for definition in registry.values():
        detector = DETECTORS[definition.detector]
        for detection in detector(session, account, {**definition.params, "severity": definition.severity}, today):
            active_keys.add((definition.signal, detection.semantic_key))
            result = session.execute(text(
                "INSERT INTO signal"
                " (tenant_id, account_id, signal_type, detector_class, detector_version,"
                "  semantic_key, severity, confidence, magnitude, rationale, requires_review)"
                " VALUES (:tid, :aid, :type, :cls, :ver, :key, :sev, :conf,"
                "         CAST(:mag AS jsonb), :rat, :rev)"
                " ON CONFLICT (tenant_id, account_id, signal_type, semantic_key)"
                " DO UPDATE SET severity = EXCLUDED.severity, confidence = EXCLUDED.confidence,"
                "   magnitude = EXCLUDED.magnitude, rationale = EXCLUDED.rationale,"
                "   state = 'active', occurrence_count = signal.occurrence_count + 1,"
                "   last_evaluated_at = now()"
                " RETURNING id, (occurrence_count = 1) AS is_new"
            ), {
                "tid": tenant_id, "aid": account_id, "type": definition.signal,
                "cls": definition.detector_class, "ver": definition.detector_version,
                "key": detection.semantic_key, "sev": detection.severity,
                "conf": detection.confidence, "mag": json.dumps(detection.magnitude),
                "rat": detection.rationale, "rev": definition.requires_review,
            }).mappings().one()
            signal_id, is_new = result["id"], result["is_new"]
            created += int(is_new)
            updated += int(not is_new)

            for spec in detection.evidence:
                evidence_id = _upsert_evidence(session, tenant_id, account_id, spec)
                session.execute(text(
                    "INSERT INTO evidence_citation"
                    " (tenant_id, evidence_id, claim_owner_type, claim_owner_id, claim_text, claim_class)"
                    " SELECT :tid, :eid, 'signal', :sid, :claim, 'observed_fact'"
                    " WHERE NOT EXISTS (SELECT 1 FROM evidence_citation"
                    "   WHERE tenant_id = :tid AND evidence_id = :eid"
                    "   AND claim_owner_type = 'signal' AND claim_owner_id = :sid)"
                ), {"tid": tenant_id, "eid": str(evidence_id), "sid": str(signal_id),
                    "claim": detection.rationale})

    # Resolve signals that no longer detect (never delete: needed for FN
    # analysis). Scoped to types this engine manages — LLM-derived signals
    # (e.g. negative_sentiment) have their own lifecycle and must not be
    # auto-resolved by detectors that know nothing about them.
    existing = session.execute(text(
        "SELECT id, signal_type, semantic_key FROM signal"
        " WHERE account_id = :aid AND state = 'active'"
        " AND signal_type = ANY(:managed)"
    ), {"aid": account_id, "managed": list(registry.keys())}).mappings().all()
    resolved = 0
    for row in existing:
        if (row["signal_type"], row["semantic_key"]) not in active_keys:
            session.execute(
                text("UPDATE signal SET state = 'resolved', last_evaluated_at = now() WHERE id = :id"),
                {"id": str(row["id"])},
            )
            resolved += 1

    return {"account_id": account_id, "created": created, "updated": updated,
            "resolved": resolved, "active": len(active_keys), "as_of": today.isoformat()}

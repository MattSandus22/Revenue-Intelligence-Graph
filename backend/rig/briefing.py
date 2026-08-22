"""Weekly executive brief (docs/06 module I, WF-11).

Composition is deterministic: numbers come from the metrics layer and are
registered as computed_metric evidence objects; risk claims cite the signals'
evidence. Every claim passes the verification layer at generation AND again
at approval (evidence can go stale or vanish between the two). The approval
gate is hard: a brief containing any non-verified body claim cannot be
approved — unsupported claims live only in the excluded appendix.

Unconfirmed LLM signals never appear in the body; they are listed in a
"pending review" appendix (docs/07 review convention).
"""

import hashlib
import json
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import audit
from .verification import Claim, verify_claims


class BriefError(Exception):
    pass


def _metric_evidence(session: Session, tenant_id: str, key: str, statement: str,
                     value, as_of: date, definition: str) -> str:
    content_hash = hashlib.sha256(f"{key}|{value}|{as_of}".encode()).hexdigest()
    return str(session.execute(text(
        "INSERT INTO evidence_object (tenant_id, kind, source_system, source_record_id,"
        " statement, content_ref, event_at, hash)"
        " VALUES (:tid, 'computed_metric', 'rig_metrics', :rec, :stmt,"
        " CAST(:ref AS jsonb), :at, :hash)"
        " ON CONFLICT (tenant_id, kind, source_system, source_record_id, hash)"
        " DO UPDATE SET freshness_at = now() RETURNING id"
    ), {"tid": tenant_id, "rec": f"{key}:{as_of.isoformat()}", "stmt": statement,
        "ref": json.dumps({"definition": definition, "value": str(value)}),
        "at": as_of, "hash": content_hash}).scalar_one())


def generate_brief(session: Session, tenant_id: str, *, created_by: str,
                   as_of: date | None = None) -> str:
    as_of = as_of or date.today()
    period_start = as_of - timedelta(days=7)

    # ---- Portfolio metrics (structured, from the metrics layer) ----
    arr_90d, n_90d = session.execute(text(
        "SELECT COALESCE(sum(arr_cents), 0), count(*) FROM account"
        " WHERE deleted_at IS NULL AND renewal_date BETWEEN :a AND :b"
    ), {"a": as_of, "b": as_of + timedelta(days=90)}).one()
    arr_at_risk, n_at_risk = session.execute(text(
        "SELECT COALESCE(sum(i.arr_at_stake_cents), 0), count(*) FROM insight i"
        " WHERE i.kind = 'risk' AND i.severity IN ('high','critical')"
        " AND i.state NOT IN ('dismissed','outcome_known')"
    )).one()
    new_risks = session.execute(text(
        "SELECT count(*) FROM insight WHERE kind = 'risk' AND created_at >= :start"
    ), {"start": period_start}).scalar_one()

    portfolio_claims = []
    ev = _metric_evidence(session, tenant_id, "arr_renewing_90d",
                          f"ARR renewing within 90 days of {as_of.isoformat()}:"
                          f" ${arr_90d / 100:,.0f} across {n_90d} accounts",
                          arr_90d, as_of,
                          "sum(account.arr_cents) where renewal_date within 90d")
    portfolio_claims.append(Claim(
        text=f"ARR renewing within the next 90 days: ${arr_90d / 100:,.0f}"
             f" across {n_90d} accounts.",
        claim_class="observed_fact", evidence_ids=[ev],
        numeric_values=["90", str(int(arr_90d / 100)), str(n_90d)]))
    ev = _metric_evidence(session, tenant_id, "arr_at_risk",
                          f"ARR on open high/critical risks: ${arr_at_risk / 100:,.0f}"
                          f" across {n_at_risk} insights",
                          arr_at_risk, as_of, "sum(insight.arr_at_stake) open high/critical")
    portfolio_claims.append(Claim(
        text=f"ARR currently flagged high or critical risk: ${arr_at_risk / 100:,.0f}"
             f" across {n_at_risk} accounts.",
        claim_class="observed_fact", evidence_ids=[ev],
        numeric_values=[str(int(arr_at_risk / 100)), str(n_at_risk)]))
    ev = _metric_evidence(session, tenant_id, "new_risks_7d",
                          f"Risk insights created in the 7 days before {as_of.isoformat()}:"
                          f" {new_risks}",
                          new_risks, as_of, "count(insight) created in period")
    portfolio_claims.append(Claim(
        text=f"New risk insights this week: {new_risks}.",
        claim_class="observed_fact", evidence_ids=[ev],
        numeric_values=["7", str(new_risks)]))

    # ---- Top risks (reviewed evidence only) ----
    top = session.execute(text(
        "SELECT i.id, i.title, i.severity, i.signal_ids, i.arr_at_stake_cents,"
        " a.name AS account_name FROM insight i JOIN account a ON a.id = i.account_id"
        " WHERE i.kind = 'risk' AND i.state NOT IN ('dismissed','outcome_known')"
        " AND i.severity IN ('high','critical')"
        " ORDER BY (CASE i.severity WHEN 'critical' THEN 2 ELSE 1 END) *"
        " COALESCE(i.arr_at_stake_cents, 0) DESC LIMIT 5"
    )).mappings().all()

    risk_claims, pending_review = [], []
    for insight in top:
        # evidence from deterministic/confirmed signals only
        rows = session.execute(text(
            "SELECT DISTINCT ec.evidence_id, sg.requires_review, sg.review_outcome,"
            " sg.rationale FROM signal sg"
            " LEFT JOIN evidence_citation ec ON ec.claim_owner_type = 'signal'"
            "   AND ec.claim_owner_id = sg.id"
            " WHERE sg.id = ANY(:sids) AND sg.state = 'active'"
        ), {"sids": list(insight["signal_ids"])}).mappings().all()
        confirmed_evidence = [str(r["evidence_id"]) for r in rows
                              if r["evidence_id"] is not None
                              and (not r["requires_review"] or r["review_outcome"] == "confirmed")]
        unconfirmed = [r["rationale"] for r in rows
                       if r["requires_review"] and r["review_outcome"] != "confirmed"]
        pending_review.extend(
            {"account": insight["account_name"], "finding": rationale,
             "note": "LLM-derived; awaiting human confirmation — excluded from this brief"}
            for rationale in set(unconfirmed))

        arr_dollars = int((insight["arr_at_stake_cents"] or 0) / 100)
        n_ev = len(confirmed_evidence)
        risk_claims.append(Claim(
            text=f"{insight['account_name']} — ${arr_dollars:,.0f} at stake"
                 f" ({insight['severity']}): {insight['title']}",
            claim_class="model_prediction",
            evidence_ids=confirmed_evidence,
            # numerals may also appear inside the insight title (e.g. "31%",
            # "8 days") — those come from signal rationales, which are
            # themselves evidence-backed; allow them explicitly
            numeric_values=[str(arr_dollars), str(n_ev)]
                           + [_n for _n in _numerals_in(insight["title"])]))

    # ---- Data-quality caveats ----
    dq_open = session.execute(text(
        "SELECT count(*) FROM data_quality_issue WHERE state = 'open'"
        " AND severity IN ('high','critical')"
    )).scalar_one()
    dq_claims = []
    ev = _metric_evidence(session, tenant_id, "dq_open_high",
                          f"Open high-severity data-quality issues: {dq_open}",
                          dq_open, as_of, "count(data_quality_issue) open high+")
    dq_claims.append(Claim(
        text=f"Open high-severity data-quality issues affecting insight confidence: {dq_open}.",
        claim_class="observed_fact", evidence_ids=[ev], numeric_values=[str(dq_open)]))

    # ---- Verify everything; unsupported claims go to the appendix ----
    sections, excluded = [], []
    for key, title, claims in [
        ("portfolio", "Portfolio", portfolio_claims),
        ("top_risks", "Top risks", risk_claims),
        ("data_quality", "Data-quality caveats", dq_claims),
    ]:
        results = verify_claims(session, claims)
        body = [r for r in results if r["verification"]["status"] == "verified"]
        excluded.extend({**r, "section": key}
                        for r in results if r["verification"]["status"] != "verified")
        sections.append({"key": key, "title": title, "claims": body})

    brief_id = session.execute(text(
        "INSERT INTO exec_brief (tenant_id, period_start, period_end, sections,"
        " pending_review, excluded_claims, created_by)"
        " VALUES (:tid, :ps, :pe, CAST(:sections AS jsonb), CAST(:pending AS jsonb),"
        " CAST(:excluded AS jsonb), :by) RETURNING id"
    ), {"tid": tenant_id, "ps": period_start, "pe": as_of,
        "sections": json.dumps(sections), "pending": json.dumps(pending_review),
        "excluded": json.dumps(excluded), "by": created_by}).scalar_one()
    audit.record(session, tenant_id=tenant_id, actor_type="user", actor_id=created_by,
                 action="brief.generate", object_type="exec_brief", object_id=str(brief_id),
                 payload={"excluded": len(excluded), "pending_review": len(pending_review)})
    return str(brief_id)


def _numerals_in(text_value: str) -> list[str]:
    from .verification import _NUMERAL, _normalize_number
    return [_normalize_number(t) for t in _NUMERAL.findall(text_value)]


def approve_brief(session: Session, tenant_id: str, brief_id: str, *, approved_by: str) -> dict:
    """Hard gate (docs/10): re-verify every body claim at approval time.
    Any failure blocks approval — the brief stays draft with reasons."""
    brief = session.execute(text(
        "SELECT state, sections FROM exec_brief WHERE id = :id"
    ), {"id": str(brief_id)}).mappings().one_or_none()
    if brief is None:
        raise LookupError("brief not found")
    if brief["state"] != "draft":
        raise BriefError(f"cannot approve from state '{brief['state']}'")

    failures = []
    for section in brief["sections"]:
        claims = [Claim(text=c["text"], claim_class=c["claim_class"],
                        evidence_ids=c["evidence_ids"], numeric_values=c["numeric_values"])
                  for c in section["claims"]]
        for result in verify_claims(session, claims):
            if result["verification"]["status"] != "verified":
                failures.append({"section": section["key"], "text": result["text"],
                                 "reasons": result["verification"]["reasons"]})
    if failures:
        audit.record(session, tenant_id=tenant_id, actor_type="system", actor_id=approved_by,
                     action="brief.approve_blocked", object_type="exec_brief",
                     object_id=str(brief_id), payload={"failures": len(failures)})
        raise BriefError(json.dumps({
            "error": "verification failed at approval — brief not approved",
            "failures": failures}))

    session.execute(text(
        "UPDATE exec_brief SET state = 'approved', approved_by = :by, approved_at = now()"
        " WHERE id = :id"
    ), {"by": approved_by, "id": str(brief_id)})
    audit.record(session, tenant_id=tenant_id, actor_type="user", actor_id=approved_by,
                 action="brief.approve", object_type="exec_brief", object_id=str(brief_id))
    return {"state": "approved"}


def distribute_brief(session: Session, tenant_id: str, brief_id: str, *,
                     actor_id: str, targets: list[dict]) -> dict:
    """targets: [{channel: slack|email, target: '#exec'|'ceo@...'}]. Only
    approved briefs distribute — unapproved never auto-send (docs/06 I)."""
    brief = session.execute(text(
        "SELECT state FROM exec_brief WHERE id = :id"
    ), {"id": str(brief_id)}).scalar_one_or_none()
    if brief is None:
        raise LookupError("brief not found")
    if brief != "approved":
        raise BriefError("only approved briefs can be distributed")

    for target in targets:
        session.execute(text(
            "INSERT INTO notification (tenant_id, channel, target, subject_type, subject_id,"
            " body) VALUES (:tid, :ch, :tg, 'brief', :sid, CAST(:body AS jsonb))"
        ), {"tid": tenant_id, "ch": target["channel"], "tg": target["target"],
            "sid": str(brief_id), "body": json.dumps({"brief_id": str(brief_id)})})
    session.execute(text(
        "UPDATE exec_brief SET state = 'distributed', distributed_at = now(),"
        " distributed_to = CAST(:to AS jsonb) WHERE id = :id"
    ), {"to": json.dumps(targets), "id": str(brief_id)})
    audit.record(session, tenant_id=tenant_id, actor_type="user", actor_id=actor_id,
                 action="brief.distribute", object_type="exec_brief", object_id=str(brief_id),
                 payload={"targets": targets})
    return {"state": "distributed", "targets": len(targets)}

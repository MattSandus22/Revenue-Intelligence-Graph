"""Executive brief: verified claims only, hard approval gate, distribution."""

from datetime import date

import pytest
from sqlalchemy import text

from rig.briefing import BriefError, approve_brief, distribute_brief, generate_brief
from rig.db import tenant_session
from rig.insights import upsert_risk_insight
from rig.scoring import compute_renewal_risk
from rig.signals.engine import evaluate_account
from rig.verification import Claim, verify_claim

TODAY = date.today()


def _prepare(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        evaluate_account(s, seeded["nsc_tenant"], seeded["acme_account"], today=TODAY)
        score = compute_renewal_risk(s, seeded["nsc_tenant"], seeded["acme_account"], as_of=TODAY)
        upsert_risk_insight(s, seeded["nsc_tenant"], seeded["acme_account"], score)


def test_verification_layer_basics(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        evidence_id = s.execute(text(
            "SELECT id FROM evidence_object LIMIT 1"
        )).scalar_one()
        # verified: evidence exists, number allowed
        status, reasons = verify_claim(s, Claim(
            text="ARR at stake: $120,000.", claim_class="observed_fact",
            evidence_ids=[str(evidence_id)], numeric_values=["120000"]))
        assert status == "verified", reasons
        # blocked: number not in allowlist
        status, reasons = verify_claim(s, Claim(
            text="Retention improved 12% this month.", claim_class="observed_fact",
            evidence_ids=[str(evidence_id)], numeric_values=[]))
        assert status == "unsupported" and any("numeric" in r for r in reasons)


def test_brief_generation_all_body_claims_verified(seeded):
    tid = seeded["nsc_tenant"]
    _prepare(seeded)
    with tenant_session(tid) as s:
        brief_id = generate_brief(s, tid, created_by="u_revops", as_of=TODAY)
        brief = s.execute(text("SELECT * FROM exec_brief WHERE id = :id"),
                          {"id": brief_id}).mappings().one()
    assert brief["state"] == "draft"
    section_keys = [sec["key"] for sec in brief["sections"]]
    assert section_keys == ["portfolio", "top_risks", "data_quality"]
    all_claims = [c for sec in brief["sections"] for c in sec["claims"]]
    assert all_claims, "brief has no claims"
    for claim in all_claims:
        assert claim["verification"]["status"] == "verified"
        assert claim["evidence_ids"], f"uncited body claim: {claim['text']}"
    # Acme appears in top risks with its ARR
    top_risk_text = " ".join(c["text"] for c in brief["sections"][1]["claims"])
    assert "$120,000" in top_risk_text


def test_unconfirmed_llm_findings_go_to_pending_appendix(seeded):
    tid = seeded["nsc_tenant"]
    _prepare(seeded)
    with tenant_session(tid) as s:
        # plant an unconfirmed LLM signal on Acme and rebuild the insight
        s.execute(text(
            "INSERT INTO signal (tenant_id, account_id, signal_type, detector_class,"
            " detector_version, semantic_key, severity, confidence, rationale,"
            " requires_review)"
            " VALUES (:tid, :aid, 'negative_sentiment', 'llm', 't@v1', 'brief-test',"
            " 'high', 0.7, 'Unconfirmed pricing concern from call', true)"
            " ON CONFLICT (tenant_id, account_id, signal_type, semantic_key) DO NOTHING"
        ), {"tid": tid, "aid": seeded["acme_account"]})
        score = compute_renewal_risk(s, tid, seeded["acme_account"], as_of=TODAY)
        upsert_risk_insight(s, tid, seeded["acme_account"], score)
        brief_id = generate_brief(s, tid, created_by="u_revops", as_of=TODAY)
        brief = s.execute(text("SELECT * FROM exec_brief WHERE id = :id"),
                          {"id": brief_id}).mappings().one()
        body_text = " ".join(c["text"] for sec in brief["sections"] for c in sec["claims"])
        pending = brief["pending_review"]
        # cleanup the planted signal for other tests
        s.execute(text(
            "DELETE FROM signal WHERE semantic_key = 'brief-test'"
        ))
    assert "Unconfirmed pricing concern" not in body_text
    assert any("Unconfirmed pricing concern" in p["finding"] for p in pending)


def test_approval_gate_blocks_on_stale_evidence_then_passes(seeded):
    tid = seeded["nsc_tenant"]
    _prepare(seeded)
    with tenant_session(tid) as s:
        brief_id = generate_brief(s, tid, created_by="u_revops", as_of=TODAY)
        # age every cited evidence object beyond the freshness policy
        s.execute(text(
            "UPDATE evidence_object SET freshness_at = now() - interval '30 days'"
        ))
        with pytest.raises(BriefError, match="verification failed"):
            approve_brief(s, tid, brief_id, approved_by="u_vp")
        state = s.execute(text("SELECT state FROM exec_brief WHERE id = :id"),
                          {"id": brief_id}).scalar_one()
        assert state == "draft"

        # evidence refreshed -> approval passes
        s.execute(text("UPDATE evidence_object SET freshness_at = now()"))
        result = approve_brief(s, tid, brief_id, approved_by="u_vp")
        assert result["state"] == "approved"

        # distribution only after approval; creates notification records
        out = distribute_brief(s, tid, brief_id, actor_id="u_vp",
                               targets=[{"channel": "email", "target": "ceo@nsc.example"},
                                        {"channel": "slack", "target": "#exec"}])
        assert out["targets"] == 2
        rows = s.execute(text(
            "SELECT channel FROM notification WHERE subject_type = 'brief'"
            " AND subject_id = :id ORDER BY channel"
        ), {"id": brief_id}).scalars().all()
        assert rows == ["email", "slack"]

        # audit covers generate -> blocked -> approve -> distribute
        actions = s.execute(text(
            "SELECT action FROM audit_event WHERE object_id = :id ORDER BY seq"
        ), {"id": brief_id}).scalars().all()
    assert actions == ["brief.generate", "brief.approve_blocked",
                       "brief.approve", "brief.distribute"]


def test_unapproved_brief_cannot_distribute(seeded):
    tid = seeded["nsc_tenant"]
    _prepare(seeded)
    with tenant_session(tid) as s:
        brief_id = generate_brief(s, tid, created_by="u_revops", as_of=TODAY)
        with pytest.raises(BriefError, match="only approved"):
            distribute_brief(s, tid, brief_id, actor_id="u_vp",
                             targets=[{"channel": "email", "target": "x@y.z"}])

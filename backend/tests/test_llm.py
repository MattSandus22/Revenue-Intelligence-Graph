"""LLM gateway + tasks: schema validation, fail-closed, budgets, run logging,
quote-verbatim anti-hallucination, citation-bound narratives, review gating."""

from datetime import date

import pytest
from sqlalchemy import text

from rig.db import tenant_session
from rig.insights import upsert_risk_insight
from rig.llm.gateway import (LLMBudgetExceeded, LLMGateway, LLMOutputInvalid,
                             LLMResult)
from rig.llm.narrative import generate_insight_narrative
from rig.llm.sentiment import analyze_ticket_sentiment
from rig.scoring import compute_renewal_risk
from rig.signals.engine import evaluate_account

TODAY = date.today()


class FixtureLLMClient:
    """Returns queued responses in order; records calls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, *, system, user, schema):
        self.calls.append({"system": system, "user": user})
        output = self.responses.pop(0)
        return LLMResult(output=output, tokens_in=500, tokens_out=200, model_id="fixture-model")


def _acme_ticket_id(session, seeded):
    return session.execute(text(
        "SELECT id FROM support_ticket WHERE source_record_id = 'ZD-8841'"
    )).scalar_one()


# ---------------------------------------------------------------------------
# Gateway mechanics
# ---------------------------------------------------------------------------

def test_gateway_validates_and_logs(seeded):
    tid = seeded["nsc_tenant"]
    schema = {"type": "object", "required": ["label"], "additionalProperties": False,
              "properties": {"label": {"enum": ["a", "b"]}}}
    gateway = LLMGateway(FixtureLLMClient([{"label": "nope"}, {"label": "a"}]))
    with tenant_session(tid) as s:
        output, run_id = gateway.run(
            s, tid, task="test_task", prompt_version="t@v1",
            system="sys", user="usr", schema=schema)
        assert output == {"label": "a"}
        statuses = s.execute(text(
            "SELECT status FROM ai_model_run WHERE task = 'test_task' ORDER BY created_at"
        )).scalars().all()
    # first attempt invalid, retry ok — both logged
    assert statuses == ["invalid", "ok"]
    assert len(gateway.client.calls) == 2
    assert "failed validation" in gateway.client.calls[1]["user"]


def test_gateway_fails_closed_after_retry(seeded):
    tid = seeded["nsc_tenant"]
    schema = {"type": "object", "required": ["label"], "additionalProperties": False,
              "properties": {"label": {"enum": ["a"]}}}
    gateway = LLMGateway(FixtureLLMClient([{"label": "x"}, {"label": "y"}]))
    with tenant_session(tid) as s:
        with pytest.raises(LLMOutputInvalid):
            gateway.run(s, tid, task="test_fail", prompt_version="t@v1",
                        system="s", user="u", schema=schema)
        statuses = s.execute(text(
            "SELECT status FROM ai_model_run WHERE task = 'test_fail'"
        )).scalars().all()
    assert statuses == ["invalid", "invalid"]


def test_gateway_enforces_budget(seeded):
    tid = seeded["nsc_tenant"]
    gateway = LLMGateway(FixtureLLMClient([{"label": "a"}]))
    with tenant_session(tid) as s:
        s.execute(text(
            "UPDATE tenant SET settings = settings ||"
            " '{\"llm_daily_token_budget\": 1}' WHERE id = :tid"
        ), {"tid": tid})
        # prior tests already spent tokens today, so budget of 1 is exhausted
        with pytest.raises(LLMBudgetExceeded):
            gateway.run(s, tid, task="test_budget", prompt_version="t@v1",
                        system="s", user="u",
                        schema={"type": "object", "properties": {}})
        s.execute(text(
            "UPDATE tenant SET settings = settings - 'llm_daily_token_budget' WHERE id = :tid"
        ), {"tid": tid})


# ---------------------------------------------------------------------------
# Sentiment task (D.1)
# ---------------------------------------------------------------------------

def test_sentiment_rejects_fabricated_quote(seeded):
    tid = seeded["nsc_tenant"]
    fabricated = {"overall": "negative",
                  "aspects": [{"topic": "pricing", "polarity": "negative",
                               "quote": "this text never appeared in the ticket"}]}
    gateway = LLMGateway(FixtureLLMClient([fabricated, fabricated]))
    with tenant_session(tid) as s:
        ticket_id = _acme_ticket_id(s, seeded)
        with pytest.raises(LLMOutputInvalid, match="verbatim"):
            analyze_ticket_sentiment(s, tid, gateway, str(ticket_id))
        # no signal was created from the failed run
        count = s.execute(text(
            "SELECT count(*) FROM signal WHERE signal_type = 'negative_sentiment'"
        )).scalar_one()
    assert count == 0


def test_sentiment_creates_review_gated_signal(seeded):
    tid = seeded["nsc_tenant"]
    # quote is a verbatim substring of the ticket subject
    valid = {"overall": "negative",
             "aspects": [{"topic": "product", "polarity": "negative",
                          "quote": "Carrier-rate sync failing"}]}
    gateway = LLMGateway(FixtureLLMClient([valid]))
    with tenant_session(tid) as s:
        ticket_id = _acme_ticket_id(s, seeded)

        # score before the LLM signal exists
        evaluate_account(s, tid, seeded["acme_account"], today=TODAY)
        before = compute_renewal_risk(s, tid, seeded["acme_account"], as_of=TODAY)

        result = analyze_ticket_sentiment(s, tid, gateway, str(ticket_id))
        assert result["signal_id"] is not None
        signal = s.execute(text(
            "SELECT requires_review, review_outcome, detector_class FROM signal WHERE id = :id"
        ), {"id": result["signal_id"]}).mappings().one()
        assert signal["requires_review"] is True and signal["detector_class"] == "llm"

        # unreviewed LLM signal must NOT move the score
        unreviewed = compute_renewal_risk(s, tid, seeded["acme_account"], as_of=TODAY)
        assert unreviewed["value"] == before["value"]

        # human confirms -> signal now contributes
        s.execute(text(
            "UPDATE signal SET review_outcome = 'confirmed', reviewed_by = 'u_csm',"
            " reviewed_at = now() WHERE id = :id"
        ), {"id": result["signal_id"]})
        confirmed = compute_renewal_risk(s, tid, seeded["acme_account"], as_of=TODAY)
        assert confirmed["value"] > unreviewed["value"]

        # evidence citation exists and is classed as AI interpretation
        claim_class = s.execute(text(
            "SELECT claim_class FROM evidence_citation WHERE claim_owner_id = :id"
        ), {"id": result["signal_id"]}).scalar_one()
    assert claim_class == "ai_interpretation"


# ---------------------------------------------------------------------------
# Narrative task (D.6)
# ---------------------------------------------------------------------------

def test_narrative_is_citation_bound(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        evaluate_account(s, tid, seeded["acme_account"], today=TODAY)
        score = compute_renewal_risk(s, tid, seeded["acme_account"], as_of=TODAY)
        insight_id = upsert_risk_insight(s, tid, seeded["acme_account"], score)

        response = {"sentences": [
            {"sentence": "Usage has declined materially against the account baseline.",
             "evidence_ids": ["E1"]},
            {"sentence": "This sentence has no citation and must be dropped.",
             "evidence_ids": []},
        ]}
        gateway = LLMGateway(FixtureLLMClient([response]))
        result = generate_insight_narrative(s, tid, gateway, str(insight_id))
        assert result["dropped_uncited_sentences"] == 1
        assert "must be dropped" not in result["narrative"]
        assert "[E1]" in result["narrative"]

        narrative_source = s.execute(text(
            "SELECT narrative_source FROM insight WHERE id = :id"
        ), {"id": str(insight_id)}).scalar_one()
    assert narrative_source == "llm"


def test_narrative_rejects_unknown_citation(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        evaluate_account(s, tid, seeded["acme_account"], today=TODAY)
        score = compute_renewal_risk(s, tid, seeded["acme_account"], as_of=TODAY)
        insight_id = upsert_risk_insight(s, tid, seeded["acme_account"], score)
        bad = {"sentences": [{"sentence": "Cites evidence that does not exist in the menu.",
                              "evidence_ids": ["E999"]}]}
        gateway = LLMGateway(FixtureLLMClient([bad, bad]))
        with pytest.raises(LLMOutputInvalid, match="unknown evidence ids"):
            generate_insight_narrative(s, tid, gateway, str(insight_id))
        # deterministic narrative untouched
        source = s.execute(text(
            "SELECT narrative_source FROM insight WHERE id = :id"
        ), {"id": str(insight_id)}).scalar_one()
    assert source in ("deterministic", "llm")  # unchanged by the failed run

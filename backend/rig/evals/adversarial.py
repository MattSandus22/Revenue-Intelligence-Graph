"""Zero-hallucination gate (docs/09 §F: 'any occurrence blocks release').

Adversarial suite: every case simulates a model (or generator) trying to get
fabricated content past the validation/verification layers. A case PASSES
when the system BLOCKS the fabrication. The pytest wrapper asserts
escapes == 0 and runs in CI on every commit — this suite requires no live
LLM, because the property under test is the validators, which are the only
path to users.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from ..llm.gateway import LLMGateway, LLMOutputInvalid, LLMResult
from ..verification import Claim, verify_claim


@dataclass
class CaseResult:
    name: str
    blocked: bool
    detail: str


class _ScriptedClient:
    def __init__(self, output: dict):
        self.output = output

    def complete(self, *, system, user, schema):
        return LLMResult(output=self.output, tokens_in=10, tokens_out=10,
                         model_id="adversary")


def run_suite(session: Session, tenant_id: str, *, acme_ticket_id: str,
              acme_insight_id: str, real_evidence_id: str) -> list[CaseResult]:
    from ..llm.narrative import generate_insight_narrative
    from ..llm.sentiment import analyze_ticket_sentiment

    results: list[CaseResult] = []

    def attempt(name: str, fn):
        try:
            outcome = fn()
        except (LLMOutputInvalid, ValueError) as exc:
            results.append(CaseResult(name, True, f"blocked: {exc}"))
            return
        results.append(CaseResult(name, False, f"ESCAPED: {outcome}"))

    def gateway(output: dict) -> LLMGateway:
        return LLMGateway(_ScriptedClient(output), use_cache=False)

    # 1. Sentiment: fabricated quote (classic hallucinated citation)
    fabricated = {"overall": "very_negative",
                  "aspects": [{"topic": "pricing", "polarity": "negative",
                               "quote": "we are cancelling immediately"}]}
    attempt("sentiment_fabricated_quote", lambda: analyze_ticket_sentiment(
        session, tenant_id, gateway(fabricated), acme_ticket_id))

    # 2. Sentiment: paraphrased quote (near-miss, still not verbatim)
    paraphrase = {"overall": "negative",
                  "aspects": [{"topic": "product", "polarity": "negative",
                               "quote": "the carrier rate sync keeps failing in Europe"}]}
    attempt("sentiment_paraphrased_quote", lambda: analyze_ticket_sentiment(
        session, tenant_id, gateway(paraphrase), acme_ticket_id))

    # 3. Sentiment: schema violation (unknown topic label)
    bad_schema = {"overall": "negative",
                  "aspects": [{"topic": "conspiracy", "polarity": "negative",
                               "quote": "x"}]}
    attempt("sentiment_schema_violation", lambda: analyze_ticket_sentiment(
        session, tenant_id, gateway(bad_schema), acme_ticket_id))

    # 4. Narrative: invented evidence id
    invented = {"sentences": [{"sentence": "The customer signed a competitor contract yesterday.",
                               "evidence_ids": ["E404"]}]}
    attempt("narrative_invented_citation", lambda: generate_insight_narrative(
        session, tenant_id, gateway(invented), acme_insight_id))

    # 5. Narrative: all sentences uncited
    uncited = {"sentences": [{"sentence": "Everything is probably fine at this account.",
                              "evidence_ids": []}]}
    attempt("narrative_all_uncited", lambda: generate_insight_narrative(
        session, tenant_id, gateway(uncited), acme_insight_id))

    # 6. Report claim: number not in the metrics allowlist
    status, reasons = verify_claim(session, Claim(
        text="Churn risk fell 47% this quarter.",
        claim_class="observed_fact", evidence_ids=[real_evidence_id],
        numeric_values=[]))
    results.append(CaseResult("claim_invented_number", status != "verified",
                              f"status={status} reasons={reasons}"))

    # 7. Report claim: nonexistent evidence id
    status, reasons = verify_claim(session, Claim(
        text="The account confirmed renewal.",
        claim_class="observed_fact",
        evidence_ids=["00000000-0000-0000-0000-000000000000"], numeric_values=[]))
    results.append(CaseResult("claim_missing_evidence", status != "verified",
                              f"status={status} reasons={reasons}"))

    # 8. Report claim: no evidence at all
    status, reasons = verify_claim(session, Claim(
        text="Sentiment is improving across the portfolio.",
        claim_class="ai_interpretation", evidence_ids=[], numeric_values=[]))
    results.append(CaseResult("claim_no_evidence", status != "verified",
                              f"status={status} reasons={reasons}"))

    return results

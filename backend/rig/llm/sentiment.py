"""Task D.1 — ticket sentiment classification (docs/09 §D.1).

Anti-hallucination contract: every non-neutral aspect must carry a verbatim
`quote` that appears character-for-character in the input text. The gateway's
content validator enforces it — a fabricated quote fails the run closed.

Resulting `negative_sentiment` signals are LLM-class and `requires_review`:
they are visible to the account owner immediately but excluded from scores
and executive surfaces until a human confirms (docs/07 conventions).
"""

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from .gateway import LLMGateway

PROMPT_VERSION = "ticket_sentiment@v1"

SENTIMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["overall", "aspects"],
    "properties": {
        "overall": {"enum": ["very_negative", "negative", "neutral", "positive", "very_positive"]},
        "aspects": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["topic", "polarity", "quote"],
                "properties": {
                    "topic": {"enum": ["product", "support", "pricing", "relationship",
                                        "roadmap", "other"]},
                    "polarity": {"enum": ["negative", "neutral", "positive"]},
                    "quote": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}

SYSTEM = (
    "You classify the sentiment of B2B customer support conversations. "
    "Classify only what the customer expresses — not the agent. "
    "For every non-neutral aspect, `quote` must be a VERBATIM substring of the "
    "conversation text; never paraphrase inside `quote`. If the text is too "
    "short or ambiguous, return overall neutral with no aspects."
)


def analyze_ticket_sentiment(session: Session, tenant_id: str, gateway: LLMGateway,
                             ticket_id: str) -> dict:
    ticket = session.execute(text(
        "SELECT id, account_id, source_system, source_record_id, subject, opened_at"
        " FROM support_ticket WHERE id = :id"
    ), {"id": str(ticket_id)}).mappings().one_or_none()
    if ticket is None:
        raise LookupError("ticket not found")

    # Conversation text: subject + description from the raw connector payload.
    description = session.execute(text(
        "SELECT payload->>'description' FROM raw_record"
        " WHERE stream = 'tickets' AND source_record_id = :rec"
    ), {"rec": ticket["source_record_id"]}).scalar_one_or_none() or ""
    conversation = f"{ticket['subject']}\n{description}".strip()

    def validate_quotes(output: dict) -> list[str]:
        errors = []
        for i, aspect in enumerate(output.get("aspects", [])):
            if aspect["polarity"] != "neutral" and aspect["quote"] not in conversation:
                errors.append(f"aspects[{i}].quote is not a verbatim substring of the input")
        return errors

    output, run_id = gateway.run(
        session, tenant_id,
        task="ticket_sentiment", prompt_version=PROMPT_VERSION,
        system=SYSTEM, user=conversation, schema=SENTIMENT_SCHEMA,
        validate_content=validate_quotes,
    )

    signal_id = None
    if output["overall"] in ("negative", "very_negative"):
        negative_aspects = [a for a in output["aspects"] if a["polarity"] == "negative"]
        severity = "high" if (output["overall"] == "very_negative"
                              or any(a["topic"] == "pricing" for a in negative_aspects)) else "medium"
        rationale = (
            f"Negative customer sentiment on ticket {ticket['source_record_id']}"
            f" ({', '.join(sorted({a['topic'] for a in negative_aspects})) or 'general'})"
        )
        signal_id = session.execute(text(
            "INSERT INTO signal (tenant_id, account_id, signal_type, detector_class,"
            " detector_version, semantic_key, severity, confidence, magnitude, rationale,"
            " requires_review)"
            " VALUES (:tid, :aid, 'negative_sentiment', 'llm', :ver, :key, :sev, 0.7,"
            " CAST(:mag AS jsonb), :rat, true)"
            " ON CONFLICT (tenant_id, account_id, signal_type, semantic_key)"
            " DO UPDATE SET severity = EXCLUDED.severity, magnitude = EXCLUDED.magnitude,"
            "   rationale = EXCLUDED.rationale, state = 'active',"
            "   occurrence_count = signal.occurrence_count + 1, last_evaluated_at = now()"
            " RETURNING id"
        ), {"tid": tenant_id, "aid": str(ticket["account_id"]), "ver": PROMPT_VERSION,
            "key": f"ticket:{ticket['source_record_id']}", "sev": severity,
            "mag": json.dumps({"overall": output["overall"],
                               "aspects": negative_aspects, "model_run_id": run_id}),
            "rat": rationale}).scalar_one()

        # Evidence: the verbatim quotes, cited to the ticket (claim class:
        # ai_interpretation — this is derived meaning, not an observed fact).
        for aspect in negative_aspects:
            evidence_id = session.execute(text(
                "INSERT INTO evidence_object (tenant_id, account_id, kind, source_system,"
                " source_record_id, statement, content_ref, event_at, hash)"
                " VALUES (:tid, :aid, 'ticket', :src, :rec, :stmt, CAST(:ref AS jsonb),"
                " :at, md5(:stmt))"
                " ON CONFLICT (tenant_id, kind, source_system, source_record_id, hash)"
                " DO UPDATE SET freshness_at = now() RETURNING id"
            ), {"tid": tenant_id, "aid": str(ticket["account_id"]),
                "src": ticket["source_system"], "rec": ticket["source_record_id"],
                "stmt": f"Customer ({aspect['topic']}): \"{aspect['quote']}\"",
                "ref": json.dumps({"model_run_id": run_id}),
                "at": ticket["opened_at"]}).scalar_one()
            session.execute(text(
                "INSERT INTO evidence_citation (tenant_id, evidence_id, claim_owner_type,"
                " claim_owner_id, claim_text, claim_class)"
                " SELECT :tid, :eid, 'signal', :sid, :claim, 'ai_interpretation'"
                " WHERE NOT EXISTS (SELECT 1 FROM evidence_citation WHERE tenant_id = :tid"
                "   AND evidence_id = :eid AND claim_owner_type = 'signal'"
                "   AND claim_owner_id = :sid)"
            ), {"tid": tenant_id, "eid": str(evidence_id), "sid": str(signal_id),
                "claim": rationale})

    return {"overall": output["overall"], "aspects": output["aspects"],
            "signal_id": str(signal_id) if signal_id else None, "model_run_id": run_id}

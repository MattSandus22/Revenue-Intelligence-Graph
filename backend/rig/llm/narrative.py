"""Insight narrative generation with citation binding (docs/09 §D.6, docs/10).

Citation-by-construction: the model receives an enumerated evidence menu
(E1..En) and may only cite those ids. Every sentence must cite at least one
menu id; the content validator rejects unknown ids, and sentences the model
returns without citations are DROPPED (counted, surfaced) — never published.
On any LLM failure the insight keeps its deterministic narrative.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from .gateway import LLMGateway

PROMPT_VERSION = "insight_narrative@v1"

NARRATIVE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sentences"],
    "properties": {
        "sentences": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["sentence", "evidence_ids"],
                "properties": {
                    "sentence": {"type": "string", "minLength": 10},
                    "evidence_ids": {"type": "array",
                                     "items": {"type": "string"}},
                },
            },
        }
    },
}

SYSTEM = (
    "You write concise account-risk narratives for B2B revenue teams. "
    "You are given an evidence menu with ids (E1, E2, ...). Rules: "
    "1) Use ONLY facts from the menu — no outside knowledge, no speculation. "
    "2) Every sentence must cite the ids it draws on in evidence_ids. "
    "3) Never state numbers not present in the menu. "
    "4) Neutral, factual tone; no advice, no causal claims."
)


def generate_insight_narrative(session: Session, tenant_id: str, gateway: LLMGateway,
                               insight_id: str) -> dict:
    insight = session.execute(text(
        "SELECT i.id, i.narrative, i.signal_ids, a.name AS account_name"
        " FROM insight i JOIN account a ON a.id = i.account_id WHERE i.id = :id"
    ), {"id": str(insight_id)}).mappings().one_or_none()
    if insight is None:
        raise LookupError("insight not found")

    citations = session.execute(text(
        "SELECT DISTINCT eo.id, eo.statement FROM evidence_citation ec"
        " JOIN evidence_object eo ON eo.id = ec.evidence_id"
        " WHERE ec.claim_owner_type = 'signal'"
        " AND ec.claim_owner_id = ANY(:sids) ORDER BY eo.statement"
    ), {"sids": list(insight["signal_ids"])}).mappings().all()
    if not citations:
        raise ValueError("insight has no citable evidence; deterministic narrative kept")

    menu = {f"E{i + 1}": row for i, row in enumerate(citations)}
    menu_text = "\n".join(f"{key}: {row['statement']}" for key, row in menu.items())
    user = (
        f"Account: {insight['account_name']}\n\nEvidence menu:\n{menu_text}\n\n"
        "Write a 2-5 sentence risk narrative."
    )

    def validate_citations(output: dict) -> list[str]:
        errors = []
        for i, item in enumerate(output.get("sentences", [])):
            unknown = [e for e in item["evidence_ids"] if e not in menu]
            if unknown:
                errors.append(f"sentences[{i}] cites unknown evidence ids {unknown}")
        return errors

    output, run_id = gateway.run(
        session, tenant_id,
        task="insight_narrative", prompt_version=PROMPT_VERSION,
        system=SYSTEM, user=user, schema=NARRATIVE_SCHEMA,
        validate_content=validate_citations,
    )

    kept, dropped = [], 0
    for item in output["sentences"]:
        if item["evidence_ids"]:
            tags = ",".join(item["evidence_ids"])
            kept.append(f"{item['sentence'].rstrip('.')}. [{tags}]")
        else:
            dropped += 1  # uncited sentence: never published (docs/10 §10.3)

    if not kept:
        raise ValueError("all generated sentences were uncited; deterministic narrative kept")

    narrative = " ".join(kept)
    session.execute(text(
        "UPDATE insight SET narrative = :narr, narrative_source = 'llm',"
        " narrative_model_run_id = :run, updated_at = now() WHERE id = :id"
    ), {"narr": narrative, "run": run_id, "id": str(insight_id)})

    return {"narrative": narrative, "dropped_uncited_sentences": dropped,
            "evidence_menu": {key: str(row["id"]) for key, row in menu.items()},
            "model_run_id": run_id}

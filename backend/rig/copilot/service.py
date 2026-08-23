"""Investigation Copilot (docs/06 module J, WF-18).

Pipeline: parse (LLM → schema-validated filter tuples) → compile (allow-listed
semantic layer) → execute (parameterized, RLS-scoped) → assemble a
deterministic answer with methodology, data gaps, and — for diagnosis —
the full cited score explanation. The LLM parses the question; it never
answers from parametric memory, never writes, never emits SQL.
"""

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import audit
from ..llm.gateway import LLMGateway
from ..scoring import explain_latest
from .semantic import catalog_description, compile_filters, execute_account_query

PROMPT_VERSION = "copilot_parse@v1"

PARSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent", "filters", "unsupported_parts", "clarification_needed"],
    "properties": {
        "intent": {"enum": ["filtered_list", "diagnosis"]},
        "filters": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["field", "op", "value"],
            "properties": {"field": {"type": "string"}, "op": {"type": "string"},
                           "value": {"type": "string"}}}},
        "account_name": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        "unsupported_parts": {"type": "array", "items": {"type": "string"}},
        "clarification_needed": {"type": "boolean"},
    },
}


def _system_prompt() -> str:
    return (
        "You translate revenue-team questions into structured queries against a "
        "fixed catalog. NEVER answer the question yourself, NEVER invent fields.\n"
        "Catalog (field: allowed ops):\n" + catalog_description() + "\n"
        "Rules: 'diagnosis' intent is for 'why is <account> ...' questions — set "
        "account_name. Everything the catalog cannot express goes into "
        "unsupported_parts verbatim. Money values are plain dollar numbers. "
        "If the question is not answerable with this catalog at all, set "
        "clarification_needed=true."
    )


def ask(session: Session, tenant_id: str, gateway: LLMGateway, *,
        question: str, actor_id: str) -> dict:
    parsed, run_id = gateway.run(
        session, tenant_id, task="copilot_parse", prompt_version=PROMPT_VERSION,
        system=_system_prompt(), user=question, schema=PARSE_SCHEMA)

    response: dict
    if parsed["clarification_needed"]:
        response = {
            "intent": "clarification",
            "answer": "I can't answer that from the connected data. I can filter accounts by "
                      "name, ARR, renewal window, segment/tier, lifecycle, plan status, risk "
                      "score, and active signals — or explain why a specific account is at risk.",
            "unsupported_parts": parsed["unsupported_parts"],
        }
    elif parsed["intent"] == "diagnosis":
        response = _diagnose(session, parsed.get("account_name") or question)
    else:
        response = _filtered_list(session, parsed)

    response["model_run_id"] = run_id
    response["disclaimer"] = ("Answer computed from structured, permission-scoped data; "
                              "the language model only parsed the question.")
    audit.record(session, tenant_id=tenant_id, actor_type="user", actor_id=actor_id,
                 action="copilot.ask",
                 payload={"question": question[:500], "intent": response["intent"],
                          "rows": len(response.get("results", [])),
                          "unsupported": response.get("methodology", {}).get("unsupported", [])})
    return response


def _filtered_list(session: Session, parsed: dict) -> dict:
    compiled = compile_filters(parsed["filters"])
    results = execute_account_query(session, compiled, parsed.get("limit") or 50)

    no_score = [r["name"] for r in results if r["risk_score"] is None]
    gaps = []
    if no_score:
        gaps.append(f"{len(no_score)} matching account(s) have no computed risk score yet: "
                    + ", ".join(no_score[:5]))
    unsupported_notes = (
        [f"Not applied (couldn't be expressed): {json.dumps(u)}" for u in compiled.unsupported]
        + [f"Not understood: {part}" for part in parsed["unsupported_parts"]]
    )

    total_arr = sum(r["arr_cents"] or 0 for r in results)
    answer = (f"{len(results)} account(s) match"
              f" (${total_arr / 100:,.0f} combined ARR).")
    if unsupported_notes:
        answer += " Some parts of your question were NOT applied — see methodology."

    return {
        "intent": "filtered_list",
        "answer": answer,
        "results": results,
        "methodology": {
            "applied_filters": compiled.applied,
            "unsupported": unsupported_notes,
            "ordering": "ARR descending",
            "source": "parameterized query via the semantic layer (RLS tenant-scoped)",
        },
        "data_gaps": gaps,
    }


def _diagnose(session: Session, account_name: str) -> dict:
    matches = session.execute(text(
        "SELECT id, name FROM account WHERE deleted_at IS NULL AND name ILIKE :n"
        " ORDER BY length(name) LIMIT 3"
    ), {"n": f"%{account_name}%"}).mappings().all()
    if not matches:
        return {"intent": "diagnosis",
                "answer": f"I couldn't find an account matching '{account_name}'.",
                "results": []}
    if len(matches) > 1:
        return {"intent": "diagnosis",
                "answer": "Multiple accounts match — which one? "
                          + ", ".join(m["name"] for m in matches),
                "results": [dict(m) for m in matches]}

    account = matches[0]
    explanation = explain_latest(session, account["id"])
    if explanation is None:
        return {"intent": "diagnosis",
                "answer": f"{account['name']} has no computed risk score yet — run an "
                          "evaluation or check data coverage.",
                "results": [dict(account)]}

    contributing = [c for c in explanation["components"] if float(c["contribution"]) > 0]
    drivers = "; ".join(
        f"{c['component'].replace('_', ' ')} (+{float(c['contribution']):.0f} pts: {c['rationale']})"
        for c in contributing[:4])
    value = float(explanation["score"]["value"])
    return {
        "intent": "diagnosis",
        "answer": f"{account['name']} scores {value:.0f}/100 renewal risk "
                  f"(higher = riskier). Top drivers: {drivers}",
        "account_id": str(account["id"]),
        "explanation": explanation,
        "results": [],
        "methodology": {
            "source": f"latest persisted score {explanation['score']['score_version']},"
                      " components and citations from the evidence store",
        },
    }

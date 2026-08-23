"""Investigation Copilot: parse→compile→execute pipeline, allow-list safety,
unsupported-part surfacing, diagnosis with citations."""

from datetime import date

from sqlalchemy import text

from rig.copilot.semantic import compile_filters
from rig.copilot.service import ask
from rig.db import tenant_session
from rig.llm.gateway import LLMGateway
from rig.scoring import compute_renewal_risk
from rig.signals.engine import evaluate_account

from .test_llm import FixtureLLMClient

TODAY = date.today()


def _gateway(parse_output: dict) -> LLMGateway:
    return LLMGateway(FixtureLLMClient([parse_output]), use_cache=False)


def _prepare(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        evaluate_account(s, seeded["nsc_tenant"], seeded["acme_account"], today=TODAY)
        compute_renewal_risk(s, seeded["nsc_tenant"], seeded["acme_account"], as_of=TODAY)


def test_filtered_list_matches_direct_query(seeded):
    _prepare(seeded)
    parse = {"intent": "filtered_list", "clarification_needed": False,
             "unsupported_parts": [],
             "filters": [
                 {"field": "arr", "op": "gte", "value": "50000"},
                 {"field": "renewal_date", "op": "within_days", "value": "120"},
                 {"field": "signal", "op": "active", "value": "usage_drop_vs_baseline"},
                 {"field": "plan_status", "op": "ne", "value": "active"},
             ]}
    with tenant_session(seeded["nsc_tenant"]) as s:
        result = ask(s, seeded["nsc_tenant"], _gateway(parse),
                     question="accounts >$50k renewing in 120 days with declining usage and no plan",
                     actor_id="u_analyst")
        names = [r["name"] for r in result["results"]]
        assert any("Acme" in n for n in names)
        assert "BetaWorks Ltd" not in names          # renews far out, plan active
        assert result["methodology"]["applied_filters"] == parse["filters"]
        assert result["methodology"]["unsupported"] == []
        # parity with a hand-built query
        direct = s.execute(text(
            "SELECT count(*) FROM account a WHERE a.deleted_at IS NULL"
            " AND a.arr_cents >= 5000000"
            " AND a.renewal_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 120"
            " AND a.plan_status != 'active'"
            " AND EXISTS (SELECT 1 FROM signal sg WHERE sg.account_id = a.id"
            "   AND sg.signal_type = 'usage_drop_vs_baseline' AND sg.state = 'active'"
            "   AND (sg.requires_review = false OR sg.review_outcome = 'confirmed'))"
        )).scalar_one()
        # audited with the question and row count
        audited = s.execute(text(
            "SELECT payload FROM audit_event WHERE action = 'copilot.ask'"
            " ORDER BY seq DESC LIMIT 1")).scalar_one()
    assert len(result["results"]) == direct
    assert audited["rows"] == direct


def test_unsupported_filters_are_surfaced_not_guessed(seeded):
    _prepare(seeded)
    parse = {"intent": "filtered_list", "clarification_needed": False,
             "unsupported_parts": ["with negative NPS"],
             "filters": [
                 {"field": "csat_score", "op": "lte", "value": "3"},       # unknown field
                 {"field": "signal", "op": "active", "value": "made_up"},  # unknown signal
                 {"field": "arr", "op": "gte", "value": "1000"},
             ]}
    with tenant_session(seeded["nsc_tenant"]) as s:
        result = ask(s, seeded["nsc_tenant"], _gateway(parse),
                     question="accounts over $1k with bad csat and negative NPS",
                     actor_id="u_analyst")
    assert len(result["methodology"]["applied_filters"]) == 1
    assert len(result["methodology"]["unsupported"]) == 3  # 2 compiler + 1 model-declared
    assert "NOT applied" in result["answer"]


def test_diagnosis_returns_cited_explanation(seeded):
    _prepare(seeded)
    parse = {"intent": "diagnosis", "clarification_needed": False,
             "unsupported_parts": [], "filters": [], "account_name": "Acme"}
    with tenant_session(seeded["nsc_tenant"]) as s:
        result = ask(s, seeded["nsc_tenant"], _gateway(parse),
                     question="Why is Acme at risk?", actor_id="u_csm")
    assert result["intent"] == "diagnosis"
    assert "/100 renewal risk" in result["answer"]
    assert "Top drivers" in result["answer"]
    contributing = [c for c in result["explanation"]["components"]
                    if float(c["contribution"]) > 0]
    assert contributing and all(c["citations"] for c in contributing)


def test_diagnosis_unknown_account_is_honest(seeded):
    parse = {"intent": "diagnosis", "clarification_needed": False,
             "unsupported_parts": [], "filters": [], "account_name": "Nonexistent GmbH"}
    with tenant_session(seeded["nsc_tenant"]) as s:
        result = ask(s, seeded["nsc_tenant"], _gateway(parse),
                     question="Why is Nonexistent GmbH at risk?", actor_id="u_csm")
    assert "couldn't find" in result["answer"]


def test_clarification_path(seeded):
    parse = {"intent": "filtered_list", "clarification_needed": True,
             "unsupported_parts": ["forecast our Q4 revenue"], "filters": []}
    with tenant_session(seeded["nsc_tenant"]) as s:
        result = ask(s, seeded["nsc_tenant"], _gateway(parse),
                     question="forecast our Q4 revenue", actor_id="u_csm")
    assert result["intent"] == "clarification"


def test_compiler_rejects_injection_shaped_values(seeded):
    """Values are always bound parameters — a hostile value can't change the
    query shape, and unknown fields/ops never reach SQL at all."""
    compiled = compile_filters([
        {"field": "name", "op": "contains", "value": "'; DROP TABLE account; --"},
        {"field": "arr; DROP TABLE account", "op": "gte", "value": "1"},
    ])
    assert len(compiled.applied) == 1 and len(compiled.unsupported) == 1
    assert compiled.params["p0"] == "%'; DROP TABLE account; --%"
    with tenant_session(seeded["nsc_tenant"]) as s:
        from rig.copilot.semantic import execute_account_query
        rows = execute_account_query(s, compiled, 10)
        assert rows == []
        # table still exists and has rows
        assert s.execute(text("SELECT count(*) FROM account")).scalar_one() > 0

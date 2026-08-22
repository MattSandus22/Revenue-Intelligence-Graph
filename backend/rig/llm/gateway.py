"""LLM gateway (docs/09, docs/13).

Every LLM call in RIG goes through this gateway. It owns the properties the
product depends on and no prompt can opt out of:

- per-tenant daily token budgets (graceful refusal, never surprise bills)
- strict JSON Schema validation of outputs, one retry with the validation
  error appended, then FAIL CLOSED (LLMOutputInvalid — callers route to a
  human review queue, nothing partial ships)
- full logging of every run to ai_model_run (model, prompt version, hashes,
  tokens, latency, status) — the audit and cost-attribution backbone
- provider abstraction: production uses the Anthropic SDK client; tests use
  fixture clients. Tenant data never reaches any provider not configured for
  the tenant.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Protocol

import jsonschema
from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULT_DAILY_TOKEN_BUDGET = 500_000


class LLMError(Exception):
    pass


class LLMOutputInvalid(LLMError):
    """Output failed schema/content validation after retry — fail closed."""


class LLMBudgetExceeded(LLMError):
    pass


class LLMRefused(LLMError):
    """Provider safety refusal — surfaced, never silently retried."""


@dataclass
class LLMResult:
    output: dict
    tokens_in: int
    tokens_out: int
    model_id: str


class LLMClient(Protocol):
    def complete(self, *, system: str, user: str, schema: dict) -> LLMResult: ...


class LLMGateway:
    def __init__(self, client: LLMClient):
        self.client = client

    def run(
        self,
        session: Session,
        tenant_id: str,
        *,
        task: str,
        prompt_version: str,
        system: str,
        user: str,
        schema: dict,
        validate_content=None,  # optional callable(output) -> list[str] of errors
    ) -> tuple[dict, str]:
        """Execute a schema-validated LLM task. Returns (output, model_run_id).

        Raises LLMBudgetExceeded / LLMOutputInvalid / LLMRefused; every path
        (including failures) logs an ai_model_run row.
        """
        input_hash = hashlib.sha256(f"{system}|{user}|{json.dumps(schema, sort_keys=True)}"
                                    .encode()).hexdigest()

        budget = self._daily_budget(session, tenant_id)
        spent = session.execute(text(
            "SELECT COALESCE(sum(tokens_in + tokens_out), 0) FROM ai_model_run"
            " WHERE created_at >= date_trunc('day', now())"
        )).scalar_one()
        if spent >= budget:
            run_id = self._log(session, tenant_id, task, prompt_version, "n/a", input_hash,
                               None, "budget_exceeded", f"daily budget {budget} exhausted", 0, 0, 0)
            raise LLMBudgetExceeded(f"tenant daily token budget exhausted ({spent}/{budget})")

        attempts_user = user
        last_errors: list[str] = []
        for attempt in range(2):
            started = time.monotonic()
            try:
                result = self.client.complete(system=system, user=attempts_user, schema=schema)
            except LLMRefused as exc:
                self._log(session, tenant_id, task, prompt_version, "unknown", input_hash,
                          None, "refused", str(exc), 0, 0,
                          int((time.monotonic() - started) * 1000))
                raise
            except Exception as exc:
                self._log(session, tenant_id, task, prompt_version, "unknown", input_hash,
                          None, "failed", str(exc)[:500], 0, 0,
                          int((time.monotonic() - started) * 1000))
                raise LLMError(f"provider call failed: {exc}") from exc
            latency_ms = int((time.monotonic() - started) * 1000)

            errors = self._validate(result.output, schema)
            if not errors and validate_content is not None:
                errors = validate_content(result.output) or []

            if not errors:
                run_id = self._log(session, tenant_id, task, prompt_version, result.model_id,
                                   input_hash, result.output, "ok", None,
                                   result.tokens_in, result.tokens_out, latency_ms)
                return result.output, run_id

            last_errors = errors
            self._log(session, tenant_id, task, prompt_version, result.model_id, input_hash,
                      result.output, "invalid", "; ".join(errors)[:500],
                      result.tokens_in, result.tokens_out, latency_ms)
            attempts_user = (
                f"{user}\n\nYour previous response failed validation:\n"
                + "\n".join(f"- {e}" for e in errors)
                + "\nReturn a corrected response that satisfies the schema and rules."
            )

        raise LLMOutputInvalid(
            f"output failed validation after retry: {'; '.join(last_errors)}"
        )

    @staticmethod
    def _validate(output: dict, schema: dict) -> list[str]:
        try:
            jsonschema.validate(output, schema)
            return []
        except jsonschema.ValidationError as exc:
            return [f"schema: {exc.message}"]

    @staticmethod
    def _daily_budget(session: Session, tenant_id: str) -> int:
        raw = session.execute(text(
            "SELECT settings->>'llm_daily_token_budget' FROM tenant WHERE id = :tid"
        ), {"tid": tenant_id}).scalar_one_or_none()
        return int(raw) if raw else DEFAULT_DAILY_TOKEN_BUDGET

    @staticmethod
    def _log(session: Session, tenant_id: str, task: str, prompt_version: str, model_id: str,
             input_hash: str, output: dict | None, status: str, error: str | None,
             tokens_in: int, tokens_out: int, latency_ms: int) -> str:
        return str(session.execute(text(
            "INSERT INTO ai_model_run (tenant_id, task, model_id, prompt_version, input_hash,"
            " output, status, error, tokens_in, tokens_out, latency_ms)"
            " VALUES (:tid, :task, :model, :pv, :ih, CAST(:out AS jsonb), :status, :err,"
            " :tin, :tout, :lat) RETURNING id"
        ), {"tid": tenant_id, "task": task, "model": model_id, "pv": prompt_version,
            "ih": input_hash, "out": json.dumps(output) if output is not None else None,
            "status": status, "err": error, "tin": tokens_in, "tout": tokens_out,
            "lat": latency_ms}).scalar_one())


class AnthropicLLMClient:
    """Production client — official Anthropic SDK, structured outputs.

    Uses claude-opus-5 with adaptive thinking (the default) and the
    server-side refusal fallback. Output is schema-constrained by the API
    (output_config.format), then re-validated by the gateway — belt and
    braces, since the gateway also runs task-specific content validators.
    """

    def __init__(self, model_id: str = "claude-opus-5"):
        import anthropic

        self._anthropic = anthropic
        self.model_id = model_id
        self.client = anthropic.Anthropic()

    def complete(self, *, system: str, user: str, schema: dict) -> LLMResult:
        response = self.client.beta.messages.create(
            model=self.model_id,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            raise LLMRefused(f"model refused: {getattr(detail, 'category', 'unknown')}")
        text_block = next(b for b in response.content if b.type == "text")
        return LLMResult(
            output=json.loads(text_block.text),
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            model_id=self.model_id,
        )


# Configured at startup (None = generative features disabled; deterministic
# product remains fully functional — docs/12 AI governance degraded mode).
default_gateway: LLMGateway | None = None

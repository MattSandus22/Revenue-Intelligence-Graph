# RIG Backend — Sprints 1–5 (MVP backend complete)

Implements the Sprint 1–3 scope from [docs/16](../docs/16-mvp-scope-and-build-plan.md):
tenant-isolated Postgres schema, tamper-evident audit log, signal registry +
deterministic engine, explained renewal-risk score, evidence/citation store,
JWT-authenticated API, the Acme Corp demo seed, the connector framework with
HubSpot + Stripe + Zendesk connectors, identity resolution v1 with a human
review queue, CSV usage import with validation reports, data-quality
monitoring v0 (freshness + hygiene, coupled to signal suppression), and the
workbench backend: insight lifecycle state machine, deterministic urgency
ranking, and feedback capture. Sprint 4 adds the approval-gated write-back
framework, the Slack notification layer, and the first LLM slice: a gateway
with schema validation + budgets + full run logging, ticket sentiment
classification (review-gated), and citation-bound insight narratives.

## LLM invariants enforced in code

1. **Every call goes through the gateway** (`rig/llm/gateway.py`): per-tenant
   daily token budgets, strict JSON Schema validation with one retry then
   fail-closed, every run logged to `ai_model_run` (model, prompt version,
   hashes, tokens, status).
2. **Anti-hallucination by construction**: sentiment quotes must be verbatim
   substrings of the input; narratives cite only ids from an enumerated
   evidence menu; uncited sentences are dropped, never published.
3. **LLM signals never affect scores or executive surfaces until a human
   confirms them** (`requires_review` + review endpoint); rejected runs leave
   deterministic outputs untouched.
4. **External writes are approval-gated**: propose (with preview diff) →
   approve → execute (idempotent), audited at every step; rejection is
   terminal.
5. **The executive brief cannot publish an unverified claim**: every claim is
   verified (citation existence, numeric allowlist from the metrics layer,
   claim-class, evidence freshness) at generation AND re-verified at
   approval; unsupported claims live only in the excluded appendix, and
   unconfirmed LLM findings appear only in a pending-review appendix.
6. **Zero-hallucination CI gate** (`tests/test_zero_hallucination_gate.py`):
   an adversarial suite pushes fabricated quotes, invented citations, and
   unbacked numbers at the validators on every commit — any escape fails the
   build. Live-model quality evals live in `rig/evals/model_eval.py`
   (`python -m rig.evals.model_eval`, needs Anthropic credentials) with the
   golden set in `evals/sentiment_golden.jsonl`.

## Layout

```
migrations/0001_init.sql   schema + RLS policies + audit hash-chain triggers
rig/config.py              settings (app vs. admin DB URLs, JWT)
rig/db.py                  tenant_session() — every query runs under app.tenant_id
rig/migrate.py             SQL migration runner + rig_app role bootstrap
rig/auth.py                JWT principals, role→capability map (OIDC-swappable)
rig/audit.py               audit writer + hash-chain verifier
rig/signals/definitions/   versioned YAML signal specs (docs/07 format)
rig/signals/engine.py      detectors + idempotent persistence + evidence binding
rig/scoring.py             renewal_risk@v0.1 — explained, reproducible composite
rig/main.py                FastAPI app (accounts, risk explanation, evaluate,
                           sources, identity review queue)
rig/seed.py                NorthstarCloud/Acme fixtures (docs/20 walkthrough)
rig/resolution.py          identity resolution: explicit→domain→fuzzy ladder,
                           confidence bands, review queue, human accept/reject
rig/connectors/base.py     SyncRunner: sync_run bookkeeping, raw landing,
                           per-stream cursors, failure capture
rig/connectors/hubspot.py  companies/contacts/deals (primary CRM — may mint
                           accounts); HTTP client behind a protocol
rig/connectors/stripe.py   customers/invoices (secondary — defers unmatched
                           records until a human resolves identity)
tests/                     RLS leak gate, audit chain, engine, scoring, API,
                           resolution, connector sync semantics
```

## Identity resolution contract

- Match ladder: explicit source_link → domain (0.98) → fuzzy name.
- ≥0.95 auto-links; 0.70–0.95 queues an `identity_candidate` for human review;
  below that, primary sources (CRM) mint a canonical account, secondary
  sources (billing/support) always queue — they never create accounts.
- Records depending on unresolved identities (e.g. Stripe invoices) are
  **deferred**, not dropped: raw payloads are retained and attach on the next
  sync after a human accepts the candidate.

## Security invariants enforced in code (not convention)

1. **App connects as `rig_app`** — non-superuser, non-owner. Postgres RLS does
   not bind superusers, so app traffic must never use one; migrations use the
   admin URL. `tests/test_rls_isolation.py` is the leak gate: it fails the
   build if any tenant-keyed table lacks FORCE RLS or leaks across tenants,
   and auto-detects new `tenant_id` tables missing from the gate.
2. **Audit log is append-only twice over** — UPDATE/DELETE revoked from
   `rig_app` *and* blocked by trigger; the per-tenant hash chain is computed
   by a DB trigger and re-verifiable via `rig.audit.verify_chain`.
3. **No signal without evidence** — the engine writes `evidence_object` +
   `evidence_citation` rows for every detection; a test fails if any active
   signal has no citation.
4. **No score without explanation** — components carry weight, normalized
   value, signed contribution, rationale, and contributing signal ids;
   insufficient data coverage yields *no score* rather than a fake one.

## Run locally

```bash
docker compose up postgres -d          # or any Postgres 16 on :55432
cd backend && pip install -e ".[dev]"
python -m rig.seed                     # migrate + seed Acme demo tenant
uvicorn rig.main:app --reload
python -m pytest tests/ -q
```

Mint a dev token:

```python
from rig.auth import issue_dev_token
print(issue_dev_token("u_dev", "<tenant-uuid-from-seed>", "leader"))
```

Then:

```
GET  /v1/accounts
GET  /v1/accounts/{id}                       # profile + active signals (audited)
POST /v1/admin/accounts/{id}/evaluate        # run detectors + score
GET  /v1/accounts/{id}/risk                  # score + components + citations
```

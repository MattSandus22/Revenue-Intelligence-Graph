# 23. Implementation Status — Spec Closure

The 22-section specification (docs 01–22) is complete. This addendum closes it
against the working implementation in this repository, records where the
implementation *improved on* the spec, and marks what remains.

## Built and test-enforced (102 tests, CI-gated)

| Spec area | Implementation | Tests |
|---|---|---|
| Tenant isolation (doc 12) | Postgres FORCE RLS on 24 tables, non-superuser `rig_app` role, CI leak gate that auto-detects unregistered `tenant_id` tables | `test_rls_isolation.py` |
| Audit (docs 8, 12) | Append-only (privilege + trigger), per-tenant SHA-256 hash chain computed in-DB, verifier | `test_audit_chain.py` |
| Connectors (doc 11) | Framework (cursors, raw landing, failure capture) + HubSpot, Stripe, Zendesk; encrypted credentials (Fernet, prod-key enforced at boot); create/sync/disconnect/reconnect lifecycle | `test_connectors.py`, `test_zendesk.py`, `test_credentials.py` |
| Identity resolution (doc 6A) | explicit→domain→fuzzy ladder, confidence bands, human review queue, accept/reject | `test_resolution.py` |
| Signals (doc 7) | Registry (YAML, versioned) + 5 detectors, dedup, resolve-on-clear scoped to owned types, stale-feed suppression | `test_signal_engine.py` |
| Scores (doc 9C) | Explained composite w/ segmentable weights, coverage-aware refusal, reproducible inputs hash; LLM signals excluded until confirmed | `test_scoring.py` |
| Workbench (doc 6D) | Insight lifecycle state machine, reason-coded dismissal, urgency ranking with exposed formula, feedback capture | `test_workbench.py` |
| Playbooks/tasks (WF-4) | 3 canned playbooks, state-guarded application, SLA-dated tasks, precision + mitigation-coverage metrics | `test_playbooks.py` |
| Write-backs (WF-19) | propose→approve→execute, preview diff, idempotent replay, terminal rejection, full audit | `test_writeback.py` |
| LLM layer (doc 9D) | Gateway (budgets, schema validation, fail-closed, run registry, cache), sentiment w/ verbatim-quote proof, citation-menu narratives, review gating | `test_llm.py` |
| Evidence & verification (doc 10) | Evidence/citation store, claim classes, numeric-allowlist verifier, brief approval re-verification gate | `test_briefing.py` |
| Zero-hallucination gate (doc 9F) | 8-case adversarial CI suite, zero escapes tolerated | `test_zero_hallucination_gate.py` |
| Copilot (doc 6J) | Allow-listed semantic layer (LLM never emits SQL), unsupported-parts surfacing, cited diagnosis, injection-proof (tested) | `test_copilot.py` |
| Outcomes (WF-15) | Label triple (flagged/lead/intervention), churn taxonomy, surprise-churn FN report, postmortems, calibration progress | `test_outcomes.py` |
| Calibration (doc 9E) | Prior + isotonic PAV fit, **holdout-gated** activation, tenant-scoped versions | `test_calibration.py` |
| Security (doc 12) | Full-branch review in SECURITY.md: traversal fixed+tested, prod-secret boot gate, rate limiting, CSV cap | `test_security.py`, `test_ratelimit.py` |
| Frontend (doc 14) | Workbench, Account 360, Renewals, Brief, Copilot, Integrations, Data Quality; claim-class badges shape+label | CI type-check + build |
| Deployment | Single container (SPA served by API, traversal-safe), boot with prod-config gate + demo seed | smoke-verified |

## Where implementation improved the spec

1. **Calibration gate is holdout-based** (not in doc 9): an in-sample isotonic
   fit can never lose to the prior, so the spec's "must beat baseline" gate
   would have been vacuous. Doc 9's backtest requirement is now interpreted as
   *out-of-sample* Brier comparison.
2. **Engine resolve-on-clear is scoped to registry-owned signal types** —
   the spec's lifecycle didn't anticipate detectors resolving LLM signals
   they don't manage.
3. **Secret-shaped keys are rejected from plaintext connector config** —
   closes an encryption-at-rest bypass the spec's write-up implied but didn't
   mandate.

## Remaining (V1+ per docs 17/22, in priority order)

Salesforce connector · OIDC/SAML via WorkOS (dev JWT is env-gated) · SCIM ·
transcript ingestion (Gong) + D.2/D.3 tasks · four-eyes write-back option ·
signed Slack interaction callbacks · Temporal for sync orchestration ·
`subscription`/`contract` tables (renewals currently derive from
`account.renewal_date` + invoices) · scenario modeling · expansion module.

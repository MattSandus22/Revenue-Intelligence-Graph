# Execution Doc 3 — Data Model Specification

The schema below **is the shipped schema** (`backend/migrations/0001–0009`),
not a proposal — apply it with `python -m rig.migrate`. Conventions first,
then per-entity DDL (abridged to the load-bearing columns; full DDL in the
migration files), then indexing, soft-delete/versioning, and seed data.

## 1. Conventions (every table)

| Convention | Rule |
|---|---|
| PK | `id UUID DEFAULT gen_random_uuid()` |
| Tenancy | `tenant_id UUID NOT NULL` + `FORCE ROW LEVEL SECURITY` policy `tenant_id = current_tenant()`; registered in the CI leak gate |
| Provenance | ingested rows carry `source_system`, `source_record_id`, unique `(tenant_id, source_system, source_record_id)` — the idempotent-upsert key |
| Time | `event_at` (source-world) vs `ingested_at`/`created_at` (ours) — never conflated |
| Actors | principal ids are TEXT (IdP subjects), matching `audit_event.actor_id` |

## 2. Core entities (SQL)

```sql
-- ── Graph spine ────────────────────────────────────────────────────────
account (
  id, tenant_id, name TEXT, domains TEXT[],
  industry, segment, tier, lifecycle_stage DEFAULT 'established',
  arr_cents BIGINT, currency CHAR(3), renewal_date DATE,
  notice_days INT, auto_renew BOOL, plan TEXT,
  plan_status TEXT DEFAULT 'none',          -- none|draft|active (account plan)
  parent_account_id → account, owner_csm_id → app_user,
  attributes JSONB, deleted_at TIMESTAMPTZ  -- soft delete
)
contact (
  id, tenant_id, account_id → account,
  name, email, title, status DEFAULT 'active',  -- active|departed|suspected_departed
  source_system, source_record_id
)
opportunity (
  id, tenant_id, account_id → account,
  name, amount_cents, stage, opp_type,      -- new|renewal|expansion
  close_date, next_step, source_system, source_record_id
)
-- billing facts (subscription: ⏳ migration 0010 — renewals currently derive
-- from account.renewal_date + invoice history)
invoice (
  id, tenant_id, account_id, source_system, source_record_id,
  amount_cents, issued_at, due_at, paid_at, status  -- open|paid|overdue|disputed
)
subscription (            -- ⏳ planned shape
  id, tenant_id, account_id, source_system, source_record_id,
  plan, mrr_cents, period_start, period_end, status, seats INT
)
support_ticket (
  id, tenant_id, account_id, source_system, source_record_id,
  subject, priority,        -- low|normal|high|critical (mapped per connector)
  status, escalated BOOL, opened_at, resolved_at
)
usage_metric_daily (
  id, tenant_id, account_id, metric TEXT, date DATE,
  value NUMERIC, user_count INT,
  UNIQUE (tenant_id, account_id, metric, date)   -- upsert key for CSV/API
)

-- ── Identity resolution ────────────────────────────────────────────────
source_link (entity_type, entity_id, source_system, source_record_id,
             match_method,           -- created|explicit|domain|fuzzy_name|human
             confidence NUMERIC(3,2), status, linked_by TEXT)
identity_candidate (source_system, source_record_id, display JSONB,
             suggested_entity_id, suggested_confidence, match_method,
             status,                 -- pending|accepted|rejected
             resolved_entity_id, resolved_by TEXT, resolved_at)

-- ── Intelligence ───────────────────────────────────────────────────────
signal (
  id, tenant_id, account_id, signal_type,   -- taxonomy id (docs/07)
  detector_class,          -- det|stat|ml|llm|hybrid
  detector_version, semantic_key,           -- dedupe discriminator
  severity, confidence NUMERIC(3,2), magnitude JSONB, rationale TEXT,
  state DEFAULT 'active',  -- active|resolved|snoozed|suppressed (never deleted: FN analysis)
  occurrence_count INT, requires_review BOOL,
  reviewed_by TEXT, reviewed_at, review_outcome,  -- confirmed|rejected
  UNIQUE (tenant_id, account_id, signal_type, semantic_key)
)
evidence_object (
  id, tenant_id, account_id, kind,   -- crm_field|usage_metric|ticket|billing_event|computed_metric
  source_system, source_record_id, statement TEXT,
  content_ref JSONB, event_at, freshness_at, hash,
  UNIQUE (tenant_id, kind, source_system, source_record_id, hash)
)
evidence_citation (
  id, tenant_id, evidence_id → evidence_object,
  claim_owner_type, claim_owner_id,  -- signal|score_change|insight|report_claim
  claim_text, claim_class,           -- observed_fact|model_prediction|ai_interpretation|recommendation
  verification_status DEFAULT 'verified'
)
score (
  id, tenant_id, account_id, score_type, score_version,
  value NUMERIC(5,2), reliability NUMERIC(3,2),   -- coverage-derived
  as_of, inputs_hash,                -- bit-for-bit reproducibility
  UNIQUE (tenant_id, account_id, score_type, as_of)   -- immutable history
)
score_component (score_id →, component, weight, norm_value,
                 contribution NUMERIC(6,3),  -- signed points
                 rationale, evidence_ids UUID[])   -- contributing signal ids
insight (
  id, tenant_id, account_id, kind DEFAULT 'risk',
  title, narrative, severity, confidence, arr_at_stake_cents,
  state DEFAULT 'detected',  -- detected→triaged→accepted|dismissed→in_progress→mitigated|not_mitigated→outcome_known
  state_reason, owner_id, signal_ids UUID[], score_id,
  narrative_source DEFAULT 'deterministic',  -- | llm  (+ narrative_model_run_id)
  outcome, outcome_at
)  -- + UNIQUE partial index: one OPEN risk insight per account
insight_transition (insight_id, from_state, to_state, reason, actor_id, occurred_at)
feedback_event (subject_type, subject_id, verdict,  -- correct|incorrect|useful|not_useful|missing_context|already_known
                comment, user_id)

-- ── Workflow ───────────────────────────────────────────────────────────
playbook (key, name, description, steps JSONB, enabled, version,
          UNIQUE (tenant_id, key))       -- steps: [{title, role, sla_days}]
task (account_id, insight_id, playbook_key, step_index,
      title, assignee_role, assignee_id TEXT, due_date,
      status DEFAULT 'open',             -- open|done|cancelled
      created_by, completed_by, completed_at)
writeback_request (connector_type, operation, target_ref JSONB,
      payload JSONB, preview JSONB,      -- {before, after} diff for approver
      state,        -- proposed→approved→executed|failed ; proposed→rejected
      proposed_by, approved_by, rejected_by, idempotency_key UNIQUE,
      external_result JSONB, insight_id, account_id)
notification (channel, target, subject_type, subject_id, body JSONB,
      status,  -- queued|sent|failed
      sent_at)

-- ── Learning ───────────────────────────────────────────────────────────
renewal_outcome (account_id, outcome,    -- renewed|churned|downgraded
      outcome_date, arr_before_cents, arr_after_cents,
      root_cause_primary,                -- churn taxonomy (docs/06 E)
      root_causes_secondary TEXT[],
      was_flagged BOOL, detection_lead_days INT,
      intervention,                      -- none|partial|completed
      insight_id, recorded_by,
      UNIQUE (tenant_id, account_id, outcome_date))
calibration_model (score_type, version, knots JSONB,  -- isotonic steps
      labels_used, brier_fitted, brier_prior,
      active BOOL,                       -- false when the holdout gate rejected
      fitted_by, UNIQUE (tenant_id, score_type, version))

-- ── Platform ───────────────────────────────────────────────────────────
data_source (type, name, status, config JSONB /* no secrets — enforced */,
             cursors JSONB, UNIQUE (tenant_id, type, name))
sync_run (data_source_id, mode,          -- backfill|incremental
          status, stats JSONB, error, started_at, finished_at)
raw_record (data_source_id, stream, source_record_id, payload JSONB,
            UNIQUE (tenant_id, data_source_id, stream, source_record_id))
integration_credential (data_source_id UNIQUE, ciphertext TEXT, rotated_at)
ai_model_run (task, model_id, prompt_version, input_hash, output JSONB,
              status,  -- ok|cached|invalid|refused|failed|budget_exceeded
              tokens_in, tokens_out, latency_ms)
data_quality_issue (issue_class, severity, dedupe_key UNIQUE-per-tenant,
              title, impact, affected_refs JSONB, state, resolved_at)
exec_brief (period_start, period_end, state,  -- draft|approved|distributed
              sections JSONB, pending_review JSONB, excluded_claims JSONB,
              created_by, approved_by, distributed_to JSONB)
audit_event (…)   -- see execution doc 1 §6: hash-chained, append-only
```

## 3. Indexing strategy

| Index | Serves |
|---|---|
| `account (tenant_id, renewal_date) WHERE deleted_at IS NULL` | Renewal calendar, brief metrics |
| `account (tenant_id, owner_csm_id)` + `gin (tenant_id, domains)` | My-book views; domain identity matching |
| `signal (tenant_id, account_id, state)` + `(tenant_id, severity, state, last_evaluated_at)` | Account drill-down; workbench feeds |
| `insight (tenant_id, state, severity)` + partial `UNIQUE (tenant_id, account_id, kind) WHERE state NOT IN ('dismissed','outcome_known')` | Workbench ranking; one-open-risk invariant |
| `evidence_citation (tenant_id, claim_owner_type, claim_owner_id)` | Evidence cards, explanation assembly |
| `task (tenant_id, insight_id, status)` + `(tenant_id, assignee_id, status)` | Mitigation panel; my-tasks |
| `sync_run (tenant_id, data_source_id, started_at DESC)` | Connector health rollup |
| `ai_model_run (tenant_id, created_at)` | Daily budget window + cache lookups |
| `renewal_outcome (tenant_id, outcome_date DESC)` | Outcomes report |
| `writeback_request (tenant_id, state) WHERE state IN ('proposed','approved')` | Approval queue |
| `data_quality_issue (tenant_id, state) WHERE state='open'` | DQ command center |

**Rules:** `tenant_id` leads every composite index (RLS predicate always
present); partial indexes for hot state filters; add indexes from the staging
slow-query log (wk 11 audit), not speculation.

## 4. Soft delete & versioning

- **Soft delete** only where users can err: `account.deleted_at` (partial
  indexes exclude it). Hard deletes are reserved for the tenant-offboarding
  purge (WF-20) and DSR flows.
- **Never delete, transition instead:** `signal.state='resolved'` (FN
  analysis needs history), insight lifecycle to `outcome_known`,
  `writeback_request` terminal states, `identity_candidate` accepted/rejected.
- **Append-only versioning:** `score` rows are immutable per `as_of` with
  `inputs_hash` for reproducibility; `calibration_model` and `playbook` carry
  integer versions; detector/prompt versions stamped on every signal and
  `ai_model_run`; `audit_event` is the tamper-evident spine.
- **Config versioning:** score-weight changes bump `score_version` and are
  visible in every stored score row — historical scores are never rewritten.

## 5. Seed data for testing

`python -m rig.seed` (or `RIG_DEMO_SEED=1` at boot) creates the NorthstarCloud
tenant reproducing the docs/20 walkthrough **relative to today**, plus an
isolation-fixture tenant:

| Fixture | Values |
|---|---|
| Acme Corp | $120k ARR, renews **+92d**, notice 60d, plan_status `none`, Enterprise tier |
| Invoice INV-2214 | $30,000, **14 days overdue**, 2 dunning attempts (Stripe) |
| Ticket ZD-8841 | critical, escalated, **open 8 days** (Zendesk) |
| Usage `core_actions` | 90 days: baseline ≈412/day → last 14d ≈284/day (**−31%**), user_count 41→29, seeded RNG(42) |
| BetaWorks Ltd | healthy control: renews +300d, plan active, no billing/support/usage → scorer refuses (insufficient coverage) — by design |
| Zenith Corp | second tenant — the cross-tenant leak-gate fixture |

Evaluating Acme yields exactly the walkthrough: 6 deterministic signals,
risk ≈72/100 with 5 cited components, P(non-renewal) ≈0.49 under the prior.
The synthetic 60-label calibration tenant is generated in
`tests/test_calibration.py::_synthetic_labeled_tenant` for learning-loop tests.

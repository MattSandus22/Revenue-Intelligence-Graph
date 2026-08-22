-- 0003: insight lifecycle (workbench), feedback capture, data-quality issues.

CREATE TABLE insight (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          UUID NOT NULL REFERENCES tenant(id),
  account_id         UUID NOT NULL REFERENCES account(id),
  kind               TEXT NOT NULL DEFAULT 'risk',   -- risk | opportunity | data_quality
  title              TEXT NOT NULL,
  narrative          TEXT NOT NULL,
  severity           TEXT NOT NULL,
  confidence         NUMERIC(3,2) NOT NULL,
  arr_at_stake_cents BIGINT,
  state              TEXT NOT NULL DEFAULT 'detected',
  -- detected -> triaged -> accepted|dismissed ; accepted -> in_progress ->
  -- mitigated|not_mitigated ; * -> outcome_known  (docs/06 D)
  state_reason       TEXT,
  owner_id           UUID,
  signal_ids         UUID[] NOT NULL DEFAULT '{}',
  score_id           UUID,
  outcome            TEXT,
  outcome_at         TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_insight_workbench ON insight (tenant_id, state, severity);
-- one open risk insight per account (closed ones keep history)
CREATE UNIQUE INDEX uq_insight_open_risk ON insight (tenant_id, account_id, kind)
  WHERE state NOT IN ('dismissed', 'outcome_known');

CREATE TABLE insight_transition (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL REFERENCES tenant(id),
  insight_id  UUID NOT NULL REFERENCES insight(id),
  from_state  TEXT NOT NULL,
  to_state    TEXT NOT NULL,
  reason      TEXT,
  actor_id    TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE feedback_event (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL REFERENCES tenant(id),
  subject_type TEXT NOT NULL,     -- insight | signal | answer | report
  subject_id   UUID NOT NULL,
  verdict      TEXT NOT NULL,     -- correct | incorrect | useful | not_useful |
                                  -- missing_context | already_known
  comment      TEXT,
  user_id      TEXT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_feedback_subject ON feedback_event (tenant_id, subject_type, subject_id);

CREATE TABLE data_quality_issue (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID NOT NULL REFERENCES tenant(id),
  issue_class    TEXT NOT NULL,   -- freshness | missing_field | orphaned_record | mismatch
  severity       TEXT NOT NULL,
  dedupe_key     TEXT NOT NULL,   -- e.g. 'freshness:usage', 'missing_field:account:<id>:renewal_date'
  title          TEXT NOT NULL,
  impact         TEXT NOT NULL,
  affected_refs  JSONB NOT NULL DEFAULT '{}',
  state          TEXT NOT NULL DEFAULT 'open',   -- open | resolved
  assignee_id    UUID,
  detected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at    TIMESTAMPTZ,
  UNIQUE (tenant_id, dedupe_key)
);
CREATE INDEX idx_dq_open ON data_quality_issue (tenant_id, state) WHERE state = 'open';

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'insight','insight_transition','feedback_event','data_quality_issue'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant())', t);
  END LOOP;
END $$;

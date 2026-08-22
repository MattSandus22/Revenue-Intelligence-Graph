-- 0004: write-back framework, notifications, AI model-run registry,
--       LLM-generated narrative provenance on insights.

CREATE TABLE writeback_request (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenant(id),
  connector_type   TEXT NOT NULL,            -- hubspot | salesforce | ...
  operation        TEXT NOT NULL,            -- create_task | update_field
  target_ref       JSONB NOT NULL,           -- {object_type, source_record_id?} or {create: true}
  payload          JSONB NOT NULL,           -- exact fields to be written
  preview          JSONB NOT NULL,           -- {before, after} diff shown to approver
  state            TEXT NOT NULL DEFAULT 'proposed',
  -- proposed -> approved -> executed | failed ; proposed -> rejected
  proposed_by      TEXT NOT NULL,
  approved_by      TEXT,
  rejected_by      TEXT,
  reject_reason    TEXT,
  idempotency_key  TEXT NOT NULL,
  external_result  JSONB,                    -- e.g. {id: <hubspot task id>}
  error            TEXT,
  insight_id       UUID,
  account_id       UUID,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  approved_at      TIMESTAMPTZ,
  executed_at      TIMESTAMPTZ,
  UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX idx_writeback_pending ON writeback_request (tenant_id, state)
  WHERE state IN ('proposed', 'approved');

CREATE TABLE notification (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL REFERENCES tenant(id),
  channel      TEXT NOT NULL,               -- slack | email
  target       TEXT NOT NULL,               -- channel id / address
  subject_type TEXT NOT NULL,
  subject_id   UUID NOT NULL,
  body         JSONB NOT NULL,
  status       TEXT NOT NULL DEFAULT 'queued',   -- queued | sent | failed
  error        TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  sent_at      TIMESTAMPTZ
);
CREATE INDEX idx_notification_subject ON notification (tenant_id, subject_type, subject_id);

-- Every LLM invocation is registered: model, prompt version, hashes, tokens,
-- validation status. This is the audit + cost-attribution backbone (docs/09).
CREATE TABLE ai_model_run (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID NOT NULL REFERENCES tenant(id),
  task           TEXT NOT NULL,             -- ticket_sentiment | insight_narrative | ...
  model_id       TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  input_hash     TEXT NOT NULL,
  output         JSONB,
  status         TEXT NOT NULL,             -- ok | invalid | refused | failed | budget_exceeded
  error          TEXT,
  tokens_in      INT NOT NULL DEFAULT 0,
  tokens_out     INT NOT NULL DEFAULT 0,
  latency_ms     INT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_model_run_budget ON ai_model_run (tenant_id, created_at);

ALTER TABLE insight ADD COLUMN narrative_source TEXT NOT NULL DEFAULT 'deterministic';
ALTER TABLE insight ADD COLUMN narrative_model_run_id UUID;

-- human review of LLM-derived signals (docs/07 conventions); reviewer ids are
-- principal subject strings, matching audit_event.actor_id
ALTER TABLE signal ADD COLUMN reviewed_by TEXT;
ALTER TABLE signal ADD COLUMN reviewed_at TIMESTAMPTZ;
ALTER TABLE signal ADD COLUMN review_outcome TEXT;  -- confirmed | rejected

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['writeback_request','notification','ai_model_run'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant())', t);
  END LOOP;
END $$;

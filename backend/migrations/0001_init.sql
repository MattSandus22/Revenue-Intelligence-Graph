-- 0001_init: core schema, tenant isolation (RLS), tamper-evident audit log.
-- Conventions per docs/08-data-model-and-graph.md.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Tenancy & identity
-- ---------------------------------------------------------------------------
CREATE TABLE tenant (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  region      TEXT NOT NULL DEFAULT 'us',
  settings    JSONB NOT NULL DEFAULT '{}',
  status      TEXT NOT NULL DEFAULT 'active',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE app_user (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL REFERENCES tenant(id),
  email       TEXT NOT NULL,
  name        TEXT NOT NULL,
  role        TEXT NOT NULL DEFAULT 'contributor',
  -- roles: org_admin | data_admin | model_admin | leader | contributor | analyst | exec_readonly | audit_viewer
  status      TEXT NOT NULL DEFAULT 'active',
  idp_subject TEXT,
  last_login_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email)
);

-- ---------------------------------------------------------------------------
-- Accounts & source facts (Sprint-1 minimal surface)
-- ---------------------------------------------------------------------------
CREATE TABLE account (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL REFERENCES tenant(id),
  name            TEXT NOT NULL,
  domains         TEXT[] NOT NULL DEFAULT '{}',
  industry        TEXT,
  segment         TEXT,
  tier            TEXT,
  lifecycle_stage TEXT NOT NULL DEFAULT 'established',
  arr_cents       BIGINT,
  currency        CHAR(3) NOT NULL DEFAULT 'USD',
  renewal_date    DATE,
  notice_days     INT,
  auto_renew      BOOLEAN NOT NULL DEFAULT false,
  plan            TEXT,
  plan_status     TEXT NOT NULL DEFAULT 'none',  -- none | draft | active (account plan)
  parent_account_id UUID REFERENCES account(id),
  owner_csm_id    UUID REFERENCES app_user(id),
  attributes      JSONB NOT NULL DEFAULT '{}',
  deleted_at      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_account_tenant_renewal ON account (tenant_id, renewal_date) WHERE deleted_at IS NULL;

CREATE TABLE invoice (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenant(id),
  account_id       UUID NOT NULL REFERENCES account(id),
  source_system    TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  amount_cents     BIGINT NOT NULL,
  issued_at        DATE NOT NULL,
  due_at           DATE NOT NULL,
  paid_at          DATE,
  status           TEXT NOT NULL,  -- open | paid | overdue | disputed
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, source_system, source_record_id)
);

CREATE TABLE support_ticket (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenant(id),
  account_id       UUID NOT NULL REFERENCES account(id),
  source_system    TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  subject          TEXT NOT NULL,
  priority         TEXT NOT NULL,   -- low | normal | high | critical
  status           TEXT NOT NULL,   -- open | pending | solved | closed
  escalated        BOOLEAN NOT NULL DEFAULT false,
  opened_at        TIMESTAMPTZ NOT NULL,
  resolved_at      TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, source_system, source_record_id)
);

CREATE TABLE usage_metric_daily (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL REFERENCES tenant(id),
  account_id  UUID NOT NULL REFERENCES account(id),
  metric      TEXT NOT NULL,
  date        DATE NOT NULL,
  value       NUMERIC NOT NULL,
  user_count  INT,
  UNIQUE (tenant_id, account_id, metric, date)
);

-- ---------------------------------------------------------------------------
-- Signals, evidence, scores
-- ---------------------------------------------------------------------------
CREATE TABLE signal (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID NOT NULL REFERENCES tenant(id),
  account_id        UUID NOT NULL REFERENCES account(id),
  signal_type       TEXT NOT NULL,
  detector_class    TEXT NOT NULL,   -- det | stat | ml | llm | hybrid
  detector_version  TEXT NOT NULL,
  semantic_key      TEXT NOT NULL,
  severity          TEXT NOT NULL,   -- info | low | medium | high | critical
  confidence        NUMERIC(3,2) NOT NULL,
  magnitude         JSONB NOT NULL DEFAULT '{}',
  rationale         TEXT NOT NULL,
  state             TEXT NOT NULL DEFAULT 'active',  -- active | resolved | snoozed | suppressed
  occurrence_count  INT NOT NULL DEFAULT 1,
  requires_review   BOOLEAN NOT NULL DEFAULT false,
  first_detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, account_id, signal_type, semantic_key)
);
CREATE INDEX idx_signal_tenant_account ON signal (tenant_id, account_id, state);

CREATE TABLE evidence_object (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenant(id),
  account_id       UUID REFERENCES account(id),
  kind             TEXT NOT NULL,  -- crm_field | usage_metric | ticket | billing_event | computed_metric
  source_system    TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  statement        TEXT NOT NULL,
  content_ref      JSONB NOT NULL DEFAULT '{}',
  event_at         TIMESTAMPTZ NOT NULL,
  ingested_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  freshness_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  hash             TEXT NOT NULL,
  UNIQUE (tenant_id, kind, source_system, source_record_id, hash)
);

CREATE TABLE evidence_citation (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenant(id),
  evidence_id      UUID NOT NULL REFERENCES evidence_object(id),
  claim_owner_type TEXT NOT NULL,  -- signal | score_change | insight | report_claim | answer
  claim_owner_id   UUID NOT NULL,
  claim_text       TEXT NOT NULL,
  claim_class      TEXT NOT NULL,  -- observed_fact | model_prediction | ai_interpretation | recommendation
  verification_status TEXT NOT NULL DEFAULT 'verified',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_citation_owner ON evidence_citation (tenant_id, claim_owner_type, claim_owner_id);

CREATE TABLE score (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES tenant(id),
  account_id    UUID NOT NULL REFERENCES account(id),
  score_type    TEXT NOT NULL,
  score_version TEXT NOT NULL,
  value         NUMERIC(5,2) NOT NULL,
  reliability   NUMERIC(3,2) NOT NULL DEFAULT 1.0,
  as_of         TIMESTAMPTZ NOT NULL DEFAULT now(),
  inputs_hash   TEXT NOT NULL,
  UNIQUE (tenant_id, account_id, score_type, as_of)
);

CREATE TABLE score_component (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL REFERENCES tenant(id),
  score_id     UUID NOT NULL REFERENCES score(id) ON DELETE CASCADE,
  component    TEXT NOT NULL,
  weight       NUMERIC(5,4) NOT NULL,
  norm_value   NUMERIC(5,4) NOT NULL,
  contribution NUMERIC(6,3) NOT NULL,
  rationale    TEXT NOT NULL DEFAULT '',
  evidence_ids UUID[] NOT NULL DEFAULT '{}'
);

-- ---------------------------------------------------------------------------
-- Tamper-evident audit log (append-only, per-tenant hash chain)
-- ---------------------------------------------------------------------------
CREATE TABLE audit_event (
  seq         BIGSERIAL PRIMARY KEY,
  id          UUID NOT NULL DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL,
  actor_type  TEXT NOT NULL,   -- user | system | connector | model
  actor_id    TEXT NOT NULL,
  action      TEXT NOT NULL,
  object_type TEXT,
  object_id   TEXT,
  payload     JSONB NOT NULL DEFAULT '{}',
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  prev_hash   TEXT NOT NULL,
  hash        TEXT NOT NULL
);
CREATE INDEX idx_audit_tenant_time ON audit_event (tenant_id, occurred_at);

-- Chain computation in-database so integrity does not depend on app code.
CREATE OR REPLACE FUNCTION audit_event_chain() RETURNS trigger AS $$
DECLARE
  last_hash TEXT;
BEGIN
  -- serialize chain appends per tenant
  PERFORM pg_advisory_xact_lock(hashtext(NEW.tenant_id::text));
  SELECT hash INTO last_hash FROM audit_event
   WHERE tenant_id = NEW.tenant_id ORDER BY seq DESC LIMIT 1;
  NEW.prev_hash := COALESCE(last_hash, 'genesis');
  NEW.hash := encode(sha256(convert_to(
      NEW.prev_hash || '|' || NEW.tenant_id::text || '|' || NEW.actor_type || '|' ||
      NEW.actor_id || '|' || NEW.action || '|' || COALESCE(NEW.object_type,'') || '|' ||
      COALESCE(NEW.object_id,'') || '|' || NEW.payload::text || '|' || NEW.occurred_at::text,
      'UTF8')), 'hex');
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_chain BEFORE INSERT ON audit_event
  FOR EACH ROW EXECUTE FUNCTION audit_event_chain();

CREATE OR REPLACE FUNCTION audit_event_block_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_event is append-only';
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_no_update BEFORE UPDATE OR DELETE ON audit_event
  FOR EACH ROW EXECUTE FUNCTION audit_event_block_mutation();

-- ---------------------------------------------------------------------------
-- Row-level security: tenant isolation on EVERY tenant-scoped table.
-- FORCE ensures even the table owner is subject to policies, so tests and
-- migrations cannot silently bypass isolation.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION current_tenant() RETURNS uuid AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$ LANGUAGE sql STABLE;

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'app_user','account','invoice','support_ticket','usage_metric_daily',
    'signal','evidence_object','evidence_citation','score','score_component','audit_event'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant())', t);
  END LOOP;
END $$;

-- tenant table: a session may only see its own tenant row.
ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_self ON tenant USING (id = current_tenant()) WITH CHECK (id = current_tenant());

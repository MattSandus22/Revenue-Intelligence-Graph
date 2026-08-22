-- 0002: connector framework (data sources, sync runs, raw landing),
--       identity resolution (source links, review queue), contacts, opportunities.

CREATE TABLE data_source (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL REFERENCES tenant(id),
  type        TEXT NOT NULL,            -- hubspot | stripe | zendesk | csv_usage
  name        TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'active',  -- active | paused | action_required | disconnected
  config      JSONB NOT NULL DEFAULT '{}',     -- field-mapping overrides etc. (no secrets)
  cursors     JSONB NOT NULL DEFAULT '{}',     -- per-stream incremental watermarks
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, type, name)
);

CREATE TABLE sync_run (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID NOT NULL REFERENCES tenant(id),
  data_source_id UUID NOT NULL REFERENCES data_source(id),
  mode           TEXT NOT NULL,          -- backfill | incremental
  status         TEXT NOT NULL DEFAULT 'running',  -- running | succeeded | failed
  stats          JSONB NOT NULL DEFAULT '{}',
  error          TEXT,
  started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at    TIMESTAMPTZ
);
CREATE INDEX idx_sync_run_source ON sync_run (tenant_id, data_source_id, started_at DESC);

-- Latest raw payload per source record. Replayability-lite: production adds an
-- immutable object-store landing zone (docs/13); this table lets us re-run
-- normalization without re-fetching.
CREATE TABLE raw_record (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenant(id),
  data_source_id   UUID NOT NULL REFERENCES data_source(id),
  stream           TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  payload          JSONB NOT NULL,
  fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, data_source_id, stream, source_record_id)
);

CREATE TABLE contact (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenant(id),
  account_id       UUID REFERENCES account(id),
  name             TEXT NOT NULL,
  email            TEXT,
  title            TEXT,
  status           TEXT NOT NULL DEFAULT 'active',  -- active | departed | suspected_departed
  source_system    TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, source_system, source_record_id)
);
CREATE INDEX idx_contact_account ON contact (tenant_id, account_id);

CREATE TABLE opportunity (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenant(id),
  account_id       UUID REFERENCES account(id),
  name             TEXT NOT NULL,
  amount_cents     BIGINT,
  stage            TEXT,
  opp_type         TEXT NOT NULL DEFAULT 'new',   -- new | renewal | expansion
  close_date       DATE,
  next_step        TEXT,
  source_system    TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, source_system, source_record_id)
);
CREATE INDEX idx_opportunity_account ON opportunity (tenant_id, account_id);

-- Identity resolution results: which source records map to which canonical entity.
CREATE TABLE source_link (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenant(id),
  entity_type      TEXT NOT NULL,        -- account | contact
  entity_id        UUID NOT NULL,
  source_system    TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  match_method     TEXT NOT NULL,        -- created | explicit | domain | fuzzy_name | human
  confidence       NUMERIC(3,2) NOT NULL,
  status           TEXT NOT NULL DEFAULT 'linked',   -- linked | rejected
  linked_by        TEXT,                 -- principal id when human
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, source_system, source_record_id, entity_type)
);
CREATE INDEX idx_source_link_entity ON source_link (tenant_id, entity_type, entity_id);

-- Human review queue for ambiguous matches (0.70–0.95 confidence band).
CREATE TABLE identity_candidate (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            UUID NOT NULL REFERENCES tenant(id),
  entity_type          TEXT NOT NULL,
  source_system        TEXT NOT NULL,
  source_record_id     TEXT NOT NULL,
  display              JSONB NOT NULL,   -- {name, domain, email} for reviewer
  suggested_entity_id  UUID,             -- best match, if any
  suggested_confidence NUMERIC(3,2),
  match_method         TEXT,
  status               TEXT NOT NULL DEFAULT 'pending',  -- pending | accepted | rejected
  resolved_entity_id   UUID,
  resolved_by          TEXT,
  resolved_at          TIMESTAMPTZ,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, source_system, source_record_id, entity_type)
);
CREATE INDEX idx_identity_candidate_pending
  ON identity_candidate (tenant_id, status) WHERE status = 'pending';

-- RLS on all new tenant-scoped tables (same policy as 0001).
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'data_source','sync_run','raw_record','contact','opportunity',
    'source_link','identity_candidate'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant())', t);
  END LOOP;
END $$;

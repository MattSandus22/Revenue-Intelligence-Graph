-- 0010: opportunity field history (Salesforce field-history feed) — powers the
-- stage-stalled (O2) and close-date-slip (O5) deterministic signals.

ALTER TABLE opportunity ADD COLUMN forecast_category TEXT;   -- omitted | pipeline | best_case | commit | closed
ALTER TABLE opportunity ADD COLUMN owner_ref TEXT;           -- source owner id (for multi-threading later)

CREATE TABLE opportunity_field_history (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenant(id),
  opportunity_id   UUID NOT NULL REFERENCES opportunity(id),
  field            TEXT NOT NULL,          -- stage | close_date | amount | forecast_category
  old_value        TEXT,
  new_value        TEXT,
  changed_at       TIMESTAMPTZ NOT NULL,
  source_system    TEXT NOT NULL,
  source_record_id TEXT NOT NULL,          -- provider history row id (idempotency)
  UNIQUE (tenant_id, source_system, source_record_id)
);
CREATE INDEX idx_opp_history ON opportunity_field_history (tenant_id, opportunity_id, field, changed_at);

ALTER TABLE opportunity_field_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE opportunity_field_history FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON opportunity_field_history
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());

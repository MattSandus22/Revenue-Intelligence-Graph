-- 0008: renewal outcomes — the labels that close the learning loop (WF-15).

CREATE TABLE renewal_outcome (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             UUID NOT NULL REFERENCES tenant(id),
  account_id            UUID NOT NULL REFERENCES account(id),
  outcome               TEXT NOT NULL,      -- renewed | churned | downgraded
  outcome_date          DATE NOT NULL,
  arr_before_cents      BIGINT,
  arr_after_cents       BIGINT,
  source                TEXT NOT NULL DEFAULT 'manual',   -- manual | crm | billing
  root_cause_primary    TEXT,               -- churn-reason taxonomy (docs/06 E)
  root_causes_secondary TEXT[] NOT NULL DEFAULT '{}',
  notes                 TEXT,
  -- label fields for calibration / FN accounting (docs/09 C, F)
  was_flagged           BOOLEAN NOT NULL,   -- any high+ risk insight existed pre-outcome
  detection_lead_days   INT,                -- insight created -> outcome date (flagged only)
  intervention          TEXT NOT NULL,      -- none | partial | completed
  insight_id            UUID,               -- the risk insight this closes, if any
  recorded_by           TEXT NOT NULL,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, account_id, outcome_date)
);
CREATE INDEX idx_outcome_tenant ON renewal_outcome (tenant_id, outcome_date DESC);

ALTER TABLE renewal_outcome ENABLE ROW LEVEL SECURITY;
ALTER TABLE renewal_outcome FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON renewal_outcome
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());

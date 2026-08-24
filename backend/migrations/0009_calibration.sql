-- 0009: fitted calibration models (docs/09 §C, §E progressive calibration).

CREATE TABLE calibration_model (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES tenant(id),
  score_type    TEXT NOT NULL,
  version       INT NOT NULL,
  knots         JSONB NOT NULL,      -- [[score, p], ...] isotonic step function
  labels_used   INT NOT NULL,
  brier_fitted  NUMERIC(6,4) NOT NULL,
  brier_prior   NUMERIC(6,4) NOT NULL,
  active        BOOLEAN NOT NULL,    -- false when the gate rejected activation
  fitted_by     TEXT NOT NULL,
  fitted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, score_type, version)
);

ALTER TABLE calibration_model ENABLE ROW LEVEL SECURITY;
ALTER TABLE calibration_model FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON calibration_model
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());

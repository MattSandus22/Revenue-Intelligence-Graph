-- 0005: executive briefs (docs/06 module I, docs/10 verification gate).

CREATE TABLE exec_brief (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL REFERENCES tenant(id),
  period_start    DATE NOT NULL,
  period_end      DATE NOT NULL,
  state           TEXT NOT NULL DEFAULT 'draft',   -- draft | approved | distributed
  sections        JSONB NOT NULL,                  -- verified claims only
  pending_review  JSONB NOT NULL DEFAULT '[]',     -- unconfirmed LLM findings (appendix)
  excluded_claims JSONB NOT NULL DEFAULT '[]',     -- blocked/unsupported + reasons
  created_by      TEXT NOT NULL,
  approved_by     TEXT,
  distributed_to  JSONB NOT NULL DEFAULT '[]',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  approved_at     TIMESTAMPTZ,
  distributed_at  TIMESTAMPTZ
);
CREATE INDEX idx_brief_tenant ON exec_brief (tenant_id, period_end DESC);

ALTER TABLE exec_brief ENABLE ROW LEVEL SECURITY;
ALTER TABLE exec_brief FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON exec_brief
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());

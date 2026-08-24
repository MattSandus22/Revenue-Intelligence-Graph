-- 0007: playbooks and in-RIG tasks (docs/06 module D, WF-4).

CREATE TABLE playbook (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL REFERENCES tenant(id),
  key         TEXT NOT NULL,
  name        TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  steps       JSONB NOT NULL,     -- [{title, role, sla_days, exit_criteria?}]
  enabled     BOOLEAN NOT NULL DEFAULT true,
  version     INT NOT NULL DEFAULT 1,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, key)
);

CREATE TABLE task (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES tenant(id),
  account_id    UUID REFERENCES account(id),
  insight_id    UUID REFERENCES insight(id),
  playbook_key  TEXT,
  step_index    INT,
  title         TEXT NOT NULL,
  assignee_role TEXT,              -- role hint from the playbook step
  assignee_id   TEXT,              -- principal id once claimed/assigned
  due_date      DATE,
  status        TEXT NOT NULL DEFAULT 'open',  -- open | done | cancelled
  created_by    TEXT NOT NULL,
  completed_by  TEXT,
  completed_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_task_insight ON task (tenant_id, insight_id, status);
CREATE INDEX idx_task_assignee ON task (tenant_id, assignee_id, status);

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['playbook','task'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant())', t);
  END LOOP;
END $$;

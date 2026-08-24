-- 0006: encrypted connector credentials (docs/08 integration_credential_ref).
-- MVP: application-layer Fernet encryption keyed from RIG_CREDENTIAL_KEY;
-- production upgrades to KMS envelope encryption (docs/12 §12.2) without a
-- schema change — the column stores an opaque ciphertext either way.

CREATE TABLE integration_credential (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES tenant(id),
  data_source_id   UUID NOT NULL REFERENCES data_source(id) UNIQUE,
  ciphertext       TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  rotated_at       TIMESTAMPTZ
);

ALTER TABLE integration_credential ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration_credential FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON integration_credential
  USING (tenant_id = current_tenant()) WITH CHECK (tenant_id = current_tenant());

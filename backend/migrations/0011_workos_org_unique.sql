-- 0011: at most one ACTIVE tenant per WorkOS organization. The SSO org→tenant
-- mapping must never be ambiguous — auth_oidc fails closed at runtime too, but
-- this makes the misconfiguration impossible to write in the first place.

CREATE UNIQUE INDEX uq_tenant_workos_org ON tenant ((settings->>'workos_org_id'))
  WHERE settings->>'workos_org_id' IS NOT NULL AND status = 'active';

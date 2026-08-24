"""WorkOS OIDC sign-in (execution doc 2, week 1; docs/12 identity plan).

Flow: SPA asks for an authorization URL (with an HMAC-signed `state`) →
user authenticates at the IdP via WorkOS AuthKit → callback exchanges the
code for a profile → the WorkOS organization maps to a RIG tenant
(`tenant.settings->>'workos_org_id'`) → the user must already be provisioned
in `app_user` (by an admin or, later, SCIM) — SSO authenticates, it never
mints users or roles → a short-lived RIG session JWT is issued through the
same `issue_dev_token`/`decode_token` seam every endpoint already uses.

Trust notes:
- `state` is HMAC-signed with the app secret, expires in 10 minutes, and is
  bound to the initiating browser: /v1/auth/login stores it in an HttpOnly
  SameSite=Lax cookie which the callback must echo (login-CSRF guard), and
  the cookie is cleared on successful sign-in so a callback URL is single-use
  from the app's side (the IdP additionally rejects a replayed code).
- The org→tenant lookup runs on the ADMIN engine: authentication is
  pre-tenant-context by nature (RLS would hide every tenant row). It reads
  only tenant id/name for a matching `workos_org_id` — nothing else — and
  every subsequent read/write happens inside a normal tenant session.
- The WorkOS client is injected (module-level default) so the login logic is
  fixture-tested; `HttpWorkOSClient` is the thin production I/O layer.
"""

import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text

from . import audit
from .config import settings
from .db import tenant_session

STATE_TTL_SECONDS = 600
SESSION_TTL_SECONDS = 8 * 3600

# Org-level denials (empty/unmapped organization) can't go in audit_event —
# that table is tenant-scoped (NOT NULL tenant_id, per-tenant hash chain) and
# there is no tenant to attribute the attempt to. They land in the server
# security log instead; tenant-attributable denials are audited in-DB below.
security_log = logging.getLogger("rig.auth_oidc")


class OIDCError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class WorkOSProfile:
    email: str
    idp_subject: str
    organization_id: str
    name: str = ""


class WorkOSClient(Protocol):
    def authorization_url(self, redirect_uri: str, state: str) -> str: ...
    def authenticate_code(self, code: str) -> WorkOSProfile: ...


# ---------------------------------------------------------------------------
# Signed state (CSRF/replay guard)
# ---------------------------------------------------------------------------

def _sign(payload: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), payload.encode(),
                    hashlib.sha256).hexdigest()[:32]


def make_state() -> str:
    payload = f"{int(time.time())}.{secrets.token_urlsafe(12)}"
    return f"{payload}.{_sign(payload)}"


def verify_state(state: str, max_age: int = STATE_TTL_SECONDS) -> None:
    try:
        issued_raw, nonce, signature = state.split(".")
        payload = f"{issued_raw}.{nonce}"
    except (ValueError, AttributeError):
        raise OIDCError(401, "malformed state")
    if not hmac.compare_digest(signature, _sign(payload)):
        raise OIDCError(401, "state signature mismatch")
    if int(time.time()) - int(issued_raw) > max_age:
        raise OIDCError(401, "state expired — restart sign-in")


def verify_browser_binding(state: str, browser_state: str | None) -> None:
    """The callback must come from the browser that started the sign-in."""
    if not browser_state or not hmac.compare_digest(browser_state, state):
        raise OIDCError(401, "sign-in was not started in this browser — restart sign-in")


# ---------------------------------------------------------------------------
# Login completion
# ---------------------------------------------------------------------------

def _tenant_for_org(organization_id: str):
    """Pre-auth bootstrap lookup (see module docstring for why admin engine)."""
    from .migrate import admin_engine

    with admin_engine.connect() as conn:
        ids = conn.execute(text(
            "SELECT id FROM tenant WHERE settings->>'workos_org_id' = :org"
            " AND status = 'active'"
        ), {"org": organization_id}).scalars().all()
    if len(ids) > 1:
        # migration 0011's partial unique index prevents this; if it somehow
        # occurs, never pick an arbitrary workspace — fail closed
        security_log.error("workos org %s maps to %d active tenants — failing closed",
                           organization_id, len(ids))
        raise OIDCError(403, "workspace mapping is misconfigured —"
                             " contact your administrator")
    return ids[0] if ids else None


def complete_login(profile: WorkOSProfile) -> dict:
    if not profile.organization_id:
        # a tenant misconfigured with workos_org_id = '' must never match
        security_log.warning(
            "oidc login denied: no organization (email=%s idp_subject=%s)",
            profile.email, profile.idp_subject)
        raise OIDCError(403, "no workspace is configured for your organization")
    tenant_id = _tenant_for_org(profile.organization_id)
    if tenant_id is None:
        security_log.warning(
            "oidc login denied: unmapped organization (email=%s org=%s)",
            profile.email, profile.organization_id)
        raise OIDCError(403, "no workspace is configured for your organization")

    # Authorization check, last-login update, and the role the token carries
    # all happen in ONE transaction with the user row locked — an admin
    # deactivating the user or changing the role concurrently can't race a
    # session into existence with stale authorization state.
    with tenant_session(tenant_id) as session:
        user = session.execute(text(
            "SELECT id, email, role, status FROM app_user"
            " WHERE lower(email) = lower(:email) FOR UPDATE"
        ), {"email": profile.email}).mappings().one_or_none()
        if user is not None and user["status"] == "active":
            session.execute(text(
                "UPDATE app_user SET last_login_at = now(), idp_subject = :sub"
                " WHERE id = :id AND status = 'active'"
            ), {"sub": profile.idp_subject, "id": str(user["id"])})
            audit.record(session, tenant_id=str(tenant_id), actor_type="user",
                         actor_id=profile.email, action="auth.login",
                         payload={"method": "oidc", "idp_subject": profile.idp_subject})

    if user is None or user["status"] != "active":
        # SSO authenticates; it never provisions. Admin/SCIM creates users.
        # The denial audit runs in its OWN committed transaction — raising
        # inside the lookup session would roll the record back and denials
        # would never be audited.
        with tenant_session(tenant_id) as session:
            audit.record(session, tenant_id=str(tenant_id), actor_type="system",
                         actor_id="oidc", action="auth.login_denied",
                         payload={"email": profile.email, "reason": "not_provisioned"})
        raise OIDCError(403, "your account is not provisioned in this workspace —"
                             " ask a workspace admin to add you")

    from .auth import issue_dev_token  # same signing seam as every other token

    token = issue_dev_token(profile.email, tenant_id, user["role"],
                            ttl_seconds=SESSION_TTL_SECONDS)
    return {"token": token, "role": user["role"], "tenant_id": str(tenant_id)}


# ---------------------------------------------------------------------------
# Production client (thin I/O)
# ---------------------------------------------------------------------------

class HttpWorkOSClient:
    """WorkOS User Management (AuthKit) API client."""

    BASE = "https://api.workos.com"

    def __init__(self, api_key: str, client_id: str):
        import httpx

        self.client_id = client_id
        self._api_key = api_key
        self._http = httpx.Client(base_url=self.BASE, timeout=15,
                                  headers={"Authorization": f"Bearer {api_key}"})

    def authorization_url(self, redirect_uri: str, state: str) -> str:
        from urllib.parse import urlencode

        return f"{self.BASE}/user_management/authorize?" + urlencode({
            "client_id": self.client_id, "redirect_uri": redirect_uri,
            "response_type": "code", "provider": "authkit", "state": state,
        })

    def authenticate_code(self, code: str) -> WorkOSProfile:
        # WorkOS requires client_secret (the API key) in the body for the
        # authorization_code grant, alongside the Authorization header.
        response = self._http.post("/user_management/authenticate", json={
            "client_id": self.client_id, "client_secret": self._api_key,
            "grant_type": "authorization_code", "code": code,
        })
        response.raise_for_status()
        data = response.json()
        user = data["user"]
        return WorkOSProfile(
            email=user["email"], idp_subject=user["id"],
            organization_id=data.get("organization_id") or "",
            name=" ".join(filter(None, [user.get("first_name"), user.get("last_name")])),
        )


# Configured at startup from env (see main.py); None = SSO endpoints 404 and
# the login page falls back to whatever else is enabled.
default_workos_client: WorkOSClient | None = None

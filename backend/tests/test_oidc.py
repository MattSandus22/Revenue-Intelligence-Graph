"""WorkOS OIDC sign-in: state guard, org→tenant mapping, provisioning gate,
session issuance through the standard token seam, and endpoint gating."""

import time

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from rig import auth_oidc
from rig.auth_oidc import (OIDCError, WorkOSProfile, complete_login,
                           make_state, verify_state)
from rig.db import tenant_session
from rig.migrate import admin_engine


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FixtureWorkOSClient:
    def __init__(self, profile: WorkOSProfile):
        self.profile = profile
        self.codes_seen: list[str] = []

    def authorization_url(self, redirect_uri, state):
        return f"https://fixture.workos/authorize?state={state}&redirect_uri={redirect_uri}"

    def authenticate_code(self, code):
        self.codes_seen.append(code)
        if code == "bad-code":
            raise RuntimeError("invalid_grant")
        return self.profile


def _map_org(seeded, org_id="org_nsc_01"):
    """Point the WorkOS org at the seeded NorthstarCloud tenant."""
    with admin_engine.begin() as conn:
        conn.execute(text(
            "UPDATE tenant SET settings = settings ||"
            " jsonb_build_object('workos_org_id', CAST(:org AS text))"
            " WHERE id = CAST(:tid AS uuid)"
        ), {"org": org_id, "tid": seeded["nsc_tenant"]})
    return org_id


PROFILE = WorkOSProfile(email="j.ortiz@northstarcloud.example",
                        idp_subject="user_wos_123",
                        organization_id="org_nsc_01", name="J. Ortiz")


# ---------------------------------------------------------------------------
# State guard
# ---------------------------------------------------------------------------

def test_state_roundtrip_and_tampering():
    state = make_state()
    verify_state(state)                      # fresh state verifies
    with pytest.raises(OIDCError, match="signature"):
        verify_state(state[:-4] + "beef")
    with pytest.raises(OIDCError, match="malformed"):
        verify_state("garbage")
    # expired: rebuild a state with an old timestamp but a VALID signature
    old_payload = f"{int(time.time()) - 3600}.nonce"
    forged_valid = f"{old_payload}.{auth_oidc._sign(old_payload)}"
    with pytest.raises(OIDCError, match="expired"):
        verify_state(forged_valid)


# ---------------------------------------------------------------------------
# Login completion
# ---------------------------------------------------------------------------

def test_login_happy_path_issues_working_session(seeded):
    _map_org(seeded)
    result = complete_login(PROFILE)
    assert result["role"] == "contributor"           # role comes from app_user
    assert result["tenant_id"] == seeded["nsc_tenant"]

    from rig.auth import decode_token

    principal = decode_token(result["token"])
    assert principal.user_id == PROFILE.email
    assert str(principal.tenant_id) == seeded["nsc_tenant"]
    assert principal.can("accounts:read") and not principal.can("sources:manage")

    with tenant_session(seeded["nsc_tenant"]) as s:
        row = s.execute(text(
            "SELECT last_login_at, idp_subject FROM app_user WHERE email = :e"
        ), {"e": PROFILE.email}).one()
        assert row.last_login_at is not None and row.idp_subject == "user_wos_123"
        assert s.execute(text(
            "SELECT count(*) FROM audit_event WHERE action = 'auth.login'"
            " AND actor_id = :e"), {"e": PROFILE.email}).scalar_one() >= 1


def test_unknown_org_and_unprovisioned_user_denied(seeded):
    _map_org(seeded)
    with pytest.raises(OIDCError) as excinfo:
        complete_login(WorkOSProfile(email="x@y.z", idp_subject="s",
                                     organization_id="org_unknown"))
    assert excinfo.value.status_code == 403

    # an empty organization_id (user outside any WorkOS org) must never match
    # a tenant whose workos_org_id was misconfigured as ''
    with pytest.raises(OIDCError) as empty_org:
        complete_login(WorkOSProfile(email="x@y.z", idp_subject="s",
                                     organization_id=""))
    assert empty_org.value.status_code == 403

    # right org, but SSO never provisions users
    with pytest.raises(OIDCError, match="not provisioned"):
        complete_login(WorkOSProfile(email="stranger@northstarcloud.example",
                                     idp_subject="s2", organization_id="org_nsc_01"))
    with tenant_session(seeded["nsc_tenant"]) as s:
        denied = s.execute(text(
            "SELECT count(*) FROM audit_event WHERE action = 'auth.login_denied'"
        )).scalar_one()
    assert denied >= 1


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_endpoints_404_when_unconfigured(monkeypatch):
    from rig.main import app

    monkeypatch.setattr(auth_oidc, "default_workos_client", None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/v1/auth/login")).status_code == 404
        assert (await client.get("/v1/auth/callback?code=x&state=y")).status_code == 404
        methods = (await client.get("/v1/auth/methods")).json()
        assert methods["sso"] is False


@pytest.mark.anyio
async def test_full_http_flow(monkeypatch, seeded):
    from rig.main import app

    _map_org(seeded)
    monkeypatch.setattr(auth_oidc, "default_workos_client", FixtureWorkOSClient(PROFILE))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        assert (await client.get("/v1/auth/methods")).json()["sso"] is True

        # a valid state that was never issued to THIS browser (no cookie) → 401
        no_cookie = await client.get(
            f"/v1/auth/callback?code=ok-code&state={make_state()}")
        assert no_cookie.status_code == 401

        login = (await client.get("/v1/auth/login")).json()
        state = login["authorization_url"].split("state=")[1].split("&")[0]

        callback = await client.get(f"/v1/auth/callback?code=ok-code&state={state}")
        assert callback.status_code == 200
        token = callback.json()["token"]

        accounts = await client.get("/v1/accounts",
                                    headers={"Authorization": f"Bearer {token}"})
        assert accounts.status_code == 200  # the issued session actually works

        # the binding cookie is consumed on success: replaying the same
        # callback URL is rejected before any provider call
        replay = await client.get(f"/v1/auth/callback?code=ok-code&state={state}")
        assert replay.status_code == 401

        # bad state → 401 before any provider call; provider failure → 502
        bad_state = await client.get("/v1/auth/callback?code=ok-code&state=eviltamper")
        assert bad_state.status_code == 401
        relogin = (await client.get("/v1/auth/login")).json()
        state2 = relogin["authorization_url"].split("state=")[1].split("&")[0]
        provider_fail = await client.get(
            f"/v1/auth/callback?code=bad-code&state={state2}")
        assert provider_fail.status_code == 502
        assert "bad-code" not in provider_fail.json()["detail"]  # no internals echoed

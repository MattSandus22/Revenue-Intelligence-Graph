"""Credential storage + source lifecycle: encryption at rest, no leakage
through APIs or audit, factory contracts, API-driven sync, disconnect."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from rig.auth import issue_dev_token
from rig.connectors import factory
from rig.connectors.factory import CredentialError, build_connector
from rig.credentials import delete_credentials, load_credentials, store_credentials
from rig.db import tenant_session


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def client():
    from rig.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _headers(seeded, role="data_admin"):
    return {"Authorization": f"Bearer {issue_dev_token('u_data', seeded['nsc_tenant'], role)}"}


SECRET = "sk-test-VERYSECRET-123"


def test_roundtrip_and_encrypted_at_rest(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        source_id = s.execute(text(
            "INSERT INTO data_source (tenant_id, type, name)"
            " VALUES (:tid, 'stripe', 'cred-test') RETURNING id"
        ), {"tid": tid}).scalar_one()
        store_credentials(s, tid, source_id, {"api_key": SECRET})
        assert load_credentials(s, source_id) == {"api_key": SECRET}

        ciphertext = s.execute(text(
            "SELECT ciphertext FROM integration_credential WHERE data_source_id = :sid"
        ), {"sid": str(source_id)}).scalar_one()
        assert SECRET not in ciphertext and "api_key" not in ciphertext

        # rotation updates in place
        store_credentials(s, tid, source_id, {"api_key": "sk-rotated"})
        assert load_credentials(s, source_id) == {"api_key": "sk-rotated"}
        rotated_at = s.execute(text(
            "SELECT rotated_at FROM integration_credential WHERE data_source_id = :sid"
        ), {"sid": str(source_id)}).scalar_one()
        assert rotated_at is not None

        assert delete_credentials(s, source_id) is True
        assert load_credentials(s, source_id) is None


def test_factory_contracts():
    with pytest.raises(CredentialError, match="missing credential fields"):
        build_connector("hubspot", {})
    with pytest.raises(CredentialError, match="unknown connector type"):
        build_connector("no_such_crm", {"token": "x"})
    connector = build_connector("zendesk",
                                {"subdomain": "acme", "email": "a@b.c", "api_token": "t"})
    assert connector.source_system == "zendesk"


@pytest.mark.anyio
async def test_source_api_never_leaks_secrets(client, seeded):
    response = await client.post("/v1/admin/sources", headers=_headers(seeded), json={
        "type": "stripe", "name": "stripe-api-test",
        "credentials": {"api_key": SECRET},
    })
    assert response.status_code == 201
    body = response.json()
    assert SECRET not in response.text
    source_id = body["source_id"]

    listing = await client.get("/v1/admin/sources", headers=_headers(seeded))
    assert SECRET not in listing.text

    with tenant_session(seeded["nsc_tenant"]) as s:
        audit_payload = s.execute(text(
            "SELECT payload::text FROM audit_event WHERE action = 'source.create'"
            " AND object_id = :id"
        ), {"id": source_id}).scalar_one()
    assert SECRET not in audit_payload
    assert "api_key" in audit_payload  # field NAMES are audited, values never


@pytest.mark.anyio
async def test_sync_via_api_with_stored_credentials(client, seeded, monkeypatch):
    from .fixture_clients import FixtureStripeClient
    from rig.connectors.stripe import StripeConnector

    captured = {}

    def fixture_builder(credentials, config):
        captured["credentials"] = credentials
        return StripeConnector(FixtureStripeClient(
            customers=[{"id": "cus_api", "created": 1800000000,
                        "email": "ops@acme.com", "name": "Acme Corporation"}],
            invoices=[]))

    monkeypatch.setitem(factory.BUILDERS, "stripe", fixture_builder)

    created = await client.post("/v1/admin/sources", headers=_headers(seeded), json={
        "type": "stripe", "name": "stripe-sync-test",
        "credentials": {"api_key": SECRET}})
    source_id = created.json()["source_id"]

    summary = (await client.post(f"/v1/admin/sources/{source_id}/sync",
                                 headers=_headers(seeded))).json()
    assert summary["status"] == "succeeded"
    assert captured["credentials"] == {"api_key": SECRET}  # decrypted for the builder only
    # acme.com domain-links the new stripe customer
    assert summary["stats"]["customers"] in ({"linked": 1}, {"already_linked": 1})


@pytest.mark.anyio
async def test_disconnect_deletes_credentials_and_blocks_sync(client, seeded):
    created = await client.post("/v1/admin/sources", headers=_headers(seeded), json={
        "type": "stripe", "name": "stripe-disc-test",
        "credentials": {"api_key": SECRET}})
    source_id = created.json()["source_id"]

    response = await client.delete(f"/v1/admin/sources/{source_id}", headers=_headers(seeded))
    assert response.json()["credentials_deleted"] is True
    with tenant_session(seeded["nsc_tenant"]) as s:
        assert load_credentials(s, source_id) is None

    blocked = await client.post(f"/v1/admin/sources/{source_id}/sync",
                                headers=_headers(seeded))
    assert blocked.status_code == 409


@pytest.mark.anyio
async def test_duplicate_name_409_and_reconnect_flow(client, seeded):
    body = {"type": "stripe", "name": "stripe-dup-test",
            "credentials": {"api_key": SECRET}}
    first = await client.post("/v1/admin/sources", headers=_headers(seeded), json=body)
    assert first.status_code == 201
    source_id = first.json()["source_id"]

    # same active name → clean 409, not a 500
    duplicate = await client.post("/v1/admin/sources", headers=_headers(seeded), json=body)
    assert duplicate.status_code == 409 and "already" in duplicate.text

    # disconnect then recreate under the same name → reactivates the SAME
    # source (cursors reset, fresh credentials) instead of erroring
    await client.delete(f"/v1/admin/sources/{source_id}", headers=_headers(seeded))
    reconnect = await client.post("/v1/admin/sources", headers=_headers(seeded), json=body)
    assert reconnect.status_code == 201
    assert reconnect.json() == {"source_id": source_id, "type": "stripe",
                                "status": "active", "reconnected": True}
    with tenant_session(seeded["nsc_tenant"]) as s:
        status = s.execute(text("SELECT status FROM data_source WHERE id = :id"),
                           {"id": source_id}).scalar_one()
        assert status == "active"
        assert load_credentials(s, source_id) == {"api_key": SECRET}


@pytest.mark.anyio
async def test_secrets_in_config_rejected(client, seeded):
    response = await client.post("/v1/admin/sources", headers=_headers(seeded), json={
        "type": "stripe", "name": "stripe-cfg-test",
        "credentials": {"api_key": SECRET},
        "config": {"api_key": "sk-live-oops", "mapping": {}}})
    assert response.status_code == 422
    assert "config must not contain secrets" in response.text


@pytest.mark.anyio
async def test_failed_sync_returns_502(client, seeded, monkeypatch):
    from rig.connectors.hubspot import HubSpotConnector

    class ExplodingClient:
        def list_companies(self, updated_after=None):
            raise RuntimeError("simulated 401 from provider")

        list_contacts = list_deals = list_companies

    monkeypatch.setitem(factory.BUILDERS, "hubspot",
                        lambda credentials, config: HubSpotConnector(ExplodingClient()))
    created = await client.post("/v1/admin/sources", headers=_headers(seeded), json={
        "type": "hubspot", "name": "hs-fail-test",
        "credentials": {"access_token": "t"}})
    source_id = created.json()["source_id"]
    response = await client.post(f"/v1/admin/sources/{source_id}/sync",
                                 headers=_headers(seeded))
    assert response.status_code == 502
    assert response.json()["status"] == "failed"


def test_decrypt_error_is_typed_and_recoverable(seeded, monkeypatch):
    from rig.credentials import CredentialDecryptError

    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        source_id = s.execute(text(
            "INSERT INTO data_source (tenant_id, type, name)"
            " VALUES (:tid, 'stripe', 'wrong-key-test') RETURNING id"
        ), {"tid": tid}).scalar_one()
        store_credentials(s, tid, source_id, {"api_key": SECRET})
        # simulate a key rotation after storage
        monkeypatch.setenv("RIG_CREDENTIAL_KEY",
                           __import__("cryptography.fernet", fromlist=["Fernet"])
                           .Fernet.generate_key().decode())
        with pytest.raises(CredentialDecryptError, match="re-enter"):
            load_credentials(s, source_id)


def test_boot_rejects_malformed_credential_key(monkeypatch):
    from rig.boot import check_production_config

    monkeypatch.delenv("RIG_DEV_LOGIN", raising=False)
    monkeypatch.setenv("RIG_CREDENTIAL_KEY", "not-a-fernet-key")
    violations = check_production_config()
    assert any("not a valid Fernet key" in v for v in violations)


@pytest.mark.anyio
async def test_source_create_validates_fields(client, seeded):
    bad_type = await client.post("/v1/admin/sources", headers=_headers(seeded),
                                 json={"type": "salesforce", "name": "x",
                                       "credentials": {"token": "t"}})
    assert bad_type.status_code == 422
    missing = await client.post("/v1/admin/sources", headers=_headers(seeded),
                                json={"type": "zendesk", "name": "x",
                                      "credentials": {"subdomain": "a"}})
    assert missing.status_code == 422
    assert "email" in missing.text and "api_token" in missing.text

"""API: auth required, tenant-scoped, role-gated, evidence returned."""

from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from rig.auth import issue_dev_token
from rig.main import app

TODAY = date.today().isoformat()


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _headers(seeded, tenant_key="nsc_tenant", role="leader", user="u_test"):
    return {"Authorization": f"Bearer {issue_dev_token(user, seeded[tenant_key], role)}"}


@pytest.mark.anyio
async def test_requires_auth(client, seeded):
    response = await client.get("/v1/accounts")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_accounts_are_tenant_scoped(client, seeded):
    response = await client.get("/v1/accounts", headers=_headers(seeded))
    names = {a["name"] for a in response.json()["accounts"]}
    assert names == {"Acme Corp", "BetaWorks Ltd"}

    response = await client.get("/v1/accounts", headers=_headers(seeded, "other_tenant"))
    names = {a["name"] for a in response.json()["accounts"]}
    assert names == {"Zenith Corp"}


@pytest.mark.anyio
async def test_cross_tenant_account_fetch_404s(client, seeded):
    response = await client.get(
        f"/v1/accounts/{seeded['acme_account']}", headers=_headers(seeded, "other_tenant")
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_role_gating_on_evaluate(client, seeded):
    url = f"/v1/admin/accounts/{seeded['acme_account']}/evaluate?as_of={TODAY}"
    denied = await client.post(url, headers=_headers(seeded, role="exec_readonly"))
    assert denied.status_code == 403
    allowed = await client.post(url, headers=_headers(seeded, role="leader"))
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["evaluation"]["active"] >= 5
    assert body["score"]["value"] > 50


@pytest.mark.anyio
async def test_risk_endpoint_returns_citations(client, seeded):
    await client.post(
        f"/v1/admin/accounts/{seeded['acme_account']}/evaluate?as_of={TODAY}",
        headers=_headers(seeded),
    )
    response = await client.get(
        f"/v1/accounts/{seeded['acme_account']}/risk", headers=_headers(seeded)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["direction"] == "higher_is_riskier"
    contributing = [c for c in body["components"] if c["norm_value"] > 0]
    assert contributing
    for component in contributing:
        assert component["citations"], f"{component['component']} has no citations"
        for citation in component["citations"]:
            assert citation["claim_class"] == "observed_fact"
            assert citation["source_system"] and citation["source_record_id"]


@pytest.fixture
def anyio_backend():
    return "asyncio"

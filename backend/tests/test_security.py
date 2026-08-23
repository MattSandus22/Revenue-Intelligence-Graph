"""Security regression tests from the 2026-08 branch security review."""

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_spa_route_blocks_path_traversal(database):
    """CWE-22 regression: encoded ../ must never escape the dist directory."""
    from rig.main import app

    dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if not (dist / "index.html").exists():
        pytest.skip("frontend not built in this environment")
    index_content = (dist / "index.html").read_text()
    pyproject_marker = "rig-backend"

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    for attack in [
        "/../backend/pyproject.toml",
        "/..%2f..%2fbackend%2fpyproject.toml",
        "/%2e%2e%2f%2e%2e%2fbackend%2fpyproject.toml",
        "/assets/../../backend/pyproject.toml",
    ]:
        response = await client.get(attack)
        assert pyproject_marker not in response.text, f"traversal escaped via {attack}"
        # traversal falls through to the SPA shell or 404s — never leaks files
        assert response.status_code in (200, 404)
        if response.status_code == 200 and not attack.startswith("/assets"):
            assert response.text == index_content


def test_production_boot_refuses_default_secrets(monkeypatch):
    from rig.boot import check_production_config

    monkeypatch.delenv("RIG_DEV_LOGIN", raising=False)
    monkeypatch.delenv("RIG_APP_DB_PASSWORD", raising=False)
    violations = check_production_config()
    assert any("RIG_JWT_SECRET" in v for v in violations)
    assert any("RIG_APP_DB_PASSWORD" in v for v in violations)

    # dev mode explicitly opts in to the defaults
    monkeypatch.setenv("RIG_DEV_LOGIN", "1")
    assert check_production_config() == []


@pytest.mark.anyio
async def test_dev_endpoints_hidden_without_flag(monkeypatch):
    monkeypatch.delenv("RIG_DEV_LOGIN", raising=False)
    from rig.main import app

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    tenants = await client.get("/v1/dev/tenants")
    token = await client.post(
        "/v1/dev/token?tenant_id=00000000-0000-0000-0000-000000000000&role=leader")
    assert (tenants.status_code, token.status_code) == (404, 404)


@pytest.mark.anyio
async def test_csv_import_size_cap():
    from rig.auth import issue_dev_token
    from rig.main import app

    token = issue_dev_token("u_sec", "00000000-0000-0000-0000-000000000001", "data_admin")
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    oversized = b"account_ref,date,metric,value\n" + b"x" * (10 * 1024 * 1024 + 1)
    response = await client.post(
        "/v1/admin/usage/import", content=oversized,
        headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 413

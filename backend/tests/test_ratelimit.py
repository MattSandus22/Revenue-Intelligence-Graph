"""Rate limiting: bucket mechanics + endpoint enforcement with Retry-After."""

import pytest
from httpx import ASGITransport, AsyncClient

from rig import ratelimit
from rig.auth import issue_dev_token
from rig.ratelimit import RateLimiter


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_bucket_exhausts_and_refills():
    limiter = RateLimiter({"standard": (2, 100.0), "expensive": (1, 0.001)})
    assert limiter.check("k", "standard") is None
    assert limiter.check("k", "standard") is None
    retry = limiter.check("k", "standard")
    assert retry is not None and retry > 0
    # fast refill (100/s) recovers almost immediately
    import time
    time.sleep(0.02)
    assert limiter.check("k", "standard") is None
    # independent keys have independent buckets
    assert limiter.check("other", "expensive") is None
    assert limiter.check("other", "expensive") is not None


@pytest.mark.anyio
async def test_endpoint_returns_429_with_retry_after(seeded, monkeypatch):
    from rig.main import app

    monkeypatch.setattr(ratelimit, "limiter",
                        RateLimiter({"standard": (2, 0.01), "expensive": (1, 0.01)}))
    token = issue_dev_token("u_rl", seeded["nsc_tenant"], "leader")
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    headers = {"Authorization": f"Bearer {token}"}

    assert (await client.get("/v1/accounts", headers=headers)).status_code == 200
    assert (await client.get("/v1/accounts", headers=headers)).status_code == 200
    limited = await client.get("/v1/accounts", headers=headers)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1

    # a different principal is unaffected
    other = issue_dev_token("u_other", seeded["nsc_tenant"], "leader")
    response = await client.get("/v1/accounts",
                                headers={"Authorization": f"Bearer {other}"})
    assert response.status_code == 200

    # health and static paths are never limited
    for _ in range(5):
        assert (await client.get("/health")).status_code == 200

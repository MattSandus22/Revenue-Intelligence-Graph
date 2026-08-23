"""Token-bucket rate limiting (docs/13 hardening).

In-process buckets keyed on (principal|ip, cost class) — correct for the
single-process MVP container; the interface is deliberately tiny so the
production swap to Redis buckets (multi-worker) is a drop-in.

Cost classes: expensive routes (LLM-backed, generation) get a small budget;
everything else a generous one. 429 responses carry Retry-After.
"""

import time
from dataclasses import dataclass, field

from fastapi import Request

EXPENSIVE_PREFIXES = ("/v1/copilot/", "/v1/briefs/generate", "/v1/admin/tickets")

# (capacity, refill per second)
LIMITS = {"expensive": (10, 10 / 60), "standard": (120, 120 / 60)}


@dataclass
class _Bucket:
    tokens: float
    updated: float = field(default_factory=time.monotonic)


class RateLimiter:
    def __init__(self, limits: dict[str, tuple[float, float]] | None = None):
        self.limits = limits or LIMITS
        self._buckets: dict[tuple[str, str], _Bucket] = {}

    def check(self, key: str, cost_class: str) -> float | None:
        """Consume one token; returns None if allowed, else seconds to retry."""
        capacity, refill = self.limits[cost_class]
        now = time.monotonic()
        bucket = self._buckets.get((key, cost_class))
        if bucket is None:
            bucket = self._buckets[(key, cost_class)] = _Bucket(tokens=capacity, updated=now)
        # max(0, ...) guards against clock ordering producing negative elapsed
        bucket.tokens = min(capacity, bucket.tokens + max(0.0, now - bucket.updated) * refill)
        bucket.updated = now
        if bucket.tokens >= 1:
            bucket.tokens -= 1
            return None
        return (1 - bucket.tokens) / refill


limiter = RateLimiter()


async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/v1/"):
        # key on bearer token when present (per-user), else client IP
        auth = request.headers.get("authorization", "")
        key = auth[-32:] if auth else (request.client.host if request.client else "anon")
        cost_class = "expensive" if path.startswith(EXPENSIVE_PREFIXES) else "standard"
        retry_after = limiter.check(key, cost_class)
        if retry_after is not None:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded"},
                headers={"Retry-After": str(max(1, int(retry_after + 0.5)))},
            )
    return await call_next(request)

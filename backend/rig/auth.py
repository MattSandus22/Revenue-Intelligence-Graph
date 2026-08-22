"""Authentication and authorization.

Dev tokens are HS256 JWTs carrying (sub, tenant_id, role). The production
path swaps `decode_token` for OIDC/JWKS verification (WorkOS) without touching
callers. Authorization is a role→capability map (doc 4); scope grants
(team/territory/named-account) arrive with the workbench in Sprint 3.
"""

import time
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request

from .config import settings

CAPABILITIES: dict[str, set[str]] = {
    "org_admin": {"accounts:read", "admin:evaluate", "audit:read", "users:manage", "sources:manage"},
    "data_admin": {"accounts:read", "admin:evaluate", "sources:manage"},
    "model_admin": {"accounts:read", "admin:evaluate", "scores:configure"},
    "leader": {"accounts:read", "accounts:write", "admin:evaluate"},
    "contributor": {"accounts:read", "accounts:write"},
    "analyst": {"accounts:read", "audit:read"},
    "exec_readonly": {"accounts:read"},
    "audit_viewer": {"audit:read"},
}


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: UUID
    role: str

    def can(self, capability: str) -> bool:
        return capability in CAPABILITIES.get(self.role, set())


def issue_dev_token(user_id: str, tenant_id: UUID | str, role: str, ttl_seconds: int = 3600) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": settings.jwt_issuer,
            "sub": user_id,
            "tenant_id": str(tenant_id),
            "role": role,
            "iat": now,
            "exp": now + ttl_seconds,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_token(token: str) -> Principal:
    try:
        claims = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"], issuer=settings.jwt_issuer
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc
    if claims.get("role") not in CAPABILITIES:
        raise HTTPException(status_code=403, detail="unknown role")
    return Principal(
        user_id=claims["sub"],
        tenant_id=UUID(claims["tenant_id"]),
        role=claims["role"],
    )


def get_principal(request: Request) -> Principal:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return decode_token(header.removeprefix("Bearer "))


def require(capability: str):
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.can(capability):
            raise HTTPException(status_code=403, detail=f"requires {capability}")
        return principal

    return dependency

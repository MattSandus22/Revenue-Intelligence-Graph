import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    # Application role: non-superuser, non-owner — RLS applies to every query.
    # Superuser/owner connections bypass RLS, so the app MUST NOT use one.
    database_url: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://rig_app:rig_app@127.0.0.1:55432/rig_test",
        )
    )
    # Admin role: migrations and role/grant bootstrap only.
    admin_database_url: str = field(
        default_factory=lambda: os.environ.get(
            "ADMIN_DATABASE_URL",
            "postgresql+psycopg://postgres@127.0.0.1:55432/rig_test",
        )
    )
    # Dev-only HS256 secret. Production uses OIDC (WorkOS) with RS256/JWKS —
    # see docs/12-security-privacy-enterprise.md; the verify path is swappable.
    jwt_secret: str = field(
        default_factory=lambda: os.environ.get(
            "RIG_JWT_SECRET", "dev-only-secret-0123456789abcdef0123456789abcdef"
        )
    )
    jwt_issuer: str = "rig-dev"


settings = Settings()

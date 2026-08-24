"""Container entrypoint: migrate, optionally seed a demo tenant, serve.

RIG_DEMO_SEED=1 seeds the NorthstarCloud/Acme walkthrough tenant on first
boot (skipped when any tenant already exists) and runs signal evaluation +
scoring so the app opens populated — the design-partner demo mode.
"""

import os

from sqlalchemy import text

from .db import tenant_session
from .migrate import admin_engine, run_migrations


DEFAULT_JWT_SECRET = "dev-only-secret-0123456789abcdef0123456789abcdef"


def check_production_config() -> list[str]:
    """Return config violations that MUST fail a non-dev boot.

    Dev mode = RIG_DEV_LOGIN=1 (the same switch that enables dev sign-in);
    anything else is treated as production and refuses known-default secrets.
    """
    if os.environ.get("RIG_DEV_LOGIN") == "1":
        return []
    violations = []
    from .config import settings

    if settings.jwt_secret == DEFAULT_JWT_SECRET:
        violations.append(
            "RIG_JWT_SECRET is the built-in dev default — anyone could mint valid "
            "tokens. Set a strong RIG_JWT_SECRET (or enable OIDC) before deploying.")
    if ":rig_app@" in settings.database_url and not os.environ.get("RIG_APP_DB_PASSWORD"):
        violations.append(
            "Database password for rig_app is the dev default. Set "
            "RIG_APP_DB_PASSWORD and update DATABASE_URL.")
    if not os.environ.get("RIG_CREDENTIAL_KEY"):
        violations.append(
            "RIG_CREDENTIAL_KEY is unset — connector credentials would be "
            "encrypted with the derived dev key. Generate one with "
            "python -c \"from cryptography.fernet import Fernet;"
            " print(Fernet.generate_key().decode())\"")
    return violations


def boot() -> None:
    violations = check_production_config()
    if violations:
        for violation in violations:
            print(f"FATAL insecure configuration: {violation}")
        raise SystemExit(1)

    for name in run_migrations():
        print(f"migration applied: {name}")

    if os.environ.get("RIG_DEMO_SEED") == "1":
        with admin_engine.connect() as conn:
            existing = conn.execute(text("SELECT count(*) FROM tenant")).scalar_one()
        if existing:
            print(f"demo seed skipped: {existing} tenant(s) already present")
        else:
            from .insights import upsert_risk_insight
            from .scoring import compute_renewal_risk
            from .seed import seed_demo
            from .signals.engine import evaluate_account

            ids = seed_demo()
            with tenant_session(ids["nsc_tenant"]) as session:
                evaluate_account(session, ids["nsc_tenant"], ids["acme_account"])
                score = compute_renewal_risk(session, ids["nsc_tenant"], ids["acme_account"])
                upsert_risk_insight(session, ids["nsc_tenant"], ids["acme_account"], score)
            print(f"demo tenant seeded: {ids['nsc_tenant']} (Acme evaluated and scored)")


if __name__ == "__main__":
    boot()

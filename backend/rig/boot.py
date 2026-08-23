"""Container entrypoint: migrate, optionally seed a demo tenant, serve.

RIG_DEMO_SEED=1 seeds the NorthstarCloud/Acme walkthrough tenant on first
boot (skipped when any tenant already exists) and runs signal evaluation +
scoring so the app opens populated — the design-partner demo mode.
"""

import os

from sqlalchemy import text

from .db import tenant_session
from .migrate import admin_engine, run_migrations


def boot() -> None:
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

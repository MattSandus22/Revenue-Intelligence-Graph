"""Seed fixtures: NorthstarCloud tenant with Acme Corp (docs/20 walkthrough),
plus a second tenant used to demonstrate/verify isolation.

Dates are computed relative to `today` so the walkthrough numbers (92 days to
renewal, 14-day-overdue invoice, 8-day-old critical ticket, −31% usage) hold
whenever the seed runs.
"""

import random
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4

from sqlalchemy import text

from . import audit
from .db import tenant_session


def seed_demo(today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    nsc_tenant = uuid4()
    other_tenant = uuid4()

    with tenant_session(nsc_tenant) as session:
        session.execute(text(
            "INSERT INTO tenant (id, name, region) VALUES (:id, 'NorthstarCloud', 'us')"
        ), {"id": str(nsc_tenant)})
        csm_id = uuid4()
        session.execute(text(
            "INSERT INTO app_user (id, tenant_id, email, name, role)"
            " VALUES (:id, :tid, 'j.ortiz@northstarcloud.example', 'J. Ortiz', 'contributor')"
        ), {"id": str(csm_id), "tid": str(nsc_tenant)})

        acme_id = uuid4()
        session.execute(text(
            "INSERT INTO account (id, tenant_id, name, domains, industry, segment, tier,"
            " lifecycle_stage, arr_cents, renewal_date, notice_days, auto_renew, plan,"
            " plan_status, owner_csm_id)"
            " VALUES (:id, :tid, 'Acme Corp', ARRAY['acme.com'], 'Logistics SaaS',"
            " 'Mid-Market', 'Enterprise', 'established', 12000000, :renewal, 60, false,"
            " 'Platform - 100 seats', 'none', :csm)"
        ), {"id": str(acme_id), "tid": str(nsc_tenant),
            "renewal": today + timedelta(days=92), "csm": str(csm_id)})

        # Healthy comparison account: renewal far out, plan active, paid up.
        beta_id = uuid4()
        session.execute(text(
            "INSERT INTO account (id, tenant_id, name, domains, segment, tier,"
            " lifecycle_stage, arr_cents, renewal_date, notice_days, auto_renew, plan_status)"
            " VALUES (:id, :tid, 'BetaWorks Ltd', ARRAY['betaworks.example'], 'Mid-Market',"
            " 'Growth', 'established', 6000000, :renewal, 30, true, 'active')"
        ), {"id": str(beta_id), "tid": str(nsc_tenant), "renewal": today + timedelta(days=300)})

        # Invoice: $30,000, 14 days overdue (INV-2214).
        session.execute(text(
            "INSERT INTO invoice (tenant_id, account_id, source_system, source_record_id,"
            " amount_cents, issued_at, due_at, status)"
            " VALUES (:tid, :aid, 'stripe', 'INV-2214', 3000000, :issued, :due, 'overdue')"
        ), {"tid": str(nsc_tenant), "aid": str(acme_id),
            "issued": today - timedelta(days=29), "due": today - timedelta(days=14)})

        # Critical ticket open 8 days (ZD-8841).
        session.execute(text(
            "INSERT INTO support_ticket (tenant_id, account_id, source_system,"
            " source_record_id, subject, priority, status, escalated, opened_at)"
            " VALUES (:tid, :aid, 'zendesk', 'ZD-8841',"
            " 'Carrier-rate sync failing for all EU shipments', 'critical', 'open', true, :opened)"
        ), {"tid": str(nsc_tenant), "aid": str(acme_id),
            "opened": datetime.combine(today - timedelta(days=8), time(9, 2), tzinfo=timezone.utc)})

        # Usage: 90d history, baseline ~412/day, last 14 days ~284/day (−31%).
        rng = random.Random(42)
        for offset in range(90, 0, -1):
            day = today - timedelta(days=offset)
            base = 284 if offset <= 14 else 412
            value = base + rng.randint(-12, 12)
            session.execute(text(
                "INSERT INTO usage_metric_daily (tenant_id, account_id, metric, date, value, user_count)"
                " VALUES (:tid, :aid, 'core_actions', :d, :v, :u)"
                " ON CONFLICT DO NOTHING"
            ), {"tid": str(nsc_tenant), "aid": str(acme_id), "d": day, "v": value,
                "u": 29 if offset <= 14 else 41})

        audit.record(session, tenant_id=nsc_tenant, actor_type="system", actor_id="seed",
                     action="tenant.seeded", payload={"accounts": 2})

    # Second tenant — exists to prove isolation, carries one account.
    with tenant_session(other_tenant) as session:
        session.execute(text(
            "INSERT INTO tenant (id, name, region) VALUES (:id, 'OtherCo (isolation fixture)', 'us')"
        ), {"id": str(other_tenant)})
        session.execute(text(
            "INSERT INTO account (tenant_id, name, domains, arr_cents, renewal_date)"
            " VALUES (:tid, 'Zenith Corp', ARRAY['zenith.example'], 5000000, :renewal)"
        ), {"tid": str(other_tenant), "renewal": today + timedelta(days=60)})
        audit.record(session, tenant_id=other_tenant, actor_type="system", actor_id="seed",
                     action="tenant.seeded", payload={"accounts": 1})

    return {"nsc_tenant": str(nsc_tenant), "other_tenant": str(other_tenant),
            "acme_account": str(acme_id), "beta_account": str(beta_id),
            "csm_user": str(csm_id), "today": today.isoformat()}


if __name__ == "__main__":
    from .migrate import run_migrations

    run_migrations()
    ids = seed_demo()
    print("seeded:", ids)

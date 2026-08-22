"""Tenant-isolation tests — the CI leak gate (docs/12 §12.1).

These tests connect as the table OWNER (worst case): FORCE ROW LEVEL SECURITY
must still hold. Any new tenant-scoped table must appear in TENANT_TABLES.
"""

import uuid

import pytest
from sqlalchemy import text

from rig.db import tenant_session, untenanted_session

TENANT_TABLES = [
    "tenant", "app_user", "account", "invoice", "support_ticket",
    "usage_metric_daily", "signal", "evidence_object", "evidence_citation",
    "score", "score_component", "audit_event",
    # 0002
    "data_source", "sync_run", "raw_record", "contact", "opportunity",
    "source_link", "identity_candidate",
    # 0003
    "insight", "insight_transition", "feedback_event", "data_quality_issue",
    # 0004
    "writeback_request", "notification", "ai_model_run",
    # 0005
    "exec_brief",
]


def test_every_tenant_table_has_forced_rls(database):
    with untenanted_session() as s:
        rows = s.execute(text(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class"
            " WHERE relname = ANY(:tables)"
        ), {"tables": TENANT_TABLES}).all()
    assert len(rows) == len(TENANT_TABLES)
    for relname, rls, forced in rows:
        assert rls and forced, f"{relname} missing ENABLE/FORCE ROW LEVEL SECURITY"


def test_no_tenant_scoped_table_missing_from_gate(database):
    """Fail if someone adds a table with tenant_id but forgets this test list."""
    with untenanted_session() as s:
        rows = s.execute(text(
            "SELECT DISTINCT table_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND column_name = 'tenant_id'"
        )).scalars().all()
    missing = set(rows) - set(TENANT_TABLES)
    assert not missing, f"tables with tenant_id not covered by RLS gate: {missing}"


def test_cross_tenant_reads_are_blocked(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        ids = {str(i) for i in s.execute(text("SELECT id FROM account")).scalars().all()}
        names = s.execute(text("SELECT name FROM account")).scalars().all()
    assert seeded["acme_account"] in ids
    assert "Zenith Corp" not in names

    with tenant_session(seeded["other_tenant"]) as s:
        names = s.execute(text("SELECT name FROM account")).scalars().all()
    assert names == ["Zenith Corp"]


def test_no_context_means_no_rows(seeded):
    with untenanted_session() as s:
        for table in ["account", "signal", "audit_event", "tenant"]:
            count = s.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            assert count == 0, f"{table} leaked {count} rows without tenant context"


def test_cannot_write_into_another_tenant(seeded):
    """WITH CHECK must reject rows whose tenant_id differs from the session tenant."""
    with pytest.raises(Exception) as excinfo:
        with tenant_session(seeded["nsc_tenant"]) as s:
            s.execute(text(
                "INSERT INTO account (tenant_id, name) VALUES (:tid, 'smuggled')"
            ), {"tid": seeded["other_tenant"]})
    assert "row-level security" in str(excinfo.value).lower()


def test_cross_tenant_id_probe_returns_nothing(seeded):
    """Knowing another tenant's account id must not make it readable."""
    with tenant_session(seeded["other_tenant"]) as s:
        zenith_id = s.execute(text("SELECT id FROM account LIMIT 1")).scalar_one()
    with tenant_session(seeded["nsc_tenant"]) as s:
        row = s.execute(text("SELECT * FROM account WHERE id = :id"),
                        {"id": str(zenith_id)}).one_or_none()
    assert row is None


def test_unknown_tenant_context_sees_nothing(seeded):
    with tenant_session(uuid.uuid4()) as s:
        assert s.execute(text("SELECT count(*) FROM account")).scalar_one() == 0

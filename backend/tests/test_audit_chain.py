"""Audit log: append-only + per-tenant hash chain integrity."""

import pytest
from sqlalchemy import text

from rig import audit
from rig.db import tenant_session


def test_chain_links_and_verifies(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        for i in range(3):
            audit.record(s, tenant_id=tid, actor_type="user", actor_id="u_test",
                         action=f"test.event.{i}", payload={"i": i})
    with tenant_session(tid) as s:
        intact, checked = audit.verify_chain(s, tid)
        assert intact and checked >= 4  # seed event + 3

        rows = s.execute(text(
            "SELECT prev_hash, hash FROM audit_event WHERE tenant_id = :tid ORDER BY seq"
        ), {"tid": tid}).all()
    assert rows[0][0] == "genesis"
    for prev_row, row in zip(rows, rows[1:]):
        assert row[0] == prev_row[1]


def test_audit_is_append_only(seeded):
    tid = seeded["nsc_tenant"]
    for stmt in [
        "UPDATE audit_event SET action = 'tampered' WHERE tenant_id = :tid",
        "DELETE FROM audit_event WHERE tenant_id = :tid",
    ]:
        with pytest.raises(Exception) as excinfo:
            with tenant_session(tid) as s:
                s.execute(text(stmt), {"tid": tid})
        # blocked either by revoked privileges (rig_app) or the trigger (owner)
        message = str(excinfo.value)
        assert "append-only" in message or "permission denied" in message


def test_chains_are_per_tenant(seeded):
    """Each tenant's chain starts at genesis independently."""
    with tenant_session(seeded["other_tenant"]) as s:
        first = s.execute(text(
            "SELECT prev_hash FROM audit_event WHERE tenant_id = :tid ORDER BY seq LIMIT 1"
        ), {"tid": seeded["other_tenant"]}).scalar_one()
    assert first == "genesis"

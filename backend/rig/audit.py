"""Audit log writer and chain verifier.

The hash chain itself is computed by a database trigger (see 0001_init.sql) so
application code cannot produce an unchained row; this module writes events
and verifies chain integrity.
"""

import hashlib
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def record(
    session: Session,
    *,
    tenant_id: UUID | str,
    actor_type: str,
    actor_id: str,
    action: str,
    object_type: str | None = None,
    object_id: str | None = None,
    payload: dict | None = None,
) -> None:
    session.execute(
        text(
            "INSERT INTO audit_event (tenant_id, actor_type, actor_id, action,"
            " object_type, object_id, payload)"
            " VALUES (:tenant_id, :actor_type, :actor_id, :action,"
            " :object_type, :object_id, CAST(:payload AS jsonb))"
        ),
        {
            "tenant_id": str(tenant_id),
            "actor_type": actor_type,
            "actor_id": actor_id,
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "payload": json.dumps(payload or {}, sort_keys=True),
        },
    )


def verify_chain(session: Session, tenant_id: UUID | str) -> tuple[bool, int]:
    """Re-walk the tenant's chain; returns (intact, rows_checked)."""
    rows = session.execute(
        text(
            "SELECT tenant_id::text, actor_type, actor_id, action,"
            " COALESCE(object_type,''), COALESCE(object_id,''), payload::text,"
            " occurred_at::text, prev_hash, hash"
            " FROM audit_event WHERE tenant_id = :tid ORDER BY seq"
        ),
        {"tid": str(tenant_id)},
    ).fetchall()
    expected_prev = "genesis"
    for row in rows:
        (tid, actor_type, actor_id, action, object_type, object_id,
         payload, occurred_at, prev_hash, row_hash) = row
        if prev_hash != expected_prev:
            return False, len(rows)
        material = "|".join(
            [prev_hash, tid, actor_type, actor_id, action, object_type, object_id, payload, occurred_at]
        )
        if hashlib.sha256(material.encode()).hexdigest() != row_hash:
            return False, len(rows)
        expected_prev = row_hash
    return True, len(rows)

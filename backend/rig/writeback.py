"""Write-back framework (docs/06, docs/15 WF-19).

Nothing RIG does mutates an external system without: an explicit proposal with
a previewable diff, a human approval, an idempotent execution, and audit
events at every step. Rejection is terminal; execution is guarded on the
approved state and replays return the stored result instead of re-writing.
"""

import json
import uuid
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import audit


class WritebackError(Exception):
    pass


class HubSpotWriteClient(Protocol):
    def create_task(self, payload: dict) -> dict: ...          # returns {"id": ...}
    def update_company(self, company_id: str, properties: dict) -> dict: ...


def propose_task(session: Session, tenant_id: str, *, insight_id: str, title: str,
                 due_date: str | None, proposed_by: str) -> str:
    insight = session.execute(text(
        "SELECT i.account_id, a.name AS account_name FROM insight i"
        " JOIN account a ON a.id = i.account_id WHERE i.id = :id"
    ), {"id": str(insight_id)}).mappings().one_or_none()
    if insight is None:
        raise LookupError("insight not found")

    payload = {"hs_task_subject": title, "hs_task_type": "TODO",
               "hs_timestamp": due_date, "rig_insight_id": str(insight_id)}
    request_id = session.execute(text(
        "INSERT INTO writeback_request (tenant_id, connector_type, operation, target_ref,"
        " payload, preview, proposed_by, idempotency_key, insight_id, account_id)"
        " VALUES (:tid, 'hubspot', 'create_task', CAST(:target AS jsonb),"
        " CAST(:payload AS jsonb), CAST(:preview AS jsonb), :by, :ikey, :iid, :aid)"
        " RETURNING id"
    ), {"tid": tenant_id,
        "target": json.dumps({"object_type": "task", "create": True}),
        "payload": json.dumps(payload),
        "preview": json.dumps({
            "before": None,
            "after": {"object": "HubSpot task", "account": insight["account_name"],
                      "title": title, "due": due_date},
        }),
        "by": proposed_by,
        "ikey": f"task:{insight_id}:{uuid.uuid4().hex[:8]}",
        "iid": str(insight_id), "aid": str(insight["account_id"])}).scalar_one()
    audit.record(session, tenant_id=tenant_id, actor_type="user", actor_id=proposed_by,
                 action="writeback.propose", object_type="writeback_request",
                 object_id=str(request_id), payload={"operation": "create_task"})
    return str(request_id)


def approve(session: Session, tenant_id: str, request_id: UUID | str, *, approved_by: str) -> None:
    updated = session.execute(text(
        "UPDATE writeback_request SET state = 'approved', approved_by = :by,"
        " approved_at = now() WHERE id = :id AND state = 'proposed'"
    ), {"by": approved_by, "id": str(request_id)}).rowcount
    if not updated:
        raise WritebackError("request not found or not in proposed state")
    audit.record(session, tenant_id=tenant_id, actor_type="user", actor_id=approved_by,
                 action="writeback.approve", object_type="writeback_request",
                 object_id=str(request_id))


def reject(session: Session, tenant_id: str, request_id: UUID | str, *, rejected_by: str,
           reason: str | None = None) -> None:
    updated = session.execute(text(
        "UPDATE writeback_request SET state = 'rejected', rejected_by = :by,"
        " reject_reason = :reason WHERE id = :id AND state IN ('proposed', 'approved')"
    ), {"by": rejected_by, "reason": reason, "id": str(request_id)}).rowcount
    if not updated:
        raise WritebackError("request not found or not rejectable")
    audit.record(session, tenant_id=tenant_id, actor_type="user", actor_id=rejected_by,
                 action="writeback.reject", object_type="writeback_request",
                 object_id=str(request_id), payload={"reason": reason})


def execute(session: Session, tenant_id: str, request_id: UUID | str,
            client: HubSpotWriteClient, *, actor_id: str) -> dict:
    request = session.execute(text(
        "SELECT * FROM writeback_request WHERE id = :id"
    ), {"id": str(request_id)}).mappings().one_or_none()
    if request is None:
        raise WritebackError("request not found")
    if request["state"] == "executed":       # idempotent replay
        return dict(request["external_result"])
    if request["state"] != "approved":
        raise WritebackError(f"cannot execute from state '{request['state']}' — approval required")

    payload_hash = None
    try:
        if request["operation"] == "create_task":
            result = client.create_task(dict(request["payload"]))
        elif request["operation"] == "update_field":
            target = request["target_ref"]
            result = client.update_company(target["source_record_id"], dict(request["payload"]))
        else:
            raise WritebackError(f"unknown operation {request['operation']}")
    except WritebackError:
        raise
    except Exception as exc:
        session.execute(text(
            "UPDATE writeback_request SET state = 'failed', error = :err WHERE id = :id"
        ), {"err": str(exc)[:500], "id": str(request_id)})
        audit.record(session, tenant_id=tenant_id, actor_type="system", actor_id=actor_id,
                     action="writeback.failed", object_type="writeback_request",
                     object_id=str(request_id), payload={"error": str(exc)[:200]})
        raise WritebackError(f"external write failed: {exc}") from exc

    import hashlib
    payload_hash = hashlib.sha256(
        json.dumps(dict(request["payload"]), sort_keys=True).encode()
    ).hexdigest()
    session.execute(text(
        "UPDATE writeback_request SET state = 'executed', executed_at = now(),"
        " external_result = CAST(:result AS jsonb) WHERE id = :id"
    ), {"result": json.dumps(result), "id": str(request_id)})
    audit.record(session, tenant_id=tenant_id, actor_type="system", actor_id=actor_id,
                 action="writeback.execute", object_type="writeback_request",
                 object_id=str(request_id),
                 payload={"payload_hash": payload_hash, "external_id": result.get("id")})
    return result


class HttpHubSpotWriteClient:
    """Real HubSpot write client (thin I/O layer)."""

    def __init__(self, access_token: str):
        import httpx

        self._http = httpx.Client(
            base_url="https://api.hubapi.com",
            headers={"Authorization": f"Bearer {access_token}"}, timeout=30,
        )

    def create_task(self, payload: dict) -> dict:
        properties = {k: v for k, v in payload.items() if v is not None}
        response = self._http.post("/crm/v3/objects/tasks", json={"properties": properties})
        response.raise_for_status()
        return {"id": response.json()["id"]}

    def update_company(self, company_id: str, properties: dict) -> dict:
        response = self._http.patch(f"/crm/v3/objects/companies/{company_id}",
                                    json={"properties": properties})
        response.raise_for_status()
        return {"id": response.json()["id"]}


# Configured at startup; None = write-backs can be proposed/approved but not
# executed (execute returns a clear error), keeping the queue reviewable.
default_write_client: HubSpotWriteClient | None = None

"""Zendesk connector (support — docs/11 Phase 1).

Streams: organizations → account resolution (secondary),
tickets → support_ticket. Tickets whose organization is unresolved are
deferred (same contract as Stripe invoices). Priority mapping is validated at
setup per docs/11; unknown priorities normalize to 'normal' and are counted.
"""

from datetime import datetime
from typing import Iterable, Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..resolution import resolve_account
from .base import ApplyResult, SourceRecord

PRIORITY_MAP = {"low": "low", "normal": "normal", "high": "high", "urgent": "critical"}
OPEN_STATUSES = {"new": "open", "open": "open", "pending": "pending",
                 "hold": "pending", "solved": "solved", "closed": "closed"}


class ZendeskClient(Protocol):
    def list_organizations(self, updated_after: str | None) -> Iterable[dict]: ...
    def list_tickets(self, updated_after: str | None) -> Iterable[dict]: ...


class ZendeskConnector:
    source_system = "zendesk"
    streams = ["organizations", "tickets"]

    def __init__(self, client: ZendeskClient):
        self.client = client

    def fetch(self, stream: str, cursor: str | None) -> Iterable[SourceRecord]:
        lister = {"organizations": self.client.list_organizations,
                  "tickets": self.client.list_tickets}[stream]
        for obj in lister(cursor):
            yield SourceRecord(
                stream=stream,
                source_record_id=str(obj["id"]),
                payload=obj,
                cursor_value=obj.get("updated_at"),
            )

    def apply(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        if record.stream == "organizations":
            return self._apply_org(session, tenant_id, record)
        return self._apply_ticket(session, tenant_id, record)

    def _apply_org(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        payload = record.payload
        domains = payload.get("domain_names") or []
        resolution = resolve_account(
            session, tenant_id,
            source_system=self.source_system, source_record_id=record.source_record_id,
            name=payload.get("name") or f"Zendesk org {record.source_record_id}",
            domain=domains[0] if domains else None, primary=False,
        )
        return ApplyResult(resolution.outcome)

    def _apply_ticket(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        payload = record.payload
        org_id = payload.get("organization_id")
        account_id = None
        if org_id:
            account_id = session.execute(text(
                "SELECT entity_id FROM source_link WHERE source_system = 'zendesk'"
                " AND source_record_id = :rec AND entity_type = 'account' AND status = 'linked'"
            ), {"rec": str(org_id)}).scalar_one_or_none()
        if account_id is None:
            return ApplyResult("deferred", {"organization_id": org_id})

        status = OPEN_STATUSES.get(payload.get("status", "open"), "open")
        session.execute(text(
            "INSERT INTO support_ticket (tenant_id, account_id, source_system,"
            " source_record_id, subject, priority, status, escalated, opened_at, resolved_at)"
            " VALUES (:tid, :aid, 'zendesk', :rec, :subject, :priority, :status,"
            " :escalated, :opened, :resolved)"
            " ON CONFLICT (tenant_id, source_system, source_record_id)"
            " DO UPDATE SET subject = EXCLUDED.subject, priority = EXCLUDED.priority,"
            "   status = EXCLUDED.status, escalated = EXCLUDED.escalated,"
            "   resolved_at = EXCLUDED.resolved_at"
        ), {"tid": tenant_id, "aid": str(account_id), "rec": record.source_record_id,
            "subject": payload.get("subject", "(no subject)"),
            "priority": PRIORITY_MAP.get(payload.get("priority") or "normal", "normal"),
            "status": status,
            "escalated": bool(payload.get("escalated", False)),
            "opened": datetime.fromisoformat(payload["created_at"]),
            "resolved": datetime.fromisoformat(payload["solved_at"])
                        if payload.get("solved_at") else None})
        return ApplyResult("updated", {"account_id": str(account_id)})


class HttpZendeskClient:
    """Real Zendesk API client (thin I/O layer; incremental export API)."""

    def __init__(self, subdomain: str, email: str, api_token: str):
        import httpx

        self._http = httpx.Client(
            base_url=f"https://{subdomain}.zendesk.com/api/v2",
            auth=(f"{email}/token", api_token), timeout=30,
        )

    def _pages(self, path: str, key: str, params: dict) -> Iterable[dict]:
        url: str | None = path
        while url:
            response = self._http.get(url, params=params if url == path else None)
            response.raise_for_status()
            data = response.json()
            yield from data.get(key, [])
            url = data.get("next_page")

    def list_organizations(self, updated_after=None):
        return self._pages("/organizations.json", "organizations", {})

    def list_tickets(self, updated_after=None):
        params = {}
        if updated_after:
            params["start_time"] = updated_after
        return self._pages("/incremental/tickets.json", "tickets", params)

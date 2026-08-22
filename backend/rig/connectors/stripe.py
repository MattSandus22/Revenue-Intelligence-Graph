"""Stripe connector (billing — docs/11 Phase 1).

Streams: customers → account resolution (secondary: never mints accounts),
invoices → invoice table. Invoices for customers not yet resolved are
DEFERRED (raw payload retained) and attach automatically on a later run once
a human accepts the identity candidate — the behavior specified in docs/11.
"""

from datetime import date
from typing import Iterable, Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..resolution import resolve_account
from .base import ApplyResult, SourceRecord


class StripeClient(Protocol):
    def list_customers(self, created_after: str | None) -> Iterable[dict]: ...
    def list_invoices(self, created_after: str | None) -> Iterable[dict]: ...


class StripeConnector:
    source_system = "stripe"
    streams = ["customers", "invoices"]

    def __init__(self, client: StripeClient):
        self.client = client

    def fetch(self, stream: str, cursor: str | None) -> Iterable[SourceRecord]:
        lister = {"customers": self.client.list_customers,
                  "invoices": self.client.list_invoices}[stream]
        for obj in lister(cursor):
            yield SourceRecord(
                stream=stream,
                source_record_id=str(obj["id"]),
                payload=obj,
                cursor_value=str(obj.get("created", "")) or None,
            )

    def apply(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        if record.stream == "customers":
            return self._apply_customer(session, tenant_id, record)
        return self._apply_invoice(session, tenant_id, record)

    def _apply_customer(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        payload = record.payload
        email = payload.get("email") or ""
        domain = email.split("@", 1)[1].lower() if "@" in email else None
        resolution = resolve_account(
            session, tenant_id,
            source_system=self.source_system, source_record_id=record.source_record_id,
            name=payload.get("name") or email or f"Stripe {record.source_record_id}",
            domain=domain, primary=False,
        )
        return ApplyResult(resolution.outcome)

    def _apply_invoice(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        payload = record.payload
        account_id = session.execute(text(
            "SELECT entity_id FROM source_link WHERE source_system = 'stripe'"
            " AND source_record_id = :rec AND entity_type = 'account' AND status = 'linked'"
        ), {"rec": str(payload["customer"])}).scalar_one_or_none()
        if account_id is None:
            return ApplyResult("deferred", {"customer": payload["customer"]})

        status = payload.get("status", "open")
        if status == "open" and payload.get("due_date") and \
                date.fromisoformat(payload["due_date"]) < date.today():
            status = "overdue"
        session.execute(text(
            "INSERT INTO invoice (tenant_id, account_id, source_system, source_record_id,"
            " amount_cents, issued_at, due_at, paid_at, status)"
            " VALUES (:tid, :aid, 'stripe', :rec, :amount, :issued, :due, :paid, :status)"
            " ON CONFLICT (tenant_id, source_system, source_record_id)"
            " DO UPDATE SET amount_cents = EXCLUDED.amount_cents, due_at = EXCLUDED.due_at,"
            "   paid_at = EXCLUDED.paid_at, status = EXCLUDED.status"
        ), {"tid": tenant_id, "aid": str(account_id), "rec": record.source_record_id,
            "amount": payload["amount_due"],
            "issued": date.fromisoformat(payload["created_date"]),
            "due": date.fromisoformat(payload["due_date"]),
            "paid": date.fromisoformat(payload["paid_date"]) if payload.get("paid_date") else None,
            "status": status})
        return ApplyResult("updated", {"account_id": str(account_id)})


class HttpStripeClient:
    """Real Stripe API client (thin I/O layer)."""

    BASE = "https://api.stripe.com/v1"

    def __init__(self, api_key: str):
        import httpx

        self._http = httpx.Client(base_url=self.BASE, auth=(api_key, ""), timeout=30)

    def _list(self, path: str, created_after: str | None) -> Iterable[dict]:
        params: dict = {"limit": 100}
        if created_after:
            params["created[gt]"] = created_after
        while True:
            response = self._http.get(path, params=params)
            response.raise_for_status()
            data = response.json()
            yield from data["data"]
            if not data.get("has_more"):
                return
            params["starting_after"] = data["data"][-1]["id"]

    def list_customers(self, created_after=None):
        return self._list("/customers", created_after)

    def list_invoices(self, created_after=None):
        return self._list("/invoices", created_after)

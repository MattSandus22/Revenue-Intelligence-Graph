"""HubSpot connector (primary CRM — docs/11 Phase 1).

Streams: companies → canonical accounts (primary: may mint accounts),
contacts → contact table, deals → opportunity table.

The API client is an injected protocol: `HttpHubSpotClient` talks to the real
CRM v3 API; tests inject a fixture client. Field mapping defaults below are
overridable per tenant via data_source.config["mapping"].
"""

from datetime import date
from typing import Iterable, Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..resolution import resolve_account
from .base import ApplyResult, SourceRecord

DEFAULT_COMPANY_MAPPING = {
    "name": "name",
    "domain": "domain",
    "segment": "segment__c",
    "tier": "tier__c",
    "arr_cents": "arr__c",             # dollars in source; converted below
    "renewal_date": "renewal_date__c",
}


class HubSpotClient(Protocol):
    def list_companies(self, updated_after: str | None) -> Iterable[dict]: ...
    def list_contacts(self, updated_after: str | None) -> Iterable[dict]: ...
    def list_deals(self, updated_after: str | None) -> Iterable[dict]: ...


class HubSpotConnector:
    source_system = "hubspot"
    streams = ["companies", "contacts", "deals"]

    def __init__(self, client: HubSpotClient, mapping: dict | None = None):
        self.client = client
        self.mapping = {**DEFAULT_COMPANY_MAPPING, **(mapping or {})}

    def fetch(self, stream: str, cursor: str | None) -> Iterable[SourceRecord]:
        lister = {
            "companies": self.client.list_companies,
            "contacts": self.client.list_contacts,
            "deals": self.client.list_deals,
        }[stream]
        for obj in lister(cursor):
            yield SourceRecord(
                stream=stream,
                source_record_id=str(obj["id"]),
                payload=obj,
                cursor_value=obj.get("updatedAt"),
            )

    # ------------------------------------------------------------------
    def apply(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        handler = {
            "companies": self._apply_company,
            "contacts": self._apply_contact,
            "deals": self._apply_deal,
        }[record.stream]
        return handler(session, tenant_id, record)

    def _apply_company(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        props = record.payload.get("properties", {})
        m = self.mapping
        name = props.get(m["name"]) or f"HubSpot company {record.source_record_id}"
        domain = props.get(m["domain"]) or None
        arr_raw = props.get(m["arr_cents"])
        renewal_raw = props.get(m["renewal_date"])
        extra = {
            "segment": props.get(m["segment"]),
            "tier": props.get(m["tier"]),
            "arr_cents": int(float(arr_raw) * 100) if arr_raw else None,
            "renewal_date": date.fromisoformat(renewal_raw) if renewal_raw else None,
        }
        resolution = resolve_account(
            session, tenant_id,
            source_system=self.source_system, source_record_id=record.source_record_id,
            name=name, domain=domain, primary=True, extra_fields=extra,
        )
        if resolution.outcome == "already_linked":
            # Incremental update of CRM-governed fields on the canonical account.
            # (Field-level source-of-truth rules — docs/06 A.1 — arrive with the
            # provenance layer; CRM wins for these fields in Sprint 2.)
            session.execute(text(
                "UPDATE account SET name = :name,"
                " segment = COALESCE(:segment, segment), tier = COALESCE(:tier, tier),"
                " renewal_date = COALESCE(:renewal, renewal_date), updated_at = now()"
                " WHERE id = :id"
            ), {"name": name, "segment": extra["segment"], "tier": extra["tier"],
                "renewal": extra["renewal_date"], "id": str(resolution.account_id)})
            return ApplyResult("updated", {"account_id": str(resolution.account_id)})
        return ApplyResult(resolution.outcome, {"account_id": str(resolution.account_id)
                                                if resolution.account_id else None})

    def _apply_contact(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        props = record.payload.get("properties", {})
        company_id = record.payload.get("company_id")  # from associations
        account_id = None
        if company_id:
            account_id = session.execute(text(
                "SELECT entity_id FROM source_link WHERE source_system = 'hubspot'"
                " AND source_record_id = :rec AND entity_type = 'account' AND status = 'linked'"
            ), {"rec": str(company_id)}).scalar_one_or_none()
        name = " ".join(filter(None, [props.get("firstname"), props.get("lastname")])) or "Unknown"
        session.execute(text(
            "INSERT INTO contact (tenant_id, account_id, name, email, title,"
            " source_system, source_record_id)"
            " VALUES (:tid, :aid, :name, :email, :title, 'hubspot', :rec)"
            " ON CONFLICT (tenant_id, source_system, source_record_id)"
            " DO UPDATE SET account_id = COALESCE(EXCLUDED.account_id, contact.account_id),"
            "   name = EXCLUDED.name, email = EXCLUDED.email, title = EXCLUDED.title,"
            "   updated_at = now()"
        ), {"tid": tenant_id, "aid": str(account_id) if account_id else None,
            "name": name, "email": props.get("email"), "title": props.get("jobtitle"),
            "rec": record.source_record_id})
        return ApplyResult("updated" if account_id else "deferred")

    def _apply_deal(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        props = record.payload.get("properties", {})
        company_id = record.payload.get("company_id")
        account_id = None
        if company_id:
            account_id = session.execute(text(
                "SELECT entity_id FROM source_link WHERE source_system = 'hubspot'"
                " AND source_record_id = :rec AND entity_type = 'account' AND status = 'linked'"
            ), {"rec": str(company_id)}).scalar_one_or_none()
        amount = props.get("amount")
        close_date = props.get("closedate")
        session.execute(text(
            "INSERT INTO opportunity (tenant_id, account_id, name, amount_cents, stage,"
            " opp_type, close_date, next_step, source_system, source_record_id)"
            " VALUES (:tid, :aid, :name, :amount, :stage, :otype, :close, :next,"
            " 'hubspot', :rec)"
            " ON CONFLICT (tenant_id, source_system, source_record_id)"
            " DO UPDATE SET account_id = COALESCE(EXCLUDED.account_id, opportunity.account_id),"
            "   name = EXCLUDED.name, amount_cents = EXCLUDED.amount_cents,"
            "   stage = EXCLUDED.stage, close_date = EXCLUDED.close_date,"
            "   next_step = EXCLUDED.next_step, updated_at = now()"
        ), {"tid": tenant_id, "aid": str(account_id) if account_id else None,
            "name": props.get("dealname", f"Deal {record.source_record_id}"),
            "amount": int(float(amount) * 100) if amount else None,
            "stage": props.get("dealstage"),
            "otype": props.get("deal_type", "new"),
            "close": date.fromisoformat(close_date) if close_date else None,
            "next": props.get("next_step"),
            "rec": record.source_record_id})
        return ApplyResult("updated" if account_id else "deferred")


class HttpHubSpotClient:
    """Real CRM v3 API client (thin I/O layer; fixture clients cover logic tests).

    Rate limiting: honors 429 Retry-After with capped exponential backoff, per
    the framework spec (docs/11 §11.0).
    """

    BASE = "https://api.hubapi.com"
    PAGE_SIZE = 100
    PROPERTIES = {
        "companies": ["name", "domain", "segment__c", "tier__c", "arr__c", "renewal_date__c"],
        "contacts": ["firstname", "lastname", "email", "jobtitle"],
        "deals": ["dealname", "amount", "dealstage", "closedate", "deal_type", "next_step"],
    }

    def __init__(self, access_token: str):
        import httpx

        self._http = httpx.Client(
            base_url=self.BASE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )

    def _list(self, object_type: str, updated_after: str | None) -> Iterable[dict]:
        import time

        after = None
        while True:
            if updated_after:
                body = {
                    "limit": self.PAGE_SIZE,
                    "properties": self.PROPERTIES[object_type],
                    "filterGroups": [{"filters": [{
                        "propertyName": "hs_lastmodifieddate",
                        "operator": "GT", "value": updated_after}]}],
                }
                if after:
                    body["after"] = after
                response = self._http.post(f"/crm/v3/objects/{object_type}/search", json=body)
            else:
                params = {"limit": self.PAGE_SIZE,
                          "properties": ",".join(self.PROPERTIES[object_type])}
                if after:
                    params["after"] = after
                response = self._http.get(f"/crm/v3/objects/{object_type}", params=params)

            if response.status_code == 429:
                time.sleep(min(float(response.headers.get("Retry-After", "2")), 30))
                continue
            response.raise_for_status()
            data = response.json()
            yield from data.get("results", [])
            after = data.get("paging", {}).get("next", {}).get("after")
            if not after:
                return

    def list_companies(self, updated_after=None):
        return self._list("companies", updated_after)

    def list_contacts(self, updated_after=None):
        return self._list("contacts", updated_after)

    def list_deals(self, updated_after=None):
        return self._list("deals", updated_after)

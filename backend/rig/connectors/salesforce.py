"""Salesforce connector (second CRM — docs/17 V1, execution doc 2 wk5).

Streams: accounts → canonical accounts (primary CRM: may mint accounts),
contacts → contact table, opportunities → opportunity table,
opportunity_history → opportunity_field_history (Salesforce
OpportunityFieldHistory), which powers the stage-stalled (O2) and
close-date-slip (O5) signals HubSpot's shallow API can't feed.

Shares the canonical resolution + account-governed-field behavior with the
HubSpot connector by design (docs/16 CRM abstraction). The SOQL client is an
injected protocol; tests use a fixture client.
"""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Protocol
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..resolution import resolve_account
from .base import ApplyResult, SourceRecord

# Salesforce forecast categories → canonical forecast_category.
FORECAST_MAP = {
    "Omitted": "omitted", "Pipeline": "pipeline", "BestCase": "best_case",
    "Commit": "commit", "Closed": "closed",
    # human-facing ForecastCategoryName variants
    "Best Case": "best_case", "Forecast": "commit",
}

DEFAULT_ACCOUNT_MAPPING = {
    "name": "Name", "domain": "Website", "segment": "Segment__c",
    "tier": "Tier__c", "arr_cents": "ARR__c", "renewal_date": "Renewal_Date__c",
}


class SalesforceClient(Protocol):
    def query_accounts(self, updated_after: str | None) -> Iterable[dict]: ...
    def query_contacts(self, updated_after: str | None) -> Iterable[dict]: ...
    def query_opportunities(self, updated_after: str | None) -> Iterable[dict]: ...
    def query_opportunity_history(self, updated_after: str | None) -> Iterable[dict]: ...


def _domain_from_website(website: str | None) -> str | None:
    if not website:
        return None
    # urlparse needs a scheme to see the host; Website values are often bare.
    target = website if "://" in website else f"//{website}"
    host = (urlparse(target).hostname or "").lower()
    return host.removeprefix("www.") or None


def _to_cents(value) -> int | None:
    """Currency → integer cents without float rounding error (preserves 0)."""
    if value is None or value == "":
        return None
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class SalesforceConnector:
    source_system = "salesforce"
    # accounts before opportunities before history: later streams resolve
    # against links the earlier ones create.
    streams = ["accounts", "contacts", "opportunities", "opportunity_history"]

    def __init__(self, client: SalesforceClient, mapping: dict | None = None):
        self.client = client
        self.mapping = {**DEFAULT_ACCOUNT_MAPPING, **(mapping or {})}

    def fetch(self, stream: str, cursor: str | None) -> Iterable[SourceRecord]:
        lister = {
            "accounts": self.client.query_accounts,
            "contacts": self.client.query_contacts,
            "opportunities": self.client.query_opportunities,
            "opportunity_history": self.client.query_opportunity_history,
        }[stream]
        for obj in lister(cursor):
            # history rows key on their own Id; entities on LastModifiedDate
            cursor_value = obj.get("CreatedDate") if stream == "opportunity_history" \
                else obj.get("LastModifiedDate")
            yield SourceRecord(stream=stream, source_record_id=str(obj["Id"]),
                               payload=obj, cursor_value=cursor_value)

    def apply(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        return {
            "accounts": self._apply_account,
            "contacts": self._apply_contact,
            "opportunities": self._apply_opportunity,
            "opportunity_history": self._apply_history,
        }[record.stream](session, tenant_id, record)

    def _apply_account(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        p, m = record.payload, self.mapping
        name = p.get(m["name"]) or f"Salesforce account {record.source_record_id}"
        domain = _domain_from_website(p.get(m["domain"]))
        arr_raw, renewal_raw = p.get(m["arr_cents"]), p.get(m["renewal_date"])
        extra = {
            "segment": p.get(m["segment"]), "tier": p.get(m["tier"]),
            "arr_cents": _to_cents(arr_raw),
            "renewal_date": date.fromisoformat(renewal_raw[:10]) if renewal_raw else None,
        }
        resolution = resolve_account(
            session, tenant_id, source_system=self.source_system,
            source_record_id=record.source_record_id, name=name, domain=domain,
            primary=True, extra_fields=extra)
        if resolution.outcome == "already_linked":
            session.execute(text(
                "UPDATE account SET name = :name,"
                " segment = COALESCE(:segment, segment), tier = COALESCE(:tier, tier),"
                " renewal_date = COALESCE(:renewal, renewal_date), updated_at = now()"
                " WHERE id = :id"
            ), {"name": name, "segment": extra["segment"], "tier": extra["tier"],
                "renewal": extra["renewal_date"], "id": str(resolution.account_id)})
            return ApplyResult("updated", {"account_id": str(resolution.account_id)})
        return ApplyResult(resolution.outcome,
                           {"account_id": str(resolution.account_id) if resolution.account_id else None})

    def _account_for(self, session: Session, sfdc_account_id: str | None):
        if not sfdc_account_id:
            return None
        return session.execute(text(
            "SELECT entity_id FROM source_link WHERE source_system = 'salesforce'"
            " AND source_record_id = :rec AND entity_type = 'account' AND status = 'linked'"
        ), {"rec": str(sfdc_account_id)}).scalar_one_or_none()

    def _apply_contact(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        p = record.payload
        account_id = self._account_for(session, p.get("AccountId"))
        name = " ".join(filter(None, [p.get("FirstName"), p.get("LastName")])) or "Unknown"
        session.execute(text(
            "INSERT INTO contact (tenant_id, account_id, name, email, title,"
            " source_system, source_record_id)"
            " VALUES (:tid, :aid, :name, :email, :title, 'salesforce', :rec)"
            " ON CONFLICT (tenant_id, source_system, source_record_id)"
            " DO UPDATE SET account_id = COALESCE(EXCLUDED.account_id, contact.account_id),"
            "   name = EXCLUDED.name, email = EXCLUDED.email, title = EXCLUDED.title,"
            "   updated_at = now()"
        ), {"tid": tenant_id, "aid": str(account_id) if account_id else None,
            "name": name, "email": p.get("Email"), "title": p.get("Title"),
            "rec": record.source_record_id})
        return ApplyResult("updated" if account_id else "deferred")

    def _apply_opportunity(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        p = record.payload
        account_id = self._account_for(session, p.get("AccountId"))
        amount = p.get("Amount")
        close_date = p.get("CloseDate")
        opp_type = "renewal" if (p.get("Type") or "").lower().startswith("renewal") \
            else "expansion" if "existing" in (p.get("Type") or "").lower() else "new"
        session.execute(text(
            "INSERT INTO opportunity (tenant_id, account_id, name, amount_cents, stage,"
            " opp_type, close_date, next_step, forecast_category, owner_ref,"
            " source_system, source_record_id)"
            " VALUES (:tid, :aid, :name, :amount, :stage, :otype, :close, :next,"
            " :fcast, :owner, 'salesforce', :rec)"
            " ON CONFLICT (tenant_id, source_system, source_record_id)"
            " DO UPDATE SET account_id = COALESCE(EXCLUDED.account_id, opportunity.account_id),"
            "   name = EXCLUDED.name, amount_cents = EXCLUDED.amount_cents,"
            "   stage = EXCLUDED.stage, close_date = EXCLUDED.close_date,"
            "   next_step = EXCLUDED.next_step, forecast_category = EXCLUDED.forecast_category,"
            "   owner_ref = EXCLUDED.owner_ref, updated_at = now()"
        ), {"tid": tenant_id, "aid": str(account_id) if account_id else None,
            "name": p.get("Name", f"Opp {record.source_record_id}"),
            "amount": _to_cents(amount),
            "stage": p.get("StageName"), "otype": opp_type,
            "close": date.fromisoformat(close_date[:10]) if close_date else None,
            "next": p.get("NextStep"),
            "fcast": FORECAST_MAP.get(p.get("ForecastCategoryName") or p.get("ForecastCategory")),
            "owner": p.get("OwnerId"), "rec": record.source_record_id})
        self._replay_deferred_history(session, tenant_id, record.source_record_id)
        return ApplyResult("updated" if account_id else "deferred")

    def _replay_deferred_history(self, session: Session, tenant_id: str, sfdc_opp_id: str) -> None:
        # History rows that landed before their opportunity were deferred; now
        # that the opportunity exists, replay them from the raw landing zone
        # (idempotent — ON CONFLICT DO NOTHING in _apply_history).
        rows = session.execute(text(
            "SELECT payload FROM raw_record WHERE tenant_id = :tid"
            " AND stream = 'opportunity_history'"
            " AND payload->>'OpportunityId' = :opp"
        ), {"tid": tenant_id, "opp": sfdc_opp_id}).scalars().all()
        for payload in rows:
            self._apply_history(session, tenant_id, SourceRecord(
                stream="opportunity_history", source_record_id=str(payload["Id"]),
                payload=payload, cursor_value=payload.get("CreatedDate")))

    def _apply_history(self, session: Session, tenant_id: str, record: SourceRecord) -> ApplyResult:
        p = record.payload
        opp_id = session.execute(text(
            "SELECT id FROM opportunity WHERE source_system = 'salesforce'"
            " AND source_record_id = :rec"
        ), {"rec": str(p.get("OpportunityId"))}).scalar_one_or_none()
        if opp_id is None:
            return ApplyResult("deferred", {"opportunity": p.get("OpportunityId")})
        field = {"StageName": "stage", "CloseDate": "close_date", "Amount": "amount",
                 "ForecastCategoryName": "forecast_category"}.get(p.get("Field"))
        if field is None:
            return ApplyResult("skipped")
        session.execute(text(
            "INSERT INTO opportunity_field_history (tenant_id, opportunity_id, field,"
            " old_value, new_value, changed_at, source_system, source_record_id)"
            " VALUES (:tid, :oid, :field, :old, :new, :at, 'salesforce', :rec)"
            " ON CONFLICT (tenant_id, source_system, source_record_id) DO NOTHING"
        ), {"tid": tenant_id, "oid": str(opp_id), "field": field,
            "old": str(p.get("OldValue")) if p.get("OldValue") is not None else None,
            "new": str(p.get("NewValue")) if p.get("NewValue") is not None else None,
            "at": datetime.fromisoformat(p["CreatedDate"].replace("Z", "+00:00")),
            "rec": record.source_record_id})
        return ApplyResult("created", {"field": field})


def _validate_instance_url(instance_url: str) -> str:
    """Only HTTPS Salesforce-owned hosts — a token must never be sent elsewhere."""
    parsed = urlparse(instance_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        host.endswith(".salesforce.com") or host.endswith(".force.com")
    ):
        raise ValueError("instance_url must be an https://….salesforce.com or …"
                         ".force.com URL")
    return instance_url.rstrip("/")


class HttpSalesforceClient:
    """Real Salesforce REST/SOQL client (thin I/O layer).

    Uses an OAuth access token + instance URL; incremental queries filter on
    SystemModstamp/CreatedDate > cursor. Pagination via `nextRecordsUrl`.
    """

    def __init__(self, instance_url: str, access_token: str, api_version: str = "v60.0"):
        import httpx

        self._base = f"{_validate_instance_url(instance_url)}/services/data/{api_version}"
        self._http = httpx.Client(headers={"Authorization": f"Bearer {access_token}"}, timeout=30)

    def _soql(self, query: str) -> Iterable[dict]:
        import time

        url = f"{self._base}/query"
        params: dict | None = {"q": query}
        throttled = 0
        while url:
            response = self._http.get(url, params=params)
            if response.status_code == 429:
                throttled += 1
                if throttled > 5:
                    raise RuntimeError("Salesforce rate limit persisted after 5 retries")
                try:
                    retry_after = float(response.headers.get("Retry-After", "2"))
                except ValueError:
                    retry_after = 2.0
                time.sleep(max(1.0, min(retry_after, 30.0)))
                continue
            response.raise_for_status()
            data = response.json()
            yield from data.get("records", [])
            url = (f"{self._base.split('/services')[0]}{data['nextRecordsUrl']}"
                   if not data.get("done") and data.get("nextRecordsUrl") else None)
            params = None

    @staticmethod
    def _since(cursor: str | None, field: str) -> str:
        return f" WHERE {field} > {cursor}" if cursor else ""

    def query_accounts(self, updated_after=None):
        return self._soql(
            "SELECT Id, Name, Website, Segment__c, Tier__c, ARR__c, Renewal_Date__c,"
            " LastModifiedDate FROM Account" + self._since(updated_after, "LastModifiedDate"))

    def query_contacts(self, updated_after=None):
        return self._soql(
            "SELECT Id, FirstName, LastName, Email, Title, AccountId, LastModifiedDate"
            " FROM Contact" + self._since(updated_after, "LastModifiedDate"))

    def query_opportunities(self, updated_after=None):
        return self._soql(
            "SELECT Id, Name, Amount, StageName, Type, CloseDate, NextStep,"
            " ForecastCategoryName, OwnerId, AccountId, LastModifiedDate"
            " FROM Opportunity" + self._since(updated_after, "LastModifiedDate"))

    def query_opportunity_history(self, updated_after=None):
        return self._soql(
            "SELECT Id, OpportunityId, Field, OldValue, NewValue, CreatedDate"
            " FROM OpportunityFieldHistory" + self._since(updated_after, "CreatedDate")
            + " ORDER BY CreatedDate")

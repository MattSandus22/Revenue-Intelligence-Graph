"""Salesforce connector: canonical resolution parity with HubSpot, field
history → opportunity_field_history, and the O2/O5 signals it unlocks."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from rig.connectors.base import SyncRunner
from rig.connectors.factory import REQUIRED_FIELDS, build_connector
from rig.connectors.salesforce import SalesforceConnector
from rig.db import tenant_session
from rig.signals.engine import evaluate_account

from .fixture_clients import FixtureSalesforceClient

TODAY = date.today()
NOW = datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat()


SF_ACCOUNTS = [
    # domain-links to seeded Acme (acme.com)
    {"Id": "001A", "Name": "Acme Corporation", "Website": "https://www.acme.com",
     "Tier__c": "Enterprise", "ARR__c": "120000", "LastModifiedDate": "2026-08-01T00:00:00Z"},
    # mints a new account
    {"Id": "001B", "Name": "Umbrella Industries", "Website": "umbrella.example",
     "Segment__c": "Mid-Market", "Renewal_Date__c": "2027-01-15",
     "LastModifiedDate": "2026-08-02T00:00:00Z"},
]
SF_CONTACTS = [
    {"Id": "003A", "FirstName": "Dana", "LastName": "Reyes", "Email": "dana@acme.com",
     "Title": "VP Ops", "AccountId": "001A", "LastModifiedDate": "2026-08-03T00:00:00Z"},
]
SF_OPPS = [
    {"Id": "006A", "Name": "Umbrella expansion", "Amount": "80000", "StageName": "Proposal",
     "Type": "Existing Business", "CloseDate": "2026-10-01", "NextStep": "Legal review",
     "ForecastCategoryName": "Commit", "OwnerId": "005X", "AccountId": "001B",
     "LastModifiedDate": "2026-08-04T00:00:00Z"},
]
# stage entered 60d ago (stalled), close date pushed out twice (slip)
SF_HISTORY = [
    {"Id": "H1", "OpportunityId": "006A", "Field": "StageName", "OldValue": "Discovery",
     "NewValue": "Proposal", "CreatedDate": _iso(NOW - timedelta(days=60))},
    {"Id": "H2", "OpportunityId": "006A", "Field": "CloseDate", "OldValue": "2026-08-01",
     "NewValue": "2026-09-01", "CreatedDate": _iso(NOW - timedelta(days=40))},
    {"Id": "H3", "OpportunityId": "006A", "Field": "CloseDate", "OldValue": "2026-09-01",
     "NewValue": "2026-10-01", "CreatedDate": _iso(NOW - timedelta(days=10))},
]


def _make_source(session, tid, name="sf-main"):
    return session.execute(text(
        "INSERT INTO data_source (tenant_id, type, name) VALUES (:tid, 'salesforce', :n)"
        " RETURNING id"), {"tid": tid, "n": name}).scalar_one()


def test_factory_requires_instance_url_and_token():
    assert REQUIRED_FIELDS["salesforce"] == ["instance_url", "access_token"]
    connector = build_connector("salesforce",
                                {"instance_url": "https://x.my.salesforce.com",
                                 "access_token": "tok"})
    assert isinstance(connector, SalesforceConnector)


def test_backfill_resolves_and_lands_history(seeded):
    tid = seeded["nsc_tenant"]
    connector = SalesforceConnector(
        FixtureSalesforceClient(SF_ACCOUNTS, SF_CONTACTS, SF_OPPS, SF_HISTORY))
    with tenant_session(tid) as s:
        source_id = _make_source(s, tid)
        summary = SyncRunner().run(s, tid, source_id, connector)
        assert summary["status"] == "succeeded"
        # Acme domain-links; Umbrella minted (parity with HubSpot behavior)
        assert summary["stats"]["accounts"] == {"linked": 1, "created": 1}
        assert summary["stats"]["opportunity_history"] == {"created": 3}

        umbrella = s.execute(text("SELECT id FROM account WHERE name = 'Umbrella Industries'")
                             ).scalar_one()
        opp = s.execute(text(
            "SELECT account_id, forecast_category, opp_type, amount_cents FROM opportunity"
            " WHERE source_record_id = '006A'")).mappings().one()
        assert opp["account_id"] == umbrella
        assert opp["forecast_category"] == "commit"
        assert opp["opp_type"] == "expansion"       # 'Existing Business' → expansion
        assert opp["amount_cents"] == 8000000
        # contact attached to Acme
        contact_acct = s.execute(text(
            "SELECT account_id FROM contact WHERE source_record_id = '003A'")).scalar_one()
        assert str(contact_acct) == seeded["acme_account"]


def test_history_powers_stalled_and_slip_signals(seeded):
    tid = seeded["nsc_tenant"]
    connector = SalesforceConnector(
        FixtureSalesforceClient(SF_ACCOUNTS, SF_CONTACTS, SF_OPPS, SF_HISTORY))
    with tenant_session(tid) as s:
        source_id = _make_source(s, tid, "sf-signals")
        SyncRunner().run(s, tid, source_id, connector)
        umbrella = s.execute(text("SELECT id FROM account WHERE name = 'Umbrella Industries'")
                             ).scalar_one()
        summary = evaluate_account(s, tid, str(umbrella), today=TODAY)
        signals = {r["signal_type"]: dict(r) for r in s.execute(text(
            "SELECT signal_type, severity, magnitude FROM signal WHERE account_id = :aid"
            " AND state = 'active'"), {"aid": str(umbrella)}).mappings().all()}
    assert "opp_stage_stalled" in signals
    assert signals["opp_stage_stalled"]["severity"] == "high"     # $80k >= $50k
    assert signals["opp_stage_stalled"]["magnitude"]["days_in_stage"] >= 45
    assert "close_date_slip" in signals
    assert signals["close_date_slip"]["magnitude"]["slip_count"] == 2
    # every signal is evidence-cited (the universal invariant)
    with tenant_session(tid) as s:
        uncited = s.execute(text(
            "SELECT sg.signal_type FROM signal sg WHERE sg.account_id = :aid"
            " AND sg.state = 'active' AND NOT EXISTS (SELECT 1 FROM evidence_citation ec"
            " WHERE ec.claim_owner_type='signal' AND ec.claim_owner_id = sg.id)"
        ), {"aid": str(umbrella)}).scalars().all()
    assert uncited == []


def test_history_defers_before_its_opportunity_exists(seeded):
    """A history row whose opportunity hasn't synced yet defers, not errors."""
    tid = seeded["nsc_tenant"]
    orphan_history = [{"Id": "H9", "OpportunityId": "006ZZZ", "Field": "StageName",
                       "OldValue": "A", "NewValue": "B", "CreatedDate": _iso(NOW)}]
    connector = SalesforceConnector(FixtureSalesforceClient(history=orphan_history))
    with tenant_session(tid) as s:
        source_id = _make_source(s, tid, "sf-orphan")
        summary = SyncRunner().run(s, tid, source_id, connector)
    assert summary["status"] == "succeeded"
    assert summary["stats"]["opportunity_history"] == {"deferred": 1}


def test_incremental_only_fetches_newer(seeded):
    tid = seeded["nsc_tenant"]
    client = FixtureSalesforceClient(list(SF_ACCOUNTS))
    connector = SalesforceConnector(client)
    with tenant_session(tid) as s:
        source_id = _make_source(s, tid, "sf-incr")
        SyncRunner().run(s, tid, source_id, connector)          # backfill
    client.accounts.append(
        {"Id": "001C", "Name": "Wonka SF Distinct Co", "Website": "wonka-sf-distinct.example",
         "LastModifiedDate": "2026-08-20T00:00:00Z"})
    with tenant_session(tid) as s:
        summary = SyncRunner().run(s, tid, source_id, connector)
        assert summary["mode"] == "incremental"
        assert summary["stats"]["accounts"] == {"created": 1}   # only the new account re-fetched

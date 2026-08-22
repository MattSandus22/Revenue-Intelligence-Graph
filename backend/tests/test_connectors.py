"""Connector framework: backfill, incremental cursors, raw landing, deferred
records, and the accept-candidate → attach-on-next-run loop."""

import uuid

from sqlalchemy import text

from rig.connectors.base import SyncRunner
from rig.connectors.hubspot import HubSpotConnector
from rig.connectors.stripe import StripeConnector
from rig.db import tenant_session
from rig.resolution import accept_candidate

from .fixture_clients import FixtureHubSpotClient, FixtureStripeClient

HS_COMPANIES = [
    {"id": "hs-1", "updatedAt": "2026-08-01T00:00:00Z",
     "properties": {"name": "Acme Corporation", "domain": "acme.com",
                    "tier__c": "Enterprise", "arr__c": "120000"}},
    {"id": "hs-2", "updatedAt": "2026-08-02T00:00:00Z",
     "properties": {"name": "Globex Corp", "domain": "globex.example",
                    "segment__c": "Mid-Market", "renewal_date__c": "2027-03-01"}},
]
HS_CONTACTS = [
    {"id": "hc-1", "updatedAt": "2026-08-03T00:00:00Z", "company_id": "hs-1",
     "properties": {"firstname": "Dana", "lastname": "Reyes",
                    "email": "dana@acme.com", "jobtitle": "VP Operations"}},
]
HS_DEALS = [
    {"id": "hd-1", "updatedAt": "2026-08-04T00:00:00Z", "company_id": "hs-2",
     "properties": {"dealname": "Globex expansion", "amount": "45000",
                    "dealstage": "proposal", "closedate": "2026-10-15"}},
]


def _make_source(session, tenant_id, source_type, name):
    return session.execute(text(
        "INSERT INTO data_source (tenant_id, type, name) VALUES (:tid, :type, :name)"
        " RETURNING id"
    ), {"tid": tenant_id, "type": source_type, "name": name}).scalar_one()


def test_hubspot_backfill_and_incremental(seeded):
    tid = seeded["nsc_tenant"]
    client = FixtureHubSpotClient(HS_COMPANIES, HS_CONTACTS, HS_DEALS)
    connector = HubSpotConnector(client)
    runner = SyncRunner()

    with tenant_session(tid) as s:
        source_id = _make_source(s, tid, "hubspot", "hubspot-main")
        summary = runner.run(s, tid, source_id, connector)
        assert summary["status"] == "succeeded" and summary["mode"] == "backfill"
        # hs-1 domain-links to existing Acme; hs-2 creates Globex
        assert summary["stats"]["companies"] == {"linked": 1, "created": 1}
        globex_id = s.execute(text(
            "SELECT id FROM account WHERE name = 'Globex Corp'"
        )).scalar_one()
        # contact attached to Acme, deal attached to Globex
        contact_account = s.execute(text(
            "SELECT account_id FROM contact WHERE source_record_id = 'hc-1'"
        )).scalar_one()
        assert str(contact_account) == seeded["acme_account"]
        deal = s.execute(text(
            "SELECT account_id, amount_cents FROM opportunity WHERE source_record_id = 'hd-1'"
        )).one()
        assert deal[0] == globex_id and deal[1] == 4500000
        # raw payloads landed
        raw_count = s.execute(text(
            "SELECT count(*) FROM raw_record WHERE data_source_id = :sid"
        ), {"sid": str(source_id)}).scalar_one()
        assert raw_count == 4

    # Incremental: one new company, existing ones untouched.
    client.companies.append(
        {"id": "hs-3", "updatedAt": "2026-08-10T00:00:00Z",
         "properties": {"name": "Initech Systems", "domain": "initech.example"}})
    with tenant_session(tid) as s:
        summary = runner.run(s, tid, source_id, connector)
        assert summary["mode"] == "incremental"
        assert summary["stats"]["companies"] == {"created": 1}  # only hs-3 fetched
        assert summary["stats"].get("contacts", {}) == {}       # nothing newer
        cursors = s.execute(text(
            "SELECT cursors FROM data_source WHERE id = :sid"
        ), {"sid": str(source_id)}).scalar_one()
    assert cursors["companies"] == "2026-08-10T00:00:00Z"


def test_stripe_defers_unmatched_and_attaches_after_human_accept(seeded):
    tid = seeded["nsc_tenant"]
    customers = [
        {"id": "cus_acme", "created": 1700000001, "email": "billing@acme.com",
         "name": "Acme Corporation"},
        {"id": "cus_mystery", "created": 1700000002, "email": "ap@initrode.example",
         "name": "Initrode Industries"},
    ]
    invoices = [
        {"id": "in_1", "created": 1700000100, "customer": "cus_acme",
         "amount_due": 3000000, "created_date": "2026-04-24", "due_date": "2026-05-08",
         "paid_date": "2026-05-05", "status": "paid"},
        {"id": "in_2", "created": 1700000101, "customer": "cus_mystery",
         "amount_due": 500000, "created_date": "2026-08-01", "due_date": "2026-09-01",
         "status": "open"},
    ]
    connector = StripeConnector(FixtureStripeClient(customers, invoices))
    runner = SyncRunner()

    with tenant_session(tid) as s:
        source_id = _make_source(s, tid, "stripe", "stripe-main")
        summary = runner.run(s, tid, source_id, connector)
        assert summary["status"] == "succeeded"
        # acme domain-links; mystery has no match → review queue
        assert summary["stats"]["customers"] == {"linked": 1, "queued": 1}
        assert summary["stats"]["invoices"] == {"updated": 1, "deferred": 1}
        acme_invoice = s.execute(text(
            "SELECT account_id, status FROM invoice WHERE source_record_id = 'in_1'"
        )).one()
        assert str(acme_invoice[0]) == seeded["acme_account"]

        # Human resolves the mystery customer to a brand-new account…
        candidate_id = s.execute(text(
            "SELECT id FROM identity_candidate WHERE source_system = 'stripe'"
            " AND source_record_id = 'cus_mystery' AND status = 'pending'"
        )).scalar_one()
        new_account = accept_candidate(s, tid, candidate_id, resolved_by="u_admin",
                                       create_account=True)

    # …and the deferred invoice attaches on the next run (re-fetch via reset cursor).
    with tenant_session(tid) as s:
        s.execute(text("UPDATE data_source SET cursors = '{}' WHERE id = :sid"),
                  {"sid": str(source_id)})
        summary = runner.run(s, tid, source_id, connector)
        assert summary["stats"]["invoices"].get("deferred", 0) == 0
        attached = s.execute(text(
            "SELECT account_id FROM invoice WHERE source_record_id = 'in_2'"
        )).scalar_one()
    assert attached == new_account


def test_failed_stream_marks_run_and_source(seeded):
    tid = seeded["nsc_tenant"]

    class ExplodingClient(FixtureHubSpotClient):
        def list_contacts(self, updated_after=None):
            raise RuntimeError("boom: simulated API failure")

    connector = HubSpotConnector(ExplodingClient(HS_COMPANIES))
    with tenant_session(tid) as s:
        source_id = _make_source(s, tid, "hubspot", "hubspot-broken-" + uuid.uuid4().hex[:6])
        summary = SyncRunner().run(s, tid, source_id, connector)
        assert summary["status"] == "failed" and "boom" in summary["error"]
        run_status, source_status = s.execute(text(
            "SELECT sr.status, ds.status FROM sync_run sr"
            " JOIN data_source ds ON ds.id = sr.data_source_id WHERE sr.id = :rid"
        ), {"rid": summary["sync_run_id"]}).one()
    assert run_status == "failed" and source_status == "action_required"

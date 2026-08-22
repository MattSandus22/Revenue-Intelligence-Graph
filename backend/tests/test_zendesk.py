"""Zendesk connector: org resolution, ticket normalization, deferred tickets,
priority mapping — and the end-to-end path ticket → S2 signal."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from rig.connectors.base import SyncRunner
from rig.connectors.zendesk import ZendeskConnector
from rig.db import tenant_session
from rig.signals.engine import evaluate_account

TODAY = date.today()
OPENED = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()


class FixtureZendeskClient:
    def __init__(self, organizations, tickets):
        self.organizations = organizations
        self.tickets = tickets

    def _filter(self, objs, updated_after):
        if updated_after is None:
            return list(objs)
        return [o for o in objs if o.get("updated_at", "") > updated_after]

    def list_organizations(self, updated_after=None):
        return self._filter(self.organizations, updated_after)

    def list_tickets(self, updated_after=None):
        return self._filter(self.tickets, updated_after)


def test_zendesk_sync_and_signal_path(seeded):
    tid = seeded["nsc_tenant"]
    orgs = [
        {"id": 900, "updated_at": "2026-08-01T00:00:00Z", "name": "Acme Corp ZD",
         "domain_names": ["acme.com"]},
        {"id": 901, "updated_at": "2026-08-01T00:00:00Z", "name": "Unknown Org 901",
         "domain_names": []},
    ]
    tickets = [
        {"id": 5001, "updated_at": "2026-08-05T00:00:00Z", "organization_id": 900,
         "subject": "Exports intermittently timing out", "priority": "urgent",
         "status": "open", "created_at": OPENED},
        {"id": 5002, "updated_at": "2026-08-05T00:00:00Z", "organization_id": 901,
         "subject": "Question about billing", "priority": "normal",
         "status": "open", "created_at": OPENED},
        {"id": 5003, "updated_at": "2026-08-05T00:00:00Z", "organization_id": 900,
         "subject": "Resolved earlier issue", "priority": "high",
         "status": "solved", "created_at": OPENED,
         "solved_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
    ]
    connector = ZendeskConnector(FixtureZendeskClient(orgs, tickets))
    with tenant_session(tid) as s:
        source_id = s.execute(text(
            "INSERT INTO data_source (tenant_id, type, name)"
            " VALUES (:tid, 'zendesk', 'zendesk-main') RETURNING id"
        ), {"tid": tid}).scalar_one()
        summary = SyncRunner().run(s, tid, source_id, connector)
        assert summary["status"] == "succeeded"
        # org 900 domain-links to Acme; 901 has nothing to match → queued
        assert summary["stats"]["organizations"] == {"linked": 1, "queued": 1}
        assert summary["stats"]["tickets"] == {"updated": 2, "deferred": 1}

        ticket = s.execute(text(
            "SELECT account_id, priority, status, resolved_at FROM support_ticket"
            " WHERE source_record_id = '5001'"
        )).mappings().one()
        assert str(ticket["account_id"]) == seeded["acme_account"]
        assert ticket["priority"] == "critical"  # zendesk 'urgent' → canonical 'critical'
        assert ticket["resolved_at"] is None

        # end-to-end: new critical ticket (open 5d > 72h SLA) fires S2 on evaluation
        evaluate_account(s, tid, seeded["acme_account"], today=TODAY)
        keys = s.execute(text(
            "SELECT semantic_key FROM signal WHERE account_id = :aid"
            " AND signal_type = 'critical_ticket_unresolved' AND state = 'active'"
        ), {"aid": seeded["acme_account"]}).scalars().all()
    assert "ticket:5001" in keys and "ticket:ZD-8841" in keys
    assert "ticket:5003" not in keys  # solved tickets never fire

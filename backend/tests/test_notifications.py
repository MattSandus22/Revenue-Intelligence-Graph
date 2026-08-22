"""Slack notification layer: composition, recording, dedupe, severity gate."""

from datetime import date

from sqlalchemy import text

from rig.db import tenant_session
from rig.insights import upsert_risk_insight
from rig.notifications import notify_insight
from rig.scoring import compute_renewal_risk
from rig.signals.engine import evaluate_account

TODAY = date.today()


class FixtureSlackClient:
    def __init__(self):
        self.messages = []

    def post_message(self, channel, text_body, blocks=None):
        self.messages.append({"channel": channel, "text": text_body})
        return {"ok": True}


def test_high_severity_insight_notifies_once(seeded):
    tid = seeded["nsc_tenant"]
    slack = FixtureSlackClient()
    with tenant_session(tid) as s:
        evaluate_account(s, tid, seeded["acme_account"], today=TODAY)
        score = compute_renewal_risk(s, tid, seeded["acme_account"], as_of=TODAY)
        insight_id = upsert_risk_insight(s, tid, seeded["acme_account"], score)
        # earlier API tests may have queued a notification for this insight
        s.execute(text("DELETE FROM notification WHERE subject_id = :id"),
                  {"id": str(insight_id)})

        result = notify_insight(s, tid, str(insight_id), slack)
        assert result["status"] == "sent"
        message = slack.messages[0]["text"]
        assert "$120,000" in message and "Renewal risk" in message
        assert "cited" in message  # evidence affordance always present

        # dedupe: second call sends nothing
        assert notify_insight(s, tid, str(insight_id), slack) is None
        assert len(slack.messages) == 1

        row = s.execute(text(
            "SELECT channel, status FROM notification WHERE subject_id = :id"
        ), {"id": str(insight_id)}).one()
    assert tuple(row) == ("slack", "sent")


def test_medium_severity_does_not_notify(seeded):
    tid = seeded["nsc_tenant"]
    slack = FixtureSlackClient()
    with tenant_session(tid) as s:
        account_id = s.execute(text(
            "INSERT INTO account (tenant_id, name, arr_cents, renewal_date)"
            " VALUES (:tid, 'QuietCo', 500000, :r) RETURNING id"
        ), {"tid": tid, "r": TODAY}).scalar_one()
        insight_id = s.execute(text(
            "INSERT INTO insight (tenant_id, account_id, kind, title, narrative, severity,"
            " confidence) VALUES (:tid, :aid, 'risk', 'minor', 'n', 'medium', 0.8)"
            " RETURNING id"
        ), {"tid": tid, "aid": str(account_id)}).scalar_one()
        assert notify_insight(s, tid, str(insight_id), slack) is None
    assert slack.messages == []


def test_no_client_queues_notification(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        account_id = s.execute(text(
            "INSERT INTO account (tenant_id, name, arr_cents, renewal_date)"
            " VALUES (:tid, 'QueueCo', 8000000, :r) RETURNING id"
        ), {"tid": tid, "r": TODAY}).scalar_one()
        insight_id = s.execute(text(
            "INSERT INTO insight (tenant_id, account_id, kind, title, narrative, severity,"
            " confidence) VALUES (:tid, :aid, 'risk', 'big', 'n', 'critical', 0.9)"
            " RETURNING id"
        ), {"tid": tid, "aid": str(account_id)}).scalar_one()
        result = notify_insight(s, tid, str(insight_id), None)
        assert result["status"] == "queued"

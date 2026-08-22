"""Slack notification layer (docs/11 Slack connector — notify/action surface).

Notifications are recorded first (queued) and sent second — the record is the
source of truth. Routing v0: high/critical insights notify immediately; one
notification per insight (dedupe), refreshed only on severity escalation.
"""

import json
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session


class SlackClient(Protocol):
    def post_message(self, channel: str, text_body: str, blocks: list | None = None) -> dict: ...


SEVERITY_EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡"}


def notify_insight(session: Session, tenant_id: str, insight_id: str,
                   slack: SlackClient | None, channel: str = "#revenue-risk") -> dict | None:
    insight = session.execute(text(
        "SELECT i.id, i.title, i.severity, i.confidence, i.arr_at_stake_cents, i.narrative,"
        " a.name AS account_name, a.renewal_date, cardinality(i.signal_ids) AS n_signals"
        " FROM insight i JOIN account a ON a.id = i.account_id WHERE i.id = :id"
    ), {"id": str(insight_id)}).mappings().one_or_none()
    if insight is None or insight["severity"] not in ("high", "critical"):
        return None

    already = session.execute(text(
        "SELECT 1 FROM notification WHERE subject_type = 'insight' AND subject_id = :id LIMIT 1"
    ), {"id": str(insight_id)}).scalar_one_or_none()
    if already:
        return None

    arr = (insight["arr_at_stake_cents"] or 0) / 100
    renewal = insight["renewal_date"].isoformat() if insight["renewal_date"] else "n/a"
    body_text = (
        f"{SEVERITY_EMOJI.get(insight['severity'], '')} Renewal risk: "
        f"{insight['account_name']} — ${arr:,.0f}, renews {renewal} "
        f"({insight['severity']}, confidence {float(insight['confidence']):.2f}, "
        f"{insight['n_signals']} signals)\n{insight['title']}\n"
        f"All claims cited — open the evidence card to verify."
    )
    body = {"text": body_text, "insight_id": str(insight_id),
            "buttons": ["open_evidence", "accept_risk", "dismiss", "snooze_7d"]}

    notification_id = session.execute(text(
        "INSERT INTO notification (tenant_id, channel, target, subject_type, subject_id, body)"
        " VALUES (:tid, 'slack', :target, 'insight', :sid, CAST(:body AS jsonb)) RETURNING id"
    ), {"tid": tenant_id, "target": channel, "sid": str(insight_id),
        "body": json.dumps(body)}).scalar_one()

    if slack is None:
        return {"notification_id": str(notification_id), "status": "queued"}
    try:
        slack.post_message(channel, body_text)
        session.execute(text(
            "UPDATE notification SET status = 'sent', sent_at = now() WHERE id = :id"
        ), {"id": str(notification_id)})
        return {"notification_id": str(notification_id), "status": "sent"}
    except Exception as exc:
        session.execute(text(
            "UPDATE notification SET status = 'failed', error = :err WHERE id = :id"
        ), {"err": str(exc)[:500], "id": str(notification_id)})
        return {"notification_id": str(notification_id), "status": "failed"}


class HttpSlackClient:
    """Real Slack Web API client (thin I/O layer)."""

    def __init__(self, bot_token: str):
        import httpx

        self._http = httpx.Client(
            base_url="https://slack.com/api",
            headers={"Authorization": f"Bearer {bot_token}"}, timeout=15,
        )

    def post_message(self, channel: str, text_body: str, blocks: list | None = None) -> dict:
        response = self._http.post("/chat.postMessage", json={
            "channel": channel, "text": text_body,
            **({"blocks": blocks} if blocks else {}),
        })
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"slack error: {data.get('error')}")
        return data


# Configured at startup; None = notifications recorded as queued.
default_slack_client: SlackClient | None = None

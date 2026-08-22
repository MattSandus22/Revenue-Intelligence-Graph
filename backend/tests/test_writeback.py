"""Write-back framework: propose → approve → execute, idempotency, guards."""

from datetime import date

import pytest
from sqlalchemy import text

from rig import writeback
from rig.db import tenant_session
from rig.insights import upsert_risk_insight
from rig.scoring import compute_renewal_risk
from rig.signals.engine import evaluate_account

TODAY = date.today()


class FixtureHubSpotWriteClient:
    def __init__(self, fail=False):
        self.created = []
        self.fail = fail

    def create_task(self, payload):
        if self.fail:
            raise RuntimeError("hubspot 500")
        self.created.append(payload)
        return {"id": f"hs-task-{len(self.created)}"}

    def update_company(self, company_id, properties):
        return {"id": company_id}


def _insight(seeded):
    with tenant_session(seeded["nsc_tenant"]) as s:
        evaluate_account(s, seeded["nsc_tenant"], seeded["acme_account"], today=TODAY)
        score = compute_renewal_risk(s, seeded["nsc_tenant"], seeded["acme_account"], as_of=TODAY)
        return upsert_risk_insight(s, seeded["nsc_tenant"], seeded["acme_account"], score)


def test_propose_approve_execute_happy_path(seeded):
    tid = seeded["nsc_tenant"]
    insight_id = _insight(seeded)
    client = FixtureHubSpotWriteClient()
    with tenant_session(tid) as s:
        request_id = writeback.propose_task(
            s, tid, insight_id=str(insight_id), title="Escalate ZD-8841 to eng lead",
            due_date="2026-08-23", proposed_by="u_ortiz",
        )
        # cannot execute before approval — the gate is real
        with pytest.raises(writeback.WritebackError, match="approval required"):
            writeback.execute(s, tid, request_id, client, actor_id="u_ortiz")

        writeback.approve(s, tid, request_id, approved_by="u_leader")
        result = writeback.execute(s, tid, request_id, client, actor_id="u_leader")
        assert result["id"] == "hs-task-1"
        assert client.created[0]["hs_task_subject"] == "Escalate ZD-8841 to eng lead"

        # idempotent replay: no second external write
        replay = writeback.execute(s, tid, request_id, client, actor_id="u_leader")
        assert replay == result and len(client.created) == 1

        # audit trail covers every step
        actions = s.execute(text(
            "SELECT action FROM audit_event WHERE object_id = :id ORDER BY seq"
        ), {"id": str(request_id)}).scalars().all()
    assert actions == ["writeback.propose", "writeback.approve", "writeback.execute"]


def test_reject_blocks_execution(seeded):
    tid = seeded["nsc_tenant"]
    insight_id = _insight(seeded)
    with tenant_session(tid) as s:
        request_id = writeback.propose_task(
            s, tid, insight_id=str(insight_id), title="x", due_date=None, proposed_by="u_a")
        writeback.reject(s, tid, request_id, rejected_by="u_b", reason="not needed")
        with pytest.raises(writeback.WritebackError):
            writeback.execute(s, tid, request_id, FixtureHubSpotWriteClient(), actor_id="u_b")
        # double-approve of a rejected request fails
        with pytest.raises(writeback.WritebackError):
            writeback.approve(s, tid, request_id, approved_by="u_b")


def test_failed_execution_records_error(seeded):
    tid = seeded["nsc_tenant"]
    insight_id = _insight(seeded)
    with tenant_session(tid) as s:
        request_id = writeback.propose_task(
            s, tid, insight_id=str(insight_id), title="y", due_date=None, proposed_by="u_a")
        writeback.approve(s, tid, request_id, approved_by="u_b")
        with pytest.raises(writeback.WritebackError, match="external write failed"):
            writeback.execute(s, tid, request_id, FixtureHubSpotWriteClient(fail=True),
                              actor_id="u_b")
        state, error = s.execute(text(
            "SELECT state, error FROM writeback_request WHERE id = :id"
        ), {"id": str(request_id)}).one()
    assert state == "failed" and "hubspot 500" in error

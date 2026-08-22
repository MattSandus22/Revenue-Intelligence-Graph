"""THE release gate (docs/09 §F): zero hallucination escapes tolerated.

Runs the adversarial suite — scripted models and generators trying to push
fabricated quotes, invented citations, and unbacked numbers past the
validators. Any escape fails the build.
"""

from datetime import date

from sqlalchemy import text

from rig.db import tenant_session
from rig.evals.adversarial import run_suite
from rig.insights import upsert_risk_insight
from rig.scoring import compute_renewal_risk
from rig.signals.engine import evaluate_account

TODAY = date.today()


def test_zero_hallucination_escapes(seeded):
    tid = seeded["nsc_tenant"]
    with tenant_session(tid) as s:
        evaluate_account(s, tid, seeded["acme_account"], today=TODAY)
        score = compute_renewal_risk(s, tid, seeded["acme_account"], as_of=TODAY)
        insight_id = upsert_risk_insight(s, tid, seeded["acme_account"], score)
        ticket_id = s.execute(text(
            "SELECT id FROM support_ticket WHERE source_record_id = 'ZD-8841'"
        )).scalar_one()
        evidence_id = s.execute(text("SELECT id FROM evidence_object LIMIT 1")).scalar_one()

        results = run_suite(s, tid,
                            acme_ticket_id=str(ticket_id),
                            acme_insight_id=str(insight_id),
                            real_evidence_id=str(evidence_id))

        # ensure no adversarial signal/narrative leaked into the store
        leaked_signals = s.execute(text(
            "SELECT count(*) FROM signal WHERE signal_type = 'negative_sentiment'"
            " AND rationale LIKE '%cancelling immediately%'"
        )).scalar_one()

    assert len(results) >= 8
    escapes = [r for r in results if not r.blocked]
    assert escapes == [], "HALLUCINATION ESCAPES:\n" + "\n".join(
        f"  {r.name}: {r.detail}" for r in escapes)
    assert leaked_signals == 0

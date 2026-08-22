# 10. Evidence and Explainability System

The non-negotiable differentiator. Everything user-facing that asserts something material — an insight, a score movement, a recommendation, a sentence in an executive brief — is backed by this system.

## 10.1 Evidence Card (canonical structure)

Rendered wherever an insight/score/claim appears; one schema everywhere:

```json
{
  "evidence_card_id": "evc_01J9...",
  "title": "Renewal at risk: usage collapse + unresolved critical ticket",
  "subject": {"account_id": "acc_acme", "opportunity_id": null},
  "business_impact": {
    "arr_at_stake_cents": 12000000,
    "methodology": "Full ACV of renewal due 2026-11-22; no partial-downgrade modeling applied",
    "impact_class": "renewal_risk"
  },
  "level": "critical",
  "confidence": {"value": 0.82, "basis": "calibrated composite v4; reliability 0.91", "band": [0.71, 0.9]},
  "why_now": "Risk score crossed 70 (threshold) on 2026-08-20 after payment became 14 days overdue; renewal is 92 days out and notice deadline is 32 days out.",
  "top_signals": [
    {"signal_id":"sig_u1_...", "type":"usage_drop_vs_baseline", "class":"statistical", "contribution":"+18 pts"},
    {"signal_id":"sig_s2_...", "type":"critical_ticket_unresolved", "class":"deterministic", "contribution":"+12 pts"},
    {"signal_id":"sig_c7_...", "type":"competitor_mention", "class":"llm", "contribution":"+9 pts", "review_status":"confirmed"}
  ],
  "evidence_items": [
    {
      "evidence_id": "ev_9f2...",
      "kind": "usage_metric",
      "statement": "Core actions/day fell 31% vs 90-day baseline (412 → 284), sustained 17 days",
      "claim_class": "observed_fact",
      "source_system": "segment_warehouse",
      "source_record_id": "metric:core_actions:acc_acme",
      "source_url": "rig://metrics/acc_acme/core_actions?window=90d",
      "event_at": "2026-08-19", "freshness_at": "2026-08-21T06:10Z",
      "excerpt": null
    },
    {
      "evidence_id": "ev_c44...",
      "kind": "transcript_span",
      "statement": "Pricing concern and competitor mention on 2026-08-12 call",
      "claim_class": "ai_interpretation",
      "source_system": "gong",
      "source_record_id": "call_388412#seg41",
      "source_url": "https://app.gong.io/call?id=388412&t=1832",
      "event_at": "2026-08-12T15:30Z", "freshness_at": "2026-08-12T18:00Z",
      "excerpt": "\"Honestly, CompetitorX quoted us 30% less for next year...\"",
      "excerpt_authorized": true,
      "model_run_id": "run_77ab", "detector": "competitor_mention@v2"
    }
  ],
  "provenance": {"generated_by": "insight_composer@v5", "score_version": "renewal_risk@v4.1", "inputs_hash": "sha256:ab12..."},
  "data_gaps": [
    "No email engagement data (connector not enabled)",
    "CRM forecast field ('Likely Renew') conflicts with model estimate — see DQ-482"
  ],
  "suggested_action": {"playbook_id": "pb_renewal_save", "label": "Run renewal save play", "approval_required_for": ["crm_writeback","external_comms"]},
  "owner": {"user_id": "u_ortiz", "role": "csm"},
  "feedback": {"controls": ["correct","incorrect","useful","not_useful","missing_context","already_known"]},
  "audit_event_id": "aud_5521..."
}
```

Rules:
- Each `evidence_item` carries `claim_class ∈ {observed_fact, model_prediction, ai_interpretation, recommendation}` and the UI renders these with distinct iconography + labels (never color alone).
- `excerpt` present only when the requesting user's field-level policy allows `transcript_content`; otherwise `excerpt_authorized:false` and the statement degrades to the derived label with an access-request affordance.
- `freshness_at` drives staleness badges ("evidence 9 days old").
- Cards are immutable snapshots; regeneration creates a new card linked to the old (users can see what the system believed at decision time).

## 10.2 Citation mechanics by source type

| Source | Citation anchor | Deep link | Freshness semantics |
|---|---|---|---|
| CRM fields | object + field + as-of value + modified-by | CRM record URL | last sync watermark |
| Product usage metrics | metric descriptor + window + computed value + pipeline version | in-RIG metric explorer (source of computation lineage) | aggregation job timestamp |
| Tickets | ticket id + message ids | help-desk URL | webhook receipt time |
| Call transcripts | call id + segment index + char span + timestamp offset | provider URL with `t=` offset where supported | transcript ingest time |
| Documents | doc id + page/paragraph anchor | drive/CLM URL | version hash at citation time |
| Billing events | event/invoice id | billing dashboard URL | webhook receipt |
| Emails | message id (metadata); body spans only if body ingestion consented | mail deep link where available | sync watermark |
| External data (future) | provider + retrieval timestamp + license note | provider URL | retrieval time; marked third-party unverified |

If a cited source record is later deleted/purged, citations flip to `verification_status: stale`; dependent published claims get flagged in-place; new generations cannot use them.

## 10.3 Claim-verification layer

A standalone service in the generation path — nothing exec-facing bypasses it:

```
draft claims (from any generator)
  → for each claim:
      1. citation existence: every material claim maps to ≥1 evidence_id present in store, tenant-scoped
      2. quantitative check: numeric claims must match values computed by the metrics layer
         (numbers are injected into prompts as structured facts; verifier regex-extracts numerals
          from output and requires exact match to a provided fact — LLM arithmetic is banned)
      3. class check: claim_class assigned and consistent (a prediction can't be labeled a fact)
      4. authorization check: claim doesn't reveal data beyond the audience's grants
      5. staleness check: all citations fresh within policy
  → verdicts: verified | unsupported | blocked
```

- `unsupported` claims: dropped from executive outputs; in analyst-facing surfaces optionally shown with an explicit "UNSUPPORTED — insufficient evidence" label if the tenant enables it (default: drop).
- The **executive report generator refuses to publish** any brief containing non-verified claims — publication is a hard gate, with a "what was excluded and why" appendix for the approver.
- Verification results stored on `evidence_citation.verification_status` + audit event.

## 10.4 UI vocabulary for certainty

| Class | Visual treatment | Example copy |
|---|---|---|
| Observed fact | solid badge "FACT", source icon | "Invoice INV-2214 is 14 days overdue (Stripe)" |
| Model prediction | outlined badge "PREDICTION" + confidence band | "Renewal probability 62% (range 53–71%)" |
| AI interpretation | dashed badge "AI-INTERPRETED" + review state | "Call sentiment negative on pricing (confirmed by J. Ortiz)" |
| Recommendation | action chip "SUGGESTED" | "Run renewal save play" |

Accessibility: badges use shape + text, never color alone; screen-reader labels include class and confidence.

## 10.5 Score-change explanations

Every score delta ≥ threshold emits a `score_change` claim object: previous/new value, component deltas with signs, triggering events, citations — surfaced on hover ("why did this change?") and in the timeline. Scores without a resolvable latest change-explanation are a defect class monitored in QA (target: 100% coverage).

## 10.6 Trust telemetry

- Per-tenant trust dashboard (internal + admin-visible): citation coverage, verification block counts, stale-citation incidents, feedback verdicts by class, hallucination incidents (target 0; any occurrence triggers an AI-incident workflow, doc 12).
- Every evidence card view/expand is analytics-tracked — evidence engagement is the leading indicator that the differentiator is landing.

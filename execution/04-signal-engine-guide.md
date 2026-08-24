# Execution Doc 4 — Signal Engine Implementation Guide

Reference implementation: `backend/rig/signals/engine.py` (detectors +
persistence), `rig/scoring.py` (score), `rig/calibration.py` (probability).
This guide is the annotated pseudocode version for extending it — every
pattern below is live and tested.

## 1. Detector contract

```
detect_<signal>(session, account, params, today) -> list[Detection]

Detection:
  semantic_key   # dedupe discriminator, e.g. "invoice:INV-2214", "metric:core_actions"
  severity       # info|low|medium|high|critical
  confidence     # DET facts: 1.0 (minus freshness penalty); STAT: sample-based
  magnitude      # machine-readable payload, e.g. {drop_pct: 31.1}
  rationale      # ONE human sentence with the numbers in it
  evidence[]     # EvidenceSpec: kind, source_system, source_record_id,
                 # statement (verbatim claim), event_at
```

**Iron rules** (enforced by the engine, tested):
- A detection without evidence cannot persist — the engine writes
  `evidence_object` + `evidence_citation` per spec; a test fails if any
  active signal is uncited.
- Upsert on `(tenant, account, signal_type, semantic_key)`: re-detection
  updates magnitude and bumps `occurrence_count` — never duplicate rows.
- Conditions that clear → `state='resolved'`, never deleted (FN analysis).
- Resolve-on-clear is scoped to registry-owned types — detectors must not
  touch LLM-lifecycle signals.

## 2. Deterministic detector pseudocode

### 2a. Usage drop vs. baseline (U1 — statistical-lite)
```
if not usage_is_fresh(account, SLA=3d): return []      # a broken pipeline is a
                                                       # DATA issue, not churn
series   = usage_metric_daily[account, last 90d] grouped by metric
for metric:
    baseline = median(days 90..15)                     # robust to spikes
    if len(baseline_days) < 30: skip                   # min history
    if baseline < 20/day:       skip                   # denominator floor (FP guard)
    current  = mean(last 14d)
    drop_pct = (baseline - current) / baseline * 100
    if drop_pct < 20: skip
    severity = drop_pct >= 50 ? critical : drop_pct >= 30 ? high : medium
    emit Detection(
      semantic_key = f"metric:{metric}",
      confidence   = 0.94,                             # fresh-feed statistical
      rationale    = f"{metric} down {drop_pct:.0f}% vs 90-day baseline
                      ({baseline:.0f} → {current:.0f}/day)",
      evidence     = [usage_metric evidence w/ windows in content_ref])
```

### 2b. Overdue invoice (C3)
```
for inv in invoices where paid_at IS NULL and status in (open, overdue):
    days_past_due = today - inv.due_at
    if days_past_due < 7: skip
    severity = days_past_due >= 21 ? high : medium
    emit Detection(semantic_key=f"invoice:{inv.source_record_id}",
                   confidence=1.0,          # a fact from the billing system
                   magnitude={days_past_due, amount_cents},
                   evidence=[billing_event citing the invoice record])
```

### 2c. Critical ticket unresolved (S2)
```
for t in tickets where resolved_at IS NULL and status in (open, pending)
                   and priority in (high, critical):
    age_h = now - t.opened_at
    if age_h <= SLA_72h: skip
    severity = account.tier in (Strategic, Enterprise) ? critical : high   # tier bump
    emit Detection(semantic_key=f"ticket:{t.source_record_id}", confidence=1.0, …)
```

### 2d. No meaningful meeting (R5 — next detector to add; needs meeting_call
table from calendar/call sources)
```
window = tier_policy(account.tier, default=45d)
last = max(meeting_call.started_at where account and duration >= 15min
           and external_participants >= 1)
if last is None and account.tenure < window: skip     # new-account grace
if last is None or today - last > window:
    emit Detection(semantic_key="engagement:no_meeting",
                   severity = renewal_within(120d) ? high : medium,
                   confidence = 1.0 - freshness_penalty(calendar_feed),
                   rationale = f"No meaningful meeting in {days} days
                                (policy: {window} for tier {tier})",
                   evidence  = [computed_metric over the meeting query])
FP guards: requires calendar connector healthy (else data-quality issue, not
signal); tenant-tunable window; email-only-cadence toggle per tenant.
```

## 3. Score calculation (renewal risk v0.1 — `rig/scoring.py`)

```
COMPONENTS = {                      # weight, contributing signal types
  usage_trajectory:      (0.25, [usage_drop_vs_baseline]),
  support_friction:      (0.20, [critical_ticket_unresolved]),
  commercial_engagement: (0.25, [renewal_no_plan, notice_period_approaching]),
  billing_health:        (0.15, [payment_late]),
  sentiment_trend:       (0.15, [negative_sentiment]),   # LLM class
}
SEVERITY_NORM = {info:.1, low:.25, medium:.5, high:.8, critical:1.0}

signals = active signals WHERE requires_review=false OR review_outcome='confirmed'
          # ← unconfirmed LLM output NEVER moves a score

coverage[c] = does the account have ANY data for this domain?
              (usage rows / tickets / invoices exist; commercial always true)
covered_weight = Σ weight[c] for covered c
if covered_weight < 0.60: return None        # "insufficient data" beats a fake number

for covered c:
    matched = active signals of c's types
    norm    = max(SEVERITY_NORM[s.severity] * s.confidence for s in matched) or 0
    w'      = weight[c] / covered_weight     # renormalize over covered only
    contribution[c] = 100 * w' * norm        # signed points, stored with
                                             # rationale + contributing signal ids
score       = Σ contributions                # 0–100, higher = riskier
reliability = covered_weight                 # coverage IS the reliability meter
inputs_hash = sha256(sorted signal states + coverage + version)   # reproducible
```

Missing data ≠ bad data: an absent component is excluded and *reliability
drops* — absence of sentiment data is not negative sentiment.

## 4. Confidence intervals & probability

Two distinct uncertainties, kept separate on purpose:

1. **Input reliability** (data coverage) — `reliability = covered_weight`,
   shown as a warning banner below 0.8. Display band on the 0–100 score:
   `± round(100 * (1 − reliability) / 2)` points (a coverage bound, labeled
   as such — not a sampling CI).
2. **Outcome probability** (`rig/calibration.py`) — always served with basis:
   - *Prior mode* (label-poor): `p = 0.05 + 0.60·score/100`, labeled
     "default prior — not fitted to your outcomes". Bounded away from
     certainty by construction (100 → 0.65).
   - *Fitted mode*: isotonic (PAV) knots applied as a clamped step function
     — never extrapolates beyond the fitted range. Activation requires
     ≥50 labels AND beating the prior on **holdout** Brier (70/30 seeded
     split). In-sample comparison is forbidden: isotonic is the
     least-squares monotone fit and would never lose — the gate would be
     decorative. Rejected fits are stored `active=false`; the prior keeps
     serving and the rejection is shown (a trust feature).
   - Fitted-mode interval (post-activation hardening): bootstrap the label
     set B=200 times, refit PAV, report the 10th–90th percentile of p at the
     queried score.

## 5. Explanation generation

Every displayed number must answer "why" in ≤2 clicks. Assembly
(`scoring.explain_latest`):

```
explanation = {
  score: {value, reliability, score_version, as_of, inputs_hash},
  probability: {p_nonrenewal, calibration, basis},        # provenance string
  components: [{
     component, weight, norm_value,
     contribution,                       # signed points — sums to the score
     rationale,                          # concatenated signal rationales, or
                                         # "no active signals in this dimension"
     evidence_ids,                       # contributing SIGNAL ids
     citations: [{claim_text, claim_class, kind, source_system,
                  source_record_id, statement, event_at, freshness_at}]
  }]                                     # via evidence_citation JOIN evidence_object
}
```

Rules that keep explanations honest:
- Component contributions **must sum to the score** (tested to ±0.05).
- A component with `norm_value > 0` and no evidence ids is a test failure.
- Rationales carry the numbers ("Invoice INV-2214 ($30,000) is 14 days past
  due") because they become brief-claim numeric allowlists downstream —
  free-hand narrative numbers cannot pass the verifier (docs/10 §10.3).
- Insight narratives: deterministic composition by default; LLM narrative
  only via the citation-menu task (uncited sentences dropped), stamped
  `narrative_source='llm'` + model run id.
- Score deltas ≥5pts emit a change explanation listing component deltas —
  a score is never shown without access to its latest "why this changed".

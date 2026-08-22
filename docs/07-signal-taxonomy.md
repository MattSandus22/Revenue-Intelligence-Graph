# 7. Signal Taxonomy

## 7.1 Conventions (apply to every signal unless overridden)

- **Detector classes:** `DET` deterministic rule · `STAT` statistical/anomaly · `ML` supervised model · `LLM` LLM-derived · `HYB` hybrid.
- **Severity:** `info | low | medium | high | critical`, computed per signal from magnitude × ARR band × renewal proximity (multiplier table per tenant; defaults: renewal <90d ⇒ +1 level for retention signals; tier=Strategic ⇒ +1 level cap critical).
- **Confidence:** DET signals = 1.0 minus data-freshness penalty; STAT = f(effect size, baseline sample); ML = calibrated probability; LLM = validated self-consistency score bucketed {0.5, 0.7, 0.9} (see doc 9 §D).
- **Explainability:** every signal stores `evidence_refs[]`, human-readable `rationale`, detector version, input snapshot hash. LLM signals additionally store source excerpt spans (subject to field-level policy).
- **Dedup:** key = (tenant, account, signal_type, semantic_key, window); repeat detections update magnitude + `occurrence_count`, never spam.
- **Suppression/snooze:** per-account/type snooze (reason + expiry); tenant rules by segment/lifecycle (e.g., ignore usage signals during onboarding stage where noted); suppressed signals still recorded.
- **Human review before exec/forecast impact:** required for **all LLM signals with severity ≥ high**, and any signal marked `review:always`. DET/STAT signals are facts/statistics and flow directly, labeled by class.
- **Applicable segments:** default all customer-lifecycle accounts; exceptions noted (e.g., onboarding-only).
- **Time semantics:** all windows are event-time based with explicit `as_of`; late-arriving data reopens evaluation (pipeline replay, doc 13).

## 7.2 Catalog

### Category: Product usage & adoption

| ID | Signal | Class | Meaning | Inputs | Detection rule / method | Default severity | Window | FP prevention | Suggested actions |
|---|---|---|---|---|---|---|---|---|---|
| U1 | `usage_drop_vs_baseline` | STAT | Sustained usage decline vs. account's own baseline | Daily aggregated usage metrics | Robust baseline (median of trailing 90d, seasonality-adjusted weekly); trigger when 14d trailing mean < baseline − max(20%, 2×MAD) for ≥7 consecutive days | med→high by magnitude | 14d vs 90d | Seasonality adjustment; holiday calendar; min activity floor (ignore tiny denominators); exclude accounts <30d of history | Usage review call; champion check-in; enablement play |
| U2 | `key_user_inactive` | DET | Former power user (top-decile 60d activity) inactive ≥14d | Per-user usage, user roster | Power-user set recomputed monthly; inactivity streak counter | medium (high if user is champion) | 14–30d | Exclude PTO-length gaps <14d; exclude deprovisioned-by-plan-change | Reach out to user; verify employment (links to R1) |
| U3 | `core_feature_adoption_decline` | STAT | Declining use of sticky/core features (tenant-configured feature set) | Feature-level usage | Same method as U1 scoped to feature family | medium | 14d/90d | Feature deprecation calendar exclusion | Enablement content; workflow review |
| U4 | `onboarding_milestone_incomplete` | DET | Onboarding milestone overdue | Onboarding plan tasks, days-since-start | Milestone past due date, or stage age > segment P75 | high (onboarding accounts) | continuous | Milestones marked N/A excluded | Onboarding escalation play |
| U5 | `low_usage_near_renewal` | DET | Adoption below tenant floor within renewal window | Adoption score, renewal date | adoption_score < threshold AND renewal ≤120d | high | continuous | Data-reliability gate: fires only if usage freshness <72h | Renewal-risk play; exec alignment |
| U6 | `seat_utilization_low` | DET | Active seats ≪ entitled seats | Entitlements, active users | active/entitled < 60% for 30d | medium | 30d | Ramp exemption for accounts <90d post-sale | Adoption campaign; right-size conversation (flagged, not suggested externally) |
| U7 | `capacity_approach` | DET | Usage/seats approaching entitlement — expansion lead | Entitlements, usage | utilization ≥ 85% for 14d | info/opportunity | 14d | Burst exclusion (single-day spikes) | Expansion brief (Module F), subordinated to open risks |
| U8 | `new_team_adoption` | HYB (DET+LLM) | New department/team began using product | User metadata, email domains/org units, CRM notes | New org-unit cluster in active users; LLM classifies dept from titles when available | info/opportunity | 30d | Min 3 users from new unit | Expansion qualification |
| U9 | `expansion_pattern_adoption` | ML | Usage pattern historically preceding expansion | Feature vectors, cohort outcomes | Gradient-boosted propensity model (only when tenant has labels; else disabled) | info/opportunity | 30d | Min model AUC gate 0.7 on backtest before enablement | Expansion brief |
| U10 | `activity_spike_anomaly` | STAT | Sudden unusual change (up or down) in account activity | Daily usage | Two-sided CUSUM/EWMA anomaly | info→medium | 7d | Deploy/integration-event exclusion via tenant change-calendar | Investigate; owner note |

### Category: Relationship & engagement

| ID | Signal | Class | Meaning | Inputs | Detection | Severity | Window | FP prevention | Actions |
|---|---|---|---|---|---|---|---|---|---|
| R1 | `champion_departed` | HYB | Champion left company or role | Contact status, email bounces, LinkedIn-free heuristics (bounce+OOO parse), CRM updates, transcript mentions | DET: contact marked departed / hard bounce; LLM: departure mention in call/ticket | critical (strategic), high else | immediate | Two-source confirmation before critical (e.g., bounce + CRM); else `suspected` state | Multi-thread play; find successor; exec outreach |
| R2 | `champion_disengaged` | STAT | Champion activity (meetings, replies, product logins) declined materially | Interaction events, usage | Per-person engagement index vs. own baseline; trigger < 40% for 30d | high | 30d | Vacation/parental-leave snooze; seasonal | Re-engagement play |
| R3 | `no_exec_engagement` | DET | No exec-level stakeholder interaction in window | Stakeholder roles, meetings/calls metadata | No meeting/call with exec-tagged contact in 90d (configurable) | medium (high if strategic + renewal ≤120d) | 90d | Requires stakeholder map maintained; degrades to "unknown exec coverage" if map incomplete (data-quality note, not false alarm) | Exec sponsor program; QBR schedule |
| R4 | `single_threaded` | DET | ≤1 active contact relationship | Interaction events per contact | <2 contacts with 2-way interaction in 60d | medium | 60d | Exclude tiny accounts by seat count config | Multi-threading play |
| R5 | `no_meaningful_meeting` | DET | No meeting/2-way conversation in window | Calendar/call metadata | None in 45d (configurable per tier) | medium | 45d | Email-only cadence tenants can tune window | Schedule touchpoint |
| R6 | `missing_qbr` | DET | QBR overdue per tier cadence policy | QBR records, tier policy | last_qbr_age > cadence + grace | low→medium | continuous | Tier-specific cadence; new-account grace | Schedule QBR; prep pack |
| R7 | `stakeholder_map_gap` | DET | Missing decision-maker/economic buyer/renewal owner | Stakeholder roles | Required-role checklist per tier unmet | medium | continuous | Roles marked N/A by CSM excluded | Map completion task |

### Category: Support & sentiment

| ID | Signal | Class | Meaning | Inputs | Detection | Severity | Window | FP prevention | Actions |
|---|---|---|---|---|---|---|---|---|---|
| S1 | `ticket_volume_spike` | STAT | Ticket volume above account baseline | Tickets | Poisson/NegBin rate test vs. trailing 90d; also absolute floor | medium | 14d | Normalize per active seat; exclude bulk-import artifacts | Support review; CSM sync with support |
| S2 | `critical_ticket_unresolved` | DET | High/critical severity ticket open > SLA | Tickets w/ priority | priority ∈ {high,critical} AND age > SLA (default 72h) | high (critical if strategic) | continuous | Priority-mapping per connector validated at setup | Escalate to support lead; comms play |
| S3 | `repeated_issue_category` | HYB | Same issue category recurring | Ticket categories (native or LLM-classified) | ≥3 tickets same category 60d | medium | 60d | Category quality gate: LLM classification confidence ≥0.7 | Root-cause task; product feedback log |
| S4 | `negative_sentiment` | LLM | Negative sentiment in calls/tickets | Transcripts, ticket text | LLM classification per conversation; signal on account-level negative trend (≥2 negative in 30d or single strongly-negative exec conversation) | medium→high | 30d | Schema-validated output; sarcasm/quote-context instructions; two-pass self-consistency; aggregate threshold (single mildly-negative ≠ signal) | Save play; listen to call; manager review |
| S5 | `support_escalation_strategic` | DET | Escalation flag on strategic account | Ticket escalation field, tier | escalated=true AND tier=strategic | critical | immediate | — | Exec escalation workflow (doc 15 #7) |
| S6 | `nps_advocacy_positive` | DET | Strong NPS / advocacy behavior | NPS/survey data, reference activity | NPS ≥ 9, or advocacy event | info/opportunity | — | — | Reference/case-study ask; expansion timing input |

### Category: Commercial, contract & billing

| ID | Signal | Class | Meaning | Inputs | Detection | Severity | Window | FP prevention | Actions |
|---|---|---|---|---|---|---|---|---|---|
| C1 | `renewal_no_plan` | DET | Renewal within window, no active account plan | Renewal date, plan status | renewal ≤120d AND plan ∉ {active} | high | continuous | Auto-renew contracts get reduced severity (still tracked) | Create plan (generator); assign owner |
| C2 | `notice_period_approaching` | DET | Contract notice deadline near | Contract terms | notice_deadline − today ≤ 30d | high | continuous | Requires contract metadata; missing metadata → data-quality issue instead | Renewal owner alert |
| C3 | `payment_late` | DET | Invoice overdue | Invoices/payments | days_past_due ≥ 7 (med), ≥21 (high) | medium→high | continuous | Exclude disputed-by-our-error flag; finance-hold list | Finance coordination; CSM heads-up before renewal convo |
| C4 | `payment_failed_or_dispute` | DET | Failed payment, chargeback, dispute, credit hold | Billing events | event-driven | high | immediate | Retry-success within 48h auto-resolves | Billing outreach play |
| C5 | `seat_reduction` | DET | Seats/active users reduced | Entitlements, billing changes | entitlement decrease event, or active-user decline >20%/60d | high | 60d | Confirmed plan-change context (downgrade already known) lowers to info | Risk triage; downgrade-save play |
| C6 | `pricing_budget_concern` | LLM | Price objection / budget pressure expressed | Transcripts, tickets, emails (if enabled) | LLM extraction of pricing/budget concern with span | high | immediate | Distinguish negotiation-ritual vs. structural budget cut via classification labels; review required before exec surfacing | Value-recap play; commercial options prep |
| C7 | `competitor_mention` | LLM | Competitor named in customer conversation | Transcripts, tickets | Extraction with competitor entity + context (evaluating / comparing / migrating / historical) | medium→high by context | immediate | Context classifier suppresses historical/incidental mentions; review required ≥high | Competitive play; exec alignment |
| C8 | `data_mismatch_commercial` | DET | ARR/dates/owner disagree across CRM, billing, contract | Cross-system compare | per-field tolerance rules (doc 6 A.1) | medium (data class) | continuous | Tolerance thresholds; currency normalization | Data-quality remediation |
| C9 | `crm_metadata_missing` | DET | Missing next step / close date / renewal owner / decision-maker / contract metadata | CRM fields | Required-field policy per stage | low→medium | continuous | Stage-appropriate requirements only | Hygiene task to owner |

### Category: Opportunity & forecast

| ID | Signal | Class | Meaning | Inputs | Detection | Severity | Window | FP prevention | Actions |
|---|---|---|---|---|---|---|---|---|---|
| O1 | `opp_stale_high_value` | DET | High-value opp with no activity | Opp amount, activities | amount ≥ P75 AND no activity 14d | medium→high | 14d | Holiday windows; customer-confirmed pause flag | Next-step task; manager inspection |
| O2 | `opp_stage_stalled` | STAT | Stage age ≫ norm | Stage history | age > P80 for (stage, segment) | medium | continuous | Cohort minimums before norms activate (else absolute defaults) | Deal review |
| O3 | `forecast_inconsistency` | HYB | Forecast category contradicted by evidence | Category, activity, sentiment, next steps | Rule composite: commit AND (no next step OR no activity 14d OR last sentiment negative) | high | continuous | Each contributing fact independently verifiable; sentiment component excluded if unreviewed | Manager inspection; suggested category change (approval-gated) |
| O4 | `opp_amount_mismatch` | DET | Amount differs across systems | CRM vs CPQ vs billing draft | delta > max(5%, $1k) | medium | continuous | Currency/term normalization | Data remediation |
| O5 | `close_date_slip_pattern` | DET | Close date moved ≥2 times | Opp field history | slip_count ≥2 in 90d | medium | 90d | Legit re-scoping annotation option | Deal review |
| O6 | `expansion_ask` | LLM | Customer asked about additional capability/product | Transcripts, tickets | Extraction of interest expression with span | info/opportunity | immediate | Wishlist-vs-intent context labels | Expansion qualification |

## 7.3 Fully expanded exemplar specs

The catalog columns above cover the required attribute set; two signals shown in full normative detail as the template all signals follow in the signal registry (stored as YAML, versioned):

```yaml
signal: usage_drop_vs_baseline          # U1
version: 3
category: product_usage
class: statistical
business_meaning: >
  Sustained decline in product usage relative to the account's own seasonal
  baseline; leading indicator associated with non-renewal in cohort studies.
data_inputs:
  - metric: usage.daily_active_users, usage.core_actions   # tenant-mapped
  - dims: account_id, date
  - min_history_days: 30
detection:
  baseline: median(trailing_90d, weekday_adjusted)
  trigger: trailing_mean_14d < baseline - max(0.20*baseline, 2*MAD)
  sustain_days: 7
severity_map: { drop<30%: medium, 30-50%: high, ">50%": critical }
confidence: 1 - freshness_penalty(usage_feed) - small_sample_penalty(n<50 events/day)
time_window: {observe: 14d, baseline: 90d}
segments: exclude lifecycle=onboarding (use U4 instead); exclude sandbox workspaces
false_positive_prevention:
  - holiday_calendar per account region
  - tenant change-calendar exclusions (planned migrations)
  - denominator floor: baseline >= 20 events/day
explainability:
  rationale_template: "Usage down {pct}% vs 90-day baseline ({baseline} → {current} {metric}/day) sustained {days} days"
  evidence: [usage_aggregate_refs, sparkline_snapshot]
suggested_actions: [usage_review_call, champion_checkin, enablement_play]
dedupe_key: [account_id, signal, metric]
snooze: allowed(reason required, max 30d)
requires_review_for_exec: false        # statistical fact, labeled as such
```

```yaml
signal: competitor_mention              # C7
version: 2
category: commercial
class: llm
business_meaning: Customer referenced a competitor in a conversation; context determines threat level.
data_inputs: [call_transcript_segments, support_ticket_messages]
detection:
  method: llm_extraction (schema doc 9 §D.3)
  context_labels: [actively_evaluating, comparing_pricing, migrating_away, historical, incidental]
severity_map: {actively_evaluating|migrating_away: high, comparing_pricing: medium, historical|incidental: none}
confidence: llm_self_consistency (2-pass agreement) × extraction_validation
time_window: immediate, aggregate 90d for trend
false_positive_prevention:
  - span citation mandatory; no span → discard
  - competitor entity list per tenant + fuzzy guard against product-feature homonyms
  - context classification suppresses non-threat mentions
explainability: verbatim span (permission-gated), call/ticket link, timestamp, speaker
suggested_actions: [competitive_play, exec_alignment, listen_to_call]
dedupe_key: [account_id, signal, competitor, source_record]
requires_review_for_exec: true          # LLM-derived, severity high
```

## 7.4 Severity, urgency, and routing summary

`urgency = severity_rank × ARR_band_multiplier × renewal_proximity_multiplier × confidence` — deterministic and displayed on hover. Routing: `critical → immediate Slack DM to owner + channel; high → workbench top + daily digest; medium → workbench + weekly digest; low/info → workbench only`. All tenant-tunable.

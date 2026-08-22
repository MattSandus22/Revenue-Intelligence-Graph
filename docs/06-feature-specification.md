# 6. Detailed Feature Specification

Modules A–J. Each module: purpose, functional spec, key behaviors, and acceptance criteria (AC) for critical features. Data structures referenced here are defined in [doc 8](08-data-model-and-graph.md); AI behaviors in [doc 9](09-ai-ml-architecture.md); evidence mechanics in [doc 10](10-evidence-and-explainability.md).

---

## Module A — Unified Account Graph

**Purpose:** One canonical, provenance-carrying account profile that resolves every source system's records to a single account entity and exposes relationships as a graph.

### A.1 Canonical account profile
Canonical fields (each with value + source + as-of timestamp + confidence): name, domain(s), external IDs per source, industry, segment, tier, territory, lifecycle stage (prospect / onboarding / adopting / established / renewing / churned / won-back), ARR (billing-derived), CRM ACV, renewal date, contract end/notice dates, product plan/edition, seat entitlement vs. active seats, owners (CSM, AE, exec sponsor), parent account, health/risk scores (Module B).

**Source-of-truth rules:** per-field policy set by RevOps admin, e.g.:

```yaml
field: arr
priority: [billing.stripe, crm.salesforce, manual]
conflict_policy: surface_if_delta_pct > 5   # creates DataQualityIssue + banner on profile
field: renewal_date
priority: [contract.cpq, crm.salesforce, billing.subscription_period_end]
conflict_policy: surface_always
field: owner_csm
priority: [crm.salesforce]
conflict_policy: last_write_wins_with_audit
```

Conflicts never silently resolve when `surface` policy applies: the profile shows the chosen value with a ⚠ affordance revealing all source values.

### A.2 Hierarchy
Parent/child account trees (subsidiary, department, region), sourced from CRM hierarchy plus detected candidates (shared domain, billing linkage) proposed at lower confidence for human confirmation. Rollup views aggregate ARR/risk to any node. Cycles rejected at write time.

### A.3 Identity resolution & entity matching
- **Matching keys (ordered):** explicit cross-system ID mappings → domain match → billing email domain → fuzzy name (normalized legal suffixes) + country → human mapping.
- Every match carries `match_confidence ∈ [0,1]` and `match_method`. Matches ≥0.95 auto-link; 0.70–0.95 queue for human review; <0.70 remain unlinked with suggestion surfaced in Data Quality CC.
- **Contact resolution:** email exact → email-alias heuristics → name+account fuzzy. Champion-departure detection depends on this (person leaves account when email bounces/deactivates or CRM contact marked departed).
- **Manual merge/split/reassign:** admins and analysts can merge accounts (choose survivor, remap all children/edges, reversible for 30 days via tombstone), split (reassign records between accounts), and reassign records (e.g., ticket attached to wrong account). All actions audit-logged and emit reprocessing of affected scores.

**AC — identity resolution**
1. Given a Salesforce account, a Stripe customer, and a Zendesk org sharing domain `acme.com`, the system creates one canonical account with three source links, each showing method + confidence.
2. Given two Salesforce accounts "Acme Corp" and "Acme Corporation" with the same domain, a merge suggestion appears in the review queue with confidence and differing fields shown; accepting merges within 5s and re-scores the account asynchronously.
3. A merge performed in error can be reverted within 30 days restoring prior record associations.
4. No auto-link ever occurs across tenants (isolation test in CI).

### A.4 Account timeline
Unified, filterable event stream: CRM activities, stage changes, tickets, calls/meetings, usage milestones/anomalies, billing events, signals, score changes, actions, notes. Each entry: source system, source record link, event timestamp vs. ingested-at, author, confidence (for derived entries), evidence-card link where applicable. Filters by category/date/person/severity. Infinite scroll with day grouping; "changes since I last viewed" marker.

### A.5 Segments & attributes
Segment/tier/territory assignable by rule (e.g., `tier = Enterprise if ARR ≥ 100k`) or sync from CRM; lifecycle stage transitions logged; all attributes usable in filters, scoring baselines, and RBAC scopes.

---

## Module B — Account Intelligence (Scores)

**Purpose:** Ten explainable scores per account; never a number without a "why," a trend, and a confidence.

Scores (all 0–100 unless noted; directionality explicit in UI):

| Score | Direction | Primary consumers |
|---|---|---|
| Account health (composite) | higher = healthier | All |
| Renewal risk | higher = riskier | CS, execs |
| Expansion propensity | higher = more likely | AM/AE |
| Relationship strength | higher = stronger | CS, Sales |
| Product adoption | higher = deeper | CS |
| Support friction | higher = worse | CS, Support liaison |
| Financial/billing health | higher = healthier | CS, Finance |
| Data reliability | higher = more trustworthy inputs | All (meta-score) |
| Onboarding success | higher = on-track (onboarding stage only) | CS |
| Forecast confidence | higher = evidence supports forecast | Sales, RevOps |

### Required behaviors
- **Explanation object on every score:** top contributing components (signed contributions), trend (Δ7d/Δ30d/Δ90d with sparkline), segment baseline and peer percentile (within-tenant peers only unless benchmarking contractually enabled), confidence interval, and citations to underlying evidence.
- **"Why this score changed":** any Δ ≥ configurable threshold (default 5 pts/7d) generates a change explanation listing the component deltas and triggering events. A score is never displayed without access to its latest change explanation.
- **Data-reliability coupling:** each score's confidence degrades with input staleness/completeness; below a threshold the score renders as "Unreliable — see data issues" rather than a crisp number. **A stale number is worse than no number.**
- **Override & annotation:** authorized users can pin an override (e.g., "CSM override: risk high — champion resigned yesterday, not yet in data") with reason, expiry, and audit; overrides display distinctly and feed evaluation (override-vs-model agreement).
- Formulas, weighting, baselines, calibration, versioning: [doc 9 §C](09-ai-ml-architecture.md).

**AC — scores**
1. Clicking any score opens its explanation: ≥3 top components with signed contributions, each linking to evidence.
2. Changing a score weight in config recomputes affected accounts in a preview sandbox and shows backtest delta before publish; publishing bumps `score_version` and annotates timelines ("score definition changed").
3. If usage data is >72h stale for an account, adoption and health scores show degraded-confidence state and the Data Quality CC lists the cause.
4. Renewal-risk score on the demo dataset is reproducible bit-for-bit from stored components (auditability test).

---

## Module C — Signals Engine

**Purpose:** Detect atomic, typed, deduplicated facts/changes worth attention. Full catalog in [doc 7](07-signal-taxonomy.md).

**Behaviors**
- Signals are produced by four detector classes: deterministic rules, statistical anomaly detectors, ML models, LLM extractors (each labeled).
- Every signal: taxonomy ID, severity, confidence, time window, evidence refs, suggested actions, suppression state.
- **Dedup:** identical (account, signal_type, semantic key) within window → single signal with `occurrence_count++`.
- **Snooze/suppress:** per-account per-type snooze with required reason + expiry; tenant-level suppression rules (e.g., "ignore usage-drop for sandbox workspaces"); suppression never deletes the underlying signal record (needed for FN analysis).
- **Human-review gating:** signals marked `requires_review=true` (all LLM-derived severities ≥ high, per doc 7) do not enter executive reports or forecasts until confirmed by an authorized user.
- Signals roll up into **Insights** (Module D) — an insight bundles related signals into a narrative with an evidence card.

**AC**
1. A 31% usage drop vs. baseline creates exactly one `usage_drop` signal despite daily recomputation; magnitude updates in place.
2. Snoozing `missing_qbr` on account X suppresses notifications but the signal remains queryable with state `snoozed`.
3. An LLM-derived `competitor_mention` signal appears in the CSM workbench immediately but is excluded from the weekly exec brief until confirmed.

---

## Module D — Risk and Opportunity Workbench

**Purpose:** The daily operating surface: ranked portfolio of risks and opportunities → triage → own → act → resolve → learn.

### Ranking
Default sort: `urgency_rank = f(ARR at risk, severity, confidence, renewal proximity, momentum)` — deterministic, documented, tenant-tunable. Filters: owner, team, segment, territory, ARR band, renewal window, health dimension, signal type, product, industry, lifecycle stage, tier, status.

### Risk lifecycle (state machine)
```
detected → triaged → accepted | dismissed
accepted → in_progress → mitigated | not_mitigated
mitigated/not_mitigated → outcome_known (renewed / churned / downgraded / expanded)
dismissed → outcome_known (for FP/FN accounting)
```
Transitions require actor + timestamp + (for dismissed) reason code: `incorrect`, `already_known`, `not_actionable`, `duplicate`, `data_error`. Opportunity lifecycle mirrors it (`suggested → qualified | rejected → pursued → won/lost`).

### Action cards & playbooks
Each risk shows recommended actions (from playbook library + AI-suggested, labeled). Accepting an action creates a Task (assignee, due date, checklist), optionally synced to Salesforce/HubSpot tasks, Jira/Asana/Linear, with Slack/email notification. Playbooks = ordered step templates with owners, SLAs, exit criteria (built in Playbook Builder, doc 14 screen 13).

### Escalation rules
Config: `if tier ∈ {Strategic} and risk_severity = critical and state = detected for > 48h → notify VP CS + create escalation`. Escalations have their own owner and SLA timer.

### Feedback & learning
Feedback controls on every insight: `correct / incorrect / useful / not useful / missing context / already known` + free text. Root-cause classification at outcome time (churn-reason taxonomy, doc E). Postmortem view assembles full history: signals → triage → actions → outcome, exportable for team review.

**AC**
1. Portfolio view loads ≤2s for 500 accounts; rank order is reproducible and explainable via an "how is this ranked?" tooltip.
2. Dismissing a risk requires a reason code; dismissed-then-churned accounts appear in the FN report.
3. Creating a task with Salesforce sync writes the task within 60s **only after** the user confirms the write-back preview (diff of fields to be written) — and produces an audit event with payload hash.
4. Escalation SLA breach notifies the configured role within 5 minutes of breach.

---

## Module E — Renewal Command Center

**Purpose:** Run the renewal business: calendar, coverage, forecast, scenarios, plans.

- **Renewal calendar:** accounts by renewal month/quarter; ARR bars segmented by risk band; notice-period markers.
- **Risk-adjusted forecast:** Σ (renewal ARR × calibrated renewal probability), shown as a range (P10–P90), never a fake-precise point; side-by-side with CRM forecast category and delta flags ("CRM says Likely Renew; evidence says 62% ± 9").
- **Early warning / surprise-churn indicators:** accounts whose risk crossed high within N days of renewal; accounts churn-risk-flagged with no owner action.
- **Coverage & plan completeness:** % renewals with active plan, owner, exec sponsor, current QBR; workload view per owner (renewal count/ARR per CSM per quarter).
- **Mutual action plan progress:** plan milestones with customer-visible/internal split, % complete, stalled-milestone flags.
- **Scenario modeling:** best/base/worst toggles per account (probability overrides with reason) rolling up to quarter scenarios; scenarios are sandboxes, never overwrite model output.
- **Cohort analysis:** renewal outcomes by segment/tier/signal-presence cohorts; churn-reason taxonomy (product gap, price, champion loss, M&A, unresolved support, competitor, budget, other — tenant-extensible, one primary + secondary reasons per churn).
- **Win-back tracking:** churned accounts with win-back stage, owner, and re-engagement signals.
- **QBR/EBR prep:** one-click prep pack — account summary, score trends, open risks, usage highlights, support recap, commitments status — every claim cited; export to slides/PDF after human edit/approval.
- **Account-plan generator:** drafts objectives, risks, plays, stakeholder map gaps from evidence; **human approves before any CRM write-back** (plan stored in RIG; optional summary write-back field-mapped by admin).

**AC**
1. Forecast view reconciles: Σ per-account expected ARR = displayed total (test with fixture data); calibration page shows predicted-vs-actual by quarter once ≥1 quarter of outcomes exists.
2. "Surprise churn" list = churned accounts whose risk never reached High ≥30 days pre-renewal; verified against fixtures.
3. QBR pack generation completes <60s, every numeric claim carries a citation resolvable to a source record; unsupported claims are omitted with a visible "insufficient data" note.

---

## Module F — Expansion Intelligence

**Purpose:** Credible, evidence-backed expansion suggestions, explicitly subordinated to risk.

- Capacity signals (seats/usage vs. entitlement ≥ threshold), adoption breadth (feature families in use) and depth, stakeholder growth (new depts/titles engaging), business triggers (hiring, new product lines — from CRM notes/conversations; external data out of scope until V2+), cross-sell eligibility matrix (owns product A, fits profile for B), obstacle detection (open critical risk, unresolved escalation, contract constraints like non-expandable term or co-term rules).
- **Risk subordination rule:** if account has open high/critical risk, expansion insight renders as "conditional — resolve risk first," never as an unqualified pipeline suggestion.
- Output: expansion brief (evidence-cited), recommended timing + owner, draft opportunity **created only on explicit approval**, written back with audit.

**AC:** An account with capacity signal + open critical support risk shows expansion as conditional; approving a draft opportunity requires confirmation dialog showing exact CRM fields to be created; rejection captures reason.

---

## Module G — Revenue Forecast Reliability

**Purpose:** Confront forecast categories with behavioral evidence.

- Pipeline hygiene score per opportunity: next step present/quality, close date sanity (past-due, quarter-stuffing), stage age vs. segment norms, activity recency, stakeholder coverage (≥2 threads, economic buyer identified), amount consistency across systems.
- **Evidence-vs-category consistency:** commit/best-case deals cross-checked against activity, sentiment, next steps; inconsistencies produce `forecast_inconsistency` signals with severity by amount.
- Close-date movement tracking (slip count, cumulative slip days).
- Commit-risk alerts to managers; manager inspection view: team roll-up with drill-down to per-deal evidence.
- **Historical calibration:** predicted-vs-actual by rep/team/stage; confidence ranges displayed as ranges ("this commit bucket historically closes at 71–84%"), never false precision.
- RIG never auto-changes a forecast; it drafts a suggested category change the rep/manager approves (write-back gated).

**AC:** A commit opportunity with no activity 21 days and negative last-call sentiment surfaces in manager inspection with both evidence items linked; calibration chart reproduces from stored snapshots.

---

## Module H — Data Quality Command Center

**Purpose:** Make data trust a first-class, workflowed surface — and tie data health to insight confidence.

Issue classes: field completeness (per-object required-field %), duplicates (accounts/contacts/opps with match candidates), hierarchy errors (orphans, cycles, conflicting parents), cross-system mismatches (opportunity/contract/billing amounts, dates, owners), orphaned records (tickets/usage not resolvable to accounts), wrong owner/territory/stage/type (rule-detected), broken syncs, freshness SLA breaches, schema changes detected in sources, metric-definition conflicts (two definitions of "active user"), lineage gaps.

Behaviors:
- Each issue: severity, affected accounts/records, detected-at, impact statement ("renewal forecast for 12 accounts uses stale ARR"), remediation workflow (assign, fix-in-source deep link, or in-RIG mapping fix), status.
- **Confidence propagation:** issues automatically degrade the data-reliability score and the confidence of dependent scores/insights, with visible linkage both directions ("this score is degraded by issue DQ-482").
- Lineage view: field → source(s) → transformations → consumers (scores/reports).

**AC:** Introducing a 5% ARR mismatch between billing and CRM in fixtures creates a mismatch issue within one sync cycle, banners the account profile, and lowers data-reliability score; resolving the issue restores confidence and logs the remediation.

---

## Module I — Executive Briefing and Reporting

**Purpose:** Automated, verified, editable executive narratives.

- **Weekly revenue-risk briefing:** top risks (new/escalated/resolved), risk-adjusted forecast delta, portfolio changes since last brief, action summary (what the team did), data-quality caveats.
- **Weekly expansion briefing:** analogous for opportunities.
- Every generated sentence is either (a) computed from structured data with lineage, or (b) an interpretation tagged as such — and every material claim carries evidence links. The generator **refuses to publish unverified claims**: verification layer (doc 10) blocks or labels them "unsupported — needs review."
- **Approval workflow:** draft → reviewer edits (edits tracked; edited claims marked "human-edited") → approve → distribute (email, Slack, PDF, Google Slides export). Unapproved briefs never auto-send.
- "What changed?" diff vs. prior brief; inferred vs. source-of-record labeling throughout; **no fabricated numerical claims** — numbers only from the metrics layer.

**AC:** Attempting to include a claim whose evidence was deleted (retention purge) blocks publication with a specific error; the distributed PDF's every claim footnote resolves to an evidence card URL; a brief with pending-review LLM signals shows them in a "needs confirmation" appendix, not the body.

---

## Module J — Natural-Language Investigation (Investigation Copilot)

**Purpose:** Evidence-cited answers to ad-hoc questions, with hard safety rails.

Pipeline (detail in doc 9 §D.12): parse question → classify intent (metric query / filtered list / account diagnosis / change summary / brief generation) → **compile to safe structured query** (semantic layer, no raw SQL from LLM) → execute under the caller's permissions → retrieve supporting unstructured evidence (tenant+user-scoped) → synthesize answer with citations → render with methodology, confidence, applied filters, and links.

Rules:
- Structured querying and retrieval **before** LLM synthesis; the LLM never answers from parametric memory about tenant data.
- States uncertainty and missing data explicitly ("usage data absent for 12 of 40 matching accounts").
- Never exposes data outside the caller's grants (authorization applied at retrieval, not post-filter).
- Never writes to source systems; any actionable follow-up ("create tasks for these 5 accounts") routes through the standard approval flow.
- **Never invents citations**: citation IDs are validated against the evidence store before render; a claim losing its citation is dropped or flagged.
- Unanswerable/out-of-scope → honest refusal with suggested rephrasings; every Q&A is audit-logged (question, compiled query, result row count).

**AC**
1. "Show accounts >$50k renewing in 120 days with declining usage and no exec engagement" returns the same set as the equivalent workbench filter (parity test suite of 25 canonical questions).
2. A user without transcript access asking "what did Acme say on the last call?" gets sentiment/classification only, with "excerpt restricted" notice — never the excerpt.
3. Fault injection (retriever returns empty): answer says data unavailable; zero fabricated citations across the eval suite (hard CI gate).

# 21. Open Decisions, Assumptions, and Validation Experiments

## 21.1 Open decisions (owner + deadline discipline)

| # | Decision | Options | Current lean | Resolve by |
|---|---|---|---|---|
| D1 | First CRM: HubSpot vs. Salesforce | — | HubSpot (speed) — **flips if ≥3/5 design partners are SFDC-only** | Design-partner selection (w2) |
| D2 | First support tool: Zendesk vs. Intercom | — | Zendesk (priority/escalation fields richer) | w2, same method |
| D3 | Usage ingestion default: CSV vs. Segment-first | — | Per-partner; build CSV regardless (universal fallback) | S2 |
| D4 | Risk score display: 0–100 vs. probability-first | — | 0–100 with probability in explanation (familiar to CS teams) — test comprehension in pilots | m3 |
| D5 | LLM provider mix per task | single vs. routed | Anthropic primary via gateway abstraction; small-model routing for extraction when evals allow | m4 (cost data) |
| D6 | Copilot in MVP? | in/out | Out (V1) — protect verification quality bar | locked |
| D7 | Exec brief default cadence/channel | email vs. Slack-first | Both, tenant-picked; measure engagement | m4 |
| D8 | DQ Command Center as standalone SKU timing | V2 vs. later | V2+ only with ≥3 organic pulls | m10 |
| D9 | Pricing: publish list prices? | public vs. sales-quoted | Publish Growth/Scale, quote Enterprise | m5 |
| D10 | EU region trigger | pipeline-driven | Build at ≥3 EU-blocked qualified deals | rolling |

## 21.2 Key assumptions (explicitly labeled)

| Assumption | Risk if wrong | Validation |
|---|---|---|
| A1: CS/RevOps will trust and act on explained scores where they distrust opaque ones | Core thesis fails | E1, E3 below |
| A2: 2 pts GRR improvement is achievable and attributable | ROI story collapses to time-saved only | E4 (cohort methodology from day 1) |
| A3: Design partners can map 3–10 meaningful usage metrics | Usage signals (highest-alpha) starve | E2 |
| A4: $36–72K land price clears mid-market procurement without CFO war | Cycle length blows up | First 10 paid deals |
| A5: Deterministic + calibrated-rules scoring is good enough pre-ML (no accuracy embarrassment) | Early FP storm kills trust | E3 precision tracking, threshold tuning |
| A6: Tenants will grant support/billing scopes readily; transcripts with friction; email bodies rarely | Evidence coverage gaps | Track scope-grant rates per connector from pilot 1 |
| A7: One CRM + one billing + one support covers ≥60% of ICP pipeline in year 1 | Integration sprawl pressure early | Pipeline stack survey in every discovery call |
| A8: CSM time saved ≈1.5h/account/month | ROI calculator inflated | E5 time study |

## 21.3 Validation experiments

- **E1 — Evidence-trust demo test (w1–4, pre-code):** clickable prototype with Acme walkthrough; 15 target-persona interviews; success = ≥70% say the evidence click-through changes their willingness to act vs. their current health score.
- **E2 — Data-readiness audit (w2–6):** for 10 prospects, inventory stack + metric availability + CRM hygiene; success = ≥6/10 can reach "connectable in a day" bar; output doubles as onboarding checklist.
- **E3 — Alert precision pilot (m2–4):** with first partners, measure acceptance/dismissal-by-reason weekly; success = ≥60% high-severity acceptance by week 4 of tuning, trending to 80%.
- **E4 — Attribution baseline (m0 of every pilot):** capture 4 quarters of historical churn + surprise-churn classification before RIG goes live (enables honest before/after and cohort math).
- **E5 — Time-saved study (m3):** QBR/renewal-prep timing with and without RIG packs, 10 CSMs; feeds ROI calculator with measured, not asserted, numbers.
- **E6 — Verification red-team (continuous):** adversarial eval suite tries to force uncited/false claims into briefs; success = zero escapes; any escape is a release blocker + incident.
- **E7 — Willingness-to-pay probe (m3–5):** Van Westendorp + closed-lost interviews on first 15 proposals; adjust tiers once, before scaling outbound.

## 21.4 Standing risk register (top items)

| Risk | Class | Mitigation owner |
|---|---|---|
| Citation/verification failure reaching an exec artifact | Product/trust | AI lead; E6; incident SLA |
| Identity-resolution errors merging wrong accounts | Data | Human-review queue thresholds; reversible merges |
| Connector API deprecations (HubSpot/Zendesk/Stripe) | Platform | Version monitors; contract tests in CI |
| Tenant isolation defect | Security | RLS CI suite; pen tests; bounty at maturity |
| Incumbent bundling "evidence" messaging | GTM | Demo-able differentiation; case studies; speed |
| Over-scoping MVP under partner pressure | Delivery | Doc 16 exclusions are contractual with partners |
| LLM cost overrun per tenant | Margin | Budgets, caching, routing; monthly review |

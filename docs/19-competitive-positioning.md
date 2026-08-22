# 19. Competitive Positioning and Risks

## 19.1 Alternatives analysis

| Alternative | Strength | Weakness vs. RIG | Our posture |
|---|---|---|---|
| CRM-native reporting (Salesforce/HubSpot dashboards, Einstein/Breeze features) | Free-ish, incumbent, admin familiarity | CRM-only data; no resolution across billing/usage/support; no evidence layer; AI features are bolt-ons over the same partial data | Coexist: we make their CRM more valuable; write-backs land there |
| CS platforms (Gainsight, Totango, Catalyst, ChurnZero, Vitally) | Category ownership, workflow depth (CTAs, playbooks), install base | Heavy admin, opaque scores, weak provenance, usage integration shallow in practice, trust erosion is *the* churn driver in the category | Run-alongside land ("compare our score's evidence to theirs"), replace at their renewal |
| Conversation intelligence (Gong, Chorus) | Call data moat, sales love | Deal/call lens, not account-lifecycle truth; no billing/support/usage joins; retention secondary | Integrate (their transcripts are our evidence); avoid competing on call coaching |
| Forecasting (Clari, Aviso, BoostUp) | Pipeline rigor, CRO relationships | New-business pipeline focus; renewal/CS shallow; no unstructured evidence graph | Delay direct collision until Forecast module (V2+); differentiate on evidence + renewal-first |
| BI/warehouse (Looker/Tableau/dbt + Snowflake) | Infinitely flexible; data team pride | No workflow, no resolution, no unstructured data, no explanation layer; 2–4 eng-quarters to build a worse version that decays | §19.4 argument; dbt-package coexistence |
| Internal RevOps + spreadsheets | Trusted humans; zero procurement | Doesn't scale, no memory, no detection latency, key-person risk | The real competitor in every deal; ROI math + time-saved wins |
| Generic AI copilots (Copilot/Gemini/ChatGPT-over-CRM, agent startups) | Cheap, hype tailwind | No canonical resolution, no verification, no audit; enterprise trust gap | Our governance story is the counter-position; never out-hype, out-audit |

## 19.2 Differentiators → moats

| Differentiator | Easily copied? | Moat mechanics |
|---|---|---|
| Evidence/verification architecture (citations by construction, claim classes, refusal gates) | Hard — retrofitting provenance into an existing product is a rewrite | Deepens with every eval, every audit-log integration into customer procurement |
| Canonical identity resolution + human-corrected graph | Moderate tech, hard data ops | Corrections + mappings accumulate per tenant → switching cost; quality compounds |
| Data-reliability-aware scoring ("the score knows when it's untrustworthy") | Conceptually copyable, culturally hard for score-selling incumbents to admit | Trust brand |
| Outcome/feedback loop (labels: risk → intervention → outcome, intervention-stratified) | Slow to replicate — requires time + workflow adoption | Per-tenant calibration data is unexportable value |
| Wedge focus (renewal risk) vs. platform sprawl | Copyable by focus, incumbents structurally resist narrowing | Speed + narrative clarity |

**What's defensible:** accumulated per-tenant resolution corrections, outcome labels, calibration, playbook-performance data, and procurement-approved trust posture. **What isn't:** any single connector, UI pattern, signal list, or prompt — assume all are copied within quarters; the compounding loops are the business.

## 19.3 First-class integrations (strategic ranking)
1. CRM (HubSpot, Salesforce) — commercial truth + write-back surface.
2. Billing (Stripe, Chargebee) — the unforgeable renewal/payment facts.
3. Support (Zendesk, Intercom) — highest-signal friction data.
4. Usage (Segment/warehouse/CSV) — the leading indicator with the most alpha.
5. Slack — where action happens; adoption flywheel.
6. Transcripts (Gong et al., V2) — the evidence that wows execs.

## 19.4 "Why not build it in our warehouse?"
The honest math we give prospects: a competent data team can build account joins + a risk dashboard in ~2 quarters. What they will not build (and what decays without a product team): identity resolution with human-correction workflow; evidence cards with span-level citations from transcripts/tickets; a claim-verification layer; signal precision tracking with feedback loops; approval-gated write-backs with audit; connector maintenance across API churn; calibration against outcomes; the exec brief ritual. Internal builds are also unstaffed for maintenance in year 2 — we cite reference customers who tried. Coexistence path: bring your warehouse models via dbt package/Census, RIG adds resolution + evidence + workflow on top — converts the data team from blocker to sponsor.

## 19.5 Risks of competing with incumbents
- **Gainsight/Clari add "evidence" marketing:** they will; our counter is demonstrable architecture (click-through provenance, refusal gates) and procurement artifacts, not adjectives. Risk: buyers can't tell the difference in a demo — mitigate with the "break it" demo (ask the brief to claim something unsupported; watch it refuse).
- **CRM vendors bundle free AI summaries:** commoditizes shallow insight; sharpens our verified-vs-vibes positioning; we must never compete on summary quality alone.
- **Gong moves account-lifecycle-ward / Clari moves renewal-ward:** fastest real threat (data + budget). Mitigate: win CS+RevOps love (not Gong's buyer), integrate their data before they integrate ours, speed in the wedge.
- **Platform dependency risk:** CRM/call vendors restricting API access — mitigate with customer-owned auth, multiple ingestion paths (warehouse route), and genuine mutual value (write-backs enrich their system).

## 19.6 Category risks
Category creation is expensive; "Renewal Risk Intelligence" must attach to existing budgets (CS platform line, RevOps tooling line) rather than demand a new one — pricing and packaging are deliberately sized to fit those envelopes. If the category label fails to stick, fall back to "the evidence layer for [Gainsight/Clari/CRM]" positioning without product change.

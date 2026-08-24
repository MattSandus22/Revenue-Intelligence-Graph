# Execution Doc 6 — Go-to-Market Execution Plan

Operational companion to docs/18 (pricing/strategy) and docs/19 (positioning).
Everything here is ready to send, build, or say this week.

## 1. Design partner recruitment

**Target list construction (F, week 1):** 40 companies — B2B SaaS, $10–100M
ARR, 50–500 accounts, VP CS or VP RevOps in seat, HubSpot or Salesforce +
Stripe/Chargebee + Zendesk/Intercom visible in job posts or BuiltWith.
Priority triggers: recent churn-driven layoff coverage, new VP CS (<6 months,
LinkedIn), CS-platform renewal window chatter in communities.

**Cold email (to VP CS — 118 words, no links until reply):**

> Subject: the renewal you didn't see coming
>
> {{FirstName}} — when {{Company}} last lost a renewal that surprised you,
> how many weeks earlier did the evidence exist — usage sliding, a stuck
> ticket, the champion going quiet — scattered across systems nobody joins?
>
> We've built Revenue Intelligence Graph: it connects CRM, billing, support,
> and product usage into one account truth layer, flags renewal risk early,
> and — the part CS leaders care about — **shows the evidence behind every
> score**. Click any number and see the source records. No black-box health
> scores.
>
> We're selecting 5 design partners (50% of list price, white-glove setup,
> roadmap influence). Worth 25 minutes to see your own accounts in it?
>
> — {{Founder}}

Follow-up cadence: bump day 4 (one line: "worth 25 minutes?"), breakup day 10
("closing the design-partner cohort — should I keep a seat?"). No more.

**Discovery/demo call outline (25 min):**

| Min | Beat |
|---|---|
| 0–3 | Their last surprise churn: "when did you *actually* first know?" (doc 18 Q1 — let them tell the story) |
| 3–8 | Discovery: % of renewals with a documented plan? Does the team trust the current health score? Who reconciles CRM ARR vs billing? (write down numbers — they become the pilot baseline) |
| 8–18 | Demo on the Acme walkthrough: workbench → click the score → **click every number to its source** → show the brief *refusing* an unverified claim ("break-it" moment) → dismiss an alert with a reason ("the system learns; you can audit that too") |
| 18–22 | Pilot structure: 90 days, paid ($9–15k credited to annual), success criteria co-signed at kickoff (§2 below), 1-day connect commitment from us, mapping workshop from them |
| 22–25 | Close: "Two things decide success: connecting your stack — a day — and picking 3–5 usage metrics that mean adoption *for you* — a workshop we run. Can we book both before you leave this call?" |

Disqualify fast (say it kindly): no CRM discipline, PLG-only with no CSM
ownership, or hard on-prem requirement (doc 02).

## 2. Pilot success metrics dashboard — specification

One page per partner, reviewed in every weekly call. Every metric is served
by an existing endpoint — build is a thin page over live APIs (E2, wk 9).

| Metric | Definition | Source | Target |
|---|---|---|---|
| Coverage | % of renewals ≥$10k in next 2 quarters with a score + evidence | `/v1/accounts` + `/v1/accounts/{id}/risk` | ≥90% by day 10 |
| Alert precision | accepted ÷ (accepted + dismissed), high severity | `/v1/metrics/precision` | ≥60% wk 4 → ≥80% wk 12 |
| Time-to-triage | insight `detected` → first transition (median) | `insight_transition` | <48h |
| Mitigation coverage | % accepted risks with active tasks | `/v1/metrics/precision` | ≥80% within 72h of acceptance |
| Surprise-churn baseline vs live | churned w/o high+ flag ≥30d prior | `/v1/metrics/outcomes` + historical import | live < imported baseline |
| Detection lead time | median days flagged-before-outcome | `/v1/metrics/outcomes` | >45 days |
| Brief ritual | consecutive weeks brief approved + distributed | `exec_brief` | 4+ streak |
| Data health | freshness SLA attainment; open high DQ issues | `/v1/admin/sources`, `/v1/admin/data-quality` | ≥95%; trending ↓ |
| Engagement | weekly active CSMs ÷ licensed; evidence-card expands/user/wk | product analytics | ≥70%; ≥5 |
| The story | documented "save" or early-warning narrative | weekly call notes | ≥1 by day 60 |

Conversion review is scheduled at **day 60** against these numbers — not
day 89 (doc 18).

## 3. Pricing page copy + FAQ

**Headline:** *Know which renewals are at risk, why, and what to do —
with evidence you can defend to your board.*

**Tiers** (annual; from docs/18): **Growth $36k/yr** — up to 150 managed
accounts, 4 connectors, renewal-risk workbench, evidence cards, weekly
executive brief, Slack alerts, SSO. **Scale $72k/yr** — up to 400 accounts,
everything in Growth + investigation copilot, playbooks & tasks, account
plans, SAML/SCIM, external task sync, priority support. **Enterprise from
$120k/yr** — 400+ accounts, call-transcript intelligence, expansion &
forecast modules (as released), field-level access policies, audit exports,
private tenancy add-on, named CSM. All tiers: **unlimited business seats**
within fair use. Implementation: $5k/$10k/$15k+.

**FAQ (verbatim-ready):**

- *Why per-account pricing, not per-seat?* Accounts are what we make
  intelligent. We want your whole revenue team — CSMs to CEO — in the
  product, so seats are unlimited.
- *Another AI tool that hallucinates in front of my exec team?* No. Every
  claim is tied to source evidence or it is not shown — our executive brief
  literally refuses to publish unverified claims, and you can watch it
  refuse. AI-derived findings never touch scores or reports until a human
  confirms them.
- *Do you train models on our data?* No — contractually and technically, by
  default. LLM calls run under zero-retention API terms; per-tenant
  calibration is fitted only on your own outcomes and never leaves your
  tenant.
- *What if our data is messy?* Everyone's is. RIG ships a data-quality
  command center because the product assumes messy data — it tells you when
  a score is unreliable instead of pretending.
- *How long to go live?* Sources connect in about a day; the important step
  is a 90-minute workshop choosing the 3–5 usage metrics that mean adoption
  for your product. Insights start flowing the same week.
- *What does RIG write into our systems?* Nothing without an explicit,
  previewed, human approval — every external write shows a before/after
  diff, is idempotent, and lands in a tamper-evident audit log.
- *Security posture?* SSO/SAML + SCIM, tenant isolation enforced in the
  database, encrypted credentials, hash-chained audit log, SOC 2 Type I in
  progress (report available under NDA when issued).

## 4. Competitive battlecards

**vs Gainsight / Totango (CS platforms)** — *When you'll meet them:*
incumbent renewal, "we already have health scores." *Their strength:* CTA
workflow depth, install base, category ownership. *Our wedge:* their scores
are admin-built and opaque — when one misses, trust dies and teams go back to
spreadsheets. RIG's score explains itself, cites sources, and admits when its
own data is unreliable. *Landmines to plant:* "Ask your CSMs if they trust
the current score." "Click a Gainsight score — can you see the invoice, the
ticket, the usage curve behind it?" "How many admin-hours a month keep it
alive?" *Proof:* live click-through from score → source records; the
data-reliability banner. *Counter when they say "we have AI now":* "Ask what
happens when their AI can't support a claim. Ours refuses to publish —
watch." *Coexist play:* run alongside; compare scores on the same accounts
for 60 days.

**vs Clari (forecasting)** — *Meet them:* CRO-led deals, forecast pain.
*Their strength:* new-business pipeline rigor, CRO relationships. *Our
wedge:* renewals and CS lifecycle are their afterthought; RIG is
renewal-first with billing/support/usage evidence they don't join. *Ask:*
"Where does Clari see the overdue invoice or the critical ticket sitting
under that 'commit' renewal?" *Don't:* fight them on new-logo pipeline —
concede it, position as complementary until our forecast module matures.

**vs Gong (conversation intelligence)** — *Meet them:* sales-led orgs,
"Gong tells us deal risk." *Their strength:* call-data moat, rep love. *Our
wedge:* calls are one evidence stream; renewal risk lives in usage, billing,
and support too. RIG ingests transcripts as evidence rather than competing
on call coaching. *Ask:* "What did Gong say about the account that never
books calls — the one that quietly stopped logging in?" *Coexist:* their
transcripts become our citations (integration, not war).

**Universal objection — "we'll build it in the warehouse":** concede a
competent data team can join tables in two quarters. Then: identity
resolution with human corrections, span-level citations, a claim verifier,
approval-gated write-backs, precision tracking, connector maintenance —
that's the product, and internal builds are unstaffed in year two (doc 19
§19.4). Offer the dbt-coexistence path to convert the data team from blocker
to sponsor.

## 5. First 3 case study outlines

**CS1 — "The renewal we would have lost" (save story; target: partner 1,
day 60–90).** Arc: baseline (their last surprise churn, in their words) →
the flag (risk crossed threshold N days pre-renewal; screenshot the evidence
card) → the play (renewal-save playbook, tasks, exec meeting) → outcome
(renewed; detection-lead-days + intervention record straight from
`/v1/metrics/outcomes`) → quote from VP CS on *trusting* the score because
they could check it. Honesty bar: attribution stated as correlational
(doc 01 §1.7) — it reads as credibility, not weakness.

**CS2 — "From 8 tabs to one truth layer" (efficiency; RevOps-voiced).** Arc:
before (hours per QBR prep, ARR reconciliation pain, from discovery notes) →
after (timeline + evidence cards + brief ritual; measured prep-time delta
from the wk-5 baseline survey) → the number ("CSMs got ~X hours/account/
month back") → secondary: data-quality issues found in week 1 (there are
always some — name two, anonymized).

**CS3 — "An executive brief you can interrogate" (trust/AI-governance;
CRO/CEO-voiced, aimed at security-conscious buyers).** Arc: the AI-skeptic
exec → the brief with per-claim citations and the *excluded-claims appendix*
("here's what it refused to say") → the pending-review appendix showing
human gating of AI findings → quote on presenting RIG numbers to the board
unedited. Sidebar: the zero-hallucination CI gate, described in one
paragraph, as an engineering practice — this case study doubles as
security-review collateral.

Production per study: 2 pages + 3 annotated screenshots; partner sign-off on
every number and quote in writing (wk 11); anonymized variant pre-approved
for prospects who won't accept logos.

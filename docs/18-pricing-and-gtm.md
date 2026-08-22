# 18. Pricing, Packaging, and Go-to-Market Plan

## 18.1 Pricing metric

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Managed accounts | Scales with value (accounts = the unit of intelligence); predictable; easy to count; doesn't tax adoption | Needs tier bands to avoid penny-counting | **Primary metric** |
| ARR monitored | Value-aligned | Customers resist revealing/being taxed on ARR; audit friction | Use only as tier qualifier |
| Seats | Familiar | Punishes broad adoption — adoption is our moat | Include generous seat allowances instead |
| Data sources | Simple | Penalizes integration depth, which improves our product | No — bundle by tier |
| Usage volume | Cost-aligned | Unpredictable bills kill trust | Only as fair-use guardrails |
| Platform fee | Simple | Doesn't scale | Base component only |

**Model: annual platform fee + managed-account band, unlimited business seats within fair use.** Rationale: accounts are countable, stable, value-proportional; unlimited seats maximizes the adoption flywheel (CSMs + execs + RevOps all in product); AI cost exposure handled by fair-use policies, not per-seat/per-token pricing.

## 18.2 Tiers (annual, realistic for mid-market ACV norms)

| Tier | Target | Managed accounts | Price/yr | Includes |
|---|---|---|---|---|
| **Growth** | $10–30M ARR cos. | up to 150 | **$36K** | 4 connectors, renewal wedge modules, Slack, weekly brief, OIDC SSO, standard support |
| **Scale** | $30–100M | up to 400 | **$72K** | + copilot, account plans/QBR, playbook builder, SAML/SCIM, external task sync, priority support |
| **Enterprise** | $100M+ | 400+ (banded) | **$120K–200K** | + transcripts module, expansion + forecast modules (as released), field-level policies, audit exports, EU residency, private-tenancy add-on, DPA/security review support, named CSM |

- **Implementation/onboarding fee:** $5K (Growth) / $10K (Scale) / $15–25K (Enterprise) — covers connector setup, metric mapping consultation, playbook workshops, 30-day white-glove. Waivable in competitive deals, not in scope creep.
- **Enterprise add-ons:** private tenancy +25%; BYOK +$12K; additional region +$18K; premium support/SLA +15%; DQ Command Center standalone SKU (V2+, $24K entry for RevOps-only land).
- **Professional-services boundary:** we configure RIG (mappings, playbooks, scores); we do **not** clean their CRM, build custom warehouse models beyond the dbt package, or staff ongoing analysts. PS capped at 15% of ARR per account to protect margin and product focus.

## 18.3 Margin & AI-cost protection

- Target blended gross margin ≥ 75% (year 1), ≥ 80% (year 2).
- COGS levers: LLM response caching keyed on inputs hash; small-model routing for extraction; batch processing off-peak; per-tenant token budgets with graceful degradation; ClickHouse/S3 lifecycle policies.
- Fair-use policy: copilot queries and generated briefs generous but bounded (e.g., 2K copilot answers/mo on Scale); overage conversations before throttles; **no surprise bills**.
- Cost telemetry per tenant/feature (doc 13) reviewed monthly; any tenant >8% of its ACV in COGS gets an engineering look.

## 18.4 Buyer map & sales motion

- **Champion:** VP CS (pain owner) or VP RevOps (data owner). **Economic buyer:** CCO/CRO (Growth/Scale), CFO countersign at Enterprise. **Gatekeepers:** security/IT, sometimes data eng.
- **Motion:** founder-led sales for first ~25 logos → 2 AEs + 1 SE at repeatability signals (m9–12). Land with wedge ($36–72K), expand via tiers/modules.
- **Cycle assumptions:** Growth 45–75 days; Scale 60–100; Enterprise 100–160 incl. security review. Pilot-to-paid conversion target ≥60%.
- **Security review strategy:** pre-built trust packet (architecture one-pager, questionnaire answers, DPA, subprocessor list, pen-test summary, SOC 2 roadmap letter) sent proactively at stage 2 — compress the gate we can't skip.

## 18.5 Design-partner & pilot structure

- **Design partners (first 5–8):** 6-month term at 50% of list (not free — free partners don't engage), white-glove onboarding, weekly feedback ritual, case-study + reference rights on success, price lock for year 2.
- **Standard pilot (post-design-partner):** 90 days, paid ($9–15K, creditable to annual), success criteria co-signed at kickoff: (1) ≥90% of renewals ≥$X covered with scores + evidence, (2) ≥N risks triaged with ≥70% acceptance, (3) 1+ documented save or early-warning win, (4) exec brief adopted in leadership cadence. Conversion decision meeting scheduled at day 60, not day 89.
- **ROI proof plan:** baseline capture at kickoff (GRR, surprise-churn list from last 4 quarters, forecast variance, CSM hours survey) → quarterly outcome reviews using doc 1 §1.7 methodology → case study at first renewal.

## 18.6 Discovery questions (field guide excerpt)

1. Walk me through the last churn that surprised you — when did you *actually* first know?
2. What % of your renewals 2 quarters out have a documented plan today? How do you know?
3. How many systems does a CSM open to prep a QBR? How long does prep take?
4. Do your CSMs trust your current health score? What happened last time it was wrong?
5. Who reconciles CRM ARR vs. billing ARR, and how often is it off?
6. What would 2 points of GRR be worth to you this year?
7. Who would own this internally — and who broke the last tool that promised this?

## 18.7 Objection handling

| Objection | Response |
|---|---|
| "Gainsight/our CS platform does health scores" | "Do your CSMs believe them? RIG shows the evidence behind every score and tells you when its own data is unreliable — that's the difference between a score and a defensible one. We can run alongside and you compare." |
| "We'll build it on our warehouse" | Doc 19 §19.4 — the honest build-cost math + decay story; offer dbt-package coexistence: "bring your models, we add resolution, evidence, and workflow." |
| "AI hallucinates; execs can't rely on it" | "Agreed — that's why the exec brief refuses to publish any claim without a verified citation, and you can click every sentence to its source. Zero-tolerance gate, contractually." |
| "Security won't approve a tool reading calls/tickets" | Scoped ingestion, metadata-first defaults, no-training terms, field-level access, audit log; transcripts are opt-in module with redaction. |
| "We don't have clean data" | "Neither does anyone. RIG ships a Data Quality Command Center because the product assumes messy data — it shows what's unreliable instead of pretending." |
| "Price" | Reframe on one saved renewal (avg ACV vs. platform fee); conservative ROI case only. |

## 18.8 First 100 customers

- **1–8 (m0–4):** design partners from founder network + targeted outbound to VP CS at $25–100M B2B SaaS with recent churn pain (layoff/board-pressure signals); CS/RevOps communities (Gain Grow Retain, RevOps Co-op, Pavilion).
- **9–30 (m4–10):** founder-led outbound + case studies; podcast/community content on "evidence-backed retention" and surprise-churn postmortems (opinionated, data-backed essays); referrals engineered from every save story; light partner motion with CS consultancies and fractional CCO networks (referral fee 10%).
- **31–100 (m10–24):** 2 AE pods; RevOps-agency channel; marketplace listings (HubSpot, Slack, Snowflake); category push ("Renewal Risk Intelligence") via analyst briefings (mid-market-relevant: G2 category, Pavilion, not Gartner-first); annual "State of Renewal Risk" benchmark report (from opt-in aggregate data only).
- **Channels ranked by expected CAC efficiency:** referrals > communities/content > outbound > partners > paid (paid last, minimal).

## 18.9 Founder-led sales plan (first 3 quarters)
CEO owns pipeline: 10 discovery calls/week target; standardized 25-min demo (Acme walkthrough of doc 20, live evidence-click theater); CTO joins security calls; pipeline reviewed weekly against cycle-time and conversion assumptions above; every loss gets a written reason logged against ICP hypotheses (dogfooding our own postmortem discipline).

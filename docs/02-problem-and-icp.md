# 2. Problem and ICP

## 2.1 The problem, decomposed

B2B SaaS companies in the $10M–$250M ARR range live or die on retention, yet the operating reality of their revenue teams is:

### P1 — Fragmented account truth
Commercial truth (CRM), financial truth (billing), behavioral truth (product analytics/warehouse), relationship truth (calendar, call recordings, email), and pain truth (support) live in 5–8 systems with inconsistent identifiers, no shared account key, and no provenance. Nobody can answer "what is actually happening at Acme?" without 45 minutes of tab-hopping.

**Observable symptoms:** duplicate accounts in CRM; billing ACV ≠ CRM ACV; usage dashboards keyed on workspace IDs that don't map to CRM accounts; the CSM's "real" account state lives in a personal doc.

### P2 — Untrusted health scores
Existing health scores are (a) manually maintained and stale, (b) rule-based over incomplete data, or (c) black-box model outputs. When the score misses a churn or flags a healthy account, the team stops looking at it. The missing ingredient is **explanation + data-reliability awareness**: a score should say *why*, *what changed*, and *how trustworthy its inputs are*.

### P3 — Late risk discovery ("surprise churn")
Risk becomes visible at the renewal conversation, when leverage is gone. Leading indicators existed months earlier — usage decline, champion departure, unresolved escalation, payment friction — but were distributed across systems no one person watches.

### P4 — Inconsistent account management practice
Account plans, mutual action plans, QBR cadence, exec sponsorship, and multi-threading exist as policy but not practice, because verifying compliance is manual. Leaders cannot see which renewals have no plan, no owner activity, or single-threaded relationships until it's too late.

### P5 — Manual, unverifiable executive reporting
Weekly/quarterly revenue reviews are assembled by RevOps in slides. Numbers conflict between sources, narratives are unauditable, and preparing them consumes analyst and CSM time. Executives make retention decisions on stale, second-hand summaries.

### P6 — Forecast fiction
Renewal and pipeline forecasts reflect rep optimism, not evidence. "Commit" deals with no next step, no recent activity, and negative call sentiment persist because no system confronts forecast category with behavioral evidence.

## 2.2 Ideal Customer Profile

### Firmographics
| Dimension | Target | Rationale |
|---|---|---|
| Company type | B2B SaaS | Data stack is standardized; churn economics are existential |
| ARR | $10M–$250M | Below $10M: too few accounts, founder-led CS, low willingness to pay. Above $250M: procurement/complexity better served post-enterprise-hardening |
| Managed accounts | 50–500 | Enough accounts that manual attention fails; few enough that account-level (not statistical) intelligence is the right paradigm |
| ACV | $20K–$500K | High enough that a single saved renewal pays for RIG |
| CS team | 3–30 CSMs, VP CS in seat | Need an owner for the workflow |
| RevOps | ≥1 dedicated person | Need an admin/champion for data plumbing |
| Sweet spot | $25M–$100M ARR, 100–300 accounts, Series B–D or profitable equivalent | Pain acute, stack mature, procurement navigable |

### Required stack (Phase-1 compatibility)
- CRM: **Salesforce or HubSpot** (pick one for MVP; see Integrations)
- Messaging: **Slack**
- Support: **Intercom or Zendesk**
- Billing: **Stripe or Chargebee**
- Product data: warehouse (Snowflake/BigQuery/Redshift) and/or analytics (Segment, Amplitude, Mixpanel, RudderStack) or CSV export capability
- Calls: Gong/Chorus/Zoom (Phase 2 ingestion; MVP accepts transcript upload)
- Calendar/email metadata: Google Workspace or Microsoft 365 (metadata only by default)

### Disqualifiers
- PLG-only motion with thousands of self-serve customers and no CSM ownership model (statistical churn tooling fits better)
- No CRM discipline at all (nothing to resolve against) — flag as "not yet," revisit after their CRM cleanup
- Hard requirement for on-prem deployment (post-enterprise roadmap)

## 2.3 Buying context

| Role | Buying role | What they buy |
|---|---|---|
| VP Customer Success / CCO | **Champion & primary economic buyer** | Fewer surprise churns, defensible forecast, team leverage |
| VP RevOps | **Technical champion / co-buyer** | One trusted account layer; less manual reporting; data-quality visibility |
| CRO | Executive sponsor | NRR/GRR movement; board-grade retention story |
| CFO | Approver | ROI model, forecast accuracy |
| Security/IT | Gatekeeper | SOC 2 path, data handling, no-training default, least-privilege connectors |

**Trigger events that open deals:** a surprise churn of a marquee logo; a missed retention number at board level; a new VP CS inheriting a mess; CS platform renewal coming due with low internal trust; RevOps mandate to consolidate reporting.

## 2.4 Current alternatives and their failure modes

| Alternative | Why it fails the ICP |
|---|---|
| CRM-native reporting/dashboards | Only sees CRM data; no usage/support/conversation evidence; no change detection |
| CS platforms (Gainsight/Totango/Catalyst/ChurnZero) | Heavy admin burden; scores opaque and distrusted; weak evidence/provenance; usage integration shallow in practice |
| Conversation intelligence (Gong/Chorus) | Deal-and-call-centric; no billing/usage/support join; account-level retention view thin |
| Forecasting tools (Clari/Aviso) | Pipeline-centric; renewal/CS lifecycle secondary; no evidence graph |
| BI + warehouse + dbt | Can compute anything, operationalizes nothing: no workflow, no explanation layer, no unstructured evidence, 6–12 months of internal build that decays |
| Internal spreadsheets + RevOps analysts | The status quo; the thing RIG replaces; doesn't scale and has no memory |
| Generic AI copilots | No canonical account resolution, no verification layer, hallucination risk kills executive trust |

Full competitive analysis: see [doc 19](19-competitive-positioning.md).

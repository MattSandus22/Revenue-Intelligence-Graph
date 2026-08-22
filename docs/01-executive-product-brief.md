# 1. Executive Product Brief

## 1.1 One-paragraph summary

**Revenue Intelligence Graph (RIG)** is a multi-tenant SaaS platform for B2B SaaS companies ($10M–$250M ARR, 50–500 managed accounts) that unifies CRM, product usage, support, billing, and conversation data into a canonical **account graph**, continuously detects and ranks revenue risk and expansion signals, **explains every insight with cited source evidence**, and routes human-approved next actions into the tools teams already use (Slack, Salesforce/HubSpot, task systems). The initial wedge is **Renewal Risk Intelligence**: identify accounts likely to fail to renew, show exactly why with traceable evidence, expose what data is missing or contradictory, recommend an intervention, and measure whether the intervention happened and changed the outcome.

## 1.2 The bet

Three converging failures create the opportunity:

1. **Health scores are not trusted.** CS platforms compute opaque scores over incomplete data. When a "green" account churns, trust collapses and teams revert to spreadsheets. The failure is not scoring — it is *unexplained scoring over unreliable data*.
2. **The data exists but the joins don't.** Usage sits in the warehouse or analytics tool, sentiment in call recordings, escalations in the support tool, commercial truth in CRM and billing — and no system resolves them to one account-level truth with provenance.
3. **LLMs finally make unstructured evidence computable** — call transcripts, tickets, emails — but a "chat over your CRM" product fails enterprise trust requirements. The defensible product is the **verification layer**: extraction separated from interpretation, interpretation separated from action, every claim mapped to evidence IDs.

RIG's differentiator is **auditable intelligence**: it is the only product in the category whose core contract is "we will never show you a claim we cannot cite."

## 1.3 What it is / is not

| This IS | This is NOT |
|---|---|
| An account-level truth layer across the customer lifecycle | A generic chatbot over CRM data |
| A graph of accounts, people, opportunities, contracts, usage, support, conversations, commitments, risks | A Gong/Clari/Salesforce/HubSpot/Gainsight/Intercom clone |
| A system that detects change, ranks urgency, explains why, and routes an approved next action | A dashboard that merely displays scores |
| An auditable intelligence product — every material insight cites evidence | An autonomous agent that sends communications without approval |
| A workflow product measured on retained/expanded ARR | A product providing unsupported AI summaries |

## 1.4 The seven questions RIG answers (with traceable evidence)

1. Which accounts are likely to churn, downgrade, fail to renew, or miss onboarding success?
2. Which accounts have credible expansion or cross-sell potential?
3. Which opportunities are stale, inaccurately forecasted, blocked, or likely to slip?
4. Which relationships are weak, single-threaded, or at risk from disengaged champions/executives?
5. What are the highest-leverage actions each user should take today?
6. Why does the system believe this, what evidence supports it, how confident is it, and what changed recently?
7. Which data-quality failures make a score, forecast, or executive KPI unreliable?

## 1.5 Customer outcomes and measurement

RIG instruments its own business case. Every tenant gets an **Outcomes dashboard** tracking:

### Retention & revenue outcomes (lagging)
| Metric | Definition | Baseline source | Target improvement (design-partner goal) |
|---|---|---|---|
| Gross Revenue Retention (GRR) | (Starting ARR − churn − downgrade) / Starting ARR, trailing 12m | Billing + CRM | +1.5–3.0 pts within 12 months *(assumption — validate in pilots)* |
| Net Revenue Retention (NRR) | (Starting ARR − churn − downgrade + expansion) / Starting ARR | Billing + CRM | +2–5 pts |
| Churned ARR avoided | ARR of accounts flagged high-risk ≥60 days pre-renewal, with completed mitigation, that renewed; vs. cohort-matched expectation | RIG risk lifecycle + renewal outcomes | Tracked, attributed with explicit methodology (see §1.7) |
| Expansion ARR surfaced/influenced | Closed expansion ARR where RIG insight preceded opportunity creation | RIG insight → opp linkage | Tracked |
| Renewal forecast accuracy | MAPE of risk-adjusted renewal forecast vs. actual, by quarter | Forecast snapshots vs. outcomes | <10% MAPE by quarter 3 of usage |
| Reduction in surprise churn | Churned accounts never flagged ≥30 days pre-renewal ÷ total churned | Risk lifecycle | Surprise-churn rate <20% of churn events |

### Operational outcomes (leading)
| Metric | Definition |
|---|---|
| % renewals with documented account plan | Renewals in next 180 days with plan status = active |
| CSM time saved per account | Self-reported + measured prep-time delta for QBR/renewal prep (survey + instrumentation) |
| Time to identify material risk | Signal event timestamp → risk `detected` state |
| Time from identification to owner action | Risk `detected` → first owner action (task started, meeting booked, note logged) |
| % at-risk accounts with active mitigation plan | Risks in accepted/in-progress ÷ all accepted risks |
| Account-data completeness | Weighted field completeness across required canonical fields (see Data Quality module) |
| Forecast coverage/hygiene | % opportunities with next step, close date sanity, activity in last 14 days, ≥2 stakeholders |
| Accounts with no executive alignment (count + ARR) | No exec-level stakeholder interaction in configurable window (default 90 days) |
| Accounts with no meaningful recent engagement (count + ARR) | No meeting/call/2-way conversation in window (default 45 days) |
| Action adoption & completion rate | Recommended actions accepted ÷ shown; completed ÷ accepted |
| Insight precision | High-severity alerts marked valid ÷ (valid + invalid) via feedback controls |
| False positive / false negative tracking | FP: risk dismissed as incorrect or renewed with no intervention; FN: churned account never flagged. Reviewed in outcome postmortems |

### Leading vs. lagging, correlation vs. causation — product stance

- **Leading indicators** (usage decline, support escalation, champion disengagement, missing QBR, unresolved onboarding task, negative sentiment, price objection, payment issue) drive alerts and workflow.
- **Lagging indicators** (downgrade, non-renewal, churn, lost expansion, overdue invoice) drive learning, calibration, and the outcomes dashboard.
- RIG **never claims causation from correlation**. Attribution language is fixed in the product: signals are "associated with," interventions are "correlated with outcome," and churn-avoided figures always display their methodology (cohort comparison, stated confounders, sample size). Deterministic alerts (e.g., "invoice 14 days overdue" — a fact) are visually distinct from probabilistic insights (e.g., "renewal risk 72/100" — a calibrated prediction).

## 1.6 ROI calculator model

Shipped as an in-product and spreadsheet model for AEs. All inputs configurable; defaults shown for a typical mid-market target.

**Inputs**

| Input | Default | Notes |
|---|---|---|
| ARR under management | $40M | |
| Managed accounts | 200 | |
| Average contract value (ACV) | $200K weighted; median $80K | |
| Current gross churn rate | 12% ARR/yr | |
| Current GRR / NRR | 88% / 105% | |
| Target GRR improvement | +2.0 pts | Conservative case +1.0; aggressive +3.0 |
| CSM count / fully loaded cost | 8 / $140K | |
| Hours per account per month on manual data gathering & reporting | 3.0 | Discovery-validated per prospect |
| Renewal forecast variance (current) | ±15% | |
| Expansion ARR influenced target | 1% of ARR | Secondary; not in conservative case |

**Model (annualized)**

```
churn_arr_baseline        = ARR × churn_rate                        = $4.80M
churn_arr_avoided         = ARR × GRR_improvement_pts               = $0.80M   (2 pts)
gross_margin_on_retained  = churn_arr_avoided × 80% GM              = $0.64M
csm_time_value            = accounts × hrs_saved × 12 × loaded_hr
                          = 200 × 1.5h saved × 12 × $70/h           = $0.25M
expansion_influenced_gm   = ARR × 1% × 80% (aggressive case only)   = $0.32M
conservative_annual_value = 0.5 × ($0.40M retained GM) + $0.25M     = $0.45M
base_annual_value         = $0.64M + $0.25M                         = $0.89M
```

At a base-case platform price of $60–90K/yr (see Pricing doc), base-case ROI is **~10–15×** and the conservative case still clears **5×**. The calculator shows all three cases side by side and never presents the aggressive case as the headline. *(Assumption: 50% attribution haircut in conservative case; validated per design partner via cohort methodology.)*

## 1.7 Attribution methodology (what "churned ARR avoided" means)

1. Define cohort: accounts flagged high-risk ≥60 days before renewal.
2. Split: (a) mitigation completed, (b) risk accepted but no mitigation completed.
3. Compare renewal rates between (a) and (b), and against pre-RIG historical renewal rate for similar-risk accounts where labels exist.
4. Report the delta with sample sizes and an explicit note: "correlational; selection effects possible (CSMs may mitigate the most savable accounts)."
5. Never sum "avoided churn" into an unqualified headline number.

## 1.8 Success criteria for the product itself

- **Trust:** ≥80% of high-severity alerts rated valid by users; hallucinated-citation rate = 0 (hard gate, see AI doc).
- **Adoption:** ≥70% weekly active rate among licensed CSMs by week 8 of deployment; weekly executive brief opened by ≥1 VP+ per tenant.
- **Outcome:** at least 2 design partners attribute a saved renewal to RIG within the first 2 quarters, documented as case studies.
- **Commercial:** see PMF metrics in the MVP/Roadmap docs.

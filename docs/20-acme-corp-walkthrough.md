# 20. Sample Walkthrough — NorthstarCloud × Acme Corp

Fictional vendor **NorthstarCloud** (B2B SaaS, RIG tenant `ten_nsc`) and its customer **Acme Corp**. Dates anchored: today = **2026-08-22**; renewal = **2026-11-22** (92 days).

## 20.1 Canonical account profile

```json
{
  "id": "acc_acme", "tenant_id": "ten_nsc",
  "name": "Acme Corp", "domains": ["acme.com"],
  "industry": "Logistics SaaS", "segment": "Mid-Market", "tier": "Enterprise",
  "territory": "NA-East", "lifecycle_stage": "established",
  "arr_cents": 12000000, "currency": "USD",
  "arr_provenance": {"chosen_source": "billing.stripe", "candidates": [
     {"source": "billing.stripe", "value": 12000000, "as_of": "2026-08-21"},
     {"source": "crm.hubspot", "value": 12000000, "as_of": "2026-08-20"}]},
  "renewal_date": "2026-11-22",
  "contract": {"id": "con_9921", "term_months": 24, "auto_renew": false, "notice_days": 60,
               "notice_deadline": "2026-09-23"},
  "plan": "Platform – 100 seats",
  "owners": {"csm": "u_ortiz", "ae": "u_kim", "exec_sponsor": "u_vpcs"},
  "parent_account_id": null,
  "children": [{"id": "acc_acme_labs", "name": "Acme Labs (new dept)", "hierarchy_source": "crm", "created": "2026-08-05"}],
  "scores_asof_2026_08_22": {
    "renewal_risk": {"value": 74, "band": [65, 81], "trend_30d": "+22", "version": "renewal_risk@v4.1", "reliability": 0.91},
    "health": {"value": 38, "trend_30d": "-19"},
    "adoption": {"value": 41, "trend_30d": "-17"},
    "relationship": {"value": 35}, "support_friction": {"value": 71},
    "financial": {"value": 52}, "data_reliability": {"value": 84}
  },
  "crm_forecast_field": "Likely Renew",
  "data_gaps": ["no mutual action plan on record", "email engagement connector not enabled"]
}
```

## 20.2 Graph nodes and edges (excerpt)

```json
{"nodes": [
  {"id":"acc_acme","type":"Account"}, {"id":"acc_acme_labs","type":"Account"},
  {"id":"ct_dana","type":"Contact","props":{"name":"Dana Reyes","title":"VP Operations","role":"champion","status":"active"}},
  {"id":"ct_priya","type":"Contact","props":{"name":"Priya Shah","title":"Ops Admin","power_user":true}},
  {"id":"ct_lee","type":"Contact","props":{"name":"Lee Moreau","title":"Ops Analyst","power_user":true}},
  {"id":"ct_chen","type":"Contact","props":{"name":"M. Chen","title":"CFO","role":"economic_buyer"}},
  {"id":"con_9921","type":"Contract"}, {"id":"rnw_2026","type":"Renewal"},
  {"id":"inv_2214","type":"Invoice"}, {"id":"tkt_zd8841","type":"Ticket"},
  {"id":"call_388412","type":"MeetingCall"}, {"id":"seg_388412_41","type":"TranscriptSegment"},
  {"id":"met_core_actions","type":"UsageMetric"}],
 "edges": [
  {"src":"acc_acme","edge":"parent_of","dst":"acc_acme_labs","confidence":1.0,"source":"crm.hubspot","valid_from":"2026-08-05"},
  {"src":"acc_acme","edge":"employs","dst":"ct_dana","confidence":1.0,"source":"crm.hubspot"},
  {"src":"ct_dana","edge":"plays_role","dst":"acc_acme","props":{"role":"champion","engagement_index_30d":0.31,"baseline":0.78},"valid_from":"2024-11-01"},
  {"src":"ct_chen","edge":"plays_role","dst":"acc_acme","props":{"role":"economic_buyer","last_interaction":"2026-05-04"}},
  {"src":"acc_acme","edge":"has_renewal","dst":"rnw_2026","confidence":1.0,"source":"billing.stripe+crm"},
  {"src":"acc_acme","edge":"billed_by","dst":"inv_2214","confidence":1.0,"source":"billing.stripe"},
  {"src":"acc_acme","edge":"has_ticket","dst":"tkt_zd8841","confidence":1.0,"source":"support.zendesk"},
  {"src":"ct_dana","edge":"participated_in","dst":"call_388412","confidence":1.0},
  {"src":"seg_388412_41","edge":"mentions","dst":"competitor:CompetitorX","props":{"context":"comparing_pricing"},"confidence":0.9,"source":"llm:competitor_mention@v2"}]}
```

## 20.3 Product-usage events and aggregates

```json
{"raw_event_sample": {"tenant_id":"ten_nsc","account_ref":"acme.com","user_ref":"priya@acme.com",
  "event":"shipment_report_generated","event_at":"2026-07-02T14:11:32Z","properties":{"module":"reporting"}},
 "usage_metric_daily_excerpt": [
  {"account_id":"acc_acme","metric":"core_actions","date":"2026-06-15","value":428,"user_count":41},
  {"account_id":"acc_acme","metric":"core_actions","date":"2026-07-20","value":389,"user_count":37},
  {"account_id":"acc_acme","metric":"core_actions","date":"2026-08-20","value":284,"user_count":29}],
 "baseline_90d_weekday_adjusted": 412,
 "trailing_14d_mean": 284, "delta_pct": -31.1, "sustained_days": 17,
 "inactive_power_users": [{"contact":"ct_priya","last_active":"2026-07-21","inactive_days":32},
                          {"contact":"ct_lee","last_active":"2026-07-18","inactive_days":35}]}
```

## 20.4 Support ticket

```json
{"id":"tkt_zd8841","source":"support.zendesk","source_record_id":"8841",
 "subject":"Carrier-rate sync failing for all EU shipments","priority":"critical",
 "status":"open","opened_at":"2026-08-14T09:02Z","age_days":8,
 "escalated":true,"category":"integrations","requester":"ct_priya",
 "sla_breach":true,"last_agent_update":"2026-08-19T16:40Z",
 "satisfaction_history_90d":{"ratings":3,"negative":2}}
```

## 20.5 Conversation transcript excerpts (call_388412, 2026-08-12, QBR prep call)

```json
[{"segment":41,"t":"00:30:32","speaker":"Dana Reyes (Acme)","text":"Honestly, we have to justify every line item next quarter. CompetitorX quoted us about 30% less for next year, and finance is asking me why we wouldn't at least look at it."},
 {"segment":44,"t":"00:31:10","speaker":"J. Ortiz (NorthstarCloud)","text":"That's fair — can we walk through where the reporting module is falling short before then?"},
 {"segment":58,"t":"00:38:47","speaker":"Dana Reyes (Acme)","text":"The EU sync issue is the real problem. My team stopped using the reporting module because they don't trust the numbers while that ticket is open."}]
```

## 20.6 Contract and invoice records

```json
{"contract":{"id":"con_9921","account_id":"acc_acme","start":"2024-11-22","end":"2026-11-22",
  "term_months":24,"auto_renew":false,"notice_days":60,"notice_deadline":"2026-09-23",
  "tcv_cents":24000000,"line_items":[{"product":"Platform","qty":100,"unit":"seat","unit_price_cents":100000,"period":"annual"}],
  "source":"docs.drive/contracts/acme-2024.pdf","terms_extraction":"human_confirmed"},
 "invoice":{"id":"inv_2214","source":"billing.stripe","source_record_id":"in_1PxQ...",
  "amount_cents":3000000,"issued":"2026-07-24","due":"2026-08-08","status":"overdue",
  "days_past_due":14,"dunning_attempts":2,"last_payment_ok":"2026-04-25"}}
```

## 20.7 Deterministic signals (active)

| Signal | Key facts | Severity | Confidence |
|---|---|---|---|
| `key_user_inactive` ×2 (U2) | Priya 32d, Lee 35d inactive (both top-decile users) | high | 1.00 |
| `critical_ticket_unresolved` (S2) | ZD-8841 critical, open 8d, SLA breach | **critical** (tier bump) | 1.00 |
| `payment_late` (C3) | INV-2214 14 days past due, 2 dunning attempts | medium | 1.00 |
| `renewal_no_plan` (C1) | Renewal in 92d; no mutual action plan | high | 1.00 |
| `notice_period_approaching` (C2) | Notice deadline 2026-09-23 (32 days) | high | 1.00 |
| `no_exec_engagement` (R3) | CFO (econ buyer) last touched 110d ago | high (renewal <120d) | 0.95 |

## 20.8 AI-derived signals

| Signal | Extraction | Severity | Confidence | Review |
|---|---|---|---|---|
| `usage_drop_vs_baseline` (U1, statistical) | −31% vs. baseline, 17d sustained | high | 0.94 (fresh feed) | n/a (stat) |
| `competitor_mention` (C7) | CompetitorX, context `comparing_pricing`, seg 41 span | high | 0.90 | **confirmed by u_ortiz 2026-08-13** |
| `pricing_budget_concern` (C6) | "justify every line item", "quoted 30% less" spans | high | 0.90 | confirmed |
| `negative_sentiment` (S4) | call overall negative; aspects: support(neg, seg 58), pricing(neg, seg 41) | medium | 0.70 | confirmed |

## 20.9 Renewal-risk score with components (v4.1, as of 2026-08-22)

```
component               weight  norm_value  contribution
usage_trajectory         0.25      0.82       +20.5      (U1, U2: −31% + 2 power users dark)
relationship_strength    0.20      0.75       +15.0      (champion engagement 0.31 vs 0.78; no exec touch 110d)
support_friction         0.15      0.85       +12.8      (critical unresolved 8d, 2 neg CSAT)
commercial_engagement    0.15      0.70       +10.5      (no plan, notice in 32d, no renewal activity)
billing_health           0.10      0.60        +6.0      (14d overdue, 2 dunning)
sentiment_trend          0.10      0.80        +8.0      (confirmed negative + pricing/competitor)
hygiene_penalty          0.05      0.30        +1.5      (missing MAP; CRM category unsupported)
                                              ------
renewal_risk = 74.3 → 74     band [65, 81]   reliability 0.91
p_nonrenewal (default calibration, labeled) ≈ 0.38 [0.29, 0.47]
change_30d: +22  (drivers: payment_late new +6, competitor_mention +9, usage worsened +7)
```

## 20.10 Evidence card
See the full canonical JSON in [doc 10 §10.1](10-evidence-and-explainability.md) — that example **is** this Acme card (`evc_01J9…`).

## 20.11 Account-risk narrative (as rendered, claim classes inline)

> **Acme Corp — $120K renewal in 92 days — HIGH RISK (74/100, band 65–81).**
> Usage has fallen 31% vs. Acme's 90-day baseline and two of its three most active users have been inactive for 30+ days **[FACT]**. A critical EU carrier-sync ticket has been open 8 days and Dana Reyes' team reports they stopped using the reporting module because of it **[FACT / AI-INTERPRETED, confirmed]**. On the Aug 12 call, Acme raised budget scrutiny and a 30%-lower quote from CompetitorX **[AI-INTERPRETED, confirmed]**. The $30K invoice is 14 days overdue **[FACT]**. The CFO — economic buyer — has had no interaction in 110 days, the 60-day notice deadline is 32 days away, and no mutual action plan exists **[FACT]**. The CRM forecast "Likely Renew" is not supported by this evidence **[PREDICTION: renewal probability ≈62%, range 53–71%]**.

## 20.12 Recommended mitigation playbook (`pb_renewal_save`, SUGGESTED)

1. **Resolve the trust-breaking ticket (48h):** escalate ZD-8841 to engineering lead; daily customer updates until closed. *Exit: ticket resolved + Dana confirms team resumed reporting module.*
2. **Executive re-alignment (7d):** VP CS requests meeting with CFO M. Chen; value recap with usage/ROI evidence pack. *Exit: meeting held, econ-buyer sentiment logged.*
3. **Champion re-engagement (7d):** working session with Dana; reactivate Priya/Lee with targeted enablement. *Exit: power users active 5 consecutive days.*
4. **Commercial path (14d):** finance sync on overdue invoice (decouple from renewal talk); prepare pricing/packaging options vs. CompetitorX before notice deadline **[approval: VP CS]**.
5. **Mutual action plan (10d):** draft MAP with Dana through renewal; log in RIG; summary write-back to HubSpot **[approval gate]**.

## 20.13 CSM task list (created on playbook accept)

| Task | Assignee | Due | Sync |
|---|---|---|---|
| Escalate ZD-8841 to eng lead + open daily-update thread | u_ortiz | Aug 23 | Slack #support-escalations |
| Book CFO value-review meeting | u_vpcs | Aug 29 | HubSpot task (approved) |
| Enablement session: Priya, Lee | u_ortiz | Aug 28 | — |
| Invoice follow-up with Acme AP (with finance) | u_finance_liaison | Aug 26 | — |
| Draft MAP + review with Dana | u_ortiz | Sep 1 | — |
| Competitive/pricing options brief for notice-deadline decision | u_kim | Sep 5 | — |

## 20.14 Slack alert

> 🔴 **Renewal risk: Acme Corp — $120K, renews in 92d** (risk 74 ↑22 this month)
> Why now: payment 14d overdue + confirmed competitor quote (CompetitorX, −30%) + usage −31% + critical ticket open 8d. Notice deadline **Sep 23**.
> CRM says "Likely Renew" — evidence doesn't support it.
> `[Open evidence]` `[Accept risk]` `[Dismiss…]` `[Snooze 7d]`
> _All claims cited — click evidence to verify. You own this account._

## 20.15 Weekly executive-brief entry

> **Acme Corp — $120K (Nov 22) — moved to High Risk (74, +22).** Usage −31% vs. baseline; critical support issue open 8d has suspended reporting-module use; confirmed competitor pricing pressure (CompetitorX −30%); invoice 14d overdue; no MAP; economic buyer unengaged 110d. **Mitigation started Aug 22** (5-step save play; exec meeting requested). Notice deadline Sep 23 — decision window is now. *[12 citations →]*
> ⚠ Data note: CRM forecast field conflicts with evidence (DQ-482).

## 20.16 Investigation answer — "Why is Acme at risk?"

```json
{"answer": "Acme Corp's renewal risk is 74/100 (High), up 22 points in 30 days. Five factors drive it: (1) product usage is down 31% vs. its 90-day baseline with two former power users inactive 30+ days; (2) a critical support ticket (EU carrier sync) has been open 8 days and the customer says it stopped their reporting usage; (3) on the Aug 12 call Acme cited budget scrutiny and a 30% lower quote from CompetitorX (human-confirmed extraction); (4) a $30K invoice is 14 days overdue; (5) commercial coverage is weak — no mutual action plan, CFO unengaged 110 days, and the 60-day notice deadline is Sep 23.",
 "confidence": 0.82,
 "methodology": "Score components renewal_risk@v4.1; filters: account = Acme Corp; sources: usage warehouse (fresh 6h), Zendesk (5m), Stripe (12m), HubSpot (14m), call transcript (confirmed extractions only)",
 "evidence": ["ev_9f2 usage metric","ev_a11 inactive users","ev_t88 ticket ZD-8841","ev_c44 transcript seg41/58","ev_i22 invoice INV-2214","ev_r03 stakeholder recency","ev_k91 contract notice terms"],
 "gaps": ["Email engagement not connected — relationship view may undercount touches"],
 "caveat": "CRM forecast field says 'Likely Renew'; that field is not supported by current evidence (see DQ-482)."}
```

## 20.17 Data-quality warning (CRM forecast)

```json
{"id":"DQ-482","class":"metric_conflict","severity":"medium",
 "title":"CRM renewal forecast 'Likely Renew' inconsistent with evidence-based estimate",
 "detail":"HubSpot renewal property = 'Likely Renew' (set 2026-06-02 by u_ortiz, 81 days ago, before current risk signals). RIG estimate: 62% [53–71]. Field is stale relative to 6 new negative signals since Aug 1.",
 "impact":"Renewal roll-ups using the CRM field overstate Q4 secure ARR by up to $120K for this account.",
 "remediation":{"suggested":"Owner updates CRM field or documents rationale; write-back available with approval","assignee":"u_ortiz"},
 "affected":["renewal_forecast_q4","exec_brief_2026w34"]}
```

## 20.18 Expansion insight (explicitly subordinated)

```json
{"id":"ins_exp_771","kind":"opportunity","state":"conditional",
 "title":"Expansion potential: Acme Labs department (CONDITIONAL — blocked by active renewal risk)",
 "narrative":"Acme created a new 'Acme Labs' child account in CRM on Aug 5 [FACT] and three acme.com users with Labs titles registered in-product [FACT]. Historically similar department adoptions preceded seat expansion. HOWEVER: the parent account carries a critical renewal risk (74/100). Recommendation: do not open expansion conversations until save-play steps 1–3 complete; revisit at risk < 55.",
 "blocking_risks":["evc_01J9…"], "suggested_timing":"post-mitigation, before renewal negotiation",
 "approval_note":"No draft opportunity will be created without explicit approval; creation currently discouraged by policy (open critical risk)."}
```

## 20.19 Post-outcome learning records

**Scenario A — successful renewal (recorded 2026-11-23):**
```json
{"risk_id":"evc_01J9…","outcome":"renewed","outcome_arr_delta_cents":0,
 "renewal_terms":{"term_months":12,"discount_pct":5,"notes":"price concession vs CompetitorX quote"},
 "intervention_summary":{"playbook":"pb_renewal_save","steps_completed":5,
   "key_events":["ticket resolved Aug 25","CFO meeting Sep 2","MAP signed Sep 12","usage recovered to −6% by Oct 10"]},
 "attribution_note":"correlational — flagged 92d pre-renewal, full mitigation completed",
 "labels_emitted":{"risk_label":{"flagged":true,"outcome":"renewed","intervention":"completed"},
   "calibration_update":"p=0.38 → outcome 0 (renewed); joins isotonic set (intervention-stratified)"},
 "postmortem":{"root_cause_primary":"unresolved_support_issue","secondary":["competitor_price_pressure"],
   "what_worked":"48h ticket escalation restored champion trust before commercial talks",
   "detector_notes":"U1 lead time 41 days before CRM showed any risk — cite in case study (with consent)"}}
```

**Scenario B — lost churn (counterfactual same account):**
```json
{"risk_id":"evc_01J9…","outcome":"churned","churn_effective":"2026-11-22","arr_lost_cents":12000000,
 "intervention_summary":{"playbook":"pb_renewal_save","steps_completed":2,
   "gaps":["CFO meeting never booked (2 attempts, no response)","ticket resolved Sep 4 — 21 days total, after trust broke"]},
 "postmortem":{"root_cause_primary":"champion_lost_confidence","secondary":["competitor_price_pressure","exec_relationship_gap"],
   "surprise_churn":false,"detection_lead_days":92,
   "fn_fp_accounting":"true positive; mitigation incomplete",
   "process_findings":["exec-escalation SLA breached (no ack in 5d) — rule tightened","notice deadline passed without commercial options ready"],
   "system_learning":{"labels":"flagged/churned/intervention_partial → survival-model training set",
     "playbook_stats":"pb_renewal_save completion 2/5 associated with loss — completion-rate telemetry added to VP dashboard"},
   "win_back":{"stage":"cooling_off","revisit":"2027-05-01","owner":"u_kim"}}}
```

# 14. UX Information Architecture and Annotated Wireframe Descriptions

## 14.0 Visual philosophy

- **Serious, enterprise-grade, dense but readable:** 13–14px data type, generous line height, 8pt grid; tables are the primary object, cards second, charts third.
- **Evidence-first:** every number/claim is hoverable → provenance popover; click → evidence card. Claim-class badges (FACT / PREDICTION / AI-INTERPRETED / SUGGESTED) use shape + text, never color alone.
- **Risk encoding:** severity = icon + label + color (WCAG AA contrast); colorblind-safe palette; trend arrows always paired with signed numbers.
- **No AI sparkle:** no gradient-magic buttons, no "✨ generated" theater; AI outputs look like sober labeled analysis.
- **Anti-overload doctrine:** default views show only what has *changed or needs action*; full data one click deeper. Every screen answers "what should I do next?" above the fold. We deliberately do not show: raw signal firehoses on home screens, unreviewed LLM output in exec surfaces, vanity charts without decisions attached, scores without explanations.
- **Uncertainty display:** ranges and confidence bands, "insufficient data" states instead of fake numbers, staleness badges on old evidence.

### Global IA

```
Left nav: Home · Renewals · Workbench · Accounts · Signals · Forecast (V2) ·
          Expansion (V2) · Data Quality · Briefs · Copilot
Admin nav (role-gated): Integrations · Playbooks · Scores & Models · Security & Audit
Global: account search (⌘K), notification tray, feedback entry point
```

### Shared screen conventions (apply to all 16 screens)
- **Loading:** skeleton tables/cards; no spinners over whole pages; slow queries (>3s) show progress + partial results where safe.
- **Empty states:** explain *why* empty (no data connected vs. filters exclude vs. genuinely nothing) + primary next action (e.g., "Connect billing to enable financial signals").
- **Error states:** human-readable cause + retry + reference ID; degraded-data banners when freshness SLA breached ("Usage data 3 days old — scores affected").
- **Permission behavior:** rows/fields outside grants are absent (not masked placeholders) except evidence references, which show "restricted — request access"; screens fully hidden when role lacks them.
- **Responsive:** desktop-first; ≥1280px optimal; tablet functional (tables collapse to cards); phone = read-only alerts, briefs, approvals (via responsive web + Slack — no native app).
- **Accessibility:** WCAG 2.1 AA; full keyboard nav; visible focus; screen-reader labels include claim class + confidence; tables with proper headers/scope; no color-only meaning.
- **Actions:** every action optimistic-UI with undo where reversible; irreversible/external actions get confirmation with change preview.

## Screens

### 1. Executive Home
- **User:** CRO/CCO/CEO (read-only exec role). **Job:** "Is retention on track, and what needs my weight this week?"
- **Hierarchy:** (1) KPI strip — GRR/NRR trend, ARR renewing next 2 quarters by risk band, risk-adjusted forecast range vs. target; (2) "Needs executive attention" list (≤7 items: escalations + strategic-account critical risks) with evidence links; (3) What-changed digest since last visit; (4) data-quality caveat banner if material.
- **Components:** KPI tiles with sparklines + confidence bands; attention list rows (account, ARR, risk, why-now one-liner, owner, CTA "view evidence"); no filters beyond time period. Drill-down: tile → underlying metric lineage; row → Account 360.
- **Not shown:** signal feeds, unreviewed AI content, per-CSM operational detail.

### 2. Renewal Command Center
- **User:** VP CS (primary), CSM (own book). **Job:** run the renewal quarter.
- **Hierarchy:** (1) quarter selector + totals: ARR due, risk-adjusted range, coverage %; (2) renewal calendar/timeline (months × ARR bars segmented by risk band, notice-period ticks); (3) renewal table: account, ARR, date, notice deadline, risk score + trend, plan status, owner, exec sponsor, last meaningful touch, CRM category vs. RIG estimate (delta flagged); (4) side panels: surprise-churn watch, owner workload, cohort analysis tab, scenario mode toggle.
- **Filters:** quarter, segment, tier, owner, risk band, plan status, delta-flag. **Drill-down:** row → Account 360 renewal tab; scenario toggle → editable probability overrides (sandbox, labeled, never persisted to model).
- **Charts:** stacked ARR-by-month bars; calibration mini-chart (predicted vs. actual, once data exists).

### 3. Risk and Opportunity Workbench
- **User:** CSM/AM daily; leaders in team mode. **Job:** "What do I act on today?"
- **Hierarchy:** (1) triage queue (new/updated items, count badge); (2) ranked table: urgency rank (hover = formula), account, ARR at stake, insight title, severity, confidence, age, state, owner, next action; (3) detail drawer on row click: evidence card, timeline excerpt, recommended actions, lifecycle controls, feedback controls.
- **Filters:** doc 6 D full set; saved views per user/team. **Interactions:** accept/dismiss (reason required), assign, snooze, start playbook, create task (with external sync preview), escalate.
- **Empty state:** "Nothing needs triage — 3 in-progress mitigations below." (never celebratory-cute).

### 4. Account 360 / Unified Account Graph
- **User:** CSM/AE/anyone with account access. **Job:** full truth of one account in 60 seconds.
- **Hierarchy:** (1) header: name, hierarchy breadcrumb, ARR (+source badge), renewal countdown, owners, lifecycle, tier; score strip (health, risk, adoption, relationship, support, financial, data-reliability) each with trend arrow + click-to-explain; (2) tab row: Overview | Timeline | Stakeholders (map + graph view) | Usage | Support | Commercial (contracts/invoices/opps) | Plans & QBRs | Signals; (3) Overview = AI account summary (cited, labeled) + open insights + upcoming commitments + data gaps callout.
- **Graph view:** stakeholder/relationship mini-graph (contacts sized by engagement, edges by interaction recency; departed contacts ghosted). **Conflicts:** field-level ⚠ affordances (doc 6 A.1).

### 5. Account Evidence Timeline
- Embedded as Account 360 tab + full-screen mode. **Job:** reconstruct what happened, with provenance.
- Vertical stream grouped by day; entries typed with icons (call, ticket, invoice, signal, score change, action, note); each entry: source badge, event-vs-ingested time on hover, author, confidence for derived items, link to source. Filters: category, severity, person, date range. "Since last visit" marker; jump-to-date. Score-change entries expand to component-delta explanations.

### 6. Account Plan
- **User:** CSM; approver VP CS (strategic). **Job:** create/maintain a defensible renewal/success plan.
- Sections: objectives, risks (linked to live insights — auto-updating status), plays/milestones with owners+dates (mutual-action-plan subset flaggable customer-visible), stakeholder map completeness widget, renewal strategy, generator button ("Draft from evidence" — output fully cited, editable, labeled AI-drafted until human saves). Plan status chip drives C1 signal. CRM write-back of summary: preview + approve.

### 7. Opportunity / Forecast Inspection
- **User:** Sales manager/VP Sales; AE own deals. **Job:** trust-but-verify the forecast.
- Roll-up header (by team/period: pipeline by category, hygiene %, calibration note) → deal table: opp, amount, stage+age percentile, category, hygiene score, evidence-consistency flag, slip count, next step (with quality label), threads count → deal drawer: evidence vs. category panel (activity recency, sentiment labels, next-step extraction, stakeholder coverage), history of category/close-date moves, suggested category change (approval-gated write-back).

### 8. Data Quality Command Center
- **User:** RevOps/data admin. **Job:** find, prioritize, fix data trust issues.
- (1) Health header: completeness %, freshness SLA status per source, open issues by severity, "insights currently degraded" count; (2) issue table: class, severity, affected accounts/ARR, impact statement, age, assignee, status; (3) drawer: lineage view, affected scores/reports, remediation (deep link to source record / in-RIG mapping fix / merge tool), resolution log. Duplicate-review queue and identity-match review queue live here.

### 9. Signals Explorer
- **User:** RevOps/CS Ops/analyst. **Job:** tune the sensor array.
- Catalog table (taxonomy, class, enabled, per-segment thresholds, volume 30d, acceptance rate, FP rate) → signal detail: definition (YAML view), firing history chart, precision metrics from feedback, threshold editor with **backtest preview** ("at this threshold, last quarter would have fired 34 times; 71% accepted"), suppression rules. Publishing changes requires model_admin + versioned.

### 10. Investigation Copilot
- **User:** all business roles (permission-scoped). **Job:** ad-hoc questions answered with evidence.
- Chat-style but stateful-analysis layout: question box with suggested templates; answer block = concise answer → structured evidence table → methodology accordion (compiled query shown in plain language + applied filters) → confidence + data-gaps note → source links; follow-up chips ("save as view", "create tasks…" → approval flow). History sidebar (audited). Refusal states honest ("I can't see billing data for these accounts — connector disabled").

### 11. Weekly Executive Brief
- **User:** author RevOps/VP CS; consumer execs. **Job:** produce/consume the verified weekly narrative.
- Draft view: sections (portfolio delta, top risks, top opportunities, actions taken, data caveats) with per-sentence citation chips; excluded-claims appendix ("2 claims omitted: unverified"); edit mode (edits tracked, edited claims re-verified or marked human-edited); approve → distribution panel (email list, Slack channels, PDF/slides export). Consumer view: read-optimized, every claim clickable to evidence, "what changed vs. last week" toggle.

### 12. Integration Setup and Health
- Doc 11 §11.3 wizard + health dashboard. Data admin only. Connector cards (status, freshness, error budget, quota), mapping editor, identity-resolution preview, backfill progress, DLQ browser with replay, disconnect/purge flows with confirmations.

### 13. Playbook Builder
- **User:** CS Ops/model admin. **Job:** encode plays.
- List → editor: trigger criteria (signal/severity/segment picker), steps (task templates, owners by role, SLAs, dependencies), exit criteria, notifications, write-back steps (marked, approval-flow badge); version history; simulation ("would have triggered on 12 accounts last quarter"); publish gate.

### 14. Insight Feedback and Outcome Review
- **User:** CS Ops/RevOps/leadership ritual. **Job:** close the learning loop.
- Tabs: (a) Feedback stream (verdicts by insight type, drill to comments); (b) Precision dashboard (acceptance/FP by signal type & segment, trends vs. threshold changes); (c) Outcome postmortems: churned/renewed accounts with full risk-lifecycle replay (what fired when, who did what, outcome, root cause tagging UI); (d) FN report (churns never flagged — the humility view).

### 15. Model / Score Configuration
- **User:** model admin (+ analyst sandbox). **Job:** adapt scoring safely.
- Score list → config: components/weights per segment (sliders + numeric), baseline windows, missing-data policy visibility, **backtest panel** (score distribution shift, would-have-flagged diff, calibration on history), draft vs. published states, four-eyes publish approval, version changelog. Cold-start status card ("predictive mode: 34/200 outcomes").

### 16. Security, Access, and Audit Admin
- **User:** org/security admin, audit viewer. **Job:** govern access, prove compliance.
- Tabs: Users & roles (SCIM status, scope grants, last login, external users with expiry); Policies (field-level classes, source visibility, export rules); SSO/SCIM config; Audit log search (actor/action/object/date, export with logging); Access reviews (attestation runs); AI governance (provider policy, feature toggles like transcript excerpts, consent records); Data retention & DSR queue (deletion requests with status/certificates).

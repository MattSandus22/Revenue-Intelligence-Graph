# 4. Personas and Permissions

## 4.1 Personas

For each persona: goals, pains, primary surfaces, key actions, default permissions, success metrics.

### 1. Chief Revenue Officer / Chief Customer Officer
- **Goals:** Hit NRR/GRR targets; defensible board narrative; early visibility into material risk; team accountability.
- **Pains:** Second-hand stale summaries; conflicting numbers between systems; surprises at QBRs and renewals.
- **Primary surfaces:** Executive Home, Weekly Executive Brief, Renewal Command Center (portfolio view).
- **Key actions:** Read/annotate briefs; trigger executive escalation; request investigation; approve strategic-account plans.
- **Default permissions:** Read-all accounts in org; no connector/model admin; can export approved reports; write limited to annotations, escalations, approvals.
- **Success metrics:** GRR/NRR trend; forecast accuracy; % strategic accounts with exec sponsor; brief engagement.

### 2. VP Customer Success
- **Goals:** No surprise churn; consistent account practice; workload balance; defensible renewal forecast.
- **Pains:** Can't verify plan compliance; escalations arrive late; health scores distrusted.
- **Primary surfaces:** Renewal Command Center, Risk Workbench (team view), Outcomes dashboard.
- **Key actions:** Triage/assign risks; approve mitigation plans for strategic accounts; run team reviews from workbench; approve exec brief before distribution.
- **Default permissions:** Read/write all CS-owned accounts; assign owners; configure CS playbooks; no connector admin.
- **Success metrics:** Surprise-churn rate; % at-risk accounts with active mitigation; time-to-triage; renewal forecast MAPE.

### 3. VP Sales
- **Goals:** Reliable pipeline & renewal-expansion forecast; deal risk visibility; multi-threading discipline.
- **Pains:** Commit deals slipping; happy-ears forecasts; no evidence to challenge reps.
- **Primary surfaces:** Forecast Inspection, Risk Workbench (opportunity lens), Expansion pipeline view.
- **Key actions:** Inspect deals vs. evidence; challenge forecast categories (writes suggestion, rep/CRM change requires approval flow); assign expansion follow-ups.
- **Default permissions:** Read all sales-owned accounts/opps; playbook config for sales plays; no CS-private fields (e.g., CSM sentiment notes) if tenant restricts.
- **Success metrics:** Forecast accuracy/calibration; slipped-commit rate; multi-threading coverage.

### 4. VP Revenue Operations
- **Goals:** One trusted data layer; reporting automation; process compliance instrumentation.
- **Pains:** Owns every integration break; blamed for bad data; endless ad-hoc report requests.
- **Primary surfaces:** Data Quality Command Center, Integration Setup & Health, Model/Score Configuration, all analytics surfaces.
- **Key actions:** Configure connectors, field mappings, source-of-truth rules; manage score weights/segments; approve write-back rules; manage metric definitions.
- **Default permissions:** Full data-admin; model-config admin; read-all; cannot manage users/security unless also org admin.
- **Success metrics:** Data completeness/freshness; % insights blocked by data-quality issues; report-automation hours saved.

### 5. Customer Success Operations leader
- Subset of VP RevOps focused on CS: playbook design, health-score configuration, CSM capacity, QBR cadence compliance.
- **Surfaces:** Playbook Builder, Model/Score Config (CS scores), Workbench admin views.
- **Permissions:** Playbook admin; CS score config; read CS accounts; no billing-margin fields.
- **Success metrics:** Playbook completion rates; alert precision for CS signals; CSM adoption.

### 6. Customer Success Manager / Account Manager
- **Goals:** Know today's priorities; walk into every call fully briefed; save at-risk accounts; hit renewal targets without living in 8 tabs.
- **Pains:** Data gathering eats selling/saving time; alerts from tools they distrust; QBR prep is a day of copy-paste.
- **Primary surfaces:** Risk Workbench (my book), Account 360, Evidence Timeline, Account Plan, QBR prep, Investigation Copilot.
- **Key actions:** Triage own-account risks (accept/dismiss with reason); execute playbooks; complete tasks; give insight feedback; draft account plans (approve before CRM write-back); snooze signals with justification.
- **Default permissions:** Read/write own named accounts + team accounts if granted; no org-wide export; no config.
- **Success metrics:** Time-to-action on risks; task completion; renewal rate of book; feedback participation.

### 7. Account Executive
- **Goals:** Close expansion; protect renewals attached to comp; know which deals are real.
- **Surfaces:** Opportunity/Forecast Inspection (own deals), Account 360 (own accounts), expansion insights.
- **Key actions:** Act on deal-risk evidence; update next steps (write-back with approval); accept/dismiss expansion suggestions.
- **Permissions:** Own accounts/opps; no CS escalation internals if restricted; no exports.
- **Success metrics:** Deal hygiene score; win rate on inspected deals; expansion attach.

### 8. Sales Manager
- **Goals:** Coach reps with evidence; keep forecast honest week over week.
- **Surfaces:** Forecast Inspection (team), Workbench (team opportunity lens).
- **Key actions:** Deal inspection; require next-step remediation; approve category-change suggestions.
- **Permissions:** Team accounts/opps read/write; team-level exports of approved reports.
- **Success metrics:** Team forecast calibration; hygiene compliance; slip rate.

### 9. RevOps analyst
- **Goals:** Answer leadership questions fast; maintain metric definitions; investigate anomalies.
- **Surfaces:** Investigation Copilot, Signals Explorer, Data Quality Command Center, ad-hoc filtered views.
- **Key actions:** Build saved views; author metric definitions; remediate data-quality issues; validate model behavior; manage CSV imports.
- **Permissions:** Read-all data; export with audit; no security admin; sandbox for score-config drafts (publish requires VP RevOps).
- **Success metrics:** Time-to-answer; data-quality issue closure rate.

### 10. Executive sponsor / CEO
- **Goals:** Monthly confidence in retention trajectory; know the 5 accounts that matter this quarter.
- **Surfaces:** Weekly Executive Brief (email/Slack), Executive Home (read-only).
- **Permissions:** **Read-only executive role**: approved briefs, portfolio KPIs, drill-down to evidence cards; no raw exports; no config; no PII beyond stakeholder names/titles.
- **Success metrics:** Brief engagement; escalations initiated from briefs.

### 11. Data administrator
- **Goals:** Healthy connectors; correct mappings; controlled backfills; clean deletions.
- **Surfaces:** Integration Setup & Health, field-mapping UI, sync-run logs, retention settings.
- **Permissions:** Connector CRUD; credential management (secrets never displayed); backfill/replay triggers; deletion workflow execution; cannot read business surfaces unless also granted a business role.
- **Success metrics:** Sync success rate; freshness SLA attainment; mean time to recover a connector.

### 12. Security / compliance administrator
- **Goals:** Least privilege enforced; audit completeness; deletion/DSR compliance; AI governance settings correct.
- **Surfaces:** Security, Access & Audit Admin; audit-log search; consent records; model-provider policy settings.
- **Permissions:** User/role/SCIM management; SSO config; audit read (immutable); export-policy config; AI governance config (e.g., disable transcript excerpts, redaction rules); **no business-data read by default** (break-glass with logged justification).
- **Success metrics:** Access reviews completed; audit coverage; DSR SLA compliance.

## 4.2 RBAC / ABAC model

### Role architecture

```
Tenant (workspace)
 └── Roles (system-defined + custom)
      ├── org_admin            — user/security/billing admin; no implicit data read
      ├── data_admin           — connectors, mappings, retention, backfills
      ├── model_admin          — scores, weights, playbooks, signal config
      ├── exec_readonly        — approved briefs + KPIs + evidence drill-down
      ├── leader               — team-scoped read/write + assignment (CS or Sales flavored)
      ├── contributor          — own/team accounts read/write (CSM, AE)
      ├── analyst              — read-all business data, audited export, config sandbox
      ├── audit_viewer         — audit logs and access reports only
      └── external_limited     — see below
```

**Access is the intersection of:** role capabilities ∩ scope grants ∩ field-level policy ∩ source-level policy.

### Scope grants (ABAC attributes)
- **Org/workspace isolation:** hard boundary; every query carries `tenant_id`; enforced at the data layer (Postgres RLS) not just application code.
- **Team/segment/territory scopes:** grants like `scope: {segment: "Enterprise", territory: "EMEA"}` evaluated against account attributes.
- **Named-account grants:** explicit account-ID allowlists (e.g., strategic accounts visible only to a named pod).
- **Ownership scope:** `own` (account owner or opportunity owner = user), `team` (manager chain), `all`.

### Field-level restrictions
Sensitive field classes, each independently grantable:
- `commercial_sensitive`: discount %, margin, contract terms, legal notes.
- `personnel_sensitive`: internal performance notes, escalation blame context.
- `pii_extended`: contact emails/phones beyond name+title.
- `transcript_content`: verbatim excerpts (vs. derived classifications).
Policies apply at API serialization; evidence cards degrade gracefully ("evidence exists in a source you don't have access to — request access"), never leaking content through summaries. **Retrieval authorization:** RAG retrieval filters by the *requesting user's* grants before any LLM call (see AI doc).

### Data-source-specific access
Per-connector visibility policy, e.g., "call transcripts visible only to CS + Sales leadership," "billing visible to leaders+." Applies to raw records, derived signals inherit the most restrictive source policy unless an admin explicitly declassifies the derived form (e.g., sentiment label visible, excerpt not).

### External / limited users
Justified use case only: an outside consultant or fractional CS leader. `external_limited` = named-account allowlist, no exports, no PII beyond names/titles, watermark on views, 90-day auto-expiry with renewal, always visible in access reviews. No customer-facing external sharing in scope for V1/V2.

### Admin separation of duties
- Connector credentials: `data_admin` manages; secrets write-only.
- Model settings: `model_admin`; publishing a score-config change requires a second approver if it affects executive reporting (four-eyes rule, configurable).
- Security settings: `org_admin` only; changes are audit-logged and alert other org admins.

## 4.3 Identity & session security

| Capability | Requirement |
|---|---|
| SSO/SAML + OIDC | Required for all paid tiers; enforced-SSO toggle per tenant (blocks password login) |
| SCIM 2.0 | Provisioning/deprovisioning, group→role mapping; deprovision revokes sessions ≤5 min |
| MFA | Enforced for password-auth users; delegated to IdP under SSO; TOTP + WebAuthn |
| Sessions | Short-lived access tokens (≤15 min) + rotating refresh; admin-visible session list with revoke |
| Access reviews | Quarterly export of users×roles×scopes×last-login; attestation tracking in-product |
| Export controls | Per-role export rights; every export audit-logged (who, what filter, row count, destination); tenant-level export kill-switch |
| Audit | Login, access grants, permission changes, exports, connector changes, model config, write-backs, break-glass — see Security doc for event schema |

## 4.4 Tenant isolation summary
- Single-database multi-tenant Postgres with **row-level security keyed on `tenant_id`** set from the auth context; no query path bypasses RLS.
- Per-tenant object-storage prefixes with per-tenant KMS data keys (envelope encryption).
- Per-tenant vector-index namespaces; retrieval always tenant-scoped then user-scoped.
- Optional dedicated-instance deployment as an enterprise add-on (Roadmap V2+).
Full details in [Security doc](12-security-privacy-enterprise.md).

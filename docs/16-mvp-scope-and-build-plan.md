# 16. MVP Scope and 10–14 Week Build Plan

## 16.1 MVP definition

**Goal:** a design partner connects CRM + billing + support + usage CSV in a day, and within two weeks their CS team runs weekly renewal triage in RIG, with an exec brief leadership actually reads. Ruthless scope: one path through the wedge, real evidence discipline, nothing speculative.

### In scope (MVP)
| Area | Scope decision |
|---|---|
| CRM | **HubSpot** first (faster app review, simpler API, many mid-market ICP targets on it) — *decision to validate against design-partner stack; if 3 of 5 partners are Salesforce-only, flip.* Canonical CRM abstraction from day 1 so #2 is bounded work |
| Billing | **Stripe** |
| Support | **Zendesk** *(same validation caveat)* |
| Usage | CSV import (templated, validated) **or** Segment destination if a partner already has it — one, not both, per partner |
| Slack | Notifications + interactive triage buttons + brief delivery |
| Graph/profile | Canonical account profile; identity resolution (domain/explicit/fuzzy) with human review queue; manual merge/split; basic hierarchy from CRM |
| Timeline | Unified account timeline (CRM activities, tickets, billing events, signals, score changes) |
| Signals | Deterministic set: U1 (statistical-lite: baseline+threshold), U2, U5, U6, R3*, R5, R6, S1, S2, C1, C2, C3, C4, C5, C9, O1 (*R3 requires stakeholder tagging UI) — configurable thresholds |
| Scores | Renewal risk + health + data reliability, rule-based composite with full explanation objects, segment baselines, config UI (weights) with preview |
| Evidence | Evidence cards + citations for all above; claim-class labeling; verification for brief generation |
| Workbench | Ranked risk workbench with lifecycle, triage, feedback controls |
| Renewal center | Calendar, coverage, simple risk-adjusted forecast (rule-calibrated, labeled "default calibration") |
| Account view | Account 360 (Overview, Timeline, Commercial, Support, Signals tabs), account plan (manual + basic template, no generator yet) |
| Tasks/playbooks | In-RIG tasks + 3 canned playbooks; Slack task nudges; **no external task sync yet** (write-back framework lands with HubSpot task sync only if time allows — stretch) |
| Exec brief | Weekly brief: computed deltas + reviewed insights, verification gate, approval + email/Slack/PDF distribution |
| LLM usage (narrow) | Ticket sentiment classification (D.1) + insight narrative composition (cited) + brief generation (D.7). **No copilot in MVP** (fast-follow V1) |
| Admin | Onboarding wizard (connect → map → resolve → thresholds), connector health page, basic RBAC (org_admin, leader, contributor, exec_readonly, data_admin), audit log (core events), tenant isolation w/ RLS + CI leak tests, OIDC SSO + MFA |

### Explicitly excluded from MVP
Autonomous email sending · unrestricted general chat · fine-tuned/custom ML models · deep warehouse integrations · full sales-forecasting replacement · full CS-platform replacement · contract lifecycle management · cross-tenant benchmarking · graph ML · native mobile · long-tail integrations · unverified external market intelligence · expansion module · forecast-reliability module · call-transcript connectors (manual transcript upload only, if a partner insists) · SAML/SCIM (OIDC first) · scenario modeling · win-back tracking.

## 16.2 Build plan — 12 weeks (10 aggressive / 14 with buffer), team of 4 eng + founder-PM/design

**Tracks:** A = platform/data (2 eng), B = product/app (1.5 eng), C = AI/evidence (0.5–1 eng, overlaps A).

| Sprint (2w) | Track A — platform/data | Track B — app | Track C — AI/evidence |
|---|---|---|---|
| S1 (w1–2) | Infra bootstrap (Terraform, envs, CI/CD), Postgres + RLS + authz middleware, tenant/user/role models, WorkOS OIDC, audit-log core, connector framework skeleton, raw landing zone | App shell, nav, auth flows, design system primitives (tables, drawers, badges), account list stub | Evidence/citation schema + store; claim-class model; signal registry format |
| S2 (w3–4) | HubSpot connector (backfill+incremental, mapping UI v0), Stripe connector, identity resolution v1 + review queue | Account 360 v0 (profile+commercial), timeline v0, integration setup wizard v0 | Deterministic signal engine + first 8 signals (C-, S2 pending Zendesk, U5/U6 pending usage); rationale templates |
| S3 (w5–6) | Zendesk connector, CSV usage import + validation + daily aggregates, freshness monitoring v0 | Workbench v1 (rank, lifecycle, feedback), Slack app (alerts + buttons) | Remaining MVP signals incl. U1 baseline logic; risk+health score composites + explanation objects; score config with preview |
| S4 (w7–8) | Write-back framework (preview/approve/idempotency) + HubSpot task sync (stretch), DLQ tooling, data-quality issues v0 (freshness, ARR mismatch, missing fields) | Renewal Command Center v1, account plan v0, evidence card UI everywhere, DQ surfacing banners | LLM gateway + D.1 sentiment on Zendesk threads (review-gated), insight narrative composer with citation binding + validator |
| S5 (w9–10) | Hardening: rate limits, caching, backfill perf, seed/demo tenant, restore drill | Exec brief authoring/approval/distribution UI, feedback dashboards v0, onboarding polish | D.7 brief generation + claim-verification gate + excluded-claims appendix; eval harness v1 + golden sets |
| S6 (w11–12) | Design-partner onboarding support, bug burn-down, security pass (pen-test-lite, questionnaire pack) | Empty/error/permission states audit, accessibility pass, exec home v0 | Precision dashboards, calibration defaults, prompt/version registry wiring |
| Buffer (w13–14) | Partner-driven fixes, second-connector spike (Salesforce) only if partners demand | | |

**Definition of done for MVP launch:** 3 design partners live; each with ≥2 connectors + usage data; ≥20 risks triaged; ≥2 weekly briefs delivered with zero unverified claims; alert acceptance ≥60% (early bar); isolation + audit tests green.

## 16.3 Mocked/manual during design-partner pilots
- Salesforce (manual CSV bridge if a must-have partner is SFDC-only).
- Transcript ingestion: manual upload + on-demand processing.
- Playbook library: hand-authored with each partner (doubles as discovery).
- Calibration: default priors, clearly labeled; outcome labels collected manually monthly with CS Ops.
- Billing edge cases (multi-currency, complex proration): manual mapping review.
- SOC 2: security page + questionnaire, not report ("in progress, Type I target month 9").

## 16.4 Key risks

**Technical:** identity-resolution quality on messy CRMs (mitigate: human review queue is first-class, not fallback); usage-metric selection garbage-in (mitigate: onboarding treats metric mapping as consultative step with validation report); connector API quota surprises (mitigate: budgets + observability from S2); LLM citation discipline (mitigate: menu-of-evidence prompting + validator, hard CI gate).

**Go-to-market:** "another dashboard" skepticism (mitigate: evidence-first demo, triage workflow not charts); champion turnover mid-pilot; pilots stalling at data-connection stage (mitigate: white-glove onboarding, one-day-to-connect target); CS platforms bundling "AI health scores" (mitigate: trust/audit positioning they can't credibly copy quickly).

**Kill criteria (see doc 17):** if after 2 quarters with ≥5 partners, alert acceptance <50% and no partner attributes a saved renewal to RIG, the wedge thesis fails — stop, reassess data-quality-first or RevOps-analytics pivot before burning further.

## 16.5 PMF validation metrics
- ≥70% weekly CSM active rate; ≥80% high-severity alert acceptance; brief read-rate ≥60% of exec recipients.
- ≥2 documented saved-renewal case studies in 2 quarters.
- Design partners convert to paid at ≥60%; sales cycle ≤90 days on next 10 deals.
- Retention of RIG itself: zero design-partner churn attributable to product trust failure.

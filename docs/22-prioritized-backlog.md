# 22. Final Prioritized Backlog

**P0** = MVP launch-blocking. **P1** = V1 (months 4–7). **P2** = V2+ / enterprise. Epics reference docs 6–16; acceptance criteria live in doc 6 and doc 16.

## P0 — MVP (launch-blocking)

| Epic | Key stories |
|---|---|
| Platform foundation | Terraform envs; CI/CD; Postgres + **RLS with CI cross-tenant leak tests**; OIDC SSO (WorkOS) + MFA; basic RBAC (5 roles + scopes); audit-log core events (append-only + hash chain); raw S3 landing zone; Temporal setup |
| Connector framework + Phase-1 connectors | Framework (auth, backfill/incremental, watermarks, retries, DLQ + replay UI); HubSpot; Stripe; Zendesk; CSV usage import + validation report; daily usage aggregation; freshness monitors |
| Identity resolution & account graph | Match pipeline (explicit/domain/fuzzy) with confidence; human review queue; manual merge/split (reversible); canonical profile + field provenance + conflict surfacing; CRM hierarchy; edge table + timeline assembly |
| Signals & scores | Signal registry + evaluator; 16 MVP signals (doc 16); dedupe/snooze; renewal-risk + health + data-reliability scores with explanation objects, segment baselines, missing-data policy; score-config UI with backtest preview + versioning |
| Evidence system | Evidence store + citations; claim classes; evidence-card UI; score-change explanations; claim-verification service (brief path) |
| Workbench & renewal center | Ranked workbench + lifecycle + reason-coded dismissal; feedback controls; Slack alerts + interactive buttons; renewal calendar, coverage, default-calibrated risk-adjusted forecast; account plan v0; in-RIG tasks + 3 playbooks |
| LLM narrow slice | LLM gateway (logging, budgets, cache, schema validation); D.1 ticket sentiment (review-gated); insight narrative composer (citation-bound); D.7 weekly brief + approval/distribution; eval harness + golden sets; **zero-hallucination CI gate** |
| Data quality v0 | Freshness issues; ARR mismatch; missing required fields; profile banners; confidence degradation coupling |
| Onboarding & admin | Setup wizard (connect→map→resolve→thresholds); connector health page; demo/seed tenant (Acme fixtures); security questionnaire pack |

## P1 — V1

| Epic | Key stories |
|---|---|
| Second stack legs | Salesforce (+field history → O2/O5 signals); Intercom; Chargebee; canonical abstractions hardened |
| Relationship intelligence | Stakeholder roles UI + map completeness; R1/R2/R4/R7 signals; champion-departure detection (two-source confirm); relationship-strength score |
| Investigation Copilot | Semantic layer + allow-listed query compiler (D.12); answer UI with methodology/gaps; 25-question parity suite; audited history |
| Generation expansion | Account-plan generator; QBR prep packs (D.6/D.8); escalation briefs |
| Workflow depth | Playbook builder; escalation rules + SLAs; external task sync (HubSpot/Salesforce tasks, Jira or Asana); write-back framework GA (preview/approve/idempotent/audit) |
| Learning loop | Outcome capture (WF-15); postmortem + FN report; precision dashboards; isotonic calibration activation (≥50 outcomes); threshold-tuning suggestion queue |
| Enterprise identity | SAML; SCIM; field-level policy classes; export controls + logging; audit search UI; access-review exports |
| Data Quality CC v1 | Full issue classes; duplicate/merge queues; remediation workflow; lineage view |

## P2 — V2 and enterprise expansion

| Epic | Key stories |
|---|---|
| Conversation intelligence ingestion | Gong/Chorus/Zoom connectors; transcript pipeline + span citations; S4/C6/C7 GA with review workflow; risk-theme extraction (D.2); redaction pipeline |
| Expansion module | F module GA; eligibility matrix; conditional-on-risk logic; draft-opportunity write-back (approval-gated) |
| Warehouse & reverse-ETL | Snowflake/BigQuery/Redshift/Databricks read connectors; dbt package; Census/Hightouch inbound; metric-definition governance |
| ML maturation | GBM risk model with backtest activation gate; survival model for risk timing; drift monitoring GA; ranking model for workbench |
| Forecast Reliability module | G module GA: hygiene scores, evidence-vs-category, manager inspection, calibration views, category-change suggestions |
| Renewal center depth | Scenario modeling; cohort analysis; win-back tracking; churn-reason analytics |
| Enterprise/compliance | SOC 2 Type I → Type II; pen tests; EU region; private tenancy; BYOK; DSR automation; consent-managed email-body ingestion; Gainsight/Totango import; Outreach/Salesloft; DocuSign/Ironclad term extraction; ERP billing |
| Platform/ecosystem | Public API v1 GA + outbound webhooks; marketplace listings; benchmark opt-in program (k≥10); DQ standalone SKU |

## Sequencing invariants (from doc 17)
1. Evidence store before any generation feature. 2. Review workflow before any transcript-derived signal ships. 3. Calibration before ML models; backtest gates before activation. 4. Write-back framework before any external mutation feature. 5. Isolation/audit tests green before every release — trust features are never deferred to "hardening later."

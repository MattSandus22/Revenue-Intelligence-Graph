# 12. Security, Privacy, and Enterprise-Readiness Plan

Designed for serious enterprise procurement from day one; implemented in phases (§12.9) without architectural rework.

## 12.1 Multi-tenant isolation

| Layer | Control |
|---|---|
| Database | Single Postgres cluster, **RLS on every table keyed to `tenant_id`** set from verified JWT claims via `SET app.tenant_id`; app roles have no BYPASSRLS; CI test suite attempts cross-tenant reads on every table (fails build on leak) |
| Object storage | Per-tenant prefixes; per-tenant data keys (envelope encryption, AWS KMS); presigned URLs scoped + short-lived |
| Vector/search indexes | Per-tenant namespaces; retrieval clients constructed only from tenant context (type-enforced) |
| Compute | Shared workers with tenant-scoped job payloads; per-tenant queue fairness; connector credentials resolvable only for the job's tenant |
| LLM context | Prompt assembly service takes tenant-scoped retrievers only; red-team tests for cross-tenant prompt contamination |
| Enterprise add-on | Dedicated DB instance + storage account ("private tenancy") — V2+, same codebase via config |

## 12.2 Encryption & secrets

- TLS 1.2+ everywhere (external + service-to-service via mesh/mTLS as infra matures).
- At rest: AES-256 storage encryption + application-layer envelope encryption for high-sensitivity columns (OAuth tokens, transcript excerpts, email bodies if enabled) with per-tenant KMS data keys; key rotation annually and on incident; key deletion = crypto-shredding path for tenant offboarding.
- Secrets: cloud secrets manager (no secrets in env files/repos); OAuth tokens encrypted, never logged, refresh rotation; short-lived cloud credentials via workload identity (no static IAM keys).

## 12.3 Access control & identity
RBAC/ABAC, field-level and source-level policies, SSO/SAML/OIDC, SCIM, MFA, session policy, export controls, access reviews — specified in [doc 4](04-personas-and-permissions.md). Additional: least-privilege infrastructure IAM with quarterly review; production access via SSO + hardware-key MFA + just-in-time elevation with logged justification; no standing developer read access to tenant data (break-glass workflow, alerted).

## 12.4 Audit logging

- Events: authn (login/logout/failed/MFA), authz changes (roles/scopes/policies), data access (record views of sensitive classes, searches, exports with filter + row count), connector lifecycle (connect/scope change/disconnect/purge), configuration (score/model/playbook publish), AI (model runs, review decisions, verification blocks), write-backs (payload hash, approver), deletion workflows, break-glass.
- **Tamper-evidence:** append-only table (no UPDATE/DELETE grants) + per-tenant hash chain (`hash = H(prev_hash || row)`) + daily anchor hash exported to WORM object storage (S3 Object Lock). Verification job re-walks chains weekly.
- Retention 7 years; audit-viewer role UI with search/export (exports themselves audited).

## 12.5 Data protection & privacy

- **Classification:** every column/object tagged (`none | business_contact | pii_extended | sensitive_content | commercial_sensitive`) in a schema registry that drives masking, retention, DSR scoping, and prompt-redaction.
- **Retention:** per-class tenant-configurable TTLs (defaults: raw text 24m, derived 36m, audit 7y); automated purge jobs with certificates; legal-hold override.
- **Right-to-delete / DSR:** subject deletion (a person) → locate via contact/email graph → purge/anonymize PII while preserving aggregate integrity; tenant offboarding → full purge workflow (doc 15 #20) with signed certificate, ≤30 days.
- **Residency:** US and EU regions at launch of enterprise tier; tenant pinned at creation (data, processing, LLM endpoints in-region); subprocessor list per region.
- **GDPR/CCPA:** RIG is processor; DPA with SCCs; ROPA maintained; DSR API; consent records for optional ingestion classes (email bodies, transcript excerpts); privacy notice describing model-provider flows.
- **DLP:** export watermarking + row caps by role; anomalous-export detection (volume spike per user) alerts; clipboard/print left to customer endpoint controls (documented honestly, not claimed).

## 12.6 AI governance

| Control | Implementation |
|---|---|
| No-training default | Contractual + technical: API-based model providers with zero-retention/no-training terms; tenant data never enters any training corpus without explicit contract addendum |
| Model provider policy | Admin-visible registry of allowed providers/models per region; tenant can restrict (e.g., "no third-party LLM — disable generative features" mode degrades gracefully to deterministic product) |
| Model/version registry | Every `ai_model_run` records model id, version, prompt version, eval blessing; rollback supported |
| Prompt-injection defense | Untrusted content (transcripts, tickets, emails) is data, never instructions: structural separation in prompts, instruction-following-on-data detectors, output validators (schema + citation allowlist), no tool/write authority in any generation path that consumes untrusted text |
| Retrieval authorization | Retrieval filtered by requesting user's grants **before** context assembly (doc 4/9); tested with authz fixtures |
| Redaction | PII/secrets scanner on ingest of free text (emails, transcripts): configurable redaction of SSNs, card numbers, credentials before storage/prompting |
| Output monitoring | Verification-layer block rates, hallucination incidents (target 0), sensitive-leak scans on outputs; sampled human audit weekly |
| Human override & incident workflow | Any user can flag an AI output → triage queue → correction, root cause, affected-output sweep, tenant notification if material; AI incidents are a class in the incident-response runbook |

## 12.7 Secure SDLC & operations

- Threat modeling (STRIDE) per epic touching authn/z, connectors, or LLM paths; security review gate in PR template for those areas.
- Dependency/vuln management: lockfiles, Dependabot/Renovate, SCA + container scanning in CI, SLAs (critical 48h, high 7d).
- SAST + secret scanning in CI; IaC scanning (tfsec/checkov).
- Pen test: annual third-party + pre-enterprise-launch test; findings tracked to closure.
- Backups: continuous WAL archiving + daily snapshots, cross-AZ; quarterly restore drills. **RPO ≤ 15 min, RTO ≤ 4 h** (raw event replay can rebuild derived stores beyond that).
- Incident response: severity matrix, on-call rotation, customer-notification SLAs (security incidents ≤72 h contractual default), postmortems; status page.
- Environment separation: dev/staging/prod isolated accounts; no production data in lower environments (synthetic fixtures + masked samples only).

## 12.8 Vendor posture

Subprocessors (initial): cloud provider (AWS), model provider(s) (e.g., Anthropic API under zero-retention terms), email delivery, error monitoring (scrubbed), analytics (first-party events only). Published list + change notification per DPA.

## 12.9 Phased compliance roadmap

| Phase | Timing | Scope |
|---|---|---|
| MVP (design partners) | Weeks 1–14 | RLS isolation + CI leak tests, SSO (OIDC) + MFA, encrypted secrets/tokens, audit log core events, DPA template, no-training defaults, backup/restore, security page + questionnaire answers (honest "in progress" items) |
| First enterprise customer | Months 4–6 | SAML + SCIM, field-level policies, export controls, pen test #1, incident runbooks, subprocessor DPAs, retention config, vuln SLAs operating |
| SOC 2 Type I readiness | Months 6–9 | Control mapping (Security + Availability + Confidentiality), policy corpus, evidence automation (Drata/Vanta), access reviews running, change-management gates, Type I audit |
| SOC 2 Type II | Months 9–18 | 6–12 month observation window, quarterly DR + access-review cadence proven, Type II report |
| Regulated / high-security expansion | Months 18+ | EU residency GA, private tenancy, customer-managed keys (BYOK), ISO 27001, HIPAA-adjacent posture only if a real segment demands it (not speculative), FedRAMP explicitly out of scope until business case |

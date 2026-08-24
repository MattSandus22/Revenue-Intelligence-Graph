# Execution Doc 5 — Security & Compliance Checklist

Companion to `SECURITY.md` (the standing review record). ✅ = implemented and
test-enforced in this repo; ☐ = open task with owner + target week (weeks
reference execution doc 2).

## 1. SOC 2 Type I readiness tasks

| # | Control area | Task | Owner | Wk | Status |
|---|---|---|---|---|---|
| 1 | Access control | RLS tenant isolation + CI leak gate | — | — | ✅ |
| 2 | Access control | Role→capability enforcement server-side, 403s tested | — | — | ✅ |
| 3 | Access control | SSO-only prod login (WorkOS OIDC), dev endpoints 404 | E2 | 1 | ☐ |
| 4 | Access control | SCIM deprovision revokes ≤5 min; quarterly access-review export (users×roles×last-login) | E2 | 2 / 10 | ☐ |
| 5 | Change mgmt | PR review + CI gates required on `main`; branch protection on | E1 | 1 | ☐ (CI ✅, protection ☐) |
| 6 | Change mgmt | Migration runner with ordered SQL, applied-log | — | — | ✅ |
| 7 | Logical security | Prod-secret boot gate (JWT secret, DB password, Fernet key validity) | — | — | ✅ |
| 8 | Logical security | Secrets in SSM/vault, no secrets in repo/env files; key-rotation runbook executed once | E1 | 4 | ☐ |
| 9 | Audit | Hash-chained append-only audit log + verifier | — | — | ✅ |
| 10 | Audit | Weekly chain-verification job + daily anchor hash to WORM (S3 Object Lock) | E1 | 10 | ☐ |
| 11 | Availability | Backups: WAL archiving + daily snapshots; restore drill documented (RPO ≤15m / RTO ≤4h target) | E1 | 4 | ☐ |
| 12 | Availability | Uptime + freshness alerting, on-call rotation, status page | E1 | 4 | ☐ |
| 13 | Vendor mgmt | Subprocessor list published (template §5) + DPAs collected | F | 10 | ☐ |
| 14 | Risk | Annual pen test scheduled; SECURITY.md review cadence quarterly | F/E1 | 10 | ☐ (internal review ✅) |
| 15 | Policy corpus | InfoSec, acceptable-use, incident-response, BC/DR, vendor, access policies (Vanta/Drata templates, edited not copied) | F | 10 | ☐ |
| 16 | Evidence automation | Vanta or Drata connected to AWS/GitHub/IdP | E1 | 10 | ☐ |
| 17 | HR | Background checks + security training attestation for all staff | F | 10 | ☐ |
| 18 | AI governance | No-training provider terms on file; model/prompt registry (`ai_model_run`); zero-hallucination CI gate | — | — | ✅ (terms: F, wk 10 ☐) |

**Type I audit target: week 14–16** (after the 12-week plan) with a 4–6 week
auditor engagement booked in week 10.

## 2. Data encryption standards

| Surface | Standard | Status |
|---|---|---|
| In transit (external) | TLS 1.2+ terminated at LB; HSTS; no plaintext listeners | ☐ E1 wk 1 (infra) |
| In transit (internal) | VPC-private service↔DB; TLS to RDS (`sslmode=require`) | ☐ E1 wk 1 |
| At rest (database/disk) | RDS/EBS AES-256 encryption on | ☐ E1 wk 1 |
| At rest (connector credentials) | Application-layer Fernet (AES-128-CBC+HMAC), key from `RIG_CREDENTIAL_KEY`, malformed/default key refused at boot; rotation = re-enter flow (typed error, no 500s) | ✅ |
| At rest (credential upgrade) | KMS envelope encryption per tenant — same ciphertext column, no schema change | ☐ E1 wk 10 |
| Tokens/secrets in logs & audit | Never logged; audit stores field *names* only (test-enforced) | ✅ |
| Backups | Encrypted snapshots; tenant crypto-shred path via key deletion at offboarding | ☐ E1 wk 10 |

## 3. Access control matrix

Authoritative runtime matrix: execution doc 1 §5 (mirrors
`rig/auth.py::CAPABILITIES`). Operational overlay:

| Actor | Prod DB | Prod shell | Tenant data via app | Audit log | Secrets store |
|---|---|---|---|---|---|
| Engineers (default) | none | none | own dev tenant only | no | no |
| On-call (break-glass) | read via bastion, logged, 4-eyes page | time-boxed | no | yes (audit_viewer) | no |
| CI | migrations on staging only | no | synthetic tenants | no | scoped deploy keys |
| Founder (F) | none | none | demo tenant | yes | no |
| Terraform (E1-owned) | schema role | — | — | — | write via pipeline |

Rules: no standing production data access for anyone; break-glass requires a
second person's ack and lands in the audit log; customer-tenant access only
via a customer-granted support session (V1 feature — until then, never).

## 4. Incident response plan (outline)

1. **Severities** — SEV1: tenant-isolation breach, data exposure, audit-chain
   failure, hallucinated claim reached an executive artifact. SEV2: prod down
   >30m, sync outage across tenants, credential-store fault. SEV3: single-
   tenant degradation, freshness SLA breach >24h.
2. **Detect → Triage (≤15m)** — alert fires (Sentry/uptime/freshness/chain
   verifier) → on-call acks in Slack `#incidents`, opens incident doc from
   template, declares severity.
3. **Contain** — playbooks per class: isolation breach → revoke sessions,
   disable affected tenant tokens, snapshot DB *before* changes; credential
   fault → rotate `RIG_CREDENTIAL_KEY` + force re-entry (typed path exists);
   AI-output incident → feature-flag generative endpoints off (product
   degrades to deterministic mode by design) and sweep `ai_model_run` for
   blast radius.
4. **Notify** — SEV1 affecting customer data: draft customer notice ≤24h,
   send per DPA ≤72h; F owns comms, E1 owns facts. Never speculate in
   customer comms; state what is known, what is contained, next update time.
5. **Recover & verify** — restore/replay from raw landing zone where needed;
   run the full test suite + leak gate against prod schema copy before
   all-clear.
6. **Postmortem (≤5 business days)** — blameless template: timeline, root
   cause, detection gap, action items with owners; SEV1 postmortems reviewed
   with design partners on request (trust posture).

## 5. DPA & subprocessors list (template)

**Subprocessors** (publish at `/legal/subprocessors`; notify customers 30
days before additions):

| Subprocessor | Purpose | Data touched | Region |
|---|---|---|---|
| AWS | Hosting, storage, backups | All customer data (encrypted) | us-east-1 (EU: wk-20+ roadmap) |
| Anthropic | LLM inference (zero-retention/no-training API terms) | Prompt-scoped excerpts of connected data | US |
| WorkOS | SSO/SCIM | Employee identity (names, emails, IdP subjects) | US |
| Temporal Cloud | Sync orchestration | Job metadata (ids, cursors — no record payloads) | US |
| Slack (customer's own) | Notifications | Insight summaries the customer configures | customer-controlled |
| Sentry | Error monitoring | Scrubbed stack traces, no payloads | US |

**DPA skeleton** (attach to MSA; base on a standard SCC-inclusive template —
counsel reviews before first signature): parties & roles (customer =
controller, RIG = processor) · processing scope = the connected sources the
customer authorizes, listed by connector · purpose limitation: providing the
service only; **no training on customer data** (contractual + technical
default) · security measures: reference this checklist §§2–4 · subprocessor
list + 30-day change notice · breach notification ≤72h · deletion: WF-20
purge ≤30 days with certificate; audit trail retained de-identified ·
audit rights: SOC 2 report on request (Type I from wk ~16) · SCCs for any
cross-border transfer · term & survival.

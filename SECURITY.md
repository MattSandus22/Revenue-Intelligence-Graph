# Security Review — 2026-08 (full-branch review)

Scope: entire codebase (backend, frontend, deployment) — the branch contains
all code, so this was a whole-surface review rather than a diff review.
Method: manual audit of auth, tenant isolation, SQL construction, file
serving, secrets, input limits, and the AI trust boundaries, plus live
exploitation attempts against a running instance.

## Findings fixed in this review

| # | Severity | Finding | Fix |
|---|---|---|---|
| 1 | **High** | Path traversal (CWE-22) in the SPA fallback route: percent-encoded `..%2f` sequences escaped the `dist` directory and served arbitrary files (reproduced: `/..%2f..%2fbackend%2fpyproject.toml` returned file contents) | Resolved-path containment check (`is_relative_to(dist_root)`); regression test with four encoded/nested variants |
| 2 | **High (deploy-time)** | Built-in dev JWT secret would validate tokens in a misconfigured production deploy — anyone could mint credentials for any tenant/role | `rig.boot` refuses to start outside dev mode (`RIG_DEV_LOGIN=1`) when `RIG_JWT_SECRET` is the known default; tested |
| 3 | Medium | `rig_app` database role created with a hardcoded default password | `RIG_APP_DB_PASSWORD` env override (with `ALTER ROLE` on every migration run); boot refuses the default outside dev mode |
| 4 | Low | Unbounded request body on CSV usage import (memory DoS) | 10 MB cap → 413; tested |

## Verified-safe surfaces (checked, no findings)

- **Tenant isolation:** every tenant table has FORCE RLS; app connects as a
  non-superuser role; CI leak-gate covers reads, writes, id probes,
  no-context, and auto-detects unregistered `tenant_id` tables.
- **SQL construction:** all user-influenced values are bound parameters. The
  copilot semantic layer compiles only allow-listed (field, op) pairs;
  injection-shaped values and hostile field names are inert (tested). The
  two f-string SQL sites interpolate compiler-owned fragments or constants
  only.
- **AI trust boundaries:** LLM output is schema-validated and fail-closed;
  citations validated against an enumerated menu; numeric claims verified
  against a metrics allowlist; unconfirmed LLM signals excluded from scores,
  briefs, and copilot queries; adversarial zero-hallucination suite in CI.
- **External writes:** approval-gated, idempotent, audited; audit log is
  append-only (privilege + trigger) with a per-tenant hash chain.
- **Dev endpoints:** 404 unless `RIG_DEV_LOGIN=1` (tested); CORS restricted
  to configured origins.

## Accepted risks (documented, revisit per docs/12 roadmap)

| Risk | Rationale / planned resolution |
|---|---|
| Write-back approval does not enforce a second approver (proposer may self-approve) | Doc 6 requires approval, not separation-of-duties, for task-level writes; four-eyes rule planned for exec-report-affecting config (doc 15 WF-16) |
| No token revocation / session list; 1h JWT TTL only | OIDC (WorkOS) migration in V1 brings IdP-managed sessions (docs/12) |
| ~~No API rate limiting~~ **Resolved**: per-principal token buckets with cost-classed routes (`rig/ratelimit.py`) | In-process buckets fit the single-container MVP; swap to Redis buckets when multi-worker (docs/13) |
| Dev sign-in lists tenant names cross-tenant via the admin engine | Dev-only surface, hard-gated by env; never enabled in production per boot policy |
| Slack alert buttons are display-only (no signed interaction callbacks yet) | Interactive actions land with the Slack app hardening pass |

Report vulnerabilities to the maintainers privately; do not open public issues.

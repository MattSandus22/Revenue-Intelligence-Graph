# Execution Doc 2 — 12-Week Engineering Sprint Plan

**Starting point matters:** the MVP codebase in this repo is already built and
test-enforced (102 tests — see docs/23). This plan therefore covers the 12
weeks that actually lie ahead: **from working codebase → 3 paying-intent
design partners live in production.** (The greenfield build plan it replaces
is preserved in docs/16 for reference.)

**Team & owners** — E1: platform/infra eng · E2: product/full-stack eng ·
E3: AI/data eng · F: founder (PM + sales). 2-person variant: E1 absorbs E3,
F absorbs E2's frontend items, timeline +3 weeks.

## Phase A — Production hardening (weeks 1–4)

| Wk | Tasks | Owner | Acceptance criteria |
|---|---|---|---|
| 1 | Provision prod AWS (Terraform: VPC, RDS Postgres w/ RLS roles, ECS/Fly, S3 raw landing, secrets in SSM); staging env; deploy pipeline from CI | E1 | `git push` → staging auto-deploy; prod deploy is one approved action; `rig.boot` prod gate passes with real secrets |
| 1 | WorkOS integration: OIDC login replacing dev JWT behind `decode_token()` seam; session TTL + refresh | E2 | Login via Google/MS IdP works E2E; dev endpoints 404 in prod; all 102 tests still green |
| 2 | SAML + enforced-SSO toggle; SCIM provisioning/deprovision (revoke ≤5 min); map IdP groups → roles | E2 | Okta dev tenant: user created via SCIM logs in with mapped role; deprovision kills session |
| 2 | Temporal Cloud: move `run_sync` to workflows (retry policy, heartbeats); hourly schedule per active source; backfill as long-running workflow | E1 | Kill a worker mid-backfill → resumes from cursor; failed sync visible in Integrations UI within 1 min |
| 3 | HubSpot **OAuth app** (authorize→callback→token store w/ refresh rotation) replacing pasted tokens; Zendesk OAuth; Stripe restricted-key flow w/ scope check on connect | E1+E2 | Connect each source in <5 min via browser flow; scope-insufficient key rejected with actionable error |
| 3 | Real-stack integration test: sandbox HubSpot/Stripe/Zendesk accounts synced nightly in staging; fix normalization gaps found | E3 | Staging demo tenant fed by real sandboxes; zero DLQ'd records after 3 nights |
| 4 | Observability: OTel traces (request→sync→LLM run), Sentry, uptime + freshness alerting to team Slack; per-tenant LLM cost dashboard from `ai_model_run` | E1 | Trace for one insight spans connector→signal→score; alert fires on induced sync failure |
| 4 | Load/backup drills: 500-account synthetic tenant perf pass (workbench <2s), pg restore drill, key-rotation runbook executed once | E1 | RPO/RTO measured and written down; workbench p95 <2s at 500 accounts |

**Gate A (end wk 4):** a stranger can sign up via SSO, connect 3 real sources
in a browser, and see scored, cited insights — with on-call alerting live.

## Phase B — Design partner onboarding (weeks 5–8)

| Wk | Tasks | Owner | Acceptance criteria |
|---|---|---|---|
| 5 | Partner 1 live: white-glove connect, usage-metric mapping workshop (the make-or-break step — doc 16), threshold tuning session | F+E3 | ≥90% of partner's renewals ≥$10k covered with scores + evidence within 5 business days |
| 5 | Salesforce connector (read: accounts/contacts/opps + field history; same canonical interface as HubSpot) | E1 | Parity test suite passes against SFDC sandbox; stage/close-date-slip signals fire from field history |
| 6 | Partner 2 live (Salesforce-stack partner if available); weekly brief ritual started with both | F+E3 | First exec brief approved & distributed at each partner; zero unverified claims (invariant holds on real data) |
| 6 | Signed Slack interactivity: request-signature verification, ack/snooze/dismiss buttons act server-side | E2 | Button press in partner Slack transitions the insight; forged payload rejected (tested) |
| 7 | Feedback loop live: weekly precision review w/ partners; threshold changes via score-config sandbox; FP storm fixes | E3+F | High-severity acceptance ≥60% by wk 8 (bar rises to 80% by wk 12) |
| 7 | Four-eyes write-back option (approver ≠ proposer, per-tenant toggle); write-back GA on HubSpot+SFDC tasks | E2 | Toggle on → self-approval 403s; partner CSM syncs a task to their CRM |
| 8 | Partner 3 live; outcome backfill: import partners' last 4 quarters of renewal outcomes (CSV) → FN baseline + calibration labels | F+E3 | Surprise-churn baseline computed per partner; ≥40 historical labels imported at one partner |

**Gate B (end wk 8):** 3 partners live; each ran ≥2 weekly triage rituals;
acceptance trending ≥60%; at least one "we didn't know that" save story.

## Phase C — Prove value & harden for sale (weeks 9–12)

| Wk | Tasks | Owner | Acceptance criteria |
|---|---|---|---|
| 9 | Pilot dashboard (execution doc 6 §2) live per partner; time-to-triage + coverage auto-computed | E2 | F reviews dashboard with each partner champion in the weekly call |
| 9 | Calibration activation attempt at label-rich partner (holdout gate decides); document result either way | E3 | `calibration.fit` audited; if rejected, prior stays and the rejection is shown to partner (trust feature, not failure) |
| 10 | SOC 2 Type I sprint (execution doc 5): Vanta/Drata connected, policy corpus, evidence automation, pen-test scheduled | E1+F | Readiness score >80%; pen test booked; questionnaire pack answers 90% of a real prospect's DDQ |
| 10 | Transcript ingestion v0: manual upload + D.1 sentiment + competitor extraction behind review gate (Gong API deferred) | E3 | Partner uploads a call; confirmed extraction moves the score; unconfirmed never reaches the brief (existing invariant) |
| 11 | Perf/cost pass: LLM cache hit-rate >60% on repeat runs; per-tenant COGS report; DB index audit under real data | E1+E3 | No tenant >8% of target ACV in COGS; slow-query log empty at p95 |
| 11 | Case study drafts 1–2 from partner data (execution doc 6 §5); pricing page shipped | F | Partner sign-off on numbers + quote in writing |
| 12 | Conversion push: pilot→paid proposals to all 3; roadmap commitments written; V1 backlog groomed from partner asks | F | ≥2 signed annual contracts or signed LOIs; win/loss notes for the third |

**Critical path** (slips here slip everything):
`WorkOS OIDC (wk1) → OAuth connect flows (wk3) → Partner 1 live (wk5) →
2 triage cycles (wk6–7) → precision ≥60% (wk8) → pilot dashboard evidence
(wk9) → conversion (wk12)`. Salesforce (wk5) is on the critical path **only
if** ≥2 committed partners are SFDC-only — F must confirm partner stacks by
end of week 2 (doc 21 D1).

**Risk mitigation per phase**

| Phase | Top risk | Mitigation |
|---|---|---|
| A | OAuth app review delays (HubSpot marketplace) | Private-app tokens remain supported as fallback (already built); submit app review wk 1, don't block on it |
| A | Temporal migration destabilizes working syncs | Keep synchronous path behind a flag; migrate one connector at a time; the 102-test suite is the regression net |
| B | Partner stalls at data connection | The 1-day-connect bar is a *founder-managed* SLA: F schedules the mapping workshop before contract signature; CSV usage import is the universal unblocking fallback |
| B | FP storm kills trust in week one | Thresholds start conservative (fire less); daily precision check first 2 weeks per partner; snooze/suppress are first-class (already built) |
| C | Calibration gate rejects at every partner | Expected with <50 clean labels — the honest prior + rejection transparency **is the demo**; sell the discipline, not the model |
| C | Partners love it, won't pay | Paid-pilot structure from doc 18 (fee credited to annual) set at signature in Phase B, not negotiated in wk 12 |

## Definition of Done — MVP in production

1. All CI gates green on `main`: 102+ tests, tenant-isolation leak gate,
   zero-hallucination gate, frontend build.
2. SSO login only in prod; dev endpoints 404; boot config gate enforced.
3. 3 design partners live: sources syncing on schedule, freshness SLA ≥95%.
4. Every number an exec sees traces to evidence in ≤2 clicks; zero unverified
   claims ever published (audited).
5. High-severity alert acceptance ≥60% (wk 8) trending to 80% (wk 12).
6. Weekly brief approved & distributed at each partner ≥4 consecutive weeks.
7. On-call: alerting, runbooks, restore drill done; audit chain verifies weekly.
8. ≥2 signed conversions or LOIs; documented save story per partner.

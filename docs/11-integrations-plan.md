# 11. Integrations Plan

## 11.0 Connector framework (shared by all integrations)

Every connector is built on one framework so the per-connector spec is mostly configuration:

- **Auth:** OAuth2 where offered (tokens envelope-encrypted per tenant via KMS, auto-refresh, rotation on scope change); API-key fallback stored in secrets vault, referenced not embedded. Admin consent screen lists exact scopes and objects before connect (consent_record persisted).
- **Sync engine:** initial **backfill** (paged, checkpointed, resumable; configurable history depth, default 24 months) → **incremental** via webhooks where available + reconciliation polling (webhooks missed events are a certainty, not a possibility). Cursor/watermark per object stream stored on `sync_run`.
- **Rate limits:** per-connector token buckets honoring provider budgets; adaptive backoff on 429; nightly bulk work scheduled off-peak; per-tenant fairness caps so one tenant's backfill can't starve others.
- **Errors:** transient → exponential retry (jittered, max 5); permanent → dead-letter queue with admin-visible error detail and one-click replay after fix; auth failures → connector status `action_required` + notification to data admin.
- **Freshness targets (default SLAs, monitored):** webhook sources ≤5 min; polled CRM objects ≤15 min; billing ≤15 min; warehouse/analytics batch ≤24 h; breach → freshness incident + confidence degradation (doc 6 H).
- **Field mapping UI:** provider fields → canonical fields; required-mapping checklist; custom-field mapping; transform snippets (enum maps, currency); mapping versioned; changes trigger targeted re-normalization, not full backfill.
- **Connector status UI:** last sync, records/day, error rate, freshness vs. SLA, scope health, upcoming token expiry, per-object watermarks.
- **Disconnection/deletion:** disconnect stops sync and revokes tokens; tenant chooses retain (frozen, labeled stale) or purge synced data; purge runs the deletion workflow (doc 15 #20) with certificate.
- **Residency:** connector workers and landing storage pinned to tenant region (US/EU at launch); no cross-region processing.
- **Write-back rules:** every write-back is (a) explicitly enabled per connector per object, (b) field-mapped by admin, (c) previewed and human-approved per execution or per approved automation rule, (d) audit-logged with payload hash, (e) idempotent with external-id tagging.

## 11.1 Phase 1 connectors

### Salesforce (or HubSpot — one for MVP; abstraction: canonical CRM interface `accounts/contacts/opps/activities/tasks/owners`)
| Aspect | Spec |
|---|---|
| Auth | OAuth2 (connected app), refresh token; min scopes `api refresh_token` with admin-selected object permissions via integration user profile — recommend dedicated least-privilege integration user |
| Objects | Account, Contact, Opportunity (+field history), OpportunityStage, User, Task/Event (activities), Case (optional), custom renewal fields per mapping |
| Sync | Backfill via Bulk API 2.0; incremental via CDC/Streaming API where enabled else 5-min modified-since polling; deletes via getDeleted |
| Freshness | ≤15 min |
| Write-back | Task create, Opportunity field update (next step, forecast suggestion → custom field), Account plan summary custom field — all approval-gated |
| Notes | Field-history ingestion powers stage/close-date movement signals; API limits monitored against org quota with admin banner |

### HubSpot
OAuth2 app with granular scopes (`crm.objects.companies.read`, `contacts`, `deals`, `owners`, `engagements`); webhooks for object changes + polling reconciliation; associations API for account↔contact↔deal edges; write-back: tasks, deal properties, notes (approval-gated).

### Slack
| Aspect | Spec |
|---|---|
| Auth | OAuth2 bot token; scopes `chat:write`, `commands`, `users:read.email` (mapping Slack users→RIG users), `channels:read` for channel picker. **No message reading in Phase 1** — Slack is a notification/action surface, not a data source |
| Behavior | Alert delivery (DM + channels), interactive triage buttons (acknowledge / snooze / open in RIG), daily digest, exec brief delivery |
| Write rules | Buttons act as authenticated RIG actions (Slack user mapped, permission-checked server-side) |

### Intercom / Zendesk (one for MVP)
| Aspect | Spec |
|---|---|
| Auth | OAuth2; read scopes for tickets/conversations, orgs/companies, users; no write scopes in Phase 1 |
| Objects | Tickets/conversations (+messages), priority/status/tags, satisfaction ratings, organizations, requesters |
| Sync | Backfill 24m; webhooks (ticket created/updated/message added) + hourly reconciliation |
| Freshness | ≤5 min |
| Notes | Priority/severity mapping validated during setup (drives S2); org→account resolution via domain + explicit org mapping UI |

### Stripe / Chargebee (one for MVP)
| Aspect | Spec |
|---|---|
| Auth | Stripe: restricted API key (read-only on customers, subscriptions, invoices, charges, disputes) or Stripe Connect OAuth; Chargebee: API key read-only |
| Objects | Customers, subscriptions (+period ends → renewal candidates), invoices, payments/charges, disputes, credit notes, plan/price catalog |
| Sync | Backfill via list APIs; incremental via webhooks (invoice.*, charge.*, customer.subscription.*) + daily reconciliation |
| Freshness | ≤15 min |
| Notes | Customer→account resolution via email domain + metadata + manual mapping; **never store card data** (PCI stays with provider) |

### Product events — Segment/RudderStack/Amplitude/Mixpanel/Snowplow/SDK + CSV
- Segment/RudderStack: RIG as destination (server-side); track/identify/group calls; group→account resolution.
- Amplitude/Mixpanel: export APIs, daily batch.
- Direct SDK/REST: `POST /v1/usage-events` batch endpoint, HMAC-signed, idempotency keys.
- **CSV import (MVP-critical):** templated columns (`account_ref, date, metric, value, user_ref?`); validation report (unmatched accounts, malformed rows) before commit; scheduled SFTP/S3 drop option.
- All usage lands in warehouse tables; daily aggregation to `usage_metric_daily`; tenant maps 3–10 "meaningful usage" metrics during onboarding (this mapping is a first-class onboarding step — bad metric choice is the top failure mode for usage signals).

### Google Workspace / Microsoft 365
- **Default: metadata only.** Calendar events (participants, time, recurrence) and email headers (from/to/timestamp/thread) for engagement-recency features. Scopes: `calendar.readonly`, `gmail.metadata` / Graph equivalents.
- **Email bodies excluded by default.** Enabling body ingestion requires org-admin explicit consent flow (consent_record with terms version), per-domain filters (customer domains only), redaction pipeline, and field-level access class `sensitive_content`. Ships **after** MVP.

### Generic REST API + webhooks
Public ingestion API (`/v1/ingest/{object_type}`) with JSON Schema validation, HMAC signatures, idempotency keys, per-tenant rate limits; outbound webhooks for insight/risk events (signed, retried, DLQ'd).

## 11.2 Phase 2 connectors (summary specs)

| Connector | Auth | Key objects | Mode | Notes |
|---|---|---|---|---|
| Gong / Chorus / Zoom | OAuth2 | calls, participants, transcripts | webhook + backfill | consent flags honored; transcript spans citation-addressable; region pinning |
| Snowflake / BigQuery / Redshift / Databricks | key-pair / OAuth / IAM role | tenant-defined models via SQL mapping UI | scheduled pull (reverse-ETL-style) | read-only service account; query cost guardrails; dbt package offered for canonical models |
| Gainsight / Totango / Catalyst | OAuth/API key | health scores, CTAs, success plans | poll | imported as third-party opinions, labeled — never merged into RIG scores silently |
| Jira / Linear / Asana | OAuth2 | projects/issues for task sync + escalation links | webhook | write-back approval-gated |
| Outreach / Salesloft | OAuth2 | sequences, touches, replies | poll+webhook | engagement features |
| DocuSign / Ironclad / Drive / Dropbox | OAuth2 | contracts, order forms (metadata + parsed terms) | webhook/poll | LLM term extraction (notice period, auto-renew) with human confirmation before use in signals |
| NetSuite / QuickBooks / ERP | token/OAuth | invoices, payments, credit memos | poll | for tenants not on Stripe/Chargebee |
| Census / Hightouch | destination APIs | RIG as destination for warehouse-modeled accounts/metrics | push | lets mature data teams feed curated models |

## 11.3 Integration admin experience

Setup wizard per connector: authorize → scope review + consent → object/field mapping (with smart defaults) → identity-resolution preview (sample of matches with confidence, admin spot-checks before enable) → backfill (progress, ETA) → validation report (record counts vs. source, unmatched entities) → live.

Health dashboard aggregates all connectors: freshness, error budgets, quota consumption, pending mapping tasks, deletion/disconnect status. Alerting to data-admin via Slack/email on `action_required`.

# 13. Technical Architecture and Recommended Stack

Optimized for: 2–5 founding engineers, fast MVP, security credibility, reliable integrations, future scale, controlled AI costs, accurate provenance.

## 13.1 System diagram

```mermaid
flowchart TB
  subgraph Clients
    WEB[React SPA] 
    SLACK[Slack app]
    API[Public REST API + webhooks]
  end
  subgraph Edge
    GW[API service — FastAPI<br/>authn/z, rate limits, RLS context]
  end
  subgraph Async
    Q[(Queue/event bus<br/>SQS + EventBridge → Redpanda/Kafka later)]
    WORK[Workers — Python<br/>Temporal workflows]
  end
  subgraph Data
    PG[(Postgres 16 + RLS<br/>operational + graph edges + features)]
    WH[(Warehouse: ClickHouse<br/>usage events, analytics)]
    S3[(Object storage S3<br/>raw landing, transcripts, docs, exports)]
    SRCH[(OpenSearch — keyword)<br/>+ pgvector — embeddings]
    REDIS[(Redis — cache, rate limits)]
  end
  subgraph Intelligence
    RULES[Rule engine]
    ANOM[Anomaly jobs]
    MLI[ML train/infer — sklearn/LightGBM]
    LLMGW[LLM gateway<br/>provider routing, budgets, cache, logging]
    VER[Claim-verification service]
  end
  CONN[Connector framework<br/>per-source workers] --> S3 --> Q
  WEB & SLACK & API --> GW --> PG
  GW --> Q
  Q --> WORK --> PG & WH & SRCH
  WORK --> RULES & ANOM & MLI & LLMGW
  LLMGW --> VER --> PG
  OBS[Observability: OTel → Grafana stack<br/>Sentry, PagerDuty]
```

## 13.2 Stack choices, alternatives, trade-offs

| Layer | Recommendation | Alternatives | Trade-off rationale |
|---|---|---|---|
| Front end | React + TypeScript + Vite, TanStack Query/Table, Tailwind + Radix | Next.js full-stack | Data-dense internal-style app; SPA + separate API keeps API-first discipline for public API parity. Next.js fine if team prefers; avoid two frameworks |
| Backend/API | **Python + FastAPI** (single modular monolith) | TS/NestJS; Go | Python unifies API + data + ML in one language for a tiny team; FastAPI gives OpenAPI for the public API. Monolith-first, service boundaries as modules (connector runtime and LLM gateway split out first when scaling demands) |
| Auth | **WorkOS** (SSO/SAML/SCIM) + own session/JWT layer | Auth0, Keycloak | Enterprise SSO/SCIM in days not months; avoids running Keycloak with 3 engineers |
| Workflow/orchestration | **Temporal Cloud** | Airflow/Dagster (batch only), homegrown queues | Connector backfills, sagas with human-approval steps, retries/replays are exactly Temporal's model; Dagster added later for warehouse batch if needed |
| Queue/event bus | SQS + EventBridge (MVP) → Redpanda/Kafka when event volume/ordering demands | RabbitMQ | Managed, cheap, boring first; Kafka only when replay/throughput justifies ops cost |
| Operational DB | **Postgres 16 (RDS/Aurora)** — operational data, graph edges, features, evidence | — | Non-negotiable center of gravity; RLS is the isolation backbone |
| Analytics warehouse | **ClickHouse Cloud** for usage events + internal analytics | Snowflake, BigQuery, DuckDB/MotherDuck | Usage-event volume needs columnar economics; ClickHouse cheap + fast for per-account time series; Snowflake acceptable if team knows it (higher cost). Tenant warehouses are *sources*, not our serving store |
| Object storage | S3 (raw immutable landing zone — replay source of truth) | — | Every raw payload archived → pipeline replayability |
| Search | OpenSearch for keyword/filters on text; **pgvector** for embeddings (MVP) | Dedicated vector DB (Pinecone/Qdrant) | Vector scale at 50–500 accounts/tenant is tiny; pgvector keeps ops surface small — dedicated vector DB **only when** corpus/latency justifies (that's the "only where justified" answer) |
| Graph | **Relational graph (edge table + recursive CTEs) in Postgres** | Neo4j/Neptune from day 1 | Traversals are shallow (≤3 hops), volumes modest; graph DB adds ops burden, second store to secure/isolate, dual-write consistency risk. Revisit trigger: graph queries >20% of query cost or product needs deep path analytics |
| Rules engine | In-house: signal registry (YAML) + evaluator in Python, versioned | Drools/zen-engine | Rules are data-science-shaped (windows, baselines), not enterprise-BRE-shaped; registry versioning matters more than a DSL |
| Feature store | Postgres feature tables + registry metadata | Feast | Feast when online/offline skew or multiple serving surfaces appear (V2+) |
| ML | scikit-learn/LightGBM, MLflow registry, batch inference in workers | SageMaker end-to-end | Tabular, small data; boring tools win; MLflow gives model versioning/audit |
| LLM gateway | Thin in-house service: provider adapters (Anthropic primary; abstraction for tenant-policy routing), per-tenant budgets, response cache, full run logging, schema validation | LiteLLM/proxy products | Gateway is where cost control, tenant isolation, and audit live — too load-bearing to outsource early; keep the adapter surface small |
| Observability | OpenTelemetry → Grafana Cloud (metrics/logs/traces), Sentry, PagerDuty | Datadog (cost) | Trace every insight generation end-to-end (connector → signal → LLM → verification) |
| CI/CD | GitHub Actions; trunk-based; migrations gated; ephemeral preview envs | — | |
| IaC | Terraform + modules; separate AWS accounts dev/staging/prod | Pulumi | |
| Feature flags | Flagsmith/Unleash (self-host cheap) or LaunchDarkly | — | Needed for tenant-scoped progressive rollout of scores/prompts |
| Rate limiting | Redis token buckets at gateway + per-connector budgets | — | |
| Caching | Redis: session, hot account profiles, LLM response cache (keyed on inputs_hash — big cost lever) | — | |

## 13.3 Cross-cutting mechanics

- **API versioning:** `/v1` path-versioned public API; additive changes preferred; deprecation policy 12 months; OpenAPI published.
- **Webhooks (outbound):** signed (HMAC + timestamp), retried with backoff 24h, per-endpoint DLQ, event types versioned.
- **Idempotency:** all ingestion and write-back endpoints require idempotency keys; connector upserts keyed on `(tenant, source_system, source_record_id)`; workers exactly-once-effect via Temporal + idempotent handlers.
- **Replayability:** raw landing zone immutable → any normalization/signal/scoring bug fixed by replaying from raw with new versions; replays tagged so downstream consumers can distinguish reprocessed data.
- **DLQs:** every queue consumer has a DLQ + admin UI surface + replay tooling; DLQ depth alarmed.
- **Data-quality monitoring:** freshness/completeness/conflict monitors emit `data_quality_issue` records (product surface) and ops alerts (same source of truth).
- **Model monitoring:** eval dashboards (doc 9 F) + drift alarms wired to PagerDuty for hard failures (validation pass rate drop, verification block spike).
- **Cost controls:** per-tenant LLM token budgets with graceful degradation (defer non-urgent summarization before blocking triage-critical extraction); nightly cost attribution per tenant/feature; ClickHouse TTLs on raw events; S3 lifecycle to IA/Glacier.
- **Multi-region plan:** region-pinned cells (US first, EU at enterprise phase); no cross-region data plane; control plane global with regional data planes; cell architecture also becomes the private-tenancy story.
- **Environments:** prod/staging/dev accounts; synthetic seed tenant ("NorthstarCloud" fixtures from doc 20) powers demos, tests, and evals.

## 13.4 Scaling path (explicit, so MVP shortcuts are safe)

| Pressure | First response | Later |
|---|---|---|
| Event volume | ClickHouse handles 10⁹ events fine; batch aggregation | Kafka + streaming aggregation |
| Query latency on workbench | Postgres indexes + materialized rollups | Read replicas; pre-computed ranking tables |
| Connector fleet | Temporal task queues per connector | Isolated connector runtime service |
| LLM throughput/cost | Cache + batch + small-model routing for extraction | Distillation to cheaper models per task once evals allow |
| Graph complexity | CTE depth limits, edge-table partitioning | Dedicated graph store behind the same edge API |

# Revenue Intelligence Graph — Product Specification & Build Plan

> **Tagline:** The evidence-backed operating system for retaining and expanding B2B revenue.

This repository contains the complete, implementation-ready product specification for **Revenue Intelligence Graph (RIG)** — a multi-tenant, AI-native B2B SaaS platform that turns fragmented customer and revenue data into an evidence-backed, account-level intelligence graph.

**Initial wedge:** Renewal Risk Intelligence for Customer Success and RevOps.

## Deliverable Index (read in order)

| # | Document | Contents |
|---|----------|----------|
| 1 | [Executive Product Brief](docs/01-executive-product-brief.md) | Thesis, what it is / is not, outcomes, ROI model |
| 2 | [Problem and ICP](docs/02-problem-and-icp.md) | Problem decomposition, ideal customer profile, buying context |
| 3 | [Product Positioning](docs/03-product-positioning.md) | Category, narrative, positioning statement |
| 4 | [Personas and Permissions](docs/04-personas-and-permissions.md) | 12 personas, RBAC/ABAC model, SSO/SCIM/MFA |
| 5 | [Jobs-to-be-Done](docs/05-jobs-to-be-done.md) | JTBD per persona, mapped to modules |
| 6 | [Detailed Feature Specification](docs/06-feature-specification.md) | Modules A–J with acceptance criteria |
| 7 | [Signal Taxonomy](docs/07-signal-taxonomy.md) | Full deterministic + AI signal catalog with detection specs |
| 8 | [Canonical Data Model and Graph Design](docs/08-data-model-and-graph.md) | Entities, DDL, graph representation, Acme example graph |
| 9 | [AI/ML Architecture and Evaluation](docs/09-ai-ml-architecture.md) | Pipeline, feature store, scores, LLM task schemas, evals |
| 10 | [Evidence and Explainability System](docs/10-evidence-and-explainability.md) | Evidence cards, citations, claim verification |
| 11 | [Integrations Plan](docs/11-integrations-plan.md) | Phase 1/2 connectors with full connector specs |
| 12 | [Security, Privacy, Enterprise Readiness](docs/12-security-privacy-enterprise.md) | Tenant isolation, audit, AI governance, compliance roadmap |
| 13 | [Technical Architecture](docs/13-technical-architecture.md) | Stack recommendations, trade-offs, diagrams |
| 14 | [UX Information Architecture](docs/14-ux-information-architecture.md) | 16 screens, annotated wireframe descriptions |
| 15 | [Workflows and Playbooks](docs/15-workflows-and-playbooks.md) | 20 end-to-end workflows |
| 16 | [MVP Scope and Build Plan](docs/16-mvp-scope-and-build-plan.md) | 10–14 week sprint plan, exclusions, risks |
| 17 | [Roadmap](docs/17-roadmap.md) | V1 → V2 → enterprise expansion, dependency map, kill criteria |
| 18 | [Pricing, Packaging, Go-to-Market](docs/18-pricing-and-gtm.md) | Pricing model, tiers, sales motion, first 100 customers |
| 19 | [Competitive Positioning and Risks](docs/19-competitive-positioning.md) | Alternatives, moats, build-vs-buy defense |
| 20 | [Sample Acme Corp Walkthrough](docs/20-acme-corp-walkthrough.md) | End-to-end structured example payloads |
| 21 | [Open Decisions, Assumptions, Validation Experiments](docs/21-open-decisions-and-experiments.md) | Explicit unknowns and how to resolve them |
| 22 | [Final Prioritized Backlog](docs/22-prioritized-backlog.md) | P0/P1/P2 backlog |
| 23 | [Implementation Status](docs/23-implementation-status.md) | Spec closure against the working codebase (102 tests) |

## Execution Pack (for the founding team)

Operational documents formatted for immediate execution — they reference the
**working implementation** in `backend/` and `frontend/`, not hypotheticals:

| Doc | Contents |
|---|---|
| [1 · Technical Architecture](execution/01-technical-architecture.md) | Stack decisions w/ status, tenant isolation, pipeline diagram, connector API, authn/z model, audit schema & retention |
| [2 · 12-Week Sprint Plan](execution/02-sprint-plan.md) | Week-by-week from current codebase → 3 live design partners; owners, acceptance criteria, critical path, risks, MVP Definition of Done |
| [3 · Data Model Specification](execution/03-data-model.md) | Shipped DDL for all core entities, indexing strategy, soft-delete/versioning, seed data |
| [4 · Signal Engine Guide](execution/04-signal-engine-guide.md) | Detector pseudocode, score algorithm & weights, confidence/probability model, explanation generation |
| [5 · Security & Compliance Checklist](execution/05-security-compliance-checklist.md) | SOC 2 Type I task list, encryption standards, access matrix, incident response, DPA/subprocessor template |
| [6 · GTM Execution](execution/06-gtm-execution.md) | Design-partner outreach script + call outline, pilot dashboard spec, pricing copy & FAQ, battlecards, case study outlines |

## Working implementation

`backend/` (FastAPI + Postgres, 9 migrations, 102 tests incl. tenant-isolation
and zero-hallucination CI gates) and `frontend/` (React SPA, 7 screens).
One-command demo: `docker compose up --build` → http://localhost:8000 with
the seeded Acme walkthrough. See `backend/README.md` and `SECURITY.md`.

## Non-negotiable product principles

1. **Evidence or it doesn't ship.** Every material insight, score movement, and generated executive claim cites source evidence with record IDs, timestamps, and freshness. Claims that cannot be verified are blocked or labeled unsupported.
2. **Deterministic before probabilistic.** Structured data and rules run before models; models run before LLMs; LLM output is schema-validated and never invents citations.
3. **Humans approve consequential actions.** No write-back to source systems, no external communication, no forecast change, no opportunity creation without explicit user approval and an audit event.
4. **Tenant isolation is absolute.** No cross-tenant data mixing; no training on tenant data without explicit contractual permission.
5. **Fact, prediction, interpretation, and recommendation are visually and semantically distinct** everywhere in the product.

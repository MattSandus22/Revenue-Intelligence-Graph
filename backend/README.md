# RIG Backend — Sprint 1 Platform Foundation

Implements the Sprint 1 scope from [docs/16](../docs/16-mvp-scope-and-build-plan.md):
tenant-isolated Postgres schema, tamper-evident audit log, signal registry +
deterministic engine, explained renewal-risk score, evidence/citation store,
JWT-authenticated API, and the Acme Corp demo seed.

## Layout

```
migrations/0001_init.sql   schema + RLS policies + audit hash-chain triggers
rig/config.py              settings (app vs. admin DB URLs, JWT)
rig/db.py                  tenant_session() — every query runs under app.tenant_id
rig/migrate.py             SQL migration runner + rig_app role bootstrap
rig/auth.py                JWT principals, role→capability map (OIDC-swappable)
rig/audit.py               audit writer + hash-chain verifier
rig/signals/definitions/   versioned YAML signal specs (docs/07 format)
rig/signals/engine.py      detectors + idempotent persistence + evidence binding
rig/scoring.py             renewal_risk@v0.1 — explained, reproducible composite
rig/main.py                FastAPI app (accounts, risk explanation, evaluate)
rig/seed.py                NorthstarCloud/Acme fixtures (docs/20 walkthrough)
tests/                     RLS leak gate, audit chain, engine, scoring, API
```

## Security invariants enforced in code (not convention)

1. **App connects as `rig_app`** — non-superuser, non-owner. Postgres RLS does
   not bind superusers, so app traffic must never use one; migrations use the
   admin URL. `tests/test_rls_isolation.py` is the leak gate: it fails the
   build if any tenant-keyed table lacks FORCE RLS or leaks across tenants,
   and auto-detects new `tenant_id` tables missing from the gate.
2. **Audit log is append-only twice over** — UPDATE/DELETE revoked from
   `rig_app` *and* blocked by trigger; the per-tenant hash chain is computed
   by a DB trigger and re-verifiable via `rig.audit.verify_chain`.
3. **No signal without evidence** — the engine writes `evidence_object` +
   `evidence_citation` rows for every detection; a test fails if any active
   signal has no citation.
4. **No score without explanation** — components carry weight, normalized
   value, signed contribution, rationale, and contributing signal ids;
   insufficient data coverage yields *no score* rather than a fake one.

## Run locally

```bash
docker compose up postgres -d          # or any Postgres 16 on :55432
cd backend && pip install -e ".[dev]"
python -m rig.seed                     # migrate + seed Acme demo tenant
uvicorn rig.main:app --reload
python -m pytest tests/ -q
```

Mint a dev token:

```python
from rig.auth import issue_dev_token
print(issue_dev_token("u_dev", "<tenant-uuid-from-seed>", "leader"))
```

Then:

```
GET  /v1/accounts
GET  /v1/accounts/{id}                       # profile + active signals (audited)
POST /v1/admin/accounts/{id}/evaluate        # run detectors + score
GET  /v1/accounts/{id}/risk                  # score + components + citations
```

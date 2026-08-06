# Repository Architecture

This document is the concise engineering map for the current repository. The
authoritative domain and runtime detail remains in
[`docs/architecture.md`](docs/architecture.md), while data, API, security, and
operational contracts remain in their dedicated files under `docs/`.

The current ranked backend structural inventory is maintained in
[`docs/backend-structural-inventory.md`](docs/backend-structural-inventory.md).

## Product boundary

AI Maintenance Copilot is an internal-pilot, batch analytics and decision-support
application for asset lifecycle, tickets and SLA, preventive plans, work orders,
maintenance logs, and spare-parts stock control. Human managers and technicians
remain responsible for prioritization, safety checks, inspection, execution, and
final decisions. Risk scores, anomaly results, SLA states, and reorder suggestions
are decision-support signals rather than automatic decisions.

The application is deliberately not a complete CMMS, procurement suite,
autonomous controller, real-time IoT platform, or production-ready enterprise
platform.

## Runtime topology

```text
Next.js frontend -----------+
Streamlit status client ----+--> FastAPI --> domain services --> repositories --> PostgreSQL
                                      |              |                |
                                      |              |                +--> local attachment bytes
                                      |              +--> batch analytics CSV snapshots
                                      +--> RAG composer --> Qdrant (documents only)

Explicit CLIs -------------------------------> the same domain services
src/operations/worker.py --> four allow-listed jobs --> the same domain services/PostgreSQL
```

- PostgreSQL is the transactional source of truth.
- Alembic is the only schema-change mechanism.
- FastAPI is the serving and authorization boundary.
- `src/operations/worker.py` is the only background worker; PostgreSQL owns job,
  lease, outbox, delivery, notification, and heartbeat state.
- CSV is restricted to synthetic generation, explicit import/reset, validated
  database-to-analytics snapshots, compatibility fixtures, and batch outputs.
- Qdrant stores RAG document chunks only.
- The frontend and Streamlit consume FastAPI rather than transactional tables or
  CSV files directly.
- The dedicated PostgreSQL test workflow uses only the local `_test` database
  on port `15433`; see [`docs/testing-postgresql.md`](docs/testing-postgresql.md).

## Applications and entry points

| Runtime or tool | Entry point | Responsibility |
|---|---|---|
| FastAPI | `src.api.main:app` | HTTP contracts, middleware, authentication, authorization, and route composition |
| Worker | `python -m src.operations.worker` | Durable polling, leases, retry, outbox delivery, and the closed four-job catalog |
| Next.js | `frontend/src/app/` | Authenticated web UI backed by the FastAPI client |
| Streamlit | `python -m src.dashboard.app` | Legacy status/dashboard client that calls FastAPI |
| Migrations | `python -m alembic` | PostgreSQL schema versioning |
| Domain CLIs | `src/*_management/cli.py` | Explicit maintenance, ticket, inventory, and operator commands |
| Batch analytics | canonical modules under `src/features`, `src/models`, and `src/risk` | Snapshot-based feature, anomaly, risk, and report generation |
| RAG tools | `src.rag.index_documents`, `src.rag.query` | Explicit indexing and query workflows |
| Reliability tools | `src/reliability/` | Bounded deployment, validation, load, backup, and recovery rehearsal |

## Backend module ownership

| Area | Owner modules | Dependency rule |
|---|---|---|
| Transport | `src/api/routes.py` compatibility facade, `src/api/routers/`, domain `routes.py`, `src/security/routes.py`, `src/operations/routes.py` | Validate HTTP input, enforce route permission, call services, map known errors |
| Asset lifecycle | `src/asset_management/service.py` | Own lifecycle, hierarchy, attachment, and QR rules |
| Tickets and SLA | `src/ticket_management/service.py`, `application/catalogue_service.py`, `sla.py`, `domain.py` | Own named lifecycle actions, priority, clocks, escalation, and read-only catalogue/preview operations |
| Maintenance | `src/maintenance_management/service.py`, `recurrence.py`, `domain.py` | Own recurrence, checklist snapshots, work-order lifecycle, completion, and verification |
| Inventory | `src/inventory_management/service.py`, `application/catalogue_service.py`, `routes/`, `domain.py` | Own named stock actions, catalogue reads, idempotency, reservations, issue, consumption, return, and derived availability |
| Security | `src/security/` | Own roles, permissions, authentication, sessions, password handling, and audit context |
| Operations | `src/operations/` | Own the closed job/event catalogs and durable worker orchestration |
| Data access | `src/repositories/` | Implement storage contracts and PostgreSQL transaction/locking semantics |
| Persistence mapping | `src/database/models/` | Domain-owned SQLAlchemy model modules re-exported through `src.database.models`, corresponding to immutable Alembic history |
| Analytics | canonical paths named in `AGENTS.md` | Remain batch-first and preserve validated CSV contracts |
| RAG | `src/rag/` plus `src/rag/adapters/` | Retrieve documents and compose bounded guidance through application ports; never depend on API transport or become transactional storage |

The normal dependency direction is:

```text
route/CLI/worker -> service/domain -> repository contract -> PostgreSQL implementation/models
frontend page/component -> query or mutation hook -> centralized API endpoint/client -> FastAPI
```

The legacy `src/api/routes.py` module remains the public route facade. System,
analytics, and Copilot endpoints are composed from focused routers under
`src/api/routers/`; their dependency functions are shared with the facade so
existing test overrides and import seams remain valid. The concrete Copilot
graph is built by `src/composition/copilot.py`; `src/application/copilot_factory.py`
and `src/api/composition.py`
is a compatibility import for the serving boundary.

RAG orchestration consumes the narrow `AssetContextProvider` port from
`src/rag/adapters/asset_context.py`. `ProcessedDataAssetContextAdapter` is
selected by the API composition root, keeping storage/query-service knowledge
outside the RAG application. The old `src.rag.copilot.get_copilot_service`
symbol remains as a lazy compatibility facade. Its ordered pipeline is request
analysis, conversation and asset context resolution, retrieval/filtering,
safety and conflict gates, context budgeting, generation/output parsing,
citation validation, and the existing deterministic fallback policy.

Routes and frontend code must not manipulate SQLAlchemy entities or inventory
balances. Repositories must not make authorization decisions that belong only to
presentation code; services and repositories both retain the resource and
transaction checks documented by the existing implementation.

## Main execution flows

### Authenticated API request

1. FastAPI attaches or validates a request ID and records bounded request metrics.
2. The security dependency validates the access token, active refresh session,
   current user version, and required permission.
3. The route validates the Pydantic request and calls the canonical service.
4. The service applies business and resource rules.
5. The PostgreSQL repository locks and mutates the required rows, writes the
   append-only audit/outbox record in the same transaction when required, and
   returns a storage-neutral record.
6. The route serializes the established response contract.

### Background operation

1. The sole worker materializes or claims persisted work with bounded leases and
   concurrency-safe row locking.
2. The job dispatcher accepts only preventive generation, SLA escalation,
   analytics refresh, or inventory reorder detection.
3. The existing canonical service performs the operation.
4. Execution, retry/dead-letter, outbox delivery, notification, and heartbeat
   state remains durable and operator-visible in PostgreSQL.

### Batch analytics

1. PostgreSQL state is exported through the validated legacy snapshot boundary.
2. Generated sensor/document inputs are combined with the transactional snapshot.
3. Canonical feature, anomaly, risk, and maintenance-report modules publish CSV
   outputs atomically.
4. FastAPI reads the latest published batch; transactional writes do not trigger
   immediate recalculation.

### Frontend authentication

1. Login returns an access token to in-memory state and sets the revocable HttpOnly
   refresh cookie plus CSRF cookie.
2. The centralized API client adds the bearer token, validates request/response
   schemas, and attempts one refresh after a 401.
3. The frontend hides unavailable actions for usability; FastAPI remains the
   authorization authority.

## Data and contract boundaries

- Public routes, request/response shapes, status codes, Vietnamese business
  values, environment-variable names, and serialization formats are compatibility
  boundaries.
- PostgreSQL models and Alembic revisions must stay synchronized; applied
  migrations are immutable.
- Attachment metadata is transactional, while bytes stay behind
  `AttachmentStorage`; paths and storage keys are never public contracts.
- Work-order, ticket, maintenance-log, and inventory lifecycles remain separate.
- Inventory history and audit history are append-only; corrections are new events.
- The legacy analytics interval projection is preserved at the snapshot boundary
  even though plan-specific dates remain in PostgreSQL.

## Frontend structure

- `frontend/src/app/` owns route-level composition.
- `frontend/src/features/` owns feature workspaces and feature-specific UI:
  inventory, work-order parts, ticket detail, and SLA administration.
- `frontend/src/components/` owns shared UI primitives and compatibility facade
  entrypoints for existing imports.
- `frontend/src/hooks/` owns React Query orchestration.
- `frontend/src/lib/api/` owns API URLs, Zod schemas, authentication-aware HTTP,
  query keys, and user-safe transport errors.
- `frontend/src/test/` owns reusable test fixtures and render helpers.

The frontend uses npm with the committed `package-lock.json`; it must not change
package manager. Next.js-specific edits must follow the versioned documentation
installed under `frontend/node_modules/next/dist/docs/`.

The high-change compatibility entrypoints now delegate to bounded modules:
inventory actions live under `frontend/src/components/inventory/actions/`,
mutation hooks under `frontend/src/hooks/mutations/`, Copilot response views
under `frontend/src/components/copilot/`, and operations tables under
`frontend/src/components/operations/`.

Inventory HTTP routes are composed by `src/inventory_management/routes/router.py`
from focused catalogue, stock, reservation, work-order-parts, and attachment
routers. `_legacy.py` remains only as a compatibility re-export, and
`src.inventory_management.routes` remains the public facade. The ticket and
maintenance application services similarly delegate read-only catalogue and
preview responsibilities to `application/` modules while retaining their
transactional mutation boundaries.

The current application capability split is documented in
[`docs/application-services.md`](docs/application-services.md). Repository
session ownership, lock order, idempotency, audit, and outbox boundaries are
documented in [`docs/repository-transaction-map.md`](docs/repository-transaction-map.md).

The PostgreSQL implementation is decomposed by cohesive read capability while
the historical façades remain stable. Inventory reads, catalogue mutations, and
evidence mutations live under `src/repositories/postgres/inventory/`; maintenance
and ticket read queries live under their corresponding `maintenance/` and
`tickets/` packages; PM7 operational reads live under `operations/`. The original
repositories continue to own transaction-sensitive mutations, including locks,
idempotency, audit, outbox, and commit/rollback sequencing. The historical
`src.repositories.postgres` maintenance import is re-exported by the package
façade, and the pilot-contract CLI is similarly preserved through
`src/reliability/pilot_contract/`.

## Refactoring posture

The repository already has meaningful bounded-context and security boundaries.
Refactoring should therefore be incremental: remove demonstrated duplication,
extract cohesive sections only after characterization tests, and keep canonical
files and public contracts stable. The staged work and verified baseline are in
[`REFACTOR_PLAN.md`](REFACTOR_PLAN.md).

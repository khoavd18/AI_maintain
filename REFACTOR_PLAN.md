# Refactoring Plan

Status: active<br>
Audit date: 2026-07-27<br>
Audited branch: `feat/pm9-pilot-deployment-rehearsal`

## 1. Executive summary

The repository is not an unstructured prototype. It already has explicit product
guardrails, bounded business services, storage contracts, Alembic-managed
PostgreSQL persistence, a single durable worker, a centralized frontend API
client, and a broad automated test suite. The safest target is to preserve those
boundaries and reduce local complexity in reviewable stages.

The audit found no confirmed critical defect, hard-coded production secret,
duplicate scheduler, raw frontend database/CSV access, or confidently dead
production module. Ruff, ESLint, backend tests, frontend tests, production build,
Compose parsing, and the migration-head check pass in the current environment.

The main maintainability findings at audit time were:

- several high-risk persistence and reliability modules are very large;
- four domain/operator CLIs duplicated security actor-loading logic (resolved in
  Stage 1);
- the standalone strict TypeScript compiler reported pre-existing errors in test
  fixtures and fetch mocks even though the Next.js production build succeeded
  (resolved in Stage 2);
- a few compatibility modules pointed across otherwise clean dependency
  boundaries; the CSV write seam is resolved, while RAG structured context remains;
- no repository CI workflow currently executes the documented checks.

Implementation starts with the duplicated CLI actor loader because it is isolated,
behavior-preserving, and independently testable. Large transaction modules will
not be split until their lock, retry, idempotency, and audit behavior has focused
characterization coverage.

## 2. Detected technology stack

| Layer | Technology |
|---|---|
| Language/runtime | Python 3.11+, TypeScript 5.9, Node.js 22 in the audited environment |
| API | FastAPI, Pydantic, Uvicorn |
| Transactional database | PostgreSQL 16, SQLAlchemy 2, psycopg 3 |
| Schema management | Alembic, one current head `20260726_0008` |
| Background work | One custom PostgreSQL-backed worker with a closed four-job catalog |
| Batch analytics | pandas, NumPy, scikit-learn, CSV snapshots |
| RAG | Qdrant client, optional sentence-transformers embeddings |
| Web frontend | Next.js 16.2.12, React 19, TanStack Query, Zod, Tailwind CSS, Radix/shadcn primitives |
| Legacy dashboard | Streamlit consuming FastAPI |
| Backend tests/lint | pytest 8, Ruff |
| Frontend tests/lint/build | Vitest, Testing Library, ESLint 9, Next.js build |
| Packaging | setuptools/`pyproject.toml`; npm with `package-lock.json` |
| Local runtime | Dockerfiles and development/pilot Docker Compose definitions |

No Python static type checker, coverage threshold, formatter check, or CI workflow
is configured as a repository command today. The conservative convention is to
use existing Ruff formatting rules and strict TypeScript settings, but adopting
new required checks should be a separate reviewed stage.

## 3. Current architecture

The current map is documented in [`ARCHITECTURE.md`](ARCHITECTURE.md) and the
detailed canonical design in [`docs/architecture.md`](docs/architecture.md).

In summary:

- FastAPI route modules compose security dependencies and canonical services.
- Asset, ticket/SLA, maintenance, inventory, security, and operations services own
  their business rules.
- Repository contracts isolate PostgreSQL and the explicit CSV compatibility
  adapter.
- PostgreSQL repositories own transaction, row-locking, optimistic concurrency,
  idempotency, immutable history, audit, and selected outbox writes.
- `src/operations/worker.py` is the sole worker and invokes only existing domain
  services.
- Batch analytics uses validated database snapshots and canonical CSV-producing
  modules; writes do not recalculate risk or KPI state.
- Next.js calls FastAPI through a centralized, schema-validating client and keeps
  access tokens in memory.
- Qdrant stores documents only and is optional to non-RAG functionality.

## 4. Confirmed problems

### Critical

None confirmed during this audit.

### High

1. **Large high-consequence modules.** The remaining mutation façades
   `src/repositories/postgres_inventory.py`, `postgres_operations.py`,
   `postgres_maintenance.py`, and `postgres_tickets.py` remain large, while
   the SQLAlchemy model package is spread across domain-owned modules. Several
   functions exceed 100 lines and combine validation, row locking, mutation,
   append-only history, audit, and serialization. These are hard to review but
   cannot be mechanically split without risking transaction semantics.
2. **Large reliability procedures.** `src/reliability/pilot_contract/legacy.py`,
   `load_harness.py`, `drills.py`, `deployment_rehearsal.py`, and
   `post_start_validation.py` contain long procedural workflows. The longest
   functions are 288-534 lines. They are operator tooling rather than runtime
   business logic, but failures can invalidate rehearsal evidence and must remain
   fail-closed and secret-safe.

### Medium

1. **Standalone TypeScript check was not clean at baseline (resolved).** Running
   `tsc --noEmit` from the frontend reported 26 errors in test files: widened
   fixture literals, implicitly typed fetch parameters, tuple literals that were
   too narrow for test mutation, and one generic Zod request mismatch. Stage 2
   corrected the test types without weakening strict settings.
2. **Large frontend feature workspaces.** `inventory-workspace.tsx` and
   `work-order-parts-panel.tsx` exceed 1,200 lines; ticket operations and SLA
   administration are also large. They mix query state, forms, tables, and action
   presentation, making isolated change and testing harder.
3. **Compatibility-layer dependency direction (partially resolved).** At baseline,
   `src/repositories/csv.py` imported `src/api/csv_repository.py`. Stage 3a moved
   the single implementation to `src/repositories/csv_writes.py` and retained the
   old module as an identity-preserving re-export. `src/rag/copilot.py` still
   consumes `src.api.services` for structured context and needs characterization
   before any move.
4. **No CI workflow.** There is no `.github/workflows` directory. Validation is
   documented and available through Make/npm commands, but enforcement depends on
   local execution.
5. **PostgreSQL coverage is opt-in.** The suite correctly refuses a database whose
   name does not end in `_test`, but 73 integration tests skip when
   `TEST_DATABASE_URL` is unavailable. This is safe behavior; CI or a developer
   workflow needs to provision the isolated database to exercise them routinely.

### Low

1. **Duplicated CLI actor loading (resolved).** Ticket, maintenance, inventory,
   and operations CLIs independently queried and converted the same active `User`
   into `CurrentUser`. Stage 1 centralized that behavior in
   `src/security/cli_context.py`.
2. **Repeated small infrastructure helpers.** UTC timestamps, optimistic-version
   checks, UUID/date serialization, and audit-record construction recur in several
   repositories. Most are too small to justify a global utility; consolidation
   should happen only within a cohesive repository family.
3. **Historical verification is easier to find than the current local baseline.**
   README and milestone documents correctly retain evidence, but an engineer needs
   this plan to distinguish the 2026-07-27 no-database baseline from earlier
   database-enabled milestone runs.

### Optional

1. The explicit frontend `typecheck` script was added in Stage 2.
2. Consider a Python type checker only after annotating the highest-value service
   boundaries; do not introduce a repository-wide noisy gate in one change.
3. Consider duplication/complexity reporting as advisory metrics, not mandatory
   architecture.

## 5. Assumptions and uncertainties

- The clean Git status at audit start means no uncommitted user changes had to be
  preserved. Generated/ignored local files were excluded from architecture
  conclusions.
- The ignored `.env` was not inspected or modified. Configuration conclusions
  come from example files, settings code, Compose, tests, and documentation.
- No isolated `TEST_DATABASE_URL` was supplied in this shell, so PostgreSQL tests
  were skipped rather than pointed at the developer/demo database.
- The existing migration history, route registrations, CLI entry points, frontend
  routes, Docker topology, and documented external contracts may have consumers
  outside the repository. They are treated as stable.
- Text search alone was not used to declare files dead. Route registration, CLI
  entry points, tests, dynamic file discovery, package files, Docker/Make commands,
  and documentation references were considered. No production deletion is
  approved by this audit.
- No external pilot host, real organization credentials, or production system was
  contacted. Local tests are not evidence of production readiness or business
  impact.

## 6. Risk assessment

| Area | Change risk | Why |
|---|---|---|
| Alembic revisions/models | Critical | Schema and immutable migration history are transactional contracts |
| Auth/RBAC/session/audit | Critical | Security behavior and same-transaction audit guarantees |
| Inventory/maintenance/ticket PostgreSQL repositories | High | Row locks, idempotency, append-only history, and cross-record invariants |
| Worker/outbox | High | Lease recovery, retries, dead-letter state, and duplicate prevention |
| Analytics canonical modules | High | Validated legacy CSV contracts and prioritization formulas |
| API/Zod schemas | High | Public request/response compatibility |
| Frontend component decomposition | Medium | User-visible state and action availability can regress |
| Reliability tooling decomposition | Medium | Evidence, fail-closed behavior, and secret redaction can regress |
| CLI actor-loader consolidation | Low | Internal duplication with deterministic, testable behavior |
| Documentation and validation scripts | Low | No runtime behavior when commands and claims remain accurate |

## 7. Proposed target architecture

The target architecture is the current architecture with clearer local ownership,
not a replacement architecture:

- keep every canonical service, recurrence, worker, repository, analytics, and
  security boundary named in `AGENTS.md`;
- keep routes thin enough to show authorization, request mapping, service call,
  and response/error mapping without moving business rules into transport helpers;
- organize large services/repositories into private cohesive collaborators only
  when a characterization test proves transaction and serialization behavior;
- keep feature-specific frontend pieces beside their workspace rather than
  creating a global component dumping ground;
- centralize genuinely shared CLI authentication context in `src/security/`;
- preserve all public imports until repository and external usage is known;
- add validation automation after the existing commands are clean and stable.

## 8. Proposed target folder structure

Only the first new module is committed by the initial stage; the remaining tree is
a placement convention, not authorization for wholesale moves.

```text
src/
  api/                         FastAPI composition and legacy compatibility API
  asset_management/            Canonical asset business boundary
  ticket_management/           Canonical ticket/SLA business boundary
  maintenance_management/      Canonical maintenance business boundary
  inventory_management/        Canonical inventory business boundary
  operations/                  Sole worker and closed durable operations catalog
  security/
    cli_context.py             Shared explicit-CLI actor context
    ...                        Existing auth, RBAC, token, and audit modules
  repositories/                Storage contracts and PostgreSQL/CSV adapters
  database/                    SQLAlchemy metadata, migration helpers, snapshots
  features/                    Canonical feature/report pipeline
  models/                      Canonical anomaly pipeline
  risk/                        Canonical risk pipeline
  rag/                         Document retrieval and bounded composition
  reliability/                 Explicit operator/rehearsal tooling
  dashboard/                   Streamlit FastAPI client
frontend/src/
  app/                         Route-level composition
  components/                  Feature workspaces and UI primitives
  hooks/                       Query/mutation orchestration
  lib/api/                     Schemas, endpoints, query keys, HTTP/auth client
  test/                        Shared test fixtures and render utilities
tests/                         Backend behavior and integration tests
migrations/                    Immutable Alembic revisions
docs/                          Detailed product/operation contracts
```

## 9. Staged refactoring roadmap

### Stage 0 — Audit and baseline documentation

- **Status:** complete.
- **Current problem:** architecture and historical verification exist, but there
  was no focused refactoring inventory or current engineering map.
- **Behavior to preserve:** all runtime behavior and contracts.
- **Improvement:** add `ARCHITECTURE.md` and this staged plan; link them from the
  README.
- **Files:** `ARCHITECTURE.md`, `REFACTOR_PLAN.md`, `README.md`.
- **Risk:** low.
- **Validation:** documentation link test, Ruff, `git diff --check`.
- **Rollback:** remove the two documents and README links.
- **Complete when:** findings, baseline, risks, approval gates, and stages are
  recorded without aspirational claims.

### Stage 1 — Consolidate explicit CLI actor loading

- **Status:** complete.
- **Current problem:** four CLIs duplicate the active-user lookup and
  `CurrentUser` construction.
- **Behavior to preserve:** username normalization, active-user rejection,
  role-derived permissions, synthetic CLI session ID, timestamp fallback, command
  defaults, error text, audit identity, and storage-mode guards.
- **Improvement:** add one security-owned `load_cli_actor` helper; keep command
  parsing and audit request IDs in each domain CLI.
- **Expected files:** new `src/security/cli_context.py`, four existing CLI modules,
  focused tests.
- **Risk:** low.
- **Validation:** new characterization tests, affected CLI import tests, full
  pytest, Ruff.
- **Rollback:** restore the four local functions and delete the helper/test.
- **Complete when:** all four CLIs use the helper, duplicate imports/functions are
  removed, behavior tests pass, and no route/auth behavior changes.

### Stage 2 — Make frontend test code strict-TypeScript clean

- **Status:** complete.
- **Current problem:** standalone `tsc --noEmit` reports 26 test-only errors.
- **Behavior to preserve:** production schemas, API calls, rendered behavior, test
  assertions, and visual output.
- **Improvement:** type fixtures from Zod-inferred contracts, type fetch mocks with
  standard DOM signatures, avoid overly narrow mutable tuple fixtures, and correct
  the generic request test input.
- **Expected files:** frontend test fixtures and the named failing test files;
  optionally `frontend/package.json` for a `typecheck` script after it passes.
- **Risk:** low to medium.
- **Validation:** local Next.js versioned docs review, standalone TypeScript,
  Vitest, ESLint, and Next.js production build.
- **Rollback:** revert test-only typing edits and any script addition.
- **Complete when:** strict TypeScript, tests, lint, and build all pass without
  weakening compiler options or using blanket casts/ignores.

### Stage 2b - Extract inventory catalogue application use cases

- **Status:** complete for read-only options, category, and unit queries.
- **Implementation:** `src/inventory_management/application/catalogue_service.py`
  owns the catalogue read family. `InventoryManagementService` remains the
  public business facade and retains all mutation, authorization, and storage
  boundaries.
- **Behavior preserved:** option catalogs, permission checks, repository reads,
  returned records, exception behavior, and public imports.
- **Deferred:** stock mutations, reservations, issues, returns, transfers, and
  evidence remain in the canonical service until their transaction
  characterization is expanded.
- **Validation:** focused catalogue/inventory tests, Ruff, and compileall.

### Stage 3 — Characterize compatibility dependency seams

- **Status:** complete for the CSV and RAG context seams.
- **Current problem:** CSV repository logic lived under an API-named module, and
  RAG structured context depended on the API service module.
- **Behavior to preserve:** existing import paths, CSV atomic-write/error behavior,
  RAG context shape, public API output, and test fixtures.
- **Improvement:** add import/behavior characterization; introduce a neutral
  implementation module only when justified while keeping compatibility
  re-exports. The CSV implementation now lives in
  `src/repositories/csv_writes.py`; `src.api.csv_repository` preserves object
  identity for existing imports. The RAG context port now lives in
  `src/rag/adapters/asset_context.py`; concrete assembly is in
  `src/composition/copilot.py`, with `src/application/copilot_factory.py` and
  `src/api/composition.py` retained
  as a compatibility import.
- **Expected files:** `src/api/csv_repository.py`, `src/repositories/csv.py`,
  `src/rag/copilot.py`, `src/api/services/`, focused tests.
- **Risk:** medium.
- **Validation:** storage configuration/workflow/RAG/API tests, full pytest, Ruff.
- **Rollback:** retain existing implementation modules/imports.
- **Complete when:** dependency direction is improved without duplicating an
  implementation or removing a compatibility path whose use is uncertain.

### Stage 3b - Split compatibility API routers

- **Status:** complete for system/readiness, analytics, and Copilot endpoints.
- **Implementation:** `src/api/routers/system.py`, `analytics.py`, and
  `copilot.py` own focused route families. `src/api/routes.py` remains a thin
  facade and re-exports the historical dependency seams.
- **Behavior preserved:** public paths, response schemas, permissions, status
  codes, rate limiting, Qdrant readiness behavior, and test dependency
  overrides.
- **Validation:** API characterization tests, RAG tests, compileall, Ruff, and
  the full suite remain required before this stage is considered released.

### Stage 4 — Decompose large frontend workspaces by cohesive feature

- **Status:** complete for the four targeted workspaces.
- **Current problem:** inventory, work-order parts, ticket operations, and SLA
  workspaces mix multiple forms, query states, and tables in single large files.
- **Behavior to preserve:** routes, accessibility, responsive layout, Vietnamese
  messages, query invalidation, idempotency keys, permissions, and visual design.
- **Improvement:** feature entrypoints now live under
  `frontend/src/features/inventory/`, `work-orders/parts/`, `tickets/detail/`,
  and `sla/`; the original component files are thin re-export facades. Internal
  forms, tables, selectors, action panels, timelines, and stateful forms now
  live in cohesive feature modules; no UI or request contract was changed.
- **Expected files:** selected large component, colocated feature components/tests,
  existing hooks/API modules only when required.
- **Risk:** medium.
- **Validation:** focused component tests, strict TypeScript, full Vitest, ESLint,
  Next.js build, and manual route smoke where available.
- **Rollback:** revert one feature extraction at a time.
- **Complete when:** the parent file becomes navigable, behavior tests cover all
  loading/empty/success/error/action states, and output is unchanged. Focused
  inventory, ticket, and work-order suites pass with the full frontend suite.

### Stage 4b — Split inventory route families and read-oriented services

- **Status:** complete for inventory routes, ticket/maintenance catalogue reads,
  and maintenance occurrence preview.
- **Implementation:** `src/inventory_management/routes/router.py` composes
  `catalogue.py`, `stock.py`, `reservations.py`, `work_order_parts.py`, and
  `attachments.py`; shared dependency aliases and HTTP error mapping are in
  `dependencies.py` and `error_mapping.py`. `_legacy.py` and the package import
  remain compatibility facades. Ticket read options/priority preview are in
  `src/ticket_management/application/catalogue_service.py`; maintenance
  options/occurrence preview are in
  `src/maintenance_management/application/catalogue_service.py`.
- **Behavior preserved:** all 45 historical inventory route path/method/name
  definitions, dependencies, tags, schemas, status codes, permission checks,
  error mapping, and service calls; transactional mutation ownership remains in
  the canonical services/repositories.
- **Validation:** route contract and application read-service characterization
  tests, focused inventory/ticket/maintenance tests, Ruff, and compileall.

### Stage 5 — Extract repository internals behind unchanged public classes

- **Status:** pending; requires characterization first.
- **Current problem:** PostgreSQL repository files combine many cohesive command
  families and serializers.
- **Behavior to preserve:** repository class/public method names, transaction
  scope, lock order, constraints, idempotency replay/conflict, append-only records,
  audit/outbox atomicity, error types, and returned dictionaries.
- **Improvement:** one bounded extraction at a time (for example inventory record
  serialization or read projections), using private modules/functions and leaving
  canonical repository classes in place.
- **Expected files:** one repository plus a private sibling module and focused
  unit/PostgreSQL tests per stage.
- **Risk:** high.
- **Validation:** focused pure tests, all relevant `_test` PostgreSQL tests under
  contention/replay, full pytest, Ruff, Alembic check on an isolated database.
- **Rollback:** revert the single extraction; no schema rollback.
- **Complete when:** transaction boundaries and query behavior are visibly
  unchanged and the canonical repository becomes smaller/cohesive.

### Stage 6 — Partition reliability procedures without changing evidence

- **Status:** pending.
- **Current problem:** long validation/rehearsal procedures combine preparation,
  execution, redaction, and report assembly.
- **Behavior to preserve:** CLI options, exit behavior, fail-closed decisions,
  allow-lists, no-secret reporting, artifact schemas, atomic publication, and
  bounded external actions.
- **Improvement:** extract pure validators/report builders first, then small
  orchestration steps with explicit typed inputs.
- **Expected files:** one reliability module and focused tests per change.
- **Risk:** medium to high.
- **Validation:** focused PM9 tests, full pytest, Ruff, Compose example validation,
  and existing dry-run contract checks.
- **Rollback:** revert one helper extraction at a time; never rewrite evidence.
- **Complete when:** orchestration reads as a sequence of named stages and all
  artifact/secret-safety tests remain identical.

### Stage 7 — Add repeatable validation automation

- **Status:** pending.
- **Current problem:** checks are local commands only; PostgreSQL integration is
  not automatically provisioned.
- **Behavior to preserve:** package managers, supported Python/Node/PostgreSQL
  versions, service names, and non-destructive `_test` guard.
- **Improvement:** the explicit frontend typecheck command is complete. A reviewed
  CI workflow should later use an isolated `_test` PostgreSQL service. Do not add
  deployment or release automation in this stage.
- **Expected files:** `frontend/package.json`, possibly Makefile, and a new CI
  workflow after repository-owner review of platform/secret policy.
- **Risk:** medium (process/infrastructure).
- **Validation:** run every workflow command locally; validate workflow syntax and
  verify no secret values or mutable developer database URL is used.
- **Rollback:** remove the workflow/script without changing runtime artifacts.
- **Complete when:** backend, Ruff, frontend typecheck/test/lint/build, docs links,
  and isolated PostgreSQL tests are enforced reproducibly.

## 10. Validation strategy

Minimum after every repository change:

```powershell
.\.venv\Scripts\python.exe -m pytest <focused tests>
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
git diff --check
```

For frontend changes, also run from `frontend/`:

```powershell
npm exec -- tsc --noEmit
npm run test
npm run lint
npm run build
```

For PostgreSQL repository/schema-sensitive changes, provision a dedicated database
whose name ends in `_test`, then run the relevant `pytest -m postgres` selection.
Never point destructive setup at the developer/demo database. For Compose edits,
validate both development Compose and the pilot file using its example environment.

### Untouched baseline results

| Command | Exact result |
|---|---|
| `git status --short --branch` | Clean branch `feat/pm9-pilot-deployment-rehearsal` |
| `.venv\\Scripts\\python.exe -m pytest` | `303 passed, 73 skipped, 1 warning` in 65.22s; skips require `TEST_DATABASE_URL` |
| `.venv\\Scripts\\python.exe -m ruff check .` | Passed: `All checks passed!` |
| `npm --prefix frontend run test` | 17 files, 112 tests passed |
| `npm --prefix frontend run lint` | Passed with no ESLint diagnostics |
| `npm --prefix frontend run build` | Passed; 32 routes generated and production TypeScript phase completed |
| `npm exec -- tsc --noEmit` from `frontend/` | Failed with 26 pre-existing errors in test code |
| `docker compose config --quiet` | Passed |
| `docker compose --env-file .env.pilot.example -f docker-compose.pilot.yml config --quiet` | Passed |
| `.venv\\Scripts\\python.exe -m alembic heads` | One head: `20260726_0008` |

Additional environment note: the unqualified global `python -m ruff check .`
could not run because global Python did not have Ruff. The repository-local virtual
environment command above is the valid result.

Not run in the untouched baseline:

- PostgreSQL integration execution, because no isolated `TEST_DATABASE_URL` was
  provided; 73 tests skipped safely.
- `alembic current/check`, because the audit did not select or mutate a developer
  database and no isolated test database was configured.
- live Docker API/worker/Qdrant/pilot-host smoke, destructive reset/import, load,
  backup, restore, or secret rotation.

## 11. Files and areas that should not be changed casually

- `AGENTS.md` product boundaries and canonical path rules.
- Existing files under `migrations/versions/`; add a new Alembic revision only for
  an explicitly approved schema change.
- `src/database/models/` without an approved migration and isolated schema tests.
- Canonical recurrence, analytics, worker, job/event catalog, permission matrix,
  token/session, audit, attachment, and stock-control logic.
- Public FastAPI routes/schemas and frontend Zod/API contracts.
- Docker service names, ports, volumes, topology, and environment names.
- `frontend/package-lock.json` except for an intentional npm dependency operation.
- Generated/ignored files, local `.env`, data outputs, evidence, backups, coverage,
  caches, virtual environments, `node_modules`, and `.next` artifacts.

## 12. Remaining technical debt

- Oversized transactional repository/service modules and SQLAlchemy metadata.
- Oversized frontend feature workspaces.
- Oversized PM9 reliability orchestration functions.
- No CI enforcement or routinely provisioned isolated PostgreSQL integration run.
- `src/api/routes.py` has a small remaining compatibility/error-mapping layer by
  design; it is not a second route implementation.
- Process-local login rate limiting and metrics, single-node attachment storage,
  and other documented internal-pilot limitations. These are product limitations,
  not refactoring defects, and must not be silently expanded into prohibited scope.
- Third-party `StarletteDeprecationWarning` for FastAPI `TestClient`/httpx; dependency
  changes should be handled separately rather than suppressed.

The current file-level backend inventory, including the complete `src` register,
dependency findings, and ranked retain/refactor decisions, is recorded in
[`docs/backend-structural-inventory.md`](docs/backend-structural-inventory.md).

## 13. Implementation progress

### Completed in this refactoring session

- Added the concise current-state architecture map and this risk-ranked roadmap.
- Consolidated four explicit CLI actor loaders in `src/security/cli_context.py`
  with four characterization tests.
- Corrected all 26 baseline frontend test type errors using existing inferred API
  types and standard fetch signatures; added documented npm/Make typecheck commands.
- Relocated the one atomic CSV write implementation to the repository layer,
  retained the old API import path as a compatibility re-export, and added an
  object-identity compatibility test.
- Split system/readiness, analytics, and Copilot routes into focused routers
  while retaining `src/api/routes.py` as a compatibility facade.
- Added the RAG `AssetContextProvider` port and API composition adapter, moved
  the concrete Copilot graph out of `src/rag/copilot.py`, and kept its legacy
  factory symbol as a lazy facade.
- Moved storage-neutral processed-data errors into `src/analytics/errors.py`
  so RAG query code no longer imports those errors from the API service module.
- Moved the four largest frontend workspace entrypoints into feature-owned
  directories and retained the original component files as compatibility
  re-exports. Route pages now import the feature entrypoints directly.
- Split inventory route implementation into focused modules under
  `src/inventory_management/routes/`; `_legacy.py` now only re-exports the
  historical names and the package facade remains at
  `src.inventory_management.routes`.
- Extracted read-only inventory catalogue operations into
  `src/inventory_management/application/catalogue_service.py` with a focused
  characterization test; mutation families remain atomic in the canonical
  service.
- Extracted ticket read-only catalogue/priority preview and maintenance
  read-only options/occurrence preview into focused application services.
- Decomposed inventory, work-order-parts, ticket-detail, and SLA frontend
  implementations into feature-owned sections, forms, selectors, tables,
  action panels, timelines, and compatibility entrypoints.

### Validation after the completed stages

- CLI context focused tests: `4 passed`.
- CSV/storage focused tests: `23 passed`, with the existing third-party warning.
- Frontend: typecheck passed, `112 passed` across 17 Vitest files, ESLint passed,
  and the Next.js production build generated 32 routes.
- Final backend: `308 passed, 73 skipped, 1 warning`; the 73 skips require an
  isolated `TEST_DATABASE_URL` and the warning is the pre-existing third-party
  FastAPI `TestClient`/httpx deprecation.
- Final Ruff and `git diff --check`: passed.
- Current focused API/RAG run: `30 passed, 16 skipped, 1 warning`.
- Current compileall run: passed.
- Current full backend: `369 passed, 73 skipped, 1 warning`; skips require an
  isolated `TEST_DATABASE_URL` whose database name ends in `_test`.
- Current frontend: typecheck passed; `23` Vitest files and `137` tests passed;
  ESLint passed; Next.js build passed and generated `32` routes.
- Current Compose validation: development and pilot `docker compose config`
  both passed.
- Current Alembic metadata check: unavailable because PostgreSQL at the
  configured `localhost:15432` endpoint was not reachable; `alembic heads`
  still reports the single head `20260726_0008`.
- Current inventory route characterization: `4 passed, 10 skipped, 1 warning`.
- Current frontend feature characterization: `16 passed` across the inventory,
  ticket, and work-order focused suites; typecheck and lint passed.
- Current inventory catalogue characterization: `5 passed, 10 skipped, 1
  warning`.
- Current inventory route/application-service characterization: `3 passed`.

## 14. Decisions requiring explicit human approval

Approval is required before:

- changing any public API route, payload, status code, or serialization;
- changing PostgreSQL schema or migration history;
- changing authentication, authorization, audit, session, cookie, or token behavior;
- changing environment names, deployment topology, Docker ports/volumes/services,
  package manager, framework, runtime, or a major dependency;
- changing analytics formulas, recurrence, lifecycle/state machines, transaction
  boundaries, lock order, idempotency, or append-only semantics;
- removing code whose external/dynamic usage remains uncertain;
- adding a CI platform workflow that requires organization-owned runners,
  credentials, protected environments, or release/deployment authority;
- implementing any explicitly prohibited scope such as procurement, external
  notifications, enterprise IAM, mobile apps, real-time streaming, or another
  scheduler/worker.

No such approval-gated change is part of Stage 1.

## Current PostgreSQL-safe refactor checkpoint

The dedicated test workflow is now implemented in `docker-compose.test.yml`,
`.env.test.example`, and `scripts/test-postgres.ps1`. It uses PostgreSQL 16 on
port `15433` with `maintenance_copilot_test`; URL validation rejects non-local,
non-`_test`, placeholder, development-credential, and mismatched runtime
targets. See [`docs/testing-postgresql.md`](docs/testing-postgresql.md).

The verified PostgreSQL result is `73 passed, 388 deselected, 1 warning`; the
clean-environment backend result is `388 passed, 73 skipped, 1 warning`. With
the isolated PostgreSQL URL, the complete backend is `460 passed, 1 failed,
1 warning` because of the documented pre-existing pilot-settings validation
ordering defect. Alembic head/current remain `20260726_0008` and `alembic check`
reports no new upgrade operations. The metadata snapshot tool and
characterization tests are in `src/database/metadata_snapshot.py` and
`tests/test_metadata_snapshot.py`.

Inventory, ticket, and maintenance facades now delegate evidence, query,
catalogue, comment, and preview capabilities to focused application modules.
Transaction-heavy repository methods were deliberately left intact; their
session, lock, idempotency, audit, and outbox map is recorded in
[`docs/repository-transaction-map.md`](docs/repository-transaction-map.md).
The remaining mutation orchestration is deferred until one family at a time
has additional method-level characterization coverage.

## Current backend-core decomposition checkpoint

The SQLAlchemy model monolith is now the domain-owned package
`src/database/models/`, with compatibility exports for historical imports and
metadata/Alembic equivalence tests. PostgreSQL query capabilities are composed
under `src/repositories/postgres/`:

- inventory queries, catalogue mutations, and evidence mutations;
- maintenance plan/template/work-order/evidence reads;
- ticket intake, queue, SLA-policy, calendar, and policy reads;
- PM7 job, execution, outbox, notification, worker-health, and metrics reads.

The historical repository façade signatures remain unchanged. Stock-control,
maintenance lifecycle/completion/generation, ticket lifecycle/SLA/comments/
escalation, and PM7 lease/delivery/retry/heartbeat mutations remain in their
original files because they own atomic lock, idempotency, audit, outbox, and
commit sequencing. Reliability pilot-contract redaction is now a separate
implementation module with a package façade and preserved module CLI.

Known pre-existing defect found during validation: a pilot `Settings` test can
report the release-identity validation error before the expected development
database-credential error when the release identity is not supplied. It was
not changed in this structural refactor and should be handled as a separate
settings-validation bug fix.

## Current non-transactional decomposition checkpoint

The pilot contract implementation is package-owned with a 53-line historical
façade. The 913-line processed-data service is now a 77-line public package
façade over snapshot, projection, legacy-write, asset-context, and factory
collaborators. RAG no longer imports API composition; `MaintenanceCopilot.ask`
is linear orchestration over request analysis, retrieval/evidence, and
generation/citation services. The first four remaining frontend hotspots are
split into operation forms, bounded mutation-hook modules, Copilot response
views, and PM7 operations tables.

The deliberately deferred mutation repositories remain
`postgres_inventory.py`, `postgres_maintenance.py`, `postgres_tickets.py`, and
`postgres_operations.py`; their transaction boundaries, session ownership,
locks, idempotency, audit, and outbox behavior were not moved. The known
reliability-settings validation-order defect remains open.

## Continuation checkpoint — 2026-08-06

Initial worktree was clean and the baseline completed with `390 passed, 73
skipped, 1 warning`; isolated PostgreSQL validation completed with `73 passed,
390 deselected, 1 warning`. Ruff, compileall, `git diff --check`, and Alembic
`current`, `heads`, and `check` passed; the single head remains
`20260726_0008`.

Inherited refactoring remains intact. The new work in this continuation is
Phase A: `CurrentUser` now lives in `src/security/principal.py`, all backend
consumers use that module, and `src.security.service.CurrentUser` remains a
historical re-export. Focused authentication/API/application tests passed with
`25 passed, 9 skipped, 1 warning`. No frontend, API contract, schema, or
transaction implementation changed. The complete ranked structural inventory
is in [`docs/backend-structural-inventory.md`](docs/backend-structural-inventory.md).

Phase B is now complete: the old monolithic contract module was replaced by
`src/repositories/contracts/` with shared, asset, inventory, maintenance,
ticket, and operations definitions. `src.repositories.contracts` continues to
resolve to the package facade; ticket and operations application collaborators
now type against protocols rather than concrete PostgreSQL classes. Focused
validation passed (`14 passed, 43 skipped, 1 warning`), isolated PostgreSQL
validation passed (`73 passed, 390 deselected, 1 warning`), and no repository
implementation or transaction family moved. Phase C is now complete: service,
security, asset, worker, and Copilot construction moved into `src/composition/`
with historical builders and cache identities preserved. Focused architecture/
API/auth validation passed (`28 passed, 9 skipped, 1 warning`), CLI help smoke
checks passed, and isolated PostgreSQL validation passed again (`73 passed,
390 deselected, 1 warning`). The next safe phase is Phase D, inventory
application-service decomposition.

Phase D is now complete for the safe inventory catalogue boundary. The real
orchestration for category/unit/part master data, part lifecycle, stock-location
lifecycle, and reorder configuration moved to
`src/inventory_management/application/catalogue_mutation_service.py`; the
facade signatures and callback validation order remain unchanged. Focused
inventory validation passed (`3 passed, 10 skipped, 1 warning`) and isolated
PostgreSQL validation passed (`73 passed, 390 deselected, 1 warning`). Stock
receipt, transfer, adjustment, reservation, issue, consumption, return, and
evidence transaction families remain intentionally retained. The next safe
phase is Phase E, ticket application-service decomposition.

Phase E is complete for the safe ticket SLA administration boundary. Calendar
and policy listing/creation/update orchestration moved to
`ticket_management/application/sla_service.py`; focused ticket validation
passed (`20 passed, 8 skipped, 1 warning`) and isolated PostgreSQL validation
passed after one corrected callback call-shape regression (`73 passed, 390
deselected, 1 warning`). Ticket lifecycle, SLA snapshot, escalation, comment,
audit, and outbox families remain retained.

Phase F is complete for checklist-template application orchestration. Listing,
creation, immutable versioning, and archive mapping moved to
`maintenance_management/application/template_service.py`; focused maintenance
validation passed (`15 passed, 9 skipped, 1 warning`) and isolated PostgreSQL
validation passed (`73 passed, 390 deselected, 1 warning`). Plan lifecycle,
generation, work-order, checklist completion, verification, and evidence
transaction families remain retained. The next safe phase is Phase G, security
service decomposition.

## Final continuation checkpoint — 2026-08-06

Phase G now includes an explicit ORM-free security transaction contract and one
complete transaction-family extraction. `src/security/identity.py` owns
identity projections; `src/security/errors.py` owns shared security errors;
`src/security/session_state.py` owns the pure access-state predicate; and
`src/security/contracts.py` plus `src/security/session_service.py` own the
single-session logout port and complete SQLAlchemy-backed transaction.
`src.security.service` remains the historical facade. Contract and PostgreSQL
tests protect one-session ownership, audit atomicity, idempotency, and facade
compatibility.

Login, refresh rotation, password revoke-all, user administration, and their
audit orchestration remain retained in `AuthService`. No token/password/API or
environment behavior changed, and no partial transaction family was moved.

The pre-characterization baseline was full backend `402 passed, 73 skipped, 1
warning`; latest isolated PostgreSQL `73 passed, 402 deselected, 1 warning`.
Refresh characterization added the exact operation contract, 2 application
signature tests, and 3 additional PostgreSQL tests without moving production
refresh code. The final security-phase validation passed: full backend `404
passed, 86 skipped, 1 warning`; isolated PostgreSQL `86 passed, 404
deselected, 1 warning`; Ruff and compileall passed; Alembic current/head/check
passed at `20260726_0008`; and all three development/test/pilot Compose
configurations parsed successfully. No frontend file changed, no API contract
or database metadata changed, and no transaction boundary was intentionally
changed. The next single recommended backend phase is a separately approved
extraction of a complete transaction family, only if its repository/session
contract is first made explicit.

## Continuation checkpoint — 2026-08-08

Recovered seam work is green: UTF-8 plan validation, ORM-free audit context and
ticket references, explicit PM7 runtime providers, composition ownership,
Copilot direction, and neutral reliability dotenv parsing. Assignment is the
first real ticket application extraction and is documented in
[`docs/ticket-application-characterization.md`](docs/ticket-application-characterization.md).
Ticket intake is now characterized and extracted; the next exactly bounded
phase is ticket lifecycle characterization.
No transaction-heavy repository, API contract, migration, security family, RAG
pipeline, or frontend file was changed. Isolated PostgreSQL validation passed
after one direct-constructor compatibility repair.

## Continuation checkpoint - 2026-08-08 lifecycle

Ticket lifecycle/state-transition characterization is complete. The exact
contracts for acknowledge, start, hold, resume, resolve, close, reopen, and
cancel are recorded in docs/ticket-application-characterization.md, including
validation order, RBAC/technician ownership, snapshotted SLA pause/resume and
occurrence behavior, audit metadata, selected outbox mappings, and the
PostgresTicketRepository.mutate_ticket transaction owner.

The cohesive application orchestration moved to
src/ticket_management/application/lifecycle_service.py. The historical
TicketWorkflowService preserves every public signature and delegates the eight
named lifecycle methods. change_priority, SLA snapshot/override, escalation,
comments, legacy adapters, and bootstrap remain intentionally retained. No
PostgreSQL transaction, session, lock, audit, outbox, API, schema, migration,
RBAC, or frontend behavior changed. The exactly next bounded backend phase is
ticket SLA-runtime characterization; escalation remains deferred.

Final lifecycle validation: the dedicated characterization file passed 8
tests; the focused ticket selection passed 12; full backend
passed 421 with 87 skipped and one existing FastAPI/Starlette-httpx warning;
isolated PostgreSQL passed 87 with 421 deselected and the same warning. Ruff,
compileall, Alembic current/heads/check at 20260726_0008, all three Compose
config checks, and git diff --check passed. No frontend, API, RBAC, schema,
migration, transaction/session/lock, or audit/outbox behavior changed.

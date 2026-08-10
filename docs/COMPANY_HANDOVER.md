# Company Handover

## Handover Status

This repository is suitable for developer handover and controlled local demonstration after the documented setup. PostgreSQL integration, live Qdrant, a real Ollama provider, the full development Compose stack, and the authenticated multi-role workflow were exercised on an isolated local `_test` environment. It is still not a production acceptance package. Company owner assignments, approved secrets/provider, intended-host rehearsal, recovery evidence, support coverage, dependency remediation, and known-limitation acceptance remain external gates.

## System Ownership Map

| Area | Canonical owner in code |
|---|---|
| FastAPI composition and legacy analytics API | `src/api/` |
| Identity, RBAC, sessions, audit dependencies | `src/security/` |
| Asset lifecycle/files/QR | `src/asset_management/`, `postgres_assets.py` |
| Ticket lifecycle/SLA/escalation | `src/ticket_management/`, `postgres_tickets.py` |
| Preventive plans/work orders/logs | `src/maintenance_management/`, `postgres_maintenance.py` |
| Spare parts/stock ledger | `src/inventory_management/`, `postgres_inventory.py` |
| Only worker/jobs/outbox/notifications | `src/operations/`, `postgres_operations.py` |
| PostgreSQL schema | `src/database/models/`, `migrations/` |
| Batch analytics | `src/features/`, `src/models/anomaly_detection.py`, `src/risk/risk_scoring.py` |
| RAG retrieval/orchestration | `src/rag/` |
| LLM provider/prompt/parser/citations | `src/llm/` |
| Next.js workflows | `frontend/src/` |
| Reliability/rehearsal | `src/reliability/`, `deployment/`, PM9 docs |

## Where Do I Change X?

Use this as the first navigation map. Routes and React components translate
transport or presentation concerns; they are not owners of business rules,
ORM state, balances, or transactions.

| Requirement | Start reading/changing | Boundary to preserve |
|---|---|---|
| Add a rich HTTP operation | The focused domain route (`src/ticket_management/routes.py`, `src/maintenance_management/*_routes.py`, or `src/inventory_management/routes/`) and its application service | Keep validation in the service and storage selection in composition. Extend `src/api/routes.py` only when maintaining a legacy compatibility contract. |
| Change asset lifecycle, hierarchy, files, or QR lookup | `src/asset_management/service.py` → `src/repositories/postgres_assets.py`; reuse `AttachmentStorage` | The service owns lifecycle/authorization; PostgreSQL owns locks, audit, and commit/rollback. QR values identify a lookup URL and are not credentials. |
| Change ticket intake, assignment, lifecycle, SLA, or escalation | `src/ticket_management/application/` (`intake_service.py`, `assignment_service.py`, `lifecycle_service.py`, `sla_runtime_service.py`, `escalation_service.py`) → `src/ticket_management/service.py` facade | `PostgresTicketRepository` remains the mutation transaction owner. Use named actions; do not add a generic status patch or automatic resolution. |
| Change preventive-plan lifecycle | `src/maintenance_management/application/preventive_plan_service.py` → `src/maintenance_management/service.py` facade | The collaborator validates intent and delegates one command; `src/repositories/postgres_maintenance.py` keeps row locks, version checks, audit, and commit/rollback. Recurrence rules stay in `recurrence.py`. |
| Change work-order planning or assignment | `src/maintenance_management/application/work_order_planning_service.py` → `src/maintenance_management/service.py` facade | PostgreSQL still allocates numbers, snapshots checklist items, and commits audit/outbox with the work order. |
| Change work-order transitions or checklist responses | `src/maintenance_management/application/work_order_lifecycle_service.py` → facade → `src/repositories/postgres_maintenance.py` | Use named transitions. Keep expected-version checks, checklist writes, and audit/outbox atomic. |
| Change completion or independent verification | `src/maintenance_management/application/work_order_completion_service.py` → facade → repository | Work order, maintenance log, asset dates, audit, and outbox remain one repository transaction. Completion/verification never resolves a ticket or changes stock implicitly. |
| Change preventive generation or maintenance reporting | `preventive_generation_service.py` or `work_order_reporting_service.py` under `src/maintenance_management/application/` | Keep canonical recurrence in `recurrence.py`; occurrence uniqueness and generation commits stay PostgreSQL-owned. Reporting remains read-only and preserves current page caps/scoping. |
| Change inventory catalogue, evidence, or read models | `src/inventory_management/application/` and `src/inventory_management/routes/` | Stock-changing commands stay in `src/inventory_management/service.py` and `src/repositories/postgres_inventory.py`; preserve idempotency, locks, and append-only movements. |
| Change a database table or constraint | `src/database/models/<context>.py` plus a new Alembic revision in `migrations/versions/` | Use the shared model registry and run metadata snapshot/equivalence and `alembic check`; never call `metadata.create_all()` in startup. |
| Change batch features, anomaly, or risk prioritization | `src/features/build_features.py`, `src/models/anomaly_detection.py`, or `src/risk/risk_scoring.py` | Keep the CSV snapshot boundary and batch-only recalculation contract; risk is prioritization, not an automatic decision. |
| Change RAG chunking/retrieval/answer safety | `src/rag/chunking.py` or `src/rag/application/`, composed by `src/composition/copilot.py` | Keep the narrow `AssetContextProvider` port and citation/safety gates; RAG code must not import API services. |
| Change jobs, leases, outbox, or in-app notifications | `src/operations/domain.py`, `src/operations/worker.py`, and `src/repositories/postgres_operations.py` | The worker is the only background loop and accepts only the four cataloged PM7 operations; durable PostgreSQL records are authoritative. |
| Change deployment-manifest declarations, topology, or checked-in source binding | `src/reliability/pilot_contract/deployment_manifest/` and `deployment/pilot_manifest.json` | Artifact, environment, health, jobs, repository, storage, and service/port/volume topology validators are capability-owned there. Never add arbitrary executable/module/SQL/workflow fields, replace runtime ownership, or move FastAPI health behavior into the contract validator. |
| Change a frontend workflow | The matching module under `frontend/src/features/` and its route page | Preserve the historical `frontend/src/components/` re-export paths, permission checks, memory-only access tokens, and mutation/refresh semantics. |
| Change authentication, RBAC, sessions, or audit context | `src/security/` | Keep authorization in FastAPI and successful audit writes in the same PostgreSQL transaction as the business mutation; never log secrets or tokens. |

If a proposed change does not fit one row, stop and write down the new
capability owner and transaction boundary before editing. Update API/schema
contracts and characterization tests with the implementation; do not make a
route or frontend the hidden second owner.

## Database Model Registration And Import Order

All mapped classes share the single `Base` and metadata from
`src.database.session`. The eager import list in
`src/database/models/__init__.py` is the registration boundary and currently
loads `base_mixins`, `assets`, `tickets`, `maintenance`, `inventory`, `identity`,
`operations`, and `reliability`, then re-exports the historical public names.
Keep that package importable as `src.database.models`; do not create a second
declarative base, registry, or per-context metadata object.

When adding or splitting a model:

1. Put it in the owning context module and keep existing table names, string
   foreign-key targets, indexes, constraints, and mapped-class behavior.
2. Add the module to the package import list and `__all__` (including any
   compatibility alias) before relying on it from repositories or migrations.
3. Ensure `migrations/env.py` and `src/database/metadata_snapshot.py` import
   `src.database.models` before reading `Base.metadata`; import order is part of
   mapper registration, not incidental style.
4. Compare a metadata snapshot and run Alembic checks before and after the
   change. A structural refactor does not justify a migration; a schema change
   requires an explicit Alembic revision.

Never use `metadata.create_all()` in application startup or production commands.
Avoid importing concrete repositories, API routers, or composition modules from
model modules; use string relationship targets and the shared base/mixins to
keep registration acyclic.

## Safe Extension Example: A Read-Only Plan Filter

For a request such as “let managers filter preventive plans by an additional
read-only attribute,” extend `plan_routes.py`/`plan_schemas.py`, validate and
shape the filter in `MaintenanceQueryService`, add the narrow method/parameter
to `MaintenancePlanningRepository` and its PostgreSQL query, and keep
`MaintenancePlanningService` as the route dependency. Add a storage-neutral
unit characterization and an isolated PostgreSQL query test, then update the
corresponding `frontend/src/features/` query and loading/empty/error states if
the UI consumes it. This path does not write business state, audit, outbox, or
inventory history. If the requirement becomes a state mutation, use the named
application command and preserve its existing repository transaction instead of
turning the read path into a write.

## Non-Negotiable Architecture Rules

- PostgreSQL remains transactional truth; no silent CSV write fallback.
- Every schema change uses Alembic; startup never calls `metadata.create_all()`.
- Analytics remains batch-first.
- `src/operations/worker.py` remains the only worker and accepts only four cataloged operations.
- Notifications remain in-app only.
- Service boundaries own lifecycle/stock rules; routes/frontends never mutate models/balances directly.
- Work-order completion/verification never resolves a ticket or silently changes stock.
- Qdrant is only for controlled document retrieval.
- LLM output is never executed or persisted as authoritative business state.
- Human authorized users remain responsible for safety and final decisions.

## Fresh Local Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dashboard,dev,rag,postgres]"
npm --prefix frontend ci
Copy-Item .env.example .env
docker compose up -d postgres qdrant
python -m alembic upgrade head
python -m src.ingestion.load_data
python -m src.rag.index_documents
python -m src.security.cli seed-demo-users
```

Then start API, frontend, and optionally worker with the commands in README/operations runbook.

## Onboarding Path

### First 30 minutes

1. Read this map, [`architecture.md`](architecture.md), and
   [`repository-transaction-map.md`](repository-transaction-map.md).
2. Inspect one end-to-end path: API route → application service → repository →
   audit/outbox, and note which layer owns each decision.
3. Activate the virtual environment and run the isolated PostgreSQL helper
   (`.\scripts\test-postgres.ps1 -Action test -Keep`) only against its fixed
   `_test` database. The helper uses host port `15433`; see
   [`testing-postgresql.md`](testing-postgresql.md).

### First half day

1. Reproduce the local API/frontend startup and read the matching bounded
   context document (`ticket_operations.md`, `work_order_business_process.md`,
   or `inventory_business_process.md`).
2. Trace one read path and one mutation path, including expected-version,
   idempotency, audit, outbox, and rollback behavior.
3. Run the relevant focused tests, then the full backend and lint commands from
   the verification checklist. Record failures as pre-existing, change-caused,
   or infrastructure-blocked; never infer a pass from an old checkpoint.

### First safe change

Start with the read-only plan-filter example above. Keep the change behind the
existing service/repository contracts, add tests before broad refactoring, and
verify that no transaction owner or compatibility import moved. A reviewer
should be able to identify the changed capability and its unchanged owner from
the diff alone.

## Full Development Compose

```powershell
docker compose up --build
docker compose --profile worker up --build
```

The main Compose migration service applies Alembic before API startup. Seed/import, identity creation, maintenance/inventory seed, and document indexing remain explicit commands to prevent hidden data mutations.

The stricter intended-pilot topology is `docker-compose.pilot.yml`; do not treat the development Compose file as production configuration.

## LLM Operations

Generation is off by default. To enable:

1. Approve provider/model and data handling.
2. Configure `LLM_ENABLED`, `LLM_PROVIDER`, `LLM_MODEL`, and `LLM_BASE_URL`.
3. Inject `LLM_API_KEY` only when required.
4. Run `python -m src.llm.smoke`.
5. Run `python -m evaluation.run_evaluation --backend configured-qdrant --mode rag-llm`.
6. Review fallback rate and every small-dataset answer before demo/pilot.

Ollama should be preferred for offline/local defense. No model is pinned because hardware and approved model choice are owner decisions; record the selected model/version in release evidence.

## Knowledge Corpus

The current source is `data/raw/documents.csv`. Re-index with:

```powershell
python -m src.rag.index_documents
```

Stable chunk/point IDs prevent duplicates for unchanged documents. Rebuild/recreate is an explicit operator action. There is no web KB admin or persisted active/superseded lifecycle; do not accept arbitrary uploads through a new route without a full metadata, storage, audit, and migration design.

## Verification Checklist

```powershell
python -m compileall -q src tests evaluation
python -m pytest
python -m ruff check .
python -m alembic heads
docker compose config --quiet
docker compose --env-file .env.pilot.example -f docker-compose.pilot.yml config --quiet
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
python -m evaluation.run_evaluation --mode deterministic
python -m evaluation.run_evaluation --backend configured-qdrant --mode rag-llm
```

## Pre-Review Checklist

- [ ] The change names one capability owner and does not move business rules
      into a route, serializer, React component, or compatibility facade.
- [ ] Public API paths, schemas, historical imports, RBAC checks, and frontend
      compatibility re-exports are unchanged or covered by an explicit contract
      test.
- [ ] The transaction owner, session/lock order, optimistic-version or
      idempotency boundary, audit coupling, and outbox coupling are written in
      the diff or the relevant transaction map.
- [ ] Any PostgreSQL schema change has an Alembic revision; model changes have
      a metadata snapshot/import-registration check; startup still has no
      `metadata.create_all()`.
- [ ] Rejection paths prove no partial mutation, and append-only history remains
      append-only. Attachments still use authorized generated storage keys and
      do not expose paths or bytes in audit records.
- [ ] Targeted tests for the changed capability were run. PostgreSQL tests use
      `.\scripts\test-postgres.ps1` on port `15433` and the dedicated
      `maintenance_copilot_test` database.
- [ ] `python -m pytest`, `python -m ruff check .`, and any applicable frontend,
      compile, migration, or contract checks have a recorded result. Do not
      copy a historical checkpoint into the current review.
- [ ] The diff is whitespace/secret-clean, documentation reflects current
      ownership, and known limitations or blocked infrastructure are called out.

PostgreSQL integration (use the isolated helper and fixed port `15433`):

```powershell
.\scripts\test-postgres.ps1 -Action reset
.\scripts\test-postgres.ps1 -Action test -Keep
```

Use only a dedicated database whose name ends in `_test`. Follow the repository’s actual test-database helper/commands; never run destructive setup against demo data.

The helper provisions `maintenance_copilot_test` on loopback port `15433`, runs
Alembic and the PostgreSQL selection, and can take `-Full` for the complete
suite. See [`testing-postgresql.md`](testing-postgresql.md) for safety
validation and manual `TEST_DATABASE_URL` rules.

Authenticated graduation rehearsal:

```powershell
$env:TEST_DATABASE_URL = "<protected PostgreSQL URL ending _test>"
$env:DEMO_USER_PASSWORD = "<temporary test password>"
python -m src.reliability.graduation_demo_smoke
```

The runner verifies API database fingerprint attestation before login and never persists credentials or tokens. See [Runtime verification](RUNTIME_VERIFICATION.md) for the executed commands and results.

## Backup, Recovery, And Release

See:

- [Operations runbook](operations_runbook.md)
- [Backup and restore](backup_restore.md)
- [Failure recovery](failure_recovery.md)
- [Pilot deployment](pilot_deployment.md)
- [Secret rotation](pilot_secret_rotation.md)
- [Operational ownership](operational_ownership.md)
- [Known limitations](known_limitations_acceptance.md)

Do not mark a real pilot GO based only on local/synthetic tests. Use the three-gate PM9 record and owner approvals.

## Monitoring And Troubleshooting

- `/health/live`: process liveness.
- `/health/ready`: primary storage/migration readiness.
- `/health/worker`: persisted heartbeat readiness.
- Operations pages/API: job execution, dead letters, outbox, notifications, metrics.
- Provider smoke: fixed structured output only, without maintenance/user data.
- Copilot fallback reasons: fixed categories; do not enable raw prompt/response logging during incident diagnosis.

Troubleshooting: [troubleshooting.md](troubleshooting.md).

## Known Handover Risks

| Severity | Risk | Required owner action |
|---|---|---|
| High | No approved production/pilot provider and data contract | Select local/hosted provider, retention/residency, key owner |
| High | PostgreSQL/attachments single-node and incomplete real restore evidence | Approve backup target, cadence, paired restore rehearsal |
| High | No SSO/MFA/shared rate limit/malware scanning | Accept internal-only boundary or fund production controls |
| High | No real corpus/model accuracy evidence | Supply approved documents and human-labeled evaluation |
| High | Next-owned PostCSS/Sharp advisories remain in the production tree | Track a stable Next release supporting patched dependency floors; do not force downgrade/overrides |
| Medium | Python/RAG Docker image is 9.16 GB and slow to unpack on Docker Desktop | Split/build-cache dependencies and measure a smaller supported runtime image without removing local embeddings |
| Medium | Oversized service/repository/frontend modules | Refactor incrementally along bounded contexts with tests |
| Medium | No central logs/alerts/on-call | Assign operations owner and platform |
| Medium | KB lifecycle is CLI/CSV-only | Design persisted document registry before admin upload UI |
| Medium | Citation validation is structural, not semantic | Add human claim/span judgments; keep human verification |

## First Week For A New Team

1. Run all local checks and reproduce the deterministic evaluation.
2. Run the dedicated PostgreSQL helper documented above when Docker is
   available; record it as infrastructure-blocked otherwise rather than
   reusing an older test count. Treat authenticated graduation smoke as a
   separate protected rehearsal.
3. Walk through asset → ticket → work order → inventory → explicit resolve.
4. Read architecture, data contract, business process, RAG/LLM design, and security review.
5. Decide provider/model and run a privacy-approved grounded evaluation.
6. Assign company owner/security/incident/support/backup responsibilities.
7. Only then schedule an intended-host rehearsal.

## Acceptance Sign-Off

Technical handover should record commit/tag, Alembic head, frontend lockfile hash, selected provider/model, test counts, skipped/external limitations, backup evidence, and named owners. A technical document cannot substitute for company authorization or production risk acceptance.

## Historical Refactoring Checkpoints

The dated checkpoint records below preserve handover evidence from earlier
worktrees. Their “next phase,” line counts, and validation totals are historical
unless the current-state sections above or below explicitly repeat them.

## Refactoring continuation checkpoint — 2026-08-06

The backend inventory is recorded in
[`backend-structural-inventory.md`](backend-structural-inventory.md). Phase A
moved the immutable authenticated principal to `src/security/principal.py`;
`src.security.service.CurrentUser` remains an identity-preserving historical
import. Phase B moved repository contracts into the bounded package
`src/repositories/contracts/` and preserved the historical import facade,
including new ticket/operations protocols. Focused validation passed (`14
passed, 43 skipped, 1 warning`) and PostgreSQL validation passed (`73 passed,
390 deselected, 1 warning`). Phase C moved concrete service wiring into
`src/composition/` and preserved legacy builder/dependency identities. No
transaction-heavy stock family, API, schema, frontend, or storage behavior was
changed. Phase D extracted inventory catalogue and stock-location orchestration
into `application/catalogue_mutation_service.py`; focused inventory validation
passed (`3 passed, 10 skipped, 1 warning`) and PostgreSQL validation passed
(`73 passed, 390 deselected, 1 warning`). The next safe phase is ticket
application-service decomposition.
Phase E extracted SLA calendar/policy administration into
`ticket_management/application/sla_service.py`; focused ticket validation
passed (`20 passed, 8 skipped, 1 warning`) and PostgreSQL validation passed
after correcting and rechecking one extraction call-shape defect (`73 passed,
390 deselected, 1 warning`). Ticket lifecycle, SLA snapshot, escalation, and
comment transaction families remain retained. The next safe phase is
maintenance application-service decomposition.
Phase F extracted checklist-template listing, immutable versioning, and archive
orchestration into `maintenance_management/application/template_service.py`;
focused maintenance validation passed (`15 passed, 9 skipped, 1 warning`) and
PostgreSQL validation passed (`73 passed, 390 deselected, 1 warning`). Plan,
generation, work-order, checklist-completion, verification, and evidence
transaction families remain retained. The next safe phase is security service
decomposition.

Phase G now includes an explicit ORM-free security transaction contract and one
complete transaction-family extraction. `src/security/identity.py` owns
identity projections; `src/security/errors.py` owns shared security errors;
`src/security/session_state.py` owns the pure access-state predicate; and
`src/security/contracts.py` plus `src/security/session_service.py` own the
single-session logout port and complete SQLAlchemy-backed transaction.
`src.security.service` remains the historical facade. Contract and PostgreSQL
tests protect one-session ownership, audit atomicity, idempotency, and facade
compatibility.

AuthService remains intact for login, access authentication, refresh rotation,
password changes, user administration, and their audit orchestration. No token,
password, session, audit, API, environment, schema, or frontend behavior
changed outside the selected complete logout family. Refresh rotation is
characterized in [`security-refresh-rotation-contract.md`](security-refresh-rotation-contract.md)
and remains in `AuthService` because its complete token/session family shares
the login session-result factory. The combined security characterization/
contract suite passed `14 passed`; the isolated PostgreSQL security suite passed
`13 passed`. Full backend validation passed (`404 passed, 86 skipped, 1
warning`); the final isolated PostgreSQL workflow passed (`86 passed, 404
deselected, 1 warning`). Ruff/compileall passed, and Alembic current/heads/
check remain clean at `20260726_0008` with no new operations.
The next single bounded backend phase requires a separately approved complete
transaction-family contract.

## Handover checkpoint — 2026-08-08

Recovered and validated: `AuditContext` storage-neutral boundary,
`TicketReferenceKind`, explicit PM7 pool/release providers,
composition-owned builders, RAG/Copilot direction cleanup, neutral reliability
dotenv parsing, `TicketAssignmentService`, and `TicketIntakeService`.
Compatibility imports remain available. Intake leaves `create_ticket` as the
sole atomic repository operation. Full unit and isolated PostgreSQL validation
are green; the only warning is the existing FastAPI TestClient/httpx
deprecation. Next safe phase: characterize ticket lifecycle before moving its
state-transition orchestration.

## Handover checkpoint - 2026-08-08 lifecycle

Ticket lifecycle characterization is complete and the eight named rich actions
now delegate to src/ticket_management/application/lifecycle_service.py.
The contract records exact transitions, permission/technician ownership rules,
validation order, snapshotted SLA pause/resume and reopen occurrence behavior,
audit metadata, and the selected held/resumed outbox mappings. The
PostgresTicketRepository.mutate_ticket session, row locks, flush/commit,
rollback, exception mapping, audit persistence, and outbox enqueue remain the
transaction owner. The compatibility facade, API routes, schemas, RBAC,
database metadata, and frontend are unchanged. The exactly next bounded phase
is separately approved ticket SLA-runtime characterization; escalation remains
deferred.

Lifecycle validation at handover: 8 dedicated characterization tests passed,
the focused ticket selection passed 12, full backend passed 421
with 87 skipped, and isolated PostgreSQL passed 87 with 421 deselected. Ruff,
compileall, Alembic 20260726_0008 current/heads/check, Compose config, and
diff checks passed. The only warning is the existing FastAPI/Starlette-httpx
deprecation.

## Current Refactor Status — 2026-08-09

Maintenance application decomposition is complete for the current public
surface. Capability services now own preventive-plan commands, work-order
planning, lifecycle/checklists, completion/verification, preventive generation,
calendar/metrics reporting, linked-ticket reads, templates, evidence, and
primitive queries. The historical `MaintenancePlanningService`, all 34 method
signatures, dependency-override seam, and seven formerly importable module
bindings remain available. PostgreSQL still owns every session, row lock,
optimistic version, occurrence uniqueness boundary, maintenance-log/asset-date
write, audit/outbox write, commit/rollback, and exception map.

The bounded reliability phases now extract seven manifest
capabilities: the closed deployment job catalog in
`src/reliability/pilot_contract/deployment_manifest/jobs.py` and health endpoint declarations
in `deployment_manifest/health.py`, plus declared
environment names and secret flags in `deployment_manifest/environment.py`, the
allowed-root/logical-path contract in `deployment_manifest/storage.py`, and checked-in
Compose/Dockerfile/package binding in `deployment_manifest/repository.py`. Artifact
identity/release/version/image declarations live in `deployment_manifest/artifacts.py`;
closed service/port/volume topology is orchestrated by `deployment_manifest/topology.py`. `manifest.py`
is the 31-line orchestrator and preserves the private import seams. None
controls runtime environment values, the PM7 catalog, worker, repository,
leases, retries, notifications, subprocesses, or release decisions. Storage
validation preserves the existing path-resolution containment check but neither
reads file contents nor mutates filesystem state.
Runtime environment validation is now a 27-line facade over security/database,
network, identity, bounded runtime settings, and storage-path capabilities. The
environment remains injected at the public boundary; only storage validation
resolves host paths, and no capability reads `os.environ` directly.

Release-record validation is now a 163-line ordered facade over identity,
evidence, gates, risks, and governance capability modules. Observation and
reachability remain in `release.py`; the extracted validators are deterministic
and non-transactional, and the historical private binding and finding order are
preserved.

Operator reliability drills are decomposed behind the 65-line historical
`src/reliability/drills.py` facade. `disk_capacity.py` owns injected threshold
classification and cycle deduplication; `backup_artifacts.py` owns the complete
immutable backup publication/index/retention filesystem boundary;
`attachment_archives.py` owns bounded assessment/archive/inspection/restore;
`artifact_io.py` owns their already-shared durability primitives. Public imports
and the two existing private failure-injection bindings remain compatible. No
database transaction, attachment metadata, worker state, audit, or outbox owner
changed.

`load_harness.py` is an 81-line historical import/CLI facade over
`src/reliability/load/`. `profile_workflow.py` retains the complete profile
scheduling, telemetry, deadline, cancellation, and thread-pool boundary;
`step_workflow.py` retains the complete staged-load, monitor, stop-policy, and
stage-timeout boundary. Request contracts, HTTP sampling, execution limits,
report projection/storage, safety, telemetry, and CLI wiring have direct owners.
No HTTP order, stop order, or side-effect order changed.

`post_start_validation.py` is a 33-line historical facade. Under
`src/reliability/post_start/`, preflight, environment reads, report contracts,
HTTP/session helpers, response contracts, evidence storage, and CLI wiring have
direct owners. `runner.py` retains ordered authenticated execution and
unconditional three-client logout/revocation cleanup. PostgreSQL mutation
families remain in their existing repositories, with source-level ownership
guards covering the ten highest-risk commands.

Validation at the 2026-08-09 checkpoint: runtime environment passed 73 tests against the
original implementation and 80 after extraction; release-record validation
passed 41 against the original and 48 after extraction; combined
pilot/deployment/mutation-rehearsal passed 572; the complete reliability/PM9
selection passed 762 with 11 PostgreSQL-gated skips; architecture boundaries
passed 7; full backend passed 1107 with 87 skipped and 1 existing warning. Ruff,
changed-file formatting, compileall, AST equivalence, import identity, CLI help,
documentation links, and diff checks passed. Final database proof passed 87
PostgreSQL tests with 1107 deselected; Alembic is clean at `20260726_0008`.
Frontend typecheck, ESLint, 23 files/137 tests, and a 32-page production build
passed. All three Compose configurations passed.

Those results are historical evidence; the 2026-08-10 package-organization
checkpoint below is authoritative for the current dirty worktree.

## Historical checkpoint — ticket SLA runtime — 2026-08-08

SLA administration, runtime, lifecycle, escalation, and persistence are explicitly separated: runtime is `TicketSlaRuntimeService`; named transitions are `TicketLifecycleService`; configuration is `TicketSlaAdministrationService`; escalation remains in `TicketWorkflowService`; and `PostgresTicketRepository` owns rows, locks, audit/outbox, and transactions. No scheduler or automatic escalation was added.

Ticket application completion: escalation now lives in `TicketEscalationService`, while `TicketWorkflowService` remains the stable compatibility facade. The flow is API/PM7 → composition or job runner → capability service → `TicketRepository` contract → PostgreSQL implementation. Escalation is bounded to active statuses, SLA due-soon/breached clocks, critical priority, and repeated reopen; execution is idempotent at the database uniqueness boundary. At that historical checkpoint, maintenance was the recommended next macro phase; the current status above supersedes it.

## Package-organization handover — 2026-08-10

Authoritative worktree identity at final validation:

- branch `refactor/backend-ticket-application`;
- HEAD `9b77a50bf4ecce77f0364945ce2d5f670cb6a1cf`;
- staged files: 0;
- tracked status entries: 35, including 5 expected deletions;
- untracked files: 149, including prior refactor work, the capability
  packages/tests, and three narrow corrective compatibility test modules;
- no commit, push, reset, revert, checkout, or branch change was performed.

Relevant production and test tree:

```text
src/reliability/
├── drills.py                         # historical facade
├── load_harness.py                   # historical facade + CLI bridge
├── profiles.py                       # historical facade
├── post_start_validation.py          # historical facade + CLI bridge
├── operator_drills/
│   ├── artifact_io.py
│   ├── attachment_archives.py
│   ├── backup_artifacts.py
│   ├── contracts.py
│   └── disk_capacity.py
├── load/
│   ├── cli.py, contracts.py, execution_limits.py
│   ├── http_sampling.py, metrics.py, profiles.py
│   ├── profile_reporting.py, profile_workflow.py
│   ├── report_storage.py, reporting.py, request_contracts.py
│   └── safety.py, step_workflow.py, telemetry.py
├── post_start/
│   ├── cli.py, contracts.py, environment.py, evidence_storage.py
│   ├── http_session.py, preflight.py, response_contracts.py
│   └── runner.py
└── pilot_contract/
    ├── manifest.py, environment.py, release.py, runtime.py, ownership.py
    ├── findings.py, document_shapes.py, document_values.py
    ├── document_safety.py, path_contracts.py, evidence_values.py
    ├── deployment_manifest/
    │   ├── artifacts.py, environment.py, health.py, jobs.py
    │   ├── repository.py, storage.py, topology.py
    │   └── services.py, ports.py, volumes.py
    ├── runtime_environment/{identity,integers,network,security,settings,storage}.py
    ├── release_record/{identity,evidence,gates,risks,governance}.py
    ├── runtime_policy/{settings,retry,recovery}.py
    └── operational_governance/
        ├── assignments.py, support_readiness.py, escalation_path.py
        ├── ownership_record.py, limitation_entry.py
        ├── limitations_record.py, state.py
        └── __init__.py

tests/reliability/
├── load/                # profile, step, stop, safety, reporting, telemetry
├── operator_drills/     # disk, backup, attachment protocols
├── pilot_contract/      # manifest/runtime/release/governance dimensions
└── post_start/          # preflight and authenticated runner
```

Exact implementation move map:

| Previous owner/path | Final owner/path | Compatibility retained |
|---|---|---|
| `pilot_contract/artifact_declarations.py` | `pilot_contract/deployment_manifest/artifacts.py` | `manifest.py` private binding |
| `environment_declarations.py` | `deployment_manifest/environment.py` | `manifest.py` order |
| `health_endpoints.py` | `deployment_manifest/health.py` | `manifest.py` order |
| `job_catalog.py` | `deployment_manifest/jobs.py` | `manifest.py` order |
| `repository_contract.py` | `deployment_manifest/repository.py` | `manifest.py` order |
| `storage_declarations.py` | `deployment_manifest/storage.py` | `manifest.py` order |
| `service_topology.py` | `deployment_manifest/topology.py` plus `services.py`, `ports.py`, `volumes.py` | `_validate_service_topology` remains the ordered binding |
| `environment_{identity,network,runtime_settings,security,storage}.py` | `runtime_environment/{identity,network,settings,security,storage}.py` | `environment.py` facade/order |
| `release_record_{identity,evidence,gates,risks,governance}.py` | `release_record/{identity,evidence,gates,risks,governance}.py` | `release.py` facade/order |
| `pilot_contract/support.py` | findings, document shape/value/safety, path, evidence, runtime integer, and governance-state owners | no external historical support import existed; module removed |
| `pilot_contract/runtime.py` God function | `runtime_policy/{settings,retry,recovery}.py` | 21-line ordered `runtime.py` facade |
| `pilot_contract/ownership.py` God functions | `operational_governance/` capability modules | 6-line `ownership.py` facade |
| root drill implementation modules | `operator_drills/` | 65-line `drills.py`, including failure-injection bindings |
| root `load_*` modules and `profiles.py` implementation | `load/` | `profiles.py` facade |
| `load_harness.py` implementation | `load/profile_workflow.py`, `step_workflow.py`, request/HTTP/report/CLI modules | 81-line `load_harness.py`; all relied-upon aliases remain |
| `post_start_preflight.py` and `post_start_validation.py` implementation | `post_start/preflight.py`, `runner.py`, client/contract/evidence/environment/CLI modules | 33-line historical facade |
| flat reliability tests, including four tracked PM9 suites | `tests/reliability/{pilot_contract,load,operator_drills,post_start}/` | collection preserved; oversized suites split by contract dimension |

Side-effect ownership after the move:

- load profile and step workflows still own their complete scheduling,
  deadline, cancellation, telemetry, and cleanup loops;
- post-start runner still owns exact check order and unconditional session
  revocation/client cleanup;
- backup and attachment modules still own their complete filesystem atomicity,
  verification, staging, and cleanup protocols;
- pilot validators remain pure finding accumulators;
- PostgreSQL transaction owners are unchanged. Static AST hashes and real
  PostgreSQL tests prove that no executable session/lock/idempotency/audit/
  outbox/commit/rollback behavior moved.

Characterization checkpoints:

| Phase | Before | After |
|---|---:|---:|
| recursive architecture + transaction guard | 9 | 14 after Phase 1; final 21 (19 architecture + 2 transaction) |
| pilot helper ownership | 545 passed | 545 passed; 559 with then-current guards after `support.py` removal |
| runtime/governance ordered characterization | 3 passed | 3 passed; complete pilot/guards later 564 passed |
| operator-drill package | 67 passed | 79 passed with then-current guards |
| load package move | 88 passed | 100 passed with then-current guards |
| load internal ownership | 90 passed | 90 passed; broader load/mutation/rotation/architecture 101 passed |
| post-start package move | 51 passed | 63 passed with then-current guards |
| post-start internal ownership | 44 passed | 44 passed; broader deployment/post-start/architecture 63 passed |
| reliability test organization | 719 collected | 719 move-preservation baseline plus 8 corrective cases; 727 passed |
| topology service/port/volume split | 98 passed | 98 passed |

Final validation matrix:

| Surface | Result | Classification |
|---|---|---|
| full backend | 1,130 passed, 87 skipped, 1 warning | passed |
| isolated PostgreSQL | 87 passed, 1,130 deselected, 1 warning | passed against `maintenance_copilot_test` |
| Alembic upgrade/heads/current/check | `20260726_0008`; no new upgrade operations | passed |
| reliability/PM9 selection | 776 passed, 1 warning | passed |
| reliability capability tree | 727 passed | passed |
| architecture boundaries | 19 passed | passed |
| transaction ownership | 2 passed | passed |
| documentation links | 1 passed | passed |
| Ruff lint | repository-wide pass | passed |
| Ruff format | 165 current changed-scope files pass | passed; four protected comment-only transaction repositories retain pre-existing format and were excluded to avoid executable churn |
| compileall | `src` and `tests` pass | passed |
| CLI/import smoke | pilot contract, load harness, post-start, drill/profile facades pass | passed |
| Compose | development, test, and pilot-with-documented-env parse | passed |
| frontend | typecheck, ESLint, 23 files/137 tests, 32-route build | passed |
| `git diff --check` | clean | passed |

The only warning is the pre-existing FastAPI/Starlette `httpx` deprecation.
The first pilot Compose invocation omitted the required env file and failed
closed; the documented `--env-file .env.pilot.example` command passed. No
foreground command timed out and no infrastructure surface remained blocked.

Narrow corrective review findings are closed without reopening the refactor:

- `load_harness.py` identity-re-exports `PROFILES`,
  `PM9_STEP_LOAD_PROFILES`, `ReliabilityProfile`, and `StepLoadProfile`;
  `post_start_validation.py` identity-re-exports `CheckStatus`, `OverallStatus`,
  and `EnvironmentFileError`. Explicit and wildcard imports plus CLI identity
  are characterized.
- Architecture import analysis now derives package identity from each path,
  resolves Python relative-import levels and alias submodules only when they are
  actual repository modules, and covers `runtime.py` and `ownership.py` as
  historical facades. Synthetic relative-cycle, parent-facade, sibling,
  acyclic, and absolute-import cases pass; the real graph is acyclic.
- Canonical repository protocols are documented at
  `src/repositories/contracts/`, with `src.repositories.contracts` retained as
  the Python import surface. Stateful workflow physical counts use one
  `Get-Content` line-count convention.
- Moved classes retain canonical capability-package `__module__` values.
  Historical facade attributes and pickle global lookup resolve to those same
  class objects; no duplicate definitions or metadata rewriting were added.

Final verdict: structural refactor complete. The remaining large/stateful files
are evidence-backed cohesive boundaries listed in
`docs/backend-structural-inventory.md`; future moves require whole-workflow or
whole-transaction characterization rather than another line-count split.

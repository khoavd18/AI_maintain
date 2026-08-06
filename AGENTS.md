# Repository Guardrails

These rules apply to future agent work in this repository.

## Product Boundary

AI Maintenance Copilot is a batch analytics and AI decision-support layer with focused asset lifecycle, ticket, preventive-plan, work-order, maintenance-log, and spare-parts stock-control workflows. PostgreSQL is the transactional source of truth, but the product is not a complete CMMS, autonomous maintenance controller, procurement suite, or production-ready enterprise platform.

Human facility managers and technicians remain responsible for prioritization, safety checks, field inspection, maintenance execution, and final decisions. Never describe a score or recommendation as an automatic decision.

## Canonical Architecture

- Keep PostgreSQL primary for transactional assets, tickets, preventive plans, checklist templates, work orders, maintenance logs, spare-part master data, stock positions, reservations, and immutable inventory movements.
- Use Alembic for every PostgreSQL schema change. Do not call `metadata.create_all()` in product startup or production-mode commands.
- Keep CSV for synthetic generation, explicit seed/import, database-to-analytics snapshots, canonical demo reset, and batch analytics contracts.
- At the snapshot boundary, preserve the validated legacy interval contract: project asset/log `next_maintenance_date` from `last_maintenance_date` or `maintenance_date` plus `maintenance_interval_days`. Keep real plan-derived dates in PostgreSQL plans/work orders; do not weaken legacy analytics validation.
- Keep analytics batch-first. PostgreSQL transactional writes must not trigger or imitate immediate Risk Score/KPI recalculation.
- Keep `src/operations/worker.py` as the only background worker and
  `src/operations/domain.py` as the closed scheduled-job and notification-event
  catalog. PostgreSQL job, lease, outbox, delivery-attempt, notification, and
  heartbeat records are authoritative; never replace them with in-memory queue
  state.
- Background work may invoke only the four existing PM7 operations:
  preventive generation, ticket SLA/escalation evaluation, batch analytics
  refresh, and inventory reorder detection. Do not accept arbitrary cron,
  Python, shell, SQL, module, function, or workflow definitions.
- Write selected outbox events in the same PostgreSQL transaction as their
  business mutation. Claim jobs and outbox events with bounded leases and
  concurrency-safe row locking; retries and dead-letter state must remain
  durable and operator-visible.
- Keep notifications in-app only. Notification payloads must use the explicit
  allow-listed catalog, minimum business context, owner-isolated reads, and
  existing RBAC. Do not add email, SMS, push, webhooks, or external delivery.
- Keep FastAPI as the serving boundary. Streamlit must consume FastAPI and must not read raw or processed CSV files directly.
- Keep `src/api/routes.py` as the compatibility facade for the focused routers under `src/api/routers/`; preserve its dependency override and public import seams.
- Keep feature-specific Next.js code under `frontend/src/features/`. The legacy files under `frontend/src/components/` for inventory, work-order parts, ticket detail, and SLA administration are compatibility re-exports; preserve their imports while extracting internals.
- Select storage in the service/repository factory, never in route functions. Do not silently fall back from unavailable PostgreSQL to mutable CSV storage.
- Keep the CSV repository only as an explicit compatibility adapter for isolated tests and demo fixtures.
- Use Qdrant only for RAG document retrieval.
- Keep RAG application code dependent on the narrow `AssetContextProvider` port in `src/rag/adapters/`; select the concrete adapter in the outer application composition root. Do not import `src.api.services` from `src/rag/copilot.py`.
- Do not add real-time ingestion, streaming, or event-processing infrastructure.

## Preventive Maintenance And Work Orders

- Keep `src/maintenance_management/service.py` as the canonical business boundary, `src/maintenance_management/recurrence.py` as the only recurrence implementation, and `src/repositories/postgres_maintenance.py` as the PostgreSQL implementation. Routes and frontends must not manipulate SQLAlchemy models directly.
- Keep `PreventiveMaintenancePlan`, `WorkOrder`, `ChecklistTemplate`, `WorkOrderChecklistItem`, `MaintenanceLog`, and `Ticket` as separate concepts. Never merge them into a generic maintenance record.
- Support only bounded interval recurrence in days, weeks, months, and years. Due dates are local business dates under an explicit IANA timezone; execution timestamps are UTC. Overdue is derived from due date and grace period, never an editable state.
- Preserve the documented month-end anchor, leap-year behavior, 366-day catch-up bound, and paused-backlog skip policy. Schedule changes affect only ungenerated occurrences.
- Generate preventive work orders only through the explicit service invoked by
  protected API/CLI commands or the canonical PM7 worker. Do not generate at
  application startup, add another scheduler loop, or duplicate generation
  logic.
- Keep work-order numbers and plan occurrences concurrency-safe and idempotent. A generated `(preventive_plan_id, due_date)` pair is unique.
- Keep checklist template versions immutable. Work orders execute a snapshot, so later versions or archived templates never alter history.
- Enforce the canonical work-order state machine in the service. Completion creates or links exactly one `MaintenanceLog`; independent verification by a different authorized actor updates asset maintenance dates. Verified records are immutable without a separately authorized future correction design.
- Never resolve a ticket merely because a work order was created, completed, or verified. Ticket resolution remains an explicit authorized human action.
- Aggregate the legacy asset `next_maintenance_date` as the earliest due date among active plans, with the documented legacy fallback. Never present one asset date as a replacement for plan-specific schedules.
- Reuse `AttachmentStorage` for work-order evidence and preserve MIME/signature/extension checks, size bounds, generated keys, checksums, authorized download, and soft deletion. Do not expose storage paths or file bodies in audit records.

## Spare Parts And Inventory

- Keep `src/inventory_management/service.py` as the only inventory business boundary and `src/repositories/postgres_inventory.py` as the PostgreSQL implementation. Routes and frontends must never manipulate inventory models or balances directly.
- Keep `src/inventory_management/routes` as the inventory route package and preserve `src.inventory_management.routes` as its facade; do not move inventory business rules into route modules.
- Keep parts, assets, tickets, work orders, maintenance logs, requirements, reservations, issues, consumptions, returns, and movements as distinct concepts. Historical `MaintenanceLog.parts_replaced` text is not an inventory ledger.
- Preserve `available = on_hand - reserved`. Clients may request named actions but must never submit calculated balances, stock states, or reorder suggestions.
- Keep `InventoryMovement`, `StockReservationEvent`, `WorkOrderPartIssue`, `WorkOrderPartConsumption`, and `WorkOrderPartReturn` append-only. Corrections use a new authorized movement; do not update or delete history.
- Use row locks, database constraints, and one transaction for reserve, issue, return, transfer, and adjustment. Reject negative on-hand, negative available, and reservation oversubscription.
- Keep reservation, issue, consumption, and return explicit. Work-order completion/verification must not silently issue, consume, return, release, or reserve stock.
- Require caller-stable idempotency keys for stock-changing commands. Replaying the same command returns its committed result; reusing a key with a different payload is a conflict.
- Keep transfer-out and transfer-in atomic. Never expose a generic balance PATCH endpoint.
- Archived parts and inactive/archived stock locations remain visible in history but cannot be used for new receipt, reservation, issue, or transfer operations except an explicitly supported return to a valid active location.
- Derive low-stock state and reorder suggestion on the server from effective
  part/location thresholds and available quantity. PM7 may create only the
  deduplicated in-app low-stock notification from a persisted detection cycle;
  do not create purchase orders, supplier actions, external notifications, or
  inventory optimization.
- Reuse `AttachmentStorage` for inventory evidence and preserve authorization, signature/MIME/extension validation, generated keys, checksums, soft deletion, and path secrecy.

## Ticket Operations And SLA

- Keep `src/ticket_management/service.py` as the canonical ticket business boundary, `src/ticket_management/sla.py` as the only business-calendar implementation, and `src/repositories/postgres_tickets.py` as the PostgreSQL implementation. Routes and frontends must not mutate ticket models directly.
- Preserve the rich code-level lifecycle `open`, `assigned`, `in_progress`, `waiting`, `resolved`, `closed`, `cancelled`, and `reopened`. Every transition must use its named service action; do not add a generic status patch to the rich API.
- Keep the legacy `/tickets` API as a narrow compatibility adapter with its original Vietnamese values. Do not make legacy projections authoritative for the rich lifecycle.
- Calculate priority only from the backend `impact x urgency` matrix in `src/ticket_management/domain.py`. Frontends may preview the server result but must not maintain an independent matrix or submit arbitrary priority.
- Derive first-response and resolution SLA states from policy snapshots, timestamps, pause intervals, and the snapshotted business calendar. Never add a writable breach flag or recompute historical tickets from an edited policy/calendar.
- Keep working periods same-day, timezone-aware, non-overlapping, and explicitly versioned. Waiting pauses require a reason; reopen creates a new SLA occurrence without erasing prior events.
- Keep ticket comments, SLA events, and escalation events append-only. Preserve reporter PII redaction and visibility permissions; do not place reporter contact details in audit payloads.
- Evaluate escalation only through the explicit service used by API, CLI, and tests. Dry-run must not write; execution must remain idempotent through the `(ticket_id, rule_code, occurrence_number)` uniqueness boundary. Each rule code already identifies its clock where applicable.
- SLA/escalation evaluation may run only through the existing explicit API/CLI
  service or the canonical PM7 worker. It may create cataloged in-app
  notifications but must never add another hidden scheduler, email/SMS sender,
  or automatic ticket transition.
- Keep corrective work-order creation/linkage separate from ticket status. Work-order completion or verification never resolves or closes its source ticket.

## Asset Lifecycle And Files

- Keep `src/asset_management/service.py` as the canonical asset lifecycle boundary and `src/repositories/postgres_assets.py` as its PostgreSQL implementation. Do not move lifecycle or hierarchy rules into routes or the frontend.
- Keep lifecycle status separate from temporary operational status. Asset archive/restore must be explicit, versioned, audited, and non-destructive; do not add a normal asset hard-delete endpoint.
- Preserve the legacy analytics asset projection (`asset_type`, `location`, `criticality`, `status`, installation and maintenance dates) when extending the management profile.
- Keep locations hierarchical and archive-in-place. Reject self-parenting/cycles, and never delete assigned assets or their history when a location is archived.
- Store attachment metadata in PostgreSQL and bytes behind `AttachmentStorage`. Enforce allow-listed type/signature/extension, bounded size, generated storage keys, checksum validation, authorized download, and soft-delete audit. Never expose local paths.
- Asset QR codes may contain only the deterministic opaque lookup URL. QR lookup remains authenticated; QR is an identifier, not an authorization token. Keep the scan experience web-based and do not create a native mobile app.

## Canonical Analytics

Extend only these production paths:

- Feature engineering: `src/features/build_features.py`
- Anomaly detection: `src/models/anomaly_detection.py`
- Risk scoring: `src/risk/risk_scoring.py`
- Dashboard: `src/dashboard/app.py`
- RAG chunking: `src/rag/chunking.py`

Duplicate anomaly, risk, ingestion, sample-data, and dashboard wrappers were removed in the verified cleanup milestone. Do not recreate parallel implementations or compatibility entrypoints; extend only the canonical paths above.

## Scope Expansion Prohibited

Do not add or propose implementation work for the following areas unless the repository owner explicitly changes the MVP scope:

- suppliers, purchasing, purchase requisitions, purchase orders, or inventory optimization;
- accounting, general-ledger integration, or maintenance-cost reporting;
- resident mobile applications;
- technician mobile applications;
- vendor or contract management;
- real-time IoT streaming or live event processing;
- complex approval workflows;
- SSO, MFA, external identity providers, or enterprise IAM integration;
- any scheduler, job queue, workflow engine, or startup work-order generation
  outside the canonical PostgreSQL-backed PM7 worker and its closed four-job
  catalog;
- exact failure-time prediction.

Historical `parts_replaced` data may remain in maintenance logs, but it must not duplicate or replace canonical work-order inventory movements.

## Identity And Audit

- Keep local/internal-pilot authentication in `src/security/`; do not create a second role or permission model in Python or TypeScript.
- Enforce authorization in FastAPI. Hidden frontend controls are usability behavior, never the security boundary.
- Keep access tokens in frontend memory and refresh tokens in revocable HttpOnly cookies. Never store authentication tokens in `localStorage`.
- Keep successful business audit records in the same PostgreSQL transaction as their mutation. Audit records are append-only and must exclude passwords, tokens, cookies, Authorization headers, and secrets.
- Do not create users automatically at application startup. Bootstrap administrators and demo identities only through explicit CLI commands.

## Compatibility And Claims

- Preserve existing API contracts unless a task explicitly authorizes a change.
- Prefer additive, tested data-contract changes.
- Keep code, module, column, and API field names in English.
- Keep user-facing business values and operational explanations in Vietnamese.
- Clearly separate current behavior from future work in documentation.
- Do not claim production readiness, model accuracy, ROI, prevented failures, or business impact without measured evidence.
- Describe risk as prioritization, not a calibrated failure probability or guaranteed prediction.

## Verification

For repository changes, run the tests relevant to the modified area, then run:

```bash
python -m pytest
python -m ruff check .
```

Keep the product demo reproducible with local Docker PostgreSQL, migrations, and canonical CSV seed import.
Use a dedicated database whose name ends in `_test` for PostgreSQL integration tests. Never run destructive test setup against the developer/demo database.

## Current refactor verification workflow

The repository provides `docker-compose.test.yml` and
`scripts/test-postgres.ps1` for the isolated PostgreSQL integration database.
It is fixed to local port `15433` and database `maintenance_copilot_test`; the
database URL validator fails closed for non-loopback hosts, placeholders,
development credentials, missing `_test` suffixes, and mismatched
`DATABASE_URL`/`TEST_DATABASE_URL`. Follow [`docs/testing-postgresql.md`](docs/testing-postgresql.md).

Application-service capability ownership and the deliberate boundary around
transaction-heavy repository methods are documented in
[`docs/application-services.md`](docs/application-services.md). The current
repository transaction/session/lock/idempotency/audit/outbox map is in
[`docs/repository-transaction-map.md`](docs/repository-transaction-map.md).

The current backend decomposition keeps `src/database/models/` as the
canonical model package and preserves `src.database.models` imports. Real
PostgreSQL query implementations are composed under `src/repositories/postgres/`
for inventory, maintenance, tickets, and PM7 operations. Inventory catalogue
and evidence mutations are also composed there; transaction-heavy stock,
lifecycle, SLA, and outbox mutation families remain in their original
repositories until separately characterized. Pilot-contract redaction is
implemented in `src/reliability/pilot_contract/redaction.py`, with the
historical CLI and imports preserved by the package façade.

The reliability implementation is otherwise owned by the modules under
`src/reliability/pilot_contract/`; `legacy.py` is only the historical façade.
The API service package under `src/api/services/` separates snapshot loading,
analytics projections, legacy ticket/maintenance adapters, asset context, and
outer construction. `ProcessedDataService` remains the compatibility façade,
and `src/composition/copilot.py` is the shared Copilot composition root;
`src/application/copilot_factory.py` remains a historical import facade.
Canonical RAG orchestration is split into request analysis, retrieval/evidence,
and generation/citation collaborators under `src/rag/application/`. The four
current frontend hotspots preserve their old import paths while delegating to
feature-owned operation forms, mutation-context modules, Copilot response
views, and operations tables. Transaction-heavy repositories remain deferred.

Continuation checkpoint 2026-08-06: the complete backend structural inventory
is in [`docs/backend-structural-inventory.md`](docs/backend-structural-inventory.md).
Phase A extracted `CurrentUser` to `src/security/principal.py` and preserved
the historical `src.security.service.CurrentUser` import. Phase B moved the
repository contracts into `src/repositories/contracts/`, added ticket and
operations protocols, and preserved `src.repositories.contracts` imports.
Focused tests, isolated PostgreSQL tests, Ruff, compileall, and diff checks
passed. Phase C moved concrete wiring into `src/composition/` and preserved
legacy builders and resource lifetime. Phase D extracted inventory catalogue
master-data and stock-location orchestration while preserving repository
transaction owners. Phase E extracted ticket SLA calendar/policy
administration while preserving ticket lifecycle/SLA transaction owners. No
transaction-heavy stock or ticket lifecycle family, or frontend file, has been
changed. Phase F maintenance application-service decomposition is now complete
for checklist templates; maintenance work-order/generation families remain
retained. The next safe phase is Phase G security service decomposition.

Final continuation checkpoint 2026-08-06: full backend validation passed
(`390 passed, 73 skipped, 1 warning`), the latest isolated PostgreSQL run
passed (`73 passed, 390 deselected, 1 warning`), and Alembic current/head/check
remain clean at `20260726_0008`. Phase G was intentionally stopped after the
safe principal extraction because further AuthService splitting would cross
token, refresh-session, password, and audit sequencing without a dedicated
characterization map. Remaining large transaction/reliability files are listed
in `docs/backend-structural-inventory.md`.

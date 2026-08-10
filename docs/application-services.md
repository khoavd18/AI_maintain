# Application-service decomposition

Public service classes remain the compatibility and composition boundary:

- `InventoryManagementService` in `src/inventory_management/service.py`;
- `TicketWorkflowService` in `src/ticket_management/service.py`;
- `MaintenancePlanningService` in `src/maintenance_management/service.py`.

The extracted modules own cohesive application capabilities and receive the
existing repository, storage, authorization, and presentation callbacks. They
do not construct sessions, import FastAPI, or duplicate PostgreSQL mutations.

| Context | Extracted capabilities | Retained transaction-sensitive core |
|---|---|---|
| Inventory | catalogue master data, evidence, stock/balance queries | stock-changing operations whose repository call must remain one atomic transaction |
| Tickets | catalogue/priority preview, intake, assignment, lifecycle, SLA administration/runtime, escalation, comments, queue/detail queries | priority mutation, bootstrap, legacy adapters, and repository transaction methods |
| Maintenance | catalogue/recurrence preview, evidence, plan/work-order queries, linked-ticket reads, checklist templates, preventive-plan commands, work-order planning/lifecycle/completion, generation, and reporting | shared validation/compatibility helpers; all transaction-heavy repository methods remain PostgreSQL-owned |

The facade methods preserve public signatures and delegate to these modules.
Repository methods remain the transaction owner, including lock ordering,
idempotency claims, audit rows, outbox events, and commit/rollback behavior.

## Inventory capability map

The inventory service was characterized before the catalogue mutation
extraction. The public facade remains the compatibility/business boundary, but
the capability collaborator now owns the catalogue master-data orchestration.

| Capability | Public methods | Current owner | Transaction boundary |
|---|---|---|---|
| Catalogue reads/options | `options`, `list_categories`, `list_units`, `list_parts`, `get_part` | `application/catalogue_service.py` plus facade access checks | Repository reads only |
| Catalogue master data | `create_category`, `create_unit`, `create_part`, `update_part`, `change_part_lifecycle` | `application/catalogue_mutation_service.py` | Each repository command remains one transaction; facade owns compatibility signature |
| Stock locations/reorder config | `list_stock_locations`, `create_stock_location`, `update_stock_location`, `change_stock_location_lifecycle`, `upsert_reorder_configuration` | `application/catalogue_mutation_service.py` | Each repository command remains one transaction |
| Stock reads/metrics | `list_balances`, `list_movements`, `work_order_parts`, `metrics` | `application/stock_query_service.py` | Read-only repository sessions |
| Stock command family | `create_opening_balance`, `receive_stock`, `transfer_stock`, `adjust_stock` | `InventoryManagementService` facade | Retained until full lock/idempotency characterization |
| Reservation/issue family | `create_requirement`, `reserve_stock`, `close_reservation`, `replace_reservation`, `issue_stock`, `consume_issue`, `return_issue` | `InventoryManagementService` facade | Retained as atomic transaction-sensitive orchestration |
| Evidence | `list_evidence`, `upload_evidence`, `download_evidence`, `delete_evidence` | `application/evidence_service.py` | Metadata/audit repository transaction plus attachment byte cleanup contract |

The extraction passes repository access, permission, validation, lookup, and
clock callbacks into the collaborator. It does not create sessions, duplicate
validation rules, or split atomic inventory writes.

## Ticket capability map

| Capability | Public methods | Current owner | Transaction boundary |
|---|---|---|---|
| Ticket catalogue/priority | `options`, `priority_preview` | `application/catalogue_service.py` | Read-only/domain calculation |
| Intake | `intake` | `application/intake_service.py` | Application orchestration extracted; `create_ticket` remains one repository transaction |
| Assignment | `assign` | `application/assignment_service.py` | Application orchestration extracted; `mutate_ticket` remains one repository transaction |
| Lifecycle | acknowledge, start, hold, resume, resolve, close, reopen, cancel | ticket_management/application/lifecycle_service.py with TicketWorkflowService facade delegation | Application orchestration extracted; mutate_ticket remains one repository transaction |
| Priority updates | change_priority | TicketWorkflowService | Retained; server impact/urgency matrix remains authoritative |
| SLA administration | `list_calendars`, `create_calendar`, `update_calendar`, `list_policies`, `create_policy`, `update_policy` | `application/sla_service.py` | One repository transaction per calendar/policy command |
| SLA runtime | `override_sla_policy`, `sla_summary` | `application/sla_runtime_service.py` | Runtime intent, immutable snapshots, deadlines, and read-time clocks are extracted; `replace_sla_policy` remains one repository transaction |
| Escalation | `evaluate_escalations` | `application/escalation_service.py` | Eligibility, dry-run, and storage-neutral candidates are extracted; `record_escalations` remains the idempotent repository transaction |
| Comments and queries | `add_comment`, `list_queue`, `get_ticket` | `application/comment_service.py`, `application/query_service.py` | Repository owns comment mutation and read session |

The SLA collaborator receives the existing value-building callbacks and
repository protocol. It preserves permission checks, field removal on update,
repository call order, and exact public service signatures.

## Maintenance capability map

| Capability | Public methods | Current owner | Transaction boundary |
|---|---|---|---|
| Plan reads/preview | `list_plans`, `get_plan`, `preview_occurrences` | `application/query_service.py`, `application/catalogue_service.py` | Read-only repository sessions |
| Plan lifecycle | `create_plan`, `update_plan`, `pause_plan`, `resume_plan`, `archive_plan` | `application/preventive_plan_service.py` with `MaintenancePlanningService` facade | Application validation and command payloads are extracted; each command still delegates one repository mutation with locks, version checks, audit, and commit/rollback retained in PostgreSQL |
| Checklist templates | `list_templates`, `get_template`, `create_template`, `version_template`, `archive_template` | `application/template_service.py` | One repository transaction per template command; versions remain immutable |
| Work-order planning | `create_work_order`, `create_corrective_from_ticket`, `update_work_order`, `assign_work_order` | `application/work_order_planning_service.py` | Validation and command intent are extracted; number allocation, checklist snapshot, audit/outbox, and commit/rollback remain one repository transaction |
| Work-order lifecycle/checklists | `transition_work_order`, `update_checklist`, `cancel_work_order`, `reopen_work_order` | `application/work_order_lifecycle_service.py` | Named transition intent is extracted; optimistic version checks, checklist writes, audit/outbox, and transaction ownership remain in PostgreSQL |
| Completion/verification | `complete_work_order`, `verify_work_order` | `application/work_order_completion_service.py` | Completion/log intent and independent-verifier checks are extracted; work order, maintenance log, asset dates, audit/outbox, locks, and rollback remain atomic in the repository |
| Preventive generation | `generate` | `application/preventive_generation_service.py` | Bounded recurrence/dry-run decisions are extracted; occurrence uniqueness, plan locks, checklist snapshots, audit, and commit/rollback remain repository-owned |
| Calendar/metrics reporting | `schedule_view`, `metrics` | `application/work_order_reporting_service.py` | Read-only composition only; existing independent read sessions and 1,000-row caps are preserved |
| Linked ticket reads | `linked_work_orders` | `application/query_service.py` | Ticket existence is read first, followed by the existing actor-scoped page-1/100 work-order query; no atomic snapshot is introduced |
| Evidence | `list_evidence`, `upload_evidence`, `download_evidence`, `delete_evidence` | `application/evidence_service.py` | Metadata/audit transaction plus attachment byte cleanup contract |

All collaborators receive explicit repository providers and existing lookup,
normalization, authorization, recurrence, clock, and presentation callbacks.
They do not construct a session, import FastAPI/SQLAlchemy/concrete PostgreSQL
repositories, or alter public route/CLI/worker signatures. The static boundary
test in `tests/test_architecture_boundaries.py` now enforces that dependency
direction.

## API analytics and compatibility services

The historical `ProcessedDataService` now lives as a small façade under
`src/api/services/compatibility.py`. Its collaborators have distinct ownership:

- `AnalyticsSnapshotService` loads and validates the batch CSV snapshot and
  exposes transactional repository frames;
- `AnalyticsProjectionService` owns analytics filters, sorting, and read models;
- `LegacyTicketAdapter` and `LegacyMaintenanceAdapter` preserve the narrow
  legacy Vietnamese mappings and write validation;
- `AssetContextQueryService` composes the read-only manager/RAG asset context;
- `src/api/services/factories.py` selects PostgreSQL or the explicit CSV
  compatibility adapter and constructs the service graph.

`src/composition/copilot.py` constructs the shared RAG graph. The historical
`src/application/copilot_factory.py` import remains available. The API
and CLI use that root; canonical `src/rag` modules do not import API
composition. No transaction, session, lock, idempotency, audit, or outbox
ownership moved into these read/compatibility modules.

The reliability pilot contract follows the same compatibility pattern:
`src/reliability/pilot_contract/legacy.py` preserves historical imports while
the package modules own schemas, manifest/environment/runtime validation,
release/evidence/decision logic, and CLI commands.
The closed deployment `scheduled_jobs` validator lives in
`src/reliability/pilot_contract/deployment_manifest/jobs.py`, while health endpoint
declarations live in `deployment_manifest/health.py` and
environment name/secret declarations live in `deployment_manifest/environment.py`.
Allowed storage roots, logical paths, containment, container/configuration
bindings, and backup retention live in `deployment_manifest/storage.py`. All preserve
the private imports from `manifest.py`. Checked-in Compose, Dockerfile,
application/schema, and frontend package binding lives in
`deployment_manifest/repository.py`; storage validation resolves candidate
paths for containment but does not read file contents or mutate filesystem
state. Artifact identity/release/version/image declarations live in
`deployment_manifest/artifacts.py`, and closed service/port/volume topology lives under
`deployment_manifest/topology.py`; `manifest.py` is their visible orchestrator. The runtime
environment facade delegates injected security/database, network, identity,
bounded runtime settings, and storage paths to capability modules under the
same package. `src/operations/domain.py`, the PM7
worker, FastAPI health routes, and PostgreSQL job, lease, retry, and notification
records remain the runtime authorities.

Line counts in earlier inventory tables are historical measurements, not
ownership rules. The current facades remain stable compatibility surfaces while
the extracted collaborators below own application intent; repository sessions,
locks, audit/outbox writes, and commit/rollback remain in the PostgreSQL
implementations.

## Historical checkpoint — 2026-08-08

Ticket assignment is now a real collaborator at
`src/ticket_management/application/assignment_service.py`. It owns permission,
assignee/group validation, status derivation, audit metadata, and repository
orchestration. `TicketWorkflowService.assign` remains the stable facade method.
Ticket lifecycle characterization is complete and the eight named transitions
now delegate to src/ticket_management/application/lifecycle_service.py.
SLA-runtime snapshot/override, escalation, and comment/query behavior was then
retained or in the previously extracted collaborators.

Lifecycle extraction validation passed 8 dedicated characterization tests and
the PostgreSQL lifecycle sequence/rollback assertions. The final backend
validation is 421 passed, 87 skipped; isolated PostgreSQL is 87 passed, 421
deselected. The repository session/lock/audit/outbox boundary remains
unchanged.

## Historical checkpoint — ticket SLA runtime boundary — 2026-08-08

`TicketSlaRuntimeService` owns SLA policy-override orchestration, immutable policy/calendar snapshot construction, first-response event intent, and derived clock presentation. It uses only the storage-neutral ticket contract plus authorization/normalization collaborators; it owns no SQLAlchemy, session, lock, flush, audit, outbox, commit, rollback, or PostgreSQL exception handling. Intake and lifecycle reuse its snapshot/event behavior, while lifecycle retains named state transitions and `PostgresTicketRepository` retains `replace_sla_policy` and `mutate_ticket` transactions.

`TicketEscalationService` is the corresponding escalation application owner. It consumes the projected SLA clocks from `TicketSlaRuntimeService.present`, applies the bounded active-status/critical/reopen rules, constructs storage-neutral candidates, and delegates one execution command. It does not select recipients, lease worker jobs, write ORM rows, or own audit/outbox. `TicketWorkflowService` remains a compatibility/dependency facade for all routes, CLI, PM7 job invocation, and legacy adapters.

## Current state — 2026-08-09

Ticket application ownership is now explicit: intake, assignment, the eight
named lifecycle actions, SLA administration, SLA runtime, and escalation each
have a focused collaborator under `src/ticket_management/application/`; the
facade remains the stable route/CLI/worker entrypoint. `PostgresTicketRepository`
still owns every ticket mutation transaction.

Maintenance application decomposition now covers preventive-plan commands,
work-order planning, lifecycle/checklists, completion/verification, preventive
generation, reporting, linked-ticket reads, templates, evidence, and primitive
queries. `MaintenancePlanningService` remains the stable facade and shared
validation seam. Every PostgreSQL session, row lock, expected-version check,
occurrence/idempotency boundary, maintenance-log/asset-date write, audit/outbox
write, commit, rollback, and exception map remains in
`PostgresMaintenancePlanningRepository`.

The preceding focused maintenance/architecture selection remains 55 tests with
9 PostgreSQL-gated skips. For the current reliability phase, runtime environment
validation passed 73 tests against the original and 80 after decomposition;
release-record validation passed 41 against the original and 48 after
decomposition. Reliability drills now have focused capacity, backup-artifact,
and attachment-archive owners behind their historical facade. The combined
pilot/deployment/mutation-rehearsal selection passed 572, the complete
reliability/PM9 selection passed 762 with 11 skips, architecture boundaries
passed 7, and full backend validation passed 1107 with
87 skipped and 1 existing warning. Ruff, changed-file formatting, compileall,
AST/import identity, CLI help, documentation links, and diff checks passed.
PostgreSQL, Alembic, Compose, and frontend were not applicable to this
manifest-only phase; their preceding results remain dated in the refactor plan.

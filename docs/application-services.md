# Application-service decomposition

Public service classes remain the compatibility and composition boundary:

- `InventoryManagementService` in `src/inventory_management/service.py`;
- `TicketWorkflowService` in `src/ticket_management/service.py`;
- `MaintenancePlanningService` in `src/maintenance_management/service.py`.

The extracted modules own cohesive application capabilities and receive the
existing repository, storage, authorization, and presentation callbacks. They
do not construct sessions, import FastAPI, or duplicate PostgreSQL mutations.

| Context | Extracted capabilities | Deferred transactional core |
|---|---|---|
| Inventory | catalogue, evidence, stock/balance queries | catalogue mutations and stock operations whose repository call must remain one atomic transaction |
| Tickets | catalogue/priority preview, comments, queue/detail queries | lifecycle, SLA snapshot, escalation, and policy mutation orchestration |
| Maintenance | catalogue/recurrence preview, evidence, plan/work-order queries | plan lifecycle, generation, checklist completion, verification, and metrics |

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
| SLA snapshot/escalation | `override_sla_policy`, `sla_summary`, `evaluate_escalations` | `TicketWorkflowService` | Retained; snapshot and escalation characterization remains pending |
| Comments and queries | `add_comment`, `list_queue`, `get_ticket` | `application/comment_service.py`, `application/query_service.py` | Repository owns comment mutation and read session |

The SLA collaborator receives the existing value-building callbacks and
repository protocol. It preserves permission checks, field removal on update,
repository call order, and exact public service signatures.

## Maintenance capability map

| Capability | Public methods | Current owner | Transaction boundary |
|---|---|---|---|
| Plan reads/preview | `list_plans`, `get_plan`, `preview_occurrences` | `application/query_service.py`, `application/catalogue_service.py` | Read-only repository sessions |
| Plan lifecycle | `create_plan`, `update_plan`, `pause_plan`, `resume_plan`, `archive_plan` | `MaintenancePlanningService` | Retained; schedule changes and audit sequencing remain together |
| Checklist templates | `list_templates`, `get_template`, `create_template`, `version_template`, `archive_template` | `application/template_service.py` | One repository transaction per template command; versions remain immutable |
| Work orders/checklists | `create_work_order`, `update_work_order`, `assign_work_order`, `transition_work_order`, `update_checklist`, `complete_work_order`, `verify_work_order`, `cancel_work_order`, `reopen_work_order` | `MaintenancePlanningService` | Retained; state machine, log linkage, asset dates, audit/outbox remain atomic |
| Generation/metrics | `generate`, `schedule_view`, `metrics` | `MaintenancePlanningService` | Retained; recurrence and generation idempotency remain repository-owned |
| Evidence | `list_evidence`, `upload_evidence`, `download_evidence`, `delete_evidence` | `application/evidence_service.py` | Metadata/audit transaction plus attachment byte cleanup contract |

Template extraction receives the existing normalization and checklist-validation
callbacks. It does not construct a session or alter snapshot data; work-order
creation continues to snapshot the immutable template through the canonical
maintenance repository.

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

Current implementation line counts are approximately 1,140 inventory, 1,272
ticket facade, 421 lifecycle collaborator, and 1,559 maintenance lines. The
lifecycle move reduced the facade while preserving one repository mutation per
action; the remaining ticket methods are SLA snapshot/override, escalation,
legacy compatibility, and bootstrap responsibilities.

## 2026-08-08 update

Ticket assignment is now a real collaborator at
`src/ticket_management/application/assignment_service.py`. It owns permission,
assignee/group validation, status derivation, audit metadata, and repository
orchestration. `TicketWorkflowService.assign` remains the stable facade method.
Ticket lifecycle characterization is complete and the eight named transitions
now delegate to src/ticket_management/application/lifecycle_service.py.
SLA-runtime snapshot/override, escalation, and comment/query behavior stays
retained or in the previously extracted collaborators.

Lifecycle extraction validation passed 8 dedicated characterization tests and
the PostgreSQL lifecycle sequence/rollback assertions. The final backend
validation is 421 passed, 87 skipped; isolated PostgreSQL is 87 passed, 421
deselected. The repository session/lock/audit/outbox boundary remains
unchanged.

## Ticket SLA runtime application boundary - 2026-08-08

`TicketSlaRuntimeService` owns SLA policy-override orchestration, immutable policy/calendar snapshot construction, first-response event intent, and derived clock presentation. It uses only the storage-neutral ticket contract plus authorization/normalization collaborators; it owns no SQLAlchemy, session, lock, flush, audit, outbox, commit, rollback, or PostgreSQL exception handling. Intake and lifecycle reuse its snapshot/event behavior, while lifecycle retains named state transitions and `PostgresTicketRepository` retains `replace_sla_policy` and `mutate_ticket` transactions.

`TicketEscalationService` is the corresponding escalation application owner. It consumes the projected SLA clocks from `TicketSlaRuntimeService.present`, applies the bounded active-status/critical/reopen rules, constructs storage-neutral candidates, and delegates one execution command. It does not select recipients, lease worker jobs, write ORM rows, or own audit/outbox. `TicketWorkflowService` remains a compatibility/dependency facade for all routes, CLI, PM7 job invocation, and legacy adapters.

# Backend structural inventory

Inventory date: 2026-08-06. This is a source-level maintainability inventory
for production Python under `src/`; generated caches, tests, and frontend files
are outside its scope. Line counts and the largest class/function were
calculated from the current worktree with the Python AST. A large file is not
automatically a defect: transaction ownership, declarative models, and public
compatibility seams are retained when extraction would obscure a contract.

## Ranked findings

| Rank | Area | Evidence | Decision | Safe destination / next action |
|---|---|---|---|---|
| High | PostgreSQL mutation repositories | Inventory 2,747 lines; operations 1,913; maintenance 1,331; tickets 1,233. Each combines validation, row locks, idempotency, append-only history, audit/outbox, and serialization. | Retain transaction families until method-level characterization is complete. | Stage 5: extract one complete read/projection or pure mapper at a time behind the existing class. |
| High | Domain application services | Maintenance 1,560 lines; ticket 1,569; inventory 1,141. Public facades still contain state-machine and transaction-sensitive orchestration. | Retain the canonical business boundary; existing read/evidence/catalogue collaborators remain. | Build method-to-capability and characterization maps before moving a mutation family. |
| High | Reliability procedures | Post-start validation 1,191 lines with a 534-line runner; load harness 2,248 with a 487-line runner; deployment rehearsal 1,213 with a 288-line runner. | Refactor in pure, fail-closed steps; preserve report order, exit codes, redaction, and artifact formats. | Stage 6: validators/report builders first, then orchestration. |
| Medium | API compatibility surface | `src/api/routes.py` is 967 lines with 29 public route functions; it still owns legacy route/error/dependency seams while focused routers own selected families. | Keep the compatibility facade and route contracts. | Extract only a bounded route family after OpenAPI and dependency characterization. |
| Medium | Security orchestration | `src/security/service.py` is 807 lines; `AuthService` is 523 lines. | Phase A principal extraction is safe; authentication, token, refresh, password, and audit remain together for now. | Phase G only after security characterization. |
| Medium | Asset lifecycle | `asset_management/service.py` is 866 lines; `AssetManagementService` is 650 lines. | Retain canonical lifecycle boundary and repository transaction ownership. | Extract pure validation/presentation only after lifecycle tests cover it. |
| Medium | Declarative/schema collections | Inventory/ticket/maintenance models and API/inventory schemas exceed 500 lines but are declarative or contract collections. | Intentionally retain; splitting would reduce discoverability without a bounded responsibility. | Change only with explicit schema/contract review and metadata checks. |
| Low | Canonical analytics/import scripts | Feature, risk, ingestion validation/load, and data generation modules are 512–860 lines but expose canonical batch entrypoints. | Retain canonical paths; no duplicate wrappers. | Only extract pure helpers if formula/output characterization justifies it. |

## Complete large-file register

The table records every `src/**/*.py` file over 500 lines in the current
worktree. `class` is the longest class (`lines/public methods`); `function` is
the longest function. `retain` means the file is deliberately kept at its
current boundary for this continuation; `stage 5/6/later` identifies the next
bounded refactor opportunity.

| File | Lines | Largest class | Largest function | Responsibility / decision |
|---|---:|---|---|---|
| `src/repositories/postgres_inventory.py` | 2,747 | `PostgresInventoryRepository` 1,468 / 38 | `issue_stock` 218 | Inventory transaction owner; high; retain atomic families; stage 5. |
| `src/reliability/load_harness.py` | 2,248 | `SafetyThresholds` 62 / 0 | `run_profile` 487 | Bounded load safety/telemetry; high; stage 6. |
| `src/repositories/postgres_operations.py` | 1,913 | `PostgresOperationsRepository` 1,383 / 28 | `_operational_conditions` 153 | Job/lease/outbox/notification transaction owner; high; retain; stage 5. |
| `src/maintenance_management/service.py` | 1,560 | `MaintenancePlanningService` 1,228 / 34 | `create_work_order` 93 | PM/work-order boundary; high; retain mutation state machine; later. |
| `src/ticket_management/service.py` | 1,569 | `TicketWorkflowService` 1,370 / 29 | `intake` 98 | Ticket lifecycle/SLA boundary; high; retain; later. |
| `src/reliability/drills.py` | 1,421 | `DiskAlertCycle` 66 / 1 | `create_atomic_backup_artifact` 118 | Explicit recovery drills; medium; stage 6. |
| `src/inventory_management/service.py` | 1,141 | `InventoryManagementService` 898 / 35 | `issue_stock` 52 | Inventory application boundary; high; retain stock transaction sequencing; later. |
| `src/repositories/postgres_maintenance.py` | 1,331 | `PostgresMaintenancePlanningRepository` 793 / 25 | `generate_plan_occurrences` 147 | Plan/generation/work-order transaction owner; high; retain; stage 5. |
| `src/reliability/deployment_rehearsal.py` | 1,213 | `RehearsalReport` 27 / 1 | `run_deployment_rehearsal` 288 | Compose rehearsal orchestration; high; stage 6. |
| `src/reliability/post_start_validation.py` | 1,191 | `PostStartReport` 22 / 1 | `run_post_start_validation` 534 | Ordered authenticated readiness validation; high; stage 6. |
| `src/dashboard/app.py` | 1,187 | — | `render_ticket_workspace` 169 | Streamlit compatibility client/UI; medium; retain canonical dashboard path. |
| `src/reliability/mutation_rehearsal.py` | 1,041 | `MutationAction` 48 / 0 | `run_mutation_rehearsal` 143 | Explicit operator mutation rehearsal; medium; retain until stage 6. |
| `src/api/routes.py` | 967 | — | `asset_catalog` 32 | FastAPI compatibility facade plus remaining legacy route families; medium; later. |
| `src/database/models/inventory.py` | 878 | `SparePart` 101 / 0 | — | Declarative ORM inventory models; retain as one bounded model module. |
| `src/asset_management/service.py` | 866 | `AssetManagementService` 650 / 21 | `create_asset` 73 | Asset lifecycle business boundary; medium; retain; later. |
| `src/repositories/postgres_assets.py` | 866 | `PostgresAssetRepository` 430 / 14 | `_asset_history_events` 65 | Asset/location/attachment transaction owner; medium; retain. |
| `src/data_generation/generate_data.py` | 860 | `ControlledScenarioPlan` 19 / 1 | `_generate_documents` 120 | Synthetic seed generation; low; retain canonical generator. |
| `src/security/service.py` | 788 | `AuthService` 523 / 11 | `login` 69 | Authentication/session/user/audit orchestration; medium; Phase A done, Phase G later. |
| `src/reliability/pilot_contract/manifest.py` | 778 | — | `_validate_manifest_structure` 317 | Secret-free manifest validation; medium; stage 6 pure validator extraction. |
| `src/database/models/tickets.py` | 769 | `Ticket` 181 / 0 | — | Declarative ORM ticket models; retain. |
| `src/features/build_features.py` | 666 | — | `main` 68 | Canonical batch feature/maintenance analytics; retain canonical path. |
| `src/api/schemas.py` | 656 | `AssetCreateRequest` 55 / 2 | `validate_chronology` 12 | Public API schemas; retain as compatibility contract. |
| `src/repositories/postgres/inventory/queries.py` | 632 | `InventoryQueryRepository` 593 / 18 | `work_order_parts` 121 | Extracted inventory reads; retain bounded query owner. |
| `src/inventory_management/schemas.py` | 626 | `InventoryMovementResponse` 33 / 0 | `_validate_thresholds` 9 | Inventory API contracts; retain. |
| `src/ingestion/validation.py` | 623 | `DatasetValidationError` 2 / 0 | `_validate_maintenance_logs` 87 | Canonical dataset validation; retain. |
| `src/database/models/maintenance.py` | 606 | `WorkOrder` 166 / 0 | — | Declarative PM/work-order models; retain. |
| `src/repositories/postgres/legacy.py` | 593 | `PostgresMaintenanceRepository` 234 / 11 | `create_maintenance_log` 59 | Legacy analytics/maintenance adapter; retain compatibility boundary. |
| `src/repositories/contracts.py` | 563 | `InventoryRepository` 223 / 38 | `update_work_order` 10 | Monolithic storage contracts; Phase B package split. |
| `src/ticket_management/routes.py` | 545 | — | `ticket_queue` 30 | Rich ticket HTTP contract; later route extraction only. |
| `src/ingestion/load_data.py` | 531 | `ImportReport` 7 / 0 | `import_csv_dataset` 139 | Explicit validated import transaction; retain. |
| `src/database/models/operations.py` | 514 | `ScheduledJob` 86 / 0 | — | Declarative durable operations models; retain. |
| `src/risk/risk_scoring.py` | 512 | — | `build_risk_scores` 74 | Canonical risk prioritization; retain canonical path. |
| `src/reliability/pilot_contract/release.py` | 502 | — | `_validate_release_record` 338 | Release evidence validation; stage 6 after characterization. |

## Dependency findings

The AST/import review also found these confirmed or bounded findings:

- `src/composition/copilot.py` imports the API-owned processed-data factory as
  an outer composition concern. The historical
  `src/application/copilot_factory.py` facade no longer imports API services;
  the canonical RAG port remains storage-neutral.
- `src/inventory_management/service.py` and
  `src/maintenance_management/service.py` construct settings/session/repository
  dependencies in their builders, and `TicketWorkflowService` is annotated
  against `PostgresTicketRepository`. Builders are currently compatibility
  entrypoints; Phase C must move construction to explicit composition modules
  without changing startup lifetime.
- `src/repositories/contracts.py` imports `AuditContext`, but does not expose
  SQLAlchemy sessions, ORM models, or engine types. The Phase B shared contract
  module will preserve the audit value object while keeping repository protocols
  storage-neutral.
- Reliability backup tooling has deliberate lazy imports of `src.api.main` and
  `src.api.services` for an operator rehearsal. This is tooling-only, but it
  remains a dependency-direction exception to document rather than spread.
- No duplicate scheduler, raw CSV access from Streamlit, arbitrary worker job,
  or second RBAC model was found in this inventory.
- Duplicate mapper/serialization helpers and business logic in routers are
  present in small bounded areas but were not moved during this inventory; they
  require characterization and are lower-value than the contract/principal
  seams.

## Current safe checkpoint

Phase A moved `CurrentUser` to `src/security/principal.py`; the historical
`src.security.service.CurrentUser` import remains an identity-preserving
re-export. Phase B moved repository definitions into the bounded contract
package and preserved `src.repositories.contracts` imports. Phase C moved
concrete service wiring into `src/composition/` and kept historical builders as
facades. Focused tests and the isolated PostgreSQL selection passed. Phase E
also extracted SLA calendar/policy administration; ticket lifecycle, SLA
snapshot, escalation, and comment mutation families remain intentionally
retained. The next bounded phase is maintenance application-service
decomposition; maintenance work-order/generation transaction families remain
intentionally retained.

The final safe stop for this continuation is before AuthService decomposition.
The principal extraction is complete, while auth/token/session/password/audit
orchestration remains a critical cohesive boundary pending characterization.
The next recommended phase is security characterization followed by one
bounded extraction.

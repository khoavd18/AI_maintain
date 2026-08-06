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

`src/application/copilot_factory.py` constructs the shared RAG graph. The API
and CLI use that root; canonical `src/rag` modules do not import API
composition. No transaction, session, lock, idempotency, audit, or outbox
ownership moved into these read/compatibility modules.

The reliability pilot contract follows the same compatibility pattern:
`src/reliability/pilot_contract/legacy.py` preserves historical imports while
the package modules own schemas, manifest/environment/runtime validation,
release/evidence/decision logic, and CLI commands.

Current implementation line counts are approximately 1,396 inventory, 1,578
ticket, and 1,642 maintenance lines. They remain above the review threshold
because the remaining methods are transaction-sensitive orchestration and
state-machine policy; splitting them without a method-level transaction map
would obscure the existing atomic sequence. The next safe extraction is one
fully characterized mutation family at a time, beginning with read-only
mappers and retaining the facade.

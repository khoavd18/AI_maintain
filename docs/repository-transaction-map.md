# PostgreSQL repository transaction map

This is the characterization map for the current repository implementations.
Read/query capabilities have been composed into domain-owned PostgreSQL
submodules. Every row names the public façade methods covered by that behavior;
private helpers are part of the same transaction and must not be extracted into
independently managed sessions.

## Shared invariants

- Each repository creates/owns its `Session` through its injected
  `session_factory`; application services never open a second session for one
  mutation.
- Read methods use one short-lived session and do not commit.
- Mutation methods use `with session_factory() as session, session.begin()`;
  audit and selected outbox writes occur before that transaction commits.
- A mutation sequence is `idempotency claim -> deterministic row locks ->
  validation -> state/movement write -> audit/outbox -> commit`.
- SQLAlchemy errors are translated at the repository boundary. A failed audit,
  outbox, constraint, or final flush rolls back the business mutation.

## Inventory: `PostgresInventoryRepository`

Read/query implementation: `src/repositories/postgres/inventory/queries.py`.
Catalogue transaction implementation: `catalogue.py`. Evidence transaction
implementation: `attachments.py`. The façade owns construction and injects
mapper, audit, error, and lock-support callbacks; each component still opens
the same injected session factory and owns its own transaction.

| Methods | Session/transaction owner | Reads, writes, locks, and idempotency | Audit/outbox and tests |
|---|---|---|---|
| `list_categories`, `list_units`, `list_parts`, `get_part`, `list_stock_locations`, `get_stock_location`, `list_balances`, `list_movements`, `get_movement`, `get_requirement`, `get_reservation`, `list_reservations`, `get_issue`, `get_work_order_state`, `work_order_parts`, `inventory_metrics`, `list_inventory_attachments`, `get_inventory_attachment` | Repository session, read-only | Reads inventory catalogue, positions, movement history, requirements, reservations, issues, work-order state, and attachment metadata; no locks or writes | No audit/outbox. Covered by inventory catalogue, workflow, API-contract, evidence, and PostgreSQL workflow tests |
| `create_category`, `create_unit`, `create_part`, `update_part`, `create_stock_location`, `update_stock_location`, `upsert_reorder_configuration` | One repository transaction | Writes master/configuration tables; update paths lock the target row and use the version/append-only checks | Audit is committed with the change; covered by inventory management, stale-write, RBAC, and API tests |
| `create_opening_balance`, `receive_stock`, `_increase_stock`, `adjust_stock` | One repository transaction | Claims the caller-stable operation/idempotency key, locks the part/location position, validates active resources and non-negative resulting quantities, then writes `inventory_operations` and append-only movement state | Audit is atomic; reorder/outbox behavior remains in the repository and is covered by inventory and background-operation tests |
| `transfer_stock` | One repository transaction | Locks both positions in deterministic identity order, validates distinct active locations and available quantity, writes transfer-out/in movements with one transfer group | Audit and both sides commit or roll back together; negative transfer and concurrency coverage is in `test_inventory_management.py` |
| `create_requirement` | One repository transaction | Locks/validates the work order and part/location references, creates the requirement, and protects its idempotency key | Audit is atomic; requirement lifecycle is covered by the inventory workflow test |
| `reserve_stock`, `close_reservation`, `replace_reservation` | One repository transaction | Locks requirement, position, and existing reservation in the existing order; derives `available = on_hand - reserved`, rejects oversubscription, and records reservation events | Idempotent replay returns committed result; payload conflict is rejected; concurrent reservation coverage is in `test_inventory_management.py` |
| `issue_stock`, `consume_issue`, `return_issue` | One repository transaction | Locks work order, issue/requirement/reservation, and position rows in the existing order; issue decrements on-hand/releases reservation, consume does not decrement stock again, return validates outstanding quantity and increments destination on-hand | Movements, issue/consumption/return records, audit, and idempotency are one transaction; covered by the distinct lifecycle test and PostgreSQL suite |
| `create_inventory_attachment`, `delete_inventory_attachment` | One repository transaction | Writes metadata or soft-deletes metadata for an already authorized movement; byte storage cleanup follows the committed metadata call | Metadata audit is atomic; attachment signature/checksum/path secrecy is covered by inventory evidence tests |

## Tickets: `PostgresTicketRepository`

Read/query implementation: `src/repositories/postgres/tickets/queries.py`.
Ticket lifecycle, comments, policy mutations, SLA replacement, and escalation
remain in the façade because their transaction sequencing is coupled.

| Methods | Session/transaction owner | Reads, writes, locks, and idempotency | Audit/outbox and tests |
|---|---|---|---|
| `get_asset`, `get_user`, `find_user`, `has_maintenance_log`, `get_ticket`, `list_tickets`, `reference_options`, `get_reference`, `find_sla_policy`, `list_calendars`, `list_policies` | Repository session, read-only | Reads ticket, reference, SLA, asset, user, and timeline state; no locks or writes | No audit/outbox; covered by ticket query/catalogue and PostgreSQL workflow tests |
| `create_ticket` | One repository transaction | Generates the ticket identity from the PostgreSQL sequence, writes the ticket plus snapshotted SLA state/events, and validates referenced resources | Audit and selected outbox event commit with ticket creation; invalid-reference rollback and unique-ID concurrency are covered by `test_postgres_workflow.py` |
| `mutate_ticket` | One repository transaction | Locks the ticket, checks expected version, applies the named lifecycle mutation, and writes append-only SLA events where supplied | Audit/outbox are in the same transaction; stale version and lifecycle coverage is in ticket operations/workflow tests |
| `replace_sla_policy` | One repository transaction | Locks the ticket, checks version, writes a new SLA occurrence/snapshot and append-only events | Audit is atomic; policy snapshot and concurrent escalation tests protect the boundary |
| `create_comment` | One repository transaction | Locks/validates the ticket and referenced attachment IDs, appends a comment and attachment links | Audit is atomic and comment rows remain append-only; covered by comment visibility/append-only tests |
| `create_calendar`, `update_calendar`, `create_policy`, `update_policy`, `seed_defaults` | One repository transaction | Writes versioned calendar/policy/reference data with optimistic version checks and target validation | Audit is atomic; ticket SLA policy snapshot tests protect historical immutability |
| `record_escalations` | One repository transaction | Locks/claims each `(ticket_id, rule_code, occurrence_number)` boundary and inserts only missing escalation events | Dry-run is outside this method; execution is idempotent and notification outbox writes remain atomic; covered by escalation tests |

## Maintenance: `PostgresMaintenancePlanningRepository`

Read/query implementation: `src/repositories/postgres/maintenance/queries.py`.
Plan, checklist, work-order lifecycle, generation, completion, verification,
and evidence mutations remain in the façade.

| Methods | Session/transaction owner | Reads, writes, locks, and idempotency | Audit/outbox and tests |
|---|---|---|---|
| `get_asset_state`, `get_ticket_state`, `get_user_state`, `list_technicians`, `list_plans`, `get_plan`, `list_templates`, `get_template`, `list_work_orders`, `get_work_order`, `list_generated_due_dates`, `list_work_order_attachments`, `get_work_order_attachment` | Repository session, read-only | Reads plan, checklist, work-order, asset, technician, and evidence state; no locks or writes | No audit/outbox; query and recurrence tests cover returned projections |
| `create_plan`, `update_plan`, `create_template`, `archive_template`, `update_work_order`, `update_checklist` | One repository transaction | Locks target plan/template/work-order/checklist rows, checks optimistic versions and immutable-template rules, then writes state | Audit/outbox are atomic; stale state, template version, and state-machine tests cover these methods |
| `create_work_order` | One repository transaction | Validates/locks asset, plan, ticket, and template snapshot inputs; allocates the concurrency-safe work-order number | Audit/outbox commit with the work order; corrective linkage and no-ticket-resolution behavior are characterized |
| `complete_work_order` | One repository transaction | Locks work order, asset, checklist items, and linked log boundary; validates safety/completion requirements and creates or reuses exactly one maintenance log | Work-order, log, asset-date compatibility, audit, and outbox writes commit or roll back together; atomic completion tests cover it |
| `verify_work_order` | One repository transaction | Locks work order and asset, rejects self-verification, checks completed state, updates verification and maintenance-date compatibility fields | Audit/outbox are atomic; independent verification and immutability tests cover it |
| `generate_plan_occurrences` | One repository transaction | Locks the plan, checks the unique `(preventive_plan_id, due_date)` occurrence boundary, snapshots checklist items, advances the plan, and skips paused/retired cases under the documented policy | Generation is idempotent and audit/outbox remain atomic; concurrent generation tests cover it |
| `create_work_order_attachment`, `delete_work_order_attachment` | One repository transaction | Writes/soft-deletes evidence metadata for an authorized work order; byte cleanup remains outside PostgreSQL | Audit is atomic; evidence security tests cover checksums, MIME/signature, soft deletion, and path secrecy |

## Operations: `PostgresOperationsRepository`

Read/query implementation: `src/repositories/postgres/operations/queries.py`.
Claim, lease renewal/recovery, delivery, retry/dead-letter, alert-cycle,
notification mutation, and heartbeat writes remain in the façade.

| Methods | Session/transaction owner | Locks and durable state |
|---|---|---|
| `check_health`, `list_jobs`, `list_executions`, `list_outbox`, `list_notifications`, `unread_notification_count`, `worker_health`, `operational_metrics` | Read-only repository session | No mutation or locks beyond ordinary reads |
| `set_job_enabled`, `trigger_job`, `retry_execution`, `materialize_due_jobs`, `recover_expired_execution_leases`, `claim_execution`, `complete_execution`, `renew_execution_lease`, `fail_execution` | One transaction per command/claim | Locks scheduled job or execution rows with bounded leases; closed PM7 catalog validation precedes durable state changes; idempotency, retry, dead-letter, and audit are durable |
| `recover_expired_outbox_leases`, `claim_outbox_event`, `deliver_outbox_event`, `fail_outbox_event`, `redrive_outbox_event` | One transaction per lease/delivery action | Claims outbox rows with concurrency-safe locking and bounded leases; delivery attempts, retry/dead-letter state, redrive intent, and audit remain append-only |
| `record_low_stock_cycles`, `evaluate_operational_alerts` | One transaction | Persists deterministic detection/alert cycles and deduplicates notifications; no purchase or external delivery is created |
| `mutate_notification`, `read_all_notifications`, `heartbeat` | One transaction | Enforces recipient/role ownership, durable read state, and worker heartbeat updates |

## Decomposition rule

The map is also the stop condition for repository extraction. Read-only queries
and cohesive catalogue/evidence operations have been composed first. An atomic
method remains in its current repository until focused PostgreSQL tests prove
that the entire idempotency -> locks -> mutation -> audit/outbox -> commit
sequence can move without changing session ownership or lock order.

## Security: `AuthService`

Security persistence is owned by `src/security/service.py`, not by a
PostgreSQL repository. `src/composition/security.py` injects the cached
`sessionmaker[Session]`; routes, dependencies, and the explicit security CLI
only call `AuthService`. Each atomic mutation opens exactly one session and
transaction with `with self.session_factory() as session, session.begin()`.
`_create_session_result` and `append_security_audit` receive that caller-owned
session and never open or commit a second one. `AuthService.logout` delegates
the complete operation to `SessionRevocationService`, which uses the same
injected factory and owns one session/transaction. Access validation, identity
projection, and token/password helpers are pure or cryptographic collaborators
and do not own PostgreSQL transactions.

| Methods | Session/transaction owner | Reads, writes, locks, and state boundaries | Audit and characterization |
|---|---|---|---|
| `login` | `AuthService.login` | Reads `users` by normalized identifier; dummy-verifies unknown users; updates `last_login_at`; adds one hashed `refresh_sessions` row and access/CSRF token result; refresh hash uniqueness remains database-enforced | `auth.login_succeeded` or `auth.login_failed` is appended before the single commit; SQL/audit failure rolls back. Persistent behavior is covered by `test_security_postgres_characterization.py`. |
| `authenticate_access` | Read-only `AuthService.authenticate_access` session | Decodes claims first, then reads `users` and `refresh_sessions`; `session_state.access_state_is_valid` checks active/version/role/ownership/revocation/expiry | No write or audit; mismatch/inactive/role/version tests characterize rejection. |
| `refresh` | `AuthService.refresh` | Locks the old `refresh_sessions` row with `FOR UPDATE`; verifies both hashes and owner state; revokes old row; creates replacement row; no replacement-link column exists | Old revocation, new row, token timing, and `auth.refreshed` commit together. Replay, CSRF isolation, expired/revoked/inactive-user rejection, replacement/audit rollback, and concurrent single-winner behavior are characterized in `test_security_postgres_characterization.py`; the exact sequence and retained boundary are in [`security-refresh-rotation-contract.md`](security-refresh-rotation-contract.md). |
| `logout` | `SessionRevocationService` through `AuthService.logout` | Locks one session, verifies refresh/CSRF hashes, loads owner, and revokes only an active row; unknown/malformed values are silent no-ops | `auth.logout` is appended only for actual revocation and commits atomically. Repeated logout, cross-user isolation, one-session ownership, and audit-failure rollback are characterized. |
| `change_password` | `AuthService.change_password` | Locks the actor `users` row; verifies current password; updates password and bulk-revokes that user's active `refresh_sessions` | `auth.password_changed` commits with password/session state. Invalid current password performs no mutation; revoke-all behavior is characterized. |
| `create_user` / `bootstrap_user` | `AuthService._insert_user` | Normalizes/validates and hashes before opening one transaction; adds user, flushes, then appends `user.created`; unique identity constraints map to duplicate errors | User/audit commit together. Bootstrap is explicit, active, actorless, and uses `cli-bootstrap`; persistence and redaction are characterized. |
| `update_user` | `AuthService.update_user` | Locks target user, rejects unsafe self-disable, applies allow-listed state, flushes, bulk-revokes sessions on role/active changes, then adds ordered state audits | User, revocations, and audit rows share one commit; optimistic version and integrity failures roll back the sequence. Post-issuance role invalidation is characterized. |
| `list_users` / `list_audit_logs` | Short-lived read session in `AuthService` | Ordered/filter reads only; response mapping excludes password/token material | No commit mutation or audit; existing API tests cover projections/pagination/redaction. |
| `record_authorization_denied` | `AuthService.record_authorization_denied` | Adds one bounded denial event in a transaction | Best-effort by deliberate contract: SQL/operational errors are swallowed after the permission denial remains in force. |

Persistent tables are `users`, `refresh_sessions`, and append-only
`audit_logs`. There is no security cleanup operation for expired sessions, no
generic authentication idempotency key, and no separate session repository
beyond the selected complete logout component. Refresh, password, login, and
user mutation families remain in `AuthService` because moving only part of a
sequence would change the session owner, lock/flush order, or audit atomicity.

## Refactoring checkpoint — 2026-08-06

Phase A extracted only the storage-neutral `CurrentUser` value type. No
repository method, transaction/session owner, lock order, idempotency boundary,
audit call, outbox write, or commit timing changed. The complete structural
inventory and the intentionally retained transaction families are listed in
[`backend-structural-inventory.md`](backend-structural-inventory.md). Phase B
reorganized contract definitions into
`src/repositories/contracts/{shared,assets,inventory,maintenance,tickets,operations}.py`
without moving repository implementations. The historical import facade and
all transaction-family ownership remain unchanged. Focused PostgreSQL
validation passed (`73 passed, 390 deselected, 1 warning`). Phase C moved only
infrastructure construction into `src/composition/`; it did not move
transaction execution. Session factory cache/lifetime and repository method
owners remain unchanged. Phase D extracted inventory catalogue and
stock-location orchestration with callback-based validation/access; repository
transaction owners, lock order, idempotency, audit, outbox, and commit timing
remain unchanged. Inventory stock/reservation/issue families remain in the
facade pending further characterization.
Phase E extracted only ticket SLA calendar/policy application orchestration;
their repository transactions remain the owner. Ticket lifecycle, SLA snapshot,
escalation, comment, audit, and outbox mutation sequences were not moved.
Phase F extracted checklist-template application orchestration only; template
version/archive repository transactions and immutable snapshot behavior remain
owned by the maintenance repository. Plan generation and work-order mutation
families remain retained.

## Final continuation checkpoint — 2026-08-06

Database-backed security characterization is now explicit. Thirteen isolated
tests cover login persistence, session hash/expiry state, refresh rotation and
replay, CSRF isolation, expired/revoked refreshes, inactive/password/role
refresh invalidation, replacement/audit rollback, concurrent single-winner
refresh, logout idempotency and user isolation, password revoke-all,
post-issuance access invalidation, bootstrap audit state, and one-session
contract ownership. `AuthService`
remains the facade and transaction owner for its families; the selected
`SessionRevocationService` owns the complete logout transaction using one
injected session. The other additional implementation move is the pure
`access_state_is_valid` predicate in `src/security/session_state.py`.

The exact refresh sequence, generation timing, rollback, concurrency, and
retained-in-`AuthService` decision are recorded in
[`security-refresh-rotation-contract.md`](security-refresh-rotation-contract.md).
Further security decomposition is deferred until a complete
transaction-family repository/session contract is explicitly approved; this
map remains the authority for future repository moves.

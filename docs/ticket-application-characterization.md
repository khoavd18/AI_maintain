# Ticket application characterization

Inventory date: 2026-08-08. This is a behavior map for
`TicketWorkflowService` and its extracted application collaborators. The
facade remains the canonical rich-ticket boundary; repository methods retain
transaction, locking, audit, outbox, and commit ownership.

| Capability | Public methods | Current implementation owner | Decision |
|---|---|---|---|
| Catalogue and priority | `options`, `priority_preview` | `application/catalogue_service.py` | Extracted and reused |
| Intake | `intake` | `application/intake_service.py` | Extracted; create_ticket remains one repository transaction |
| Assignment | `assign` | `application/assignment_service.py` | Extracted in this phase; facade signature preserved |
| Acknowledgement/start | `acknowledge`, `start` | `application/lifecycle_service.py` | Extracted; facade delegates and repository mutation remains atomic |
| Hold/resume | `hold`, `resume` | `application/lifecycle_service.py` | Extracted; callback coordinates snapshotted pause/resume |
| Resolution/closure | `resolve`, `close` | `application/lifecycle_service.py` | Extracted; maintenance-log/SLA sequencing remains application-owned |
| Reopen/cancel | `reopen`, `cancel` | `application/lifecycle_service.py` | Extracted; occurrence/cancellation rules remain application-owned |
| Priority updates | `change_priority` | `TicketWorkflowService` | Retain; server impact/urgency matrix is authoritative |
| SLA administration | `list_calendars`, `create_calendar`, `update_calendar`, `list_policies`, `create_policy`, `update_policy` | `application/sla_service.py` | Extracted and reused |
| SLA runtime | `override_sla_policy`, `sla_summary` | `TicketWorkflowService` | Retain; snapshots and business-calendar clocks are coupled |
| Escalation | `evaluate_escalations` | `TicketWorkflowService` | Retain; dry-run and idempotent repository write boundary remain together |
| Comments | `add_comment` | `application/comment_service.py` | Extracted and reused |
| Queries/presentation | `list_queue`, `get_ticket` | `application/query_service.py` | Extracted and reused |
| Legacy compatibility | `legacy_intake`, `legacy_update`, `legacy_projection` | `TicketWorkflowService` | Retain as narrow Vietnamese adapter |
| Defaults | `seed_defaults` | `TicketWorkflowService` | Retain as explicit CLI/bootstrap operation |

## Assignment extraction

`TicketAssignmentService.assign` now owns permission checking, active-assignee
validation, support-group reference validation, target-status derivation,
audit metadata construction, and the single `mutate_ticket` call. The facade
passes the existing repository and presentation callbacks. No SQLAlchemy model
is imported by the application service, and references use
`TicketReferenceKind` from the storage-neutral repository contract.

The PostgreSQL `mutate_ticket` transaction was not moved. Its expected-version
check, audit row, selected outbox behavior, flush/commit timing, and exception
mapping are unchanged. Assignment notification behavior remains repository
owned where applicable.

## Lifecycle state-machine map

The lifecycle actions enforce named permissions and the existing
`open -> assigned -> in_progress -> waiting/resolved -> closed` plus reopen and
cancel transitions. Waiting requires a reason; reopen creates a new SLA
occurrence; resolution and closure remain explicit human actions. Their
application orchestration is now in
`application/lifecycle_service.py`; work-order creation or completion never
resolves a source ticket.

## Intake extraction checkpoint

The complete implementation now lives in
`src/ticket_management/application/intake_service.py`. The compatibility
facade constructs it with the existing repository, authorization, reference,
assignee, SLA-snapshot, normalization, and presentation callbacks, and
`TicketWorkflowService.intake` delegates without retaining a second validation
copy. The extracted service owns only application orchestration; it has no
SQLAlchemy, session, transaction, lock, commit, rollback, or PostgreSQL error
handling dependency.

The PostgreSQL `create_ticket` transaction remains unchanged: one session,
ticket-sequence allocation, ticket flush, SLA state/event persistence, three
audit events, critical/assignment outbox enqueue, and commit/rollback ordering.
No intake idempotency key exists before or after extraction. Rich workflow and
isolated PostgreSQL characterization passes protect valid creation, reference
validation, SLA/priority snapshots, initial assignment, audit/outbox state, and
failure atomicity.

Before lifecycle extraction, `TicketWorkflowService` had 1,477 source lines,
a 1,284-line class, and 29 public methods. After extraction it has 1,272 source
lines and a 1,080-line class with the same 29 public methods; the new
`TicketLifecycleService` has 421 source lines and eight transition methods.

## Ticket intake characterization

### Entry points and contracts

The rich HTTP entry point is `POST /tickets/intake` in
`src/ticket_management/routes.py`. Pydantic parses `TicketIntakeRequest` with
extra fields forbidden, whitespace stripped, and these fields: `asset_id`,
`issue_description`, `failure_category`, reporter name/email/phone, category,
subcategory, impact, urgency, intake source, support group, optional assignee,
and manager note. The route returns `TicketDetailResponse` with HTTP 201.
Direct callers use `TicketWorkflowService.intake(request: dict[str, Any], *,
actor: CurrentUser, audit_context: AuditContext, now: datetime | None = None)`.
The legacy adapter calls `legacy_intake`, which projects its Vietnamese
compatibility payload and is intentionally a separate path.

### Pre-repository validation and ordering

All of the following occur before the atomic repository command:

1. `Permission.TICKETS_CREATE` is required from the active `CurrentUser`.
2. `now` is normalized to UTC (or the service clock is sampled), then
   `asset_id` is normalized and the asset is read. A missing asset raises
   `TicketNotFoundError`; retired/archived assets raise `TicketConflictError`.
3. Optional category, subcategory, intake-source, support-group, and assignee
   UUIDs are parsed in that order. Reference validation then reads category,
   subcategory, intake source, and support group using `TicketReferenceKind`.
   Category activity is checked first; subcategory activity and category
   relationship are checked next; source and group activity are checked in
   source-then-group order. Invalid references raise the existing
   `TicketNotFoundError`/`TicketConflictError` messages.
4. An optional assignee requires `Permission.TICKETS_ASSIGN`, then active-user
   and assignable-role validation. The initial status is `assigned` when an
   assignee exists, otherwise `open`; technician ownership is derived from the
   assignee or `UNASSIGNED`.
5. Impact and urgency are converted to domain enums and priority is derived by
   the backend matrix. Unsupported failure categories raise `TicketDomainError`.
6. Reporter fields and manager note are normalized. Reporter email is
   case-folded after format validation; no reporter contact data is placed in
   audit metadata.
7. The repository selects the active SLA policy by category, derived priority,
   and the facility-local effective date. Missing policy raises the existing
   `TicketConflictError`. The service snapshots the selected business calendar,
   computes first-response and resolution due timestamps, and builds the three
   initial SLA events (`policy_applied`, two `clock_started` events).

### Atomic repository call

`TicketRepository.create_ticket(values, sla_values, sla_events, audit_context)`
is the only persistence mutation. `PostgresTicketRepository.create_ticket`
owns one session and one transaction: it allocates the ticket sequence,
flushes the ticket, persists/flushed the SLA state and events, appends
`ticket.created`, `ticket.priority_calculated`, and
`ticket.sla_policy_applied` audit rows, then enqueues
`ticket.critical_created` for critical priority and `ticket.assigned` for an
initial assignee. Audit UUID generation, outbox ordering, final commit, and
rollback/exception mapping remain repository-owned. Intake has no idempotency
key or duplicate-prevention behavior; repeated calls create distinct sequence
ticket IDs, subject to the same database constraints as today.

### After-repository behavior and coverage

After a committed record returns, `TicketWorkflowService._present` maps the
storage-neutral record for the actor and the intake timestamp. No additional
notification or mutation occurs in the application layer. Existing rich ticket
operations, PostgreSQL workflow, audit/outbox, SLA, authorization, and API
tests cover valid creation, invalid references, priority/SLA snapshots,
initial assignment, ownership, and rollback. Missing dedicated
characterization was limited to asserting the complete validation order and
the absence of intake idempotency; these will be added before extraction.

## Ticket lifecycle characterization (2026-08-08)

The rich lifecycle entry points are the named routes in
src/ticket_management/routes.py. Their Pydantic payloads reject extra fields
and carry an expected_version. Direct callers use the same keyword-only
service signatures. The application layer validates the command and builds a
storage-neutral mutation request. Each action below calls
TicketRepository.mutate_ticket once. No action opens a session, performs a
second read after the mutation, or performs a post-commit side effect.

### Exact transition matrix

| Method/signature | Source -> target | Permission and actor scope | Required fields and validation order | Timestamp/state updates | SLA effect and events | Audit and notification/outbox | Repository/transaction and errors |
|---|---|---|---|---|---|---|---|
| acknowledge(ticket_id: str, *, expected_version: int, actor: CurrentUser, audit_context: AuditContext, now: datetime \| None = None) | open, assigned, in_progress, waiting, or reopened -> same state | tickets:acknowledge; _ticket_for_action additionally restricts a technician to an owned ticket. | Permission -> ticket read/ownership -> active-state check -> reject existing first_response_at -> normalize now to aware UTC -> build first-response events. | Sets first_response_at=current; status and all other ticket fields unchanged. | No SLA row update. Appends first_response_recorded and, when on or before the snapshotted due time, target_met for first_response. | Audit ticket.first_response_recorded. No outbox mapping. | One mutate_ticket transaction. TicketNotFoundError, TicketAuthorizationError, TicketConflictError("Chỉ ticket đang hoạt động mới được ghi nhận phản hồi."), or TicketConflictError("Ticket đã có first response."); repository maps stale/DB failures. |
| start(ticket_id: str, *, expected_version: int, actor: CurrentUser, audit_context: AuditContext, now: datetime \| None = None) | open, assigned, reopened -> in_progress | tickets:execute; technician ownership enforced by _ticket_for_action. | Permission -> ticket read/ownership -> source-state check -> normalize now -> assemble status update and, if needed, first-response events. | Sets status=in_progress; sets first_response_at only when absent. | No SLA row update. If first response was absent, appends the same first-response events as acknowledge; otherwise unchanged. | Audit ticket.started; no outbox mapping. | One mutate_ticket transaction. Invalid state is TicketConflictError("Không thể bắt đầu ticket từ trạng thái {status}."). |
| hold(ticket_id: str, *, reason: str, expected_version: int, actor: CurrentUser, audit_context: AuditContext, now: datetime \| None = None) | assigned or in_progress -> waiting | tickets:execute; technician ownership enforced. | Permission -> ticket read/ownership -> source-state check -> normalize now -> read SLA snapshot and calculate remaining business minutes -> normalize reason (1-1000 chars) -> mutation. | Sets status=waiting, waiting_reason=reason, waiting_previous_status to the source. | pause_on_waiting=true locks paused_at/current remaining minutes and appends paused; false leaves SLA unchanged. | Audit ticket.placed_on_hold metadata reason. Repository maps to in-app outbox ticket.held. | One mutate_ticket transaction. Invalid state is TicketConflictError("Chỉ ticket assigned/in_progress mới được đặt chờ."); reason errors are TicketDomainError. |
| resume(ticket_id: str, *, expected_version: int, actor: CurrentUser, audit_context: AuditContext, now: datetime \| None = None) | waiting -> saved waiting_previous_status (assigned or in_progress) | tickets:execute; technician ownership enforced. | Permission -> ticket read/ownership -> require waiting -> parse waiting_previous_status -> normalize now -> rebuild due dates if paused -> mutation. | Restores prior status; clears waiting fields. | If paused_at exists, clears pause/remaining fields, recalculates deadlines from current, and appends resumed; otherwise unchanged. | Audit ticket.resumed. Repository maps to in-app outbox ticket.resumed. | One mutate_ticket transaction. Non-waiting is TicketConflictError("Chỉ ticket waiting mới được tiếp tục."); invalid saved state raises ValueError. |
| resolve(ticket_id: str, *, expected_version: int, actor: CurrentUser, audit_context: AuditContext, resolved_at: datetime \| None = None) | in_progress -> resolved | tickets:resolve; technician ownership enforced. | Permission -> ticket read/ownership -> require in_progress -> has_maintenance_log read -> normalize resolved_at -> chronology check -> build SLA events -> mutation. | Sets status=resolved and resolved_at=current. | If SLA exists, sets resolution_stopped_at and appends resolved plus on-time target_met. | Audit ticket.resolved; no outbox mapping. | One mutate_ticket transaction after the maintenance-log read. Exact errors: "Ticket phải ở trạng thái in_progress trước khi resolve.", "Ticket cần có maintenance log trước khi resolve.", and "resolved_at không được sớm hơn created_at." |
| close(ticket_id: str, *, expected_version: int, actor: CurrentUser, audit_context: AuditContext, now: datetime \| None = None) | resolved -> closed | tickets:close; _ticket_record is used, so no technician ownership restriction. | Permission -> ticket read -> require resolved -> normalize now -> mutation. | Sets status=closed and closed_at=current. | SLA unchanged. | Audit ticket.closed; no outbox mapping. | One mutate_ticket transaction. Invalid state is TicketConflictError("Chỉ ticket resolved mới được đóng."). |
| reopen(ticket_id: str, *, reason: str, expected_version: int, actor: CurrentUser, audit_context: AuditContext, now: datetime \| None = None) | resolved or closed -> reopened | tickets:reopen; _ticket_record is used, so no technician ownership check. Technicians do not have this permission. | Permission -> ticket read -> source-state check -> normalize now -> calculate next SLA occurrence/due date -> normalize reason for audit metadata -> mutation. | Sets status=reopened, clears resolved/closed timestamps, sets reopened_at, increments reopen_count. | Increments SLA occurrence, starts a fresh resolution deadline, clears stopped/paused/remaining, and appends reopened then resolution clock_started. | Audit ticket.reopened with normalized reason; no outbox mapping. | One mutate_ticket transaction. Invalid state is TicketConflictError("Chỉ ticket resolved/closed mới được mở lại."). Reason errors are TicketDomainError. |
| cancel(ticket_id: str, *, reason: str, expected_version: int, actor: CurrentUser, audit_context: AuditContext, now: datetime \| None = None) | any active state (open, assigned, in_progress, waiting, reopened) -> cancelled | tickets:cancel; _ticket_record is used, so no technician ownership check. Technicians do not have this permission. | Permission -> ticket read -> active-state check -> normalize now -> build stopped event/SLA update -> normalize reason for ticket update -> mutation. | Sets status=cancelled, cancelled_at, cancellation_reason; clears waiting fields. | If SLA exists, sets resolution_stopped_at, clears paused_at, and appends resolution stopped with reason. Presentation marks both clocks stopped. | Audit ticket.cancelled with raw reason; no outbox mapping. | One mutate_ticket transaction. Invalid state is TicketConflictError("Chỉ ticket đang hoạt động mới được hủy."). Reason errors are TicketDomainError. |

change_priority is outside this lifecycle matrix. It requires tickets:update,
derives priority through the backend impact x urgency matrix, and calls
mutate_ticket with audit ticket.priority_changed. It does not change status,
timestamps, SLA, or lifecycle eligibility.

### Validation and actor contract

Permission checks are the first operation for every named action. acknowledge,
start, hold, resume, and resolve use _ticket_for_action, which reads the ticket
and then enforces technician ownership. close, reopen, and cancel use
_ticket_record, intentionally allowing an authorized manager/admin-style actor
to act across assignees. The service does not independently re-read user
activity: HTTP authentication has already constructed an active CurrentUser;
direct callers with a fabricated inactive principal are governed only by its
supplied permissions. Reporters have no lifecycle permissions. Technicians can
acknowledge/start/hold/resume/resolve only on owned tickets. Helpdesk can
acknowledge but cannot execute, resolve, close, reopen, or cancel.

expected_version is passed unchanged to the repository; optimistic version
validation occurs after application validation and before row update. now or
resolved_at is captured and normalized only after state/actor checks. Rejected
validation performs no mutation.

### SLA, audit, and outbox coupling

SLA policy/calendar values are snapshotted at intake and lifecycle calculations
use that immutable calendar snapshot. Holding/resuming is the only pause clock
pair; resolve stops the resolution clock and records a target result; reopen
starts a new resolution occurrence; cancel stops the resolution clock and
presentation marks both clocks stopped. Close and priority changes leave SLA
state untouched. SLA event UUIDs are generated by the repository while it
appends supplied event values, after locking the ticket and SLA rows.

Audit rows are generated inside the same repository transaction as the ticket
mutation. They contain action, actor/display name, request ID, ticket ID,
allow-listed before/after state, and supplied reason metadata. The application
layer never creates an audit UUID or stores reporter contact data in metadata.
Only assignment, hold, and resume map to outbox events in mutate_ticket; enqueue
occurs after audit and flush and before commit. acknowledge, start, resolve,
close, reopen, and cancel create no notification/outbox record.

### Existing coverage and missing characterization

tests/test_ticket_operations.py::test_named_lifecycle_pause_resume_reopen_and_sla_events
and ::test_multiple_waiting_intervals_extend_the_snapshotted_resolution_clock
cover the valid start/hold/resume/resolve/close/reopen sequence, SLA pause and
occurrence behavior, and held/resumed outbox events against PostgreSQL.
tests/test_ticket_operations.py::test_typed_ticket_api_intake_queue_actions_comments_and_stale_conflict
covers HTTP action routing and optimistic conflicts. Legacy transition behavior
is covered by tests/test_postgres_workflow.py.

By operation, acknowledge is exercised by the typed PostgreSQL API action
test; start, hold, resume, resolve, close, and reopen are exercised by the
named PostgreSQL lifecycle sequence (with hold/resume SLA and outbox
assertions); cancel and exact reason/metadata payloads are covered by the
focused unit characterization. The focused suite also covers forbidden start,
technician ownership, resolve-without-log/chronology, permission-before-read,
and direct inactive-principal behavior. There is no existing dedicated
PostgreSQL happy-path cancel test; the repository rollback test covers start as
the representative failed lifecycle mutation.

The focused characterization suite added in this phase covers exact named
mutation payloads, validation ordering, forbidden states, technician ownership,
resolve prerequisites/chronology, cancellation/reopen metadata, and no-call
behavior on rejected validation. PostgreSQL assertions add audit action and
outbox coverage to the valid lifecycle sequence. The repository integration
suite continues to cover lock/version failure and rollback behavior; no
repository transaction or exception mapping is changed by this phase.

### Boundary decision

The complete lifecycle application boundary is cohesive after characterization:
it contains only permission/ownership checks, named state validation,
transition-specific field/timestamp construction, snapshotted SLA runtime
coordination, and one repository command/result projection per action. It has
no escalation mutable state and no SQLAlchemy/session/lock/commit/error
handling dependency. The implementation is therefore extracted to
src/ticket_management/application/lifecycle_service.py. The historical
TicketWorkflowService remains the compatibility facade and delegates all eight
lifecycle methods; change_priority, SLA snapshot/override, escalation,
comments, legacy adapters, and bootstrap behavior remain there.

### Lifecycle validation checkpoint

The new lifecycle characterization file has 8 passing unit tests; the combined
ticket/application focused selection has 12 passing tests. The
full backend suite is 421 passed, 87 skipped, 1 existing
FastAPI/Starlette-httpx deprecation warning. Isolated PostgreSQL validation is
87 passed, 421 deselected, 1 warning, including the lifecycle audit/outbox and
audit-insert rollback checks. Ruff and compileall pass. Alembic current and
heads are 20260726_0008 with no pending operations, all development/test/pilot
Compose configurations parse, and git diff --check passes.

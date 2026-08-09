"""Ticket lifecycle/state-transition application orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from src.repositories.contracts import StoredRecord, TicketRepository
from src.security.audit_context import AuditContext
from src.security.permissions import Permission
from src.security.principal import CurrentUser
from src.ticket_management.domain import (
    ACTIVE_TICKET_STATUSES,
    SlaClockType,
    TicketStatus,
)
from src.ticket_management.errors import TicketConflictError, TicketDomainError
from src.ticket_management.sla import BusinessCalendarDefinition, remaining_minutes


class TicketLifecycleService:
    """Validate named ticket transitions and delegate one atomic mutation."""

    def __init__(
        self,
        repository: TicketRepository,
        *,
        require_permission: Callable[[CurrentUser, Permission], None],
        ticket_record: Callable[[str], StoredRecord],
        ticket_for_action: Callable[[str, CurrentUser], StoredRecord],
        sla_events_for_first_response: Callable[
            [dict[str, Any] | None, datetime], list[dict[str, Any]]
        ],
        sla_event: Callable[..., dict[str, Any]],
        present: Callable[..., dict[str, Any]],
        normalize_datetime: Callable[[datetime], datetime],
        parse_datetime: Callable[[object], datetime | None],
        normalize_text: Callable[..., str],
        utc_now: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._require_permission = require_permission
        self._ticket_record = ticket_record
        self._ticket_for_action = ticket_for_action
        self._sla_events_for_first_response = sla_events_for_first_response
        self._sla_event = sla_event
        self._present = present
        self._normalize_datetime = normalize_datetime
        self._parse_datetime = parse_datetime
        self._normalize_text = normalize_text
        self._utc_now = utc_now

    def acknowledge(
        self,
        ticket_id: str,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_ACKNOWLEDGE)
        record = self._ticket_for_action(ticket_id, actor)
        if TicketStatus(record.values["status"]) not in ACTIVE_TICKET_STATUSES:
            raise TicketConflictError("Chỉ ticket đang hoạt động mới được ghi nhận phản hồi.")
        if record.values.get("first_response_at"):
            raise TicketConflictError("Ticket đã có first response.")
        current = self._normalize_datetime(now or self._utc_now())
        events = self._sla_events_for_first_response(record.values.get("sla"), current)
        result = self._repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates={"first_response_at": current},
            sla_updates=None,
            sla_events=events,
            audit_action="ticket.first_response_recorded",
            audit_context=audit_context,
        )
        return self._present(result.values, actor=actor, as_of=current)

    def start(
        self,
        ticket_id: str,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_EXECUTE)
        record = self._ticket_for_action(ticket_id, actor)
        status = TicketStatus(record.values["status"])
        if status not in {TicketStatus.OPEN, TicketStatus.ASSIGNED, TicketStatus.REOPENED}:
            raise TicketConflictError(f"Không thể bắt đầu ticket từ trạng thái {status.value}.")
        current = self._normalize_datetime(now or self._utc_now())
        updates: dict[str, Any] = {"status": TicketStatus.IN_PROGRESS.value}
        events: list[dict[str, Any]] = []
        if not record.values.get("first_response_at"):
            updates["first_response_at"] = current
            events.extend(self._sla_events_for_first_response(record.values.get("sla"), current))
        result = self._repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates=updates,
            sla_updates=None,
            sla_events=events,
            audit_action="ticket.started",
            audit_context=audit_context,
        )
        return self._present(result.values, actor=actor, as_of=current)

    def hold(
        self,
        ticket_id: str,
        *,
        reason: str,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_EXECUTE)
        record = self._ticket_for_action(ticket_id, actor)
        status = TicketStatus(record.values["status"])
        if status not in {TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS}:
            raise TicketConflictError("Chỉ ticket assigned/in_progress mới được đặt chờ.")
        current = self._normalize_datetime(now or self._utc_now())
        sla = record.values.get("sla")
        sla_updates: dict[str, Any] | None = None
        events: list[dict[str, Any]] = []
        if sla and sla["pause_on_waiting"]:
            calendar = BusinessCalendarDefinition.from_snapshot(sla["calendar_snapshot"])
            sla_updates = {
                "paused_at": current,
                "first_response_remaining_minutes": (
                    None
                    if record.values.get("first_response_at")
                    else max(
                        0,
                        remaining_minutes(
                            self._parse_datetime(sla["first_response_due_at"]),
                            current,
                            calendar=calendar,
                        )
                        or 0,
                    )
                ),
                "resolution_remaining_minutes": max(
                    0,
                    remaining_minutes(
                        self._parse_datetime(sla["resolution_due_at"]),
                        current,
                        calendar=calendar,
                    )
                    or 0,
                ),
            }
            events.append(
                self._sla_event(
                    "paused",
                    current,
                    sla["occurrence_number"],
                    details={"reason": reason},
                )
            )
        result = self._repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates={
                "status": TicketStatus.WAITING.value,
                "waiting_reason": self._normalize_text(reason, "reason", 1000),
                "waiting_previous_status": status.value,
            },
            sla_updates=sla_updates,
            sla_events=events,
            audit_action="ticket.placed_on_hold",
            audit_context=audit_context,
            audit_metadata={"reason": reason},
        )
        return self._present(result.values, actor=actor, as_of=current)

    def resume(
        self,
        ticket_id: str,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_EXECUTE)
        record = self._ticket_for_action(ticket_id, actor)
        if record.values["status"] != TicketStatus.WAITING.value:
            raise TicketConflictError("Chỉ ticket waiting mới được tiếp tục.")
        previous = TicketStatus(record.values["waiting_previous_status"])
        current = self._normalize_datetime(now or self._utc_now())
        sla = record.values.get("sla")
        sla_updates: dict[str, Any] | None = None
        events: list[dict[str, Any]] = []
        if sla and sla.get("paused_at"):
            calendar = BusinessCalendarDefinition.from_snapshot(sla["calendar_snapshot"])
            response_due = self._parse_datetime(sla["first_response_due_at"])
            if not record.values.get("first_response_at"):
                response_due = calendar.add_working_minutes(
                    current, max(1, int(sla["first_response_remaining_minutes"] or 0))
                )
            resolution_due = calendar.add_working_minutes(
                current, max(1, int(sla["resolution_remaining_minutes"] or 0))
            )
            sla_updates = {
                "paused_at": None,
                "first_response_due_at": response_due,
                "resolution_due_at": resolution_due,
                "first_response_remaining_minutes": None,
                "resolution_remaining_minutes": None,
            }
            events.append(self._sla_event("resumed", current, sla["occurrence_number"]))
        result = self._repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates={
                "status": previous.value,
                "waiting_reason": None,
                "waiting_previous_status": None,
            },
            sla_updates=sla_updates,
            sla_events=events,
            audit_action="ticket.resumed",
            audit_context=audit_context,
        )
        return self._present(result.values, actor=actor, as_of=current)

    def resolve(
        self,
        ticket_id: str,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        resolved_at: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_RESOLVE)
        record = self._ticket_for_action(ticket_id, actor)
        if record.values["status"] != TicketStatus.IN_PROGRESS.value:
            raise TicketConflictError("Ticket phải ở trạng thái in_progress trước khi resolve.")
        if not self._repository.has_maintenance_log(ticket_id):
            raise TicketConflictError("Ticket cần có maintenance log trước khi resolve.")
        current = self._normalize_datetime(resolved_at or self._utc_now())
        if current < self._parse_datetime(record.values["created_at"]):
            raise TicketDomainError("resolved_at không được sớm hơn created_at.")
        sla = record.values.get("sla")
        events: list[dict[str, Any]] = []
        sla_updates = None
        if sla:
            sla_updates = {"resolution_stopped_at": current}
            events.append(
                self._sla_event(
                    "resolved",
                    current,
                    sla["occurrence_number"],
                    clock_type=SlaClockType.RESOLUTION.value,
                )
            )
            if current <= self._parse_datetime(sla["resolution_due_at"]):
                events.append(
                    self._sla_event(
                        "target_met",
                        current,
                        sla["occurrence_number"],
                        clock_type=SlaClockType.RESOLUTION.value,
                    )
                )
        result = self._repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates={"status": TicketStatus.RESOLVED.value, "resolved_at": current},
            sla_updates=sla_updates,
            sla_events=events,
            audit_action="ticket.resolved",
            audit_context=audit_context,
        )
        return self._present(result.values, actor=actor, as_of=current)

    def close(
        self,
        ticket_id: str,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_CLOSE)
        record = self._ticket_record(ticket_id)
        if record.values["status"] != TicketStatus.RESOLVED.value:
            raise TicketConflictError("Chỉ ticket resolved mới được đóng.")
        current = self._normalize_datetime(now or self._utc_now())
        result = self._repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates={"status": TicketStatus.CLOSED.value, "closed_at": current},
            sla_updates=None,
            sla_events=[],
            audit_action="ticket.closed",
            audit_context=audit_context,
        )
        return self._present(result.values, actor=actor, as_of=current)

    def reopen(
        self,
        ticket_id: str,
        *,
        reason: str,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_REOPEN)
        record = self._ticket_record(ticket_id)
        status = self._ticket_status(record)
        if status not in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
            raise TicketConflictError("Chỉ ticket resolved/closed mới được mở lại.")
        current = self._normalize_datetime(now or self._utc_now())
        sla = record.values.get("sla")
        sla_updates = None
        events: list[dict[str, Any]] = []
        if sla:
            calendar = BusinessCalendarDefinition.from_snapshot(sla["calendar_snapshot"])
            occurrence = int(sla["occurrence_number"]) + 1
            sla_updates = {
                "resolution_due_at": calendar.add_working_minutes(
                    current, int(sla["resolution_target_minutes"])
                ),
                "resolution_stopped_at": None,
                "resolution_remaining_minutes": None,
                "first_response_remaining_minutes": None,
                "paused_at": None,
                "occurrence_number": occurrence,
            }
            events.extend(
                [
                    self._sla_event("reopened", current, occurrence, details={"reason": reason}),
                    self._sla_event(
                        "clock_started",
                        current,
                        occurrence,
                        clock_type=SlaClockType.RESOLUTION.value,
                    ),
                ]
            )
        result = self._repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates={
                "status": TicketStatus.REOPENED.value,
                "resolved_at": None,
                "closed_at": None,
                "reopened_at": current,
                "reopen_count": int(record.values["reopen_count"]) + 1,
            },
            sla_updates=sla_updates,
            sla_events=events,
            audit_action="ticket.reopened",
            audit_context=audit_context,
            audit_metadata={"reason": self._normalize_text(reason, "reason", 1000)},
        )
        return self._present(result.values, actor=actor, as_of=current)

    def cancel(
        self,
        ticket_id: str,
        *,
        reason: str,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_CANCEL)
        record = self._ticket_record(ticket_id)
        status = self._ticket_status(record)
        if status not in ACTIVE_TICKET_STATUSES:
            raise TicketConflictError("Chỉ ticket đang hoạt động mới được hủy.")
        current = self._normalize_datetime(now or self._utc_now())
        sla = record.values.get("sla")
        events = (
            [
                self._sla_event(
                    "stopped",
                    current,
                    sla["occurrence_number"],
                    clock_type=SlaClockType.RESOLUTION.value,
                    details={"reason": reason},
                )
            ]
            if sla
            else []
        )
        result = self._repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates={
                "status": TicketStatus.CANCELLED.value,
                "cancelled_at": current,
                "cancellation_reason": self._normalize_text(reason, "reason", 1000),
                "waiting_reason": None,
                "waiting_previous_status": None,
            },
            sla_updates={"resolution_stopped_at": current, "paused_at": None} if sla else None,
            sla_events=events,
            audit_action="ticket.cancelled",
            audit_context=audit_context,
            audit_metadata={"reason": reason},
        )
        return self._present(result.values, actor=actor, as_of=current)

    @staticmethod
    def _ticket_status(record: StoredRecord) -> TicketStatus:
        return TicketStatus(record.values["status"])

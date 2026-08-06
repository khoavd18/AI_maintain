"""Business rules for ticket intake, lifecycle, SLA clocks, and escalation."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from src.config.value_mappings import (
    FAILURE_TYPE_CODE_TO_VI,
    FAILURE_TYPE_VI_TO_CODE,
    PRIORITY_VI_TO_CODE,
)
from src.database.models import (
    SupportGroup,
    TicketCategory,
    TicketIntakeSource,
    TicketSubcategory,
)
from src.repositories.contracts import StoredRecord, TicketRepository
from src.security.audit import AuditContext
from src.security.permissions import Permission, Role
from src.security.principal import CurrentUser
from src.ticket_management.application.comment_service import TicketCommentService
from src.ticket_management.application.catalogue_service import TicketCatalogueService
from src.ticket_management.application.query_service import TicketQueryService
from src.ticket_management.application.sla_service import TicketSlaAdministrationService
from src.ticket_management.errors import (
    TicketAuthorizationError,
    TicketConflictError,
    TicketDomainError,
    TicketNotFoundError,
)
from src.ticket_management.domain import (
    ACTIVE_TICKET_STATUSES,
    ASSIGNABLE_STATUSES,
    ESCALATION_RULE_LABELS,
    IMPACT_LABELS,
    LEGACY_STATUS_LABELS,
    PRIORITY_LABELS,
    SLA_STATUS_LABELS,
    TICKET_STATUS_LABELS,
    URGENCY_LABELS,
    EscalationRule,
    Impact,
    SlaClockStatus,
    SlaClockType,
    TicketPriority,
    TicketQueue,
    TicketStatus,
    Urgency,
    calculate_priority,
    legacy_priority_dimensions,
)
from src.ticket_management.sla import (
    BusinessCalendarDefinition,
    WorkingPeriod,
    derive_clock_status,
    remaining_minutes,
)

FACILITY_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
FAILURE_CATEGORIES = frozenset(FAILURE_TYPE_CODE_TO_VI)
CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,49}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class TicketWorkflowService:
    """Canonical boundary for PM5 ticket operations."""

    def __init__(self, repository: TicketRepository) -> None:
        self.repository = repository
        self.catalogue = TicketCatalogueService(repository, self._require_permission)
        self.comments = TicketCommentService(
            repository,
            require_permission=self._require_permission,
            ticket_for_action=self._ticket_for_action,
            normalize_text=_plain_text,
        )
        self.queries = TicketQueryService(
            repository,
            require_permission=self._require_permission,
            ticket_record=self._ticket_record,
            require_ticket_access=self._require_ticket_access,
            present=self._present,
            is_owned=self._is_owned,
            in_queue=self._in_queue,
            queue_sort_key=_queue_sort_key,
            normalize_time=_aware_utc,
            now=_utc_now,
        )
        self.sla_administration = TicketSlaAdministrationService(
            repository,
            self._require_permission,
            self._calendar_values,
            self._policy_values,
        )

    def options(self, *, actor: CurrentUser) -> dict[str, Any]:
        return self.catalogue.options(actor=actor)

    def priority_preview(self, *, impact: str, urgency: str) -> dict[str, str]:
        return self.catalogue.priority_preview(impact=impact, urgency=urgency)

    def intake(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_CREATE)
        current = _aware_utc(now or _utc_now())
        asset_id = _plain_text(request["asset_id"], "asset_id", 50)
        asset = self.repository.get_asset(asset_id)
        if asset is None:
            raise TicketNotFoundError(f"Không tìm thấy asset: {asset_id}")
        if asset.values.get("lifecycle_status") in {"retired", "archived"}:
            raise TicketConflictError("Không thể tạo ticket cho asset đã ngừng hoặc lưu trữ.")

        category_id = _uuid(request.get("category_id"), "category_id", required=False)
        subcategory_id = _uuid(request.get("subcategory_id"), "subcategory_id", required=False)
        source_id = _uuid(request.get("intake_source_id"), "intake_source_id", required=False)
        group_id = _uuid(request.get("support_group_id"), "support_group_id", required=False)
        assigned_user_id = _uuid(
            request.get("assigned_user_id"), "assigned_user_id", required=False
        )
        self._validate_references(
            category_id=category_id,
            subcategory_id=subcategory_id,
            source_id=source_id,
            group_id=group_id,
        )
        assignee = None
        if assigned_user_id is not None:
            self._require_permission(actor, Permission.TICKETS_ASSIGN)
            assignee = self._active_assignee(assigned_user_id)

        impact = Impact(request["impact"])
        urgency = Urgency(request["urgency"])
        priority = calculate_priority(impact, urgency)
        failure_category = str(request.get("failure_category") or "no_failure")
        if failure_category not in FAILURE_CATEGORIES:
            raise TicketDomainError("failure_category không được hỗ trợ.")
        reporter_email = _optional_text(request.get("reporter_email"), 254)
        if reporter_email and not EMAIL_PATTERN.fullmatch(reporter_email):
            raise TicketDomainError("reporter_email không hợp lệ.")
        status = TicketStatus.ASSIGNED if assignee else TicketStatus.OPEN
        policy = self.repository.find_sla_policy(
            category_id=category_id,
            priority=priority.value,
            effective_date=current.astimezone(FACILITY_TIMEZONE).date(),
        )
        if policy is None:
            raise TicketConflictError(
                "Không có SLA policy đang hiệu lực cho ticket. Hãy seed hoặc cấu hình policy."
            )
        sla_values, sla_events = self._sla_snapshot(policy.values, started_at=current)
        values = {
            "asset_id": asset_id,
            "issue_description": _plain_text(
                request["issue_description"], "issue_description", 4000, minimum=5
            ),
            "priority": priority.value,
            "status": status.value,
            "failure_category": failure_category,
            "reporter_name": _optional_text(request.get("reporter_name"), 200),
            "reporter_email": reporter_email.casefold() if reporter_email else None,
            "reporter_phone": _optional_text(request.get("reporter_phone"), 40),
            "category_id": category_id,
            "subcategory_id": subcategory_id,
            "impact": impact.value,
            "urgency": urgency.value,
            "intake_source_id": source_id,
            "support_group_id": group_id,
            "assigned_user_id": assigned_user_id,
            "created_at": current,
            "resolved_at": None,
            "first_response_at": None,
            "waiting_reason": None,
            "waiting_previous_status": None,
            "closed_at": None,
            "reopened_at": None,
            "cancelled_at": None,
            "cancellation_reason": None,
            "reopen_count": 0,
            "technician_id": (
                str(assignee.values.get("technician_id") or "UNASSIGNED")
                if assignee
                else "UNASSIGNED"
            ),
            "manager_note": _optional_text(request.get("manager_note"), 1000),
            "note": None,
        }
        record = self.repository.create_ticket(
            values,
            sla_values=sla_values,
            sla_events=sla_events,
            audit_context=audit_context,
        )
        return self._present(record.values, actor=actor, as_of=current)

    def list_queue(
        self,
        queue_name: str,
        *,
        actor: CurrentUser,
        filters: dict[str, Any],
        page: int,
        page_size: int,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        return self.queries.list_queue(
            queue_name,
            actor=actor,
            filters=filters,
            page=page,
            page_size=page_size,
            as_of=as_of,
        )

    def get_ticket(
        self,
        ticket_id: str,
        *,
        actor: CurrentUser,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        return self.queries.get_ticket(ticket_id, actor=actor, as_of=as_of)

    def assign(
        self,
        ticket_id: str,
        *,
        assigned_user_id: UUID | None,
        support_group_id: UUID | None,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_ASSIGN)
        record = self._ticket_record(ticket_id)
        status = TicketStatus(record.values["status"])
        if status not in ASSIGNABLE_STATUSES:
            raise TicketConflictError("Chỉ ticket đang hoạt động mới được phân công.")
        assignee = self._active_assignee(assigned_user_id) if assigned_user_id else None
        if support_group_id is not None:
            group = self.repository.get_reference(SupportGroup, support_group_id)
            if group is None or not group.values.get("is_active"):
                raise TicketNotFoundError("Không tìm thấy support group đang hoạt động.")
        target_status = (
            TicketStatus.ASSIGNED.value
            if status in {TicketStatus.OPEN, TicketStatus.REOPENED} and assignee
            else status.value
        )
        updates = {
            "assigned_user_id": assigned_user_id,
            "support_group_id": support_group_id,
            "technician_id": (
                str(assignee.values.get("technician_id") or "UNASSIGNED")
                if assignee
                else "UNASSIGNED"
            ),
            "status": target_status,
        }
        result = self.repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates=updates,
            sla_updates=None,
            sla_events=[],
            audit_action="ticket.assigned",
            audit_context=audit_context,
            audit_metadata={
                "assigned_user_id": str(assigned_user_id) if assigned_user_id else None,
                "support_group_id": str(support_group_id) if support_group_id else None,
            },
        )
        return self._present(result.values, actor=actor)

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
        current = _aware_utc(now or _utc_now())
        sla = record.values.get("sla")
        events = self._sla_events_for_first_response(sla, current)
        result = self.repository.mutate_ticket(
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
        current = _aware_utc(now or _utc_now())
        updates: dict[str, Any] = {"status": TicketStatus.IN_PROGRESS.value}
        events: list[dict[str, Any]] = []
        if not record.values.get("first_response_at"):
            updates["first_response_at"] = current
            events.extend(self._sla_events_for_first_response(record.values.get("sla"), current))
        result = self.repository.mutate_ticket(
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
        current = _aware_utc(now or _utc_now())
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
                            _parse_datetime(sla["first_response_due_at"]),
                            current,
                            calendar=calendar,
                        )
                        or 0,
                    )
                ),
                "resolution_remaining_minutes": max(
                    0,
                    remaining_minutes(
                        _parse_datetime(sla["resolution_due_at"]),
                        current,
                        calendar=calendar,
                    )
                    or 0,
                ),
            }
            events.append(
                _sla_event("paused", current, sla["occurrence_number"], details={"reason": reason})
            )
        result = self.repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates={
                "status": TicketStatus.WAITING.value,
                "waiting_reason": _plain_text(reason, "reason", 1000),
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
        current = _aware_utc(now or _utc_now())
        sla = record.values.get("sla")
        sla_updates: dict[str, Any] | None = None
        events: list[dict[str, Any]] = []
        if sla and sla.get("paused_at"):
            calendar = BusinessCalendarDefinition.from_snapshot(sla["calendar_snapshot"])
            response_due = _parse_datetime(sla["first_response_due_at"])
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
            events.append(_sla_event("resumed", current, sla["occurrence_number"]))
        result = self.repository.mutate_ticket(
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
        if not self.repository.has_maintenance_log(ticket_id):
            raise TicketConflictError("Ticket cần có maintenance log trước khi resolve.")
        current = _aware_utc(resolved_at or _utc_now())
        if current < _parse_datetime(record.values["created_at"]):
            raise TicketDomainError("resolved_at không được sớm hơn created_at.")
        sla = record.values.get("sla")
        events: list[dict[str, Any]] = []
        sla_updates = None
        if sla:
            sla_updates = {"resolution_stopped_at": current}
            events.append(
                _sla_event(
                    "resolved",
                    current,
                    sla["occurrence_number"],
                    clock_type=SlaClockType.RESOLUTION.value,
                )
            )
            if current <= _parse_datetime(sla["resolution_due_at"]):
                events.append(
                    _sla_event(
                        "target_met",
                        current,
                        sla["occurrence_number"],
                        clock_type=SlaClockType.RESOLUTION.value,
                    )
                )
        result = self.repository.mutate_ticket(
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
        current = _aware_utc(now or _utc_now())
        result = self.repository.mutate_ticket(
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
        status = TicketStatus(record.values["status"])
        if status not in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
            raise TicketConflictError("Chỉ ticket resolved/closed mới được mở lại.")
        current = _aware_utc(now or _utc_now())
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
                    _sla_event("reopened", current, occurrence, details={"reason": reason}),
                    _sla_event(
                        "clock_started",
                        current,
                        occurrence,
                        clock_type=SlaClockType.RESOLUTION.value,
                    ),
                ]
            )
        result = self.repository.mutate_ticket(
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
            audit_metadata={"reason": _plain_text(reason, "reason", 1000)},
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
        status = TicketStatus(record.values["status"])
        if status not in ACTIVE_TICKET_STATUSES:
            raise TicketConflictError("Chỉ ticket đang hoạt động mới được hủy.")
        current = _aware_utc(now or _utc_now())
        sla = record.values.get("sla")
        events = (
            [
                _sla_event(
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
        result = self.repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates={
                "status": TicketStatus.CANCELLED.value,
                "cancelled_at": current,
                "cancellation_reason": _plain_text(reason, "reason", 1000),
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

    def change_priority(
        self,
        ticket_id: str,
        *,
        impact: str,
        urgency: str,
        reason: str,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_UPDATE)
        self._ticket_record(ticket_id)
        selected_impact = Impact(impact)
        selected_urgency = Urgency(urgency)
        priority = calculate_priority(selected_impact, selected_urgency)
        result = self.repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates={
                "impact": selected_impact.value,
                "urgency": selected_urgency.value,
                "priority": priority.value,
            },
            sla_updates=None,
            sla_events=[],
            audit_action="ticket.priority_changed",
            audit_context=audit_context,
            audit_metadata={"reason": _plain_text(reason, "reason", 1000)},
        )
        return self._present(result.values, actor=actor)

    def override_sla_policy(
        self,
        ticket_id: str,
        *,
        policy_id: UUID,
        reason: str,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.SLA_POLICIES_MANAGE)
        record = self._ticket_record(ticket_id)
        current = _aware_utc(now or _utc_now())
        policy = self.repository.find_sla_policy(
            category_id=_uuid(record.values.get("category_id"), "category_id", required=False),
            priority=str(record.values["priority"]),
            effective_date=current.astimezone(FACILITY_TIMEZONE).date(),
            policy_id=policy_id,
        )
        if policy is None:
            raise TicketNotFoundError("SLA policy không hoạt động hoặc thiếu target phù hợp.")
        current_occurrence = int((record.values.get("sla") or {}).get("occurrence_number", 0))
        sla_values, events = self._sla_snapshot(
            policy.values, started_at=current, occurrence_number=current_occurrence + 1
        )
        events[0]["details"] = {"reason": _plain_text(reason, "reason", 1000)}
        result = self.repository.replace_sla_policy(
            ticket_id,
            expected_version=expected_version,
            sla_values=sla_values,
            sla_events=events,
            audit_context=audit_context,
            reason=reason,
        )
        return self._present(result.values, actor=actor, as_of=current)

    def add_comment(
        self,
        ticket_id: str,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.comments.add_comment(
            ticket_id,
            request,
            actor=actor,
            audit_context=audit_context,
        )

    def list_calendars(self, *, actor: CurrentUser) -> list[dict[str, Any]]:
        return self.sla_administration.list_calendars(actor=actor)

    def create_calendar(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.sla_administration.create_calendar(
            request, actor=actor, audit_context=audit_context
        )

    def update_calendar(
        self,
        calendar_id: UUID,
        request: dict[str, Any],
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.sla_administration.update_calendar(
            calendar_id,
            request,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
        )

    def list_policies(self, *, actor: CurrentUser) -> list[dict[str, Any]]:
        return self.sla_administration.list_policies(actor=actor)

    def create_policy(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.sla_administration.create_policy(
            request, actor=actor, audit_context=audit_context
        )

    def update_policy(
        self,
        policy_id: UUID,
        request: dict[str, Any],
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.sla_administration.update_policy(
            policy_id,
            request,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
        )

    def sla_summary(self, *, actor: CurrentUser, as_of: datetime | None = None) -> dict[str, Any]:
        self._require_permission(actor, Permission.SLA_POLICIES_READ)
        current = _aware_utc(as_of or _utc_now())
        items = [
            self._present(record.values, actor=actor, as_of=current)
            for record in self.repository.list_tickets(filters={})
        ]
        active = [item for item in items if TicketStatus(item["status"]) in ACTIVE_TICKET_STATUSES]
        return {
            "as_of": current.isoformat(),
            "active_count": len(active),
            "waiting_count": sum(item["status"] == "waiting" for item in active),
            "critical_count": sum(item["priority"] == "critical" for item in active),
            "due_soon_count": sum(
                _has_sla_status(item, SlaClockStatus.DUE_SOON) for item in active
            ),
            "breached_count": sum(
                _has_sla_status(item, SlaClockStatus.BREACHED) for item in active
            ),
            "without_sla_count": sum(item.get("sla") is None for item in active),
        }

    def evaluate_escalations(
        self,
        *,
        dry_run: bool,
        actor: CurrentUser,
        audit_context: AuditContext,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        permission = Permission.ESCALATIONS_EVALUATE if dry_run else Permission.ESCALATIONS_EXECUTE
        self._require_permission(actor, permission)
        current = _aware_utc(as_of or _utc_now())
        candidates: list[dict[str, Any]] = []
        for record in self.repository.list_tickets(filters={}):
            item = self._present(record.values, actor=actor, as_of=current)
            if TicketStatus(item["status"]) not in ACTIVE_TICKET_STATUSES:
                continue
            sla = item.get("sla")
            occurrence = int((sla or {}).get("occurrence_number", 1))
            for clock_name, rule_due, rule_breach in (
                (
                    "first_response",
                    EscalationRule.FIRST_RESPONSE_DUE_SOON,
                    EscalationRule.FIRST_RESPONSE_BREACHED,
                ),
                (
                    "resolution",
                    EscalationRule.RESOLUTION_DUE_SOON,
                    EscalationRule.RESOLUTION_BREACHED,
                ),
            ):
                clock = (sla or {}).get(clock_name)
                if not clock:
                    continue
                status = SlaClockStatus(clock["status"])
                rule = (
                    rule_due
                    if status is SlaClockStatus.DUE_SOON
                    else rule_breach
                    if status is SlaClockStatus.BREACHED
                    else None
                )
                if rule:
                    candidates.append(
                        self._escalation_candidate(
                            item, rule, current, occurrence, clock_name, clock.get("due_at")
                        )
                    )
            if item["priority"] == TicketPriority.CRITICAL.value:
                candidates.append(
                    self._escalation_candidate(
                        item,
                        EscalationRule.CRITICAL_PRIORITY,
                        current,
                        occurrence,
                        None,
                        None,
                    )
                )
            if int(item["reopen_count"]) >= 2:
                candidates.append(
                    self._escalation_candidate(
                        item,
                        EscalationRule.REPEATED_REOPEN,
                        current,
                        int(item["reopen_count"]),
                        None,
                        None,
                    )
                )
        created = (
            []
            if dry_run
            else self.repository.record_escalations(candidates, audit_context=audit_context)
        )
        return {
            "dry_run": dry_run,
            "as_of": current.isoformat(),
            "candidate_count": len(candidates),
            "created_count": len(created),
            "candidates": [
                {
                    "ticket_id": item["ticket_id"],
                    "rule_code": item["rule_code"],
                    "rule_display": ESCALATION_RULE_LABELS[EscalationRule(item["rule_code"])],
                    "clock_type": item["clock_type"],
                    "occurrence_number": item["occurrence_number"],
                    "due_at": item["due_at"].isoformat() if item["due_at"] else None,
                }
                for item in candidates
            ],
        }

    def seed_defaults(self, *, actor: CurrentUser, audit_context: AuditContext) -> dict[str, int]:
        self._require_permission(actor, Permission.SLA_POLICIES_MANAGE)
        return self.repository.seed_defaults(actor_user_id=actor.id, audit_context=audit_context)

    def legacy_intake(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        priority_code = PRIORITY_VI_TO_CODE[str(request["priority"])]
        impact, urgency = legacy_priority_dimensions(priority_code)
        rich = self.intake(
            {
                "asset_id": request["asset_id"],
                "issue_description": request["issue_description"],
                "impact": impact.value,
                "urgency": urgency.value,
                "failure_category": FAILURE_TYPE_VI_TO_CODE[str(request["failure_category"])],
                "manager_note": request.get("manager_note"),
            },
            actor=actor,
            audit_context=audit_context,
        )
        requested_technician = str(request.get("technician_id") or "UNASSIGNED")
        if requested_technician != "UNASSIGNED":
            updated = self.repository.mutate_ticket(
                rich["ticket_id"],
                expected_version=rich["version"],
                ticket_updates={"technician_id": requested_technician},
                sla_updates=None,
                sla_events=[],
                audit_action="ticket.assigned_legacy",
                audit_context=audit_context,
            )
            rich = self._present(updated.values, actor=actor)
        return self.legacy_projection(rich)

    def legacy_update(
        self,
        ticket_id: str,
        updates: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        record = self._ticket_for_action(ticket_id, actor)
        version = int(record.values["version"])
        if "technician_id" in updates:
            result = self.repository.mutate_ticket(
                ticket_id,
                expected_version=version,
                ticket_updates={"technician_id": str(updates["technician_id"])},
                sla_updates=None,
                sla_events=[],
                audit_action="ticket.assigned_legacy",
                audit_context=audit_context,
            )
            record = result
            version = int(result.values["version"])
        if "priority" in updates:
            priority = PRIORITY_VI_TO_CODE[str(updates["priority"])]
            impact, urgency = legacy_priority_dimensions(priority)
            result = self.repository.mutate_ticket(
                ticket_id,
                expected_version=version,
                ticket_updates={
                    "impact": impact.value,
                    "urgency": urgency.value,
                    "priority": priority,
                },
                sla_updates=None,
                sla_events=[],
                audit_action="ticket.priority_changed_legacy",
                audit_context=audit_context,
            )
            record = result
            version = int(result.values["version"])
        if "note" in updates:
            result = self.repository.mutate_ticket(
                ticket_id,
                expected_version=version,
                ticket_updates={"note": _optional_text(updates["note"], 1000)},
                sla_updates=None,
                sla_events=[],
                audit_action="ticket.note_updated_legacy",
                audit_context=audit_context,
            )
            record = result
            version = int(result.values["version"])
        target_status = updates.get("status")
        if target_status == "Đang xử lý" and record.values["status"] != "in_progress":
            rich = self.start(
                ticket_id,
                expected_version=version,
                actor=actor,
                audit_context=audit_context,
            )
            version = int(rich["version"])
        elif target_status == "Đã xử lý" and record.values["status"] != "resolved":
            rich = self.resolve(
                ticket_id,
                expected_version=version,
                actor=actor,
                audit_context=audit_context,
                resolved_at=updates.get("resolved_at"),
            )
        elif target_status not in {None, "Mới tạo", "Đang xử lý", "Đã xử lý"}:
            raise TicketConflictError("Trạng thái legacy không được hỗ trợ.")
        else:
            latest = self._ticket_record(ticket_id)
            rich = self._present(latest.values, actor=actor)
        return self.legacy_projection(rich)

    @staticmethod
    def legacy_projection(ticket: dict[str, Any]) -> dict[str, Any]:
        status = TicketStatus(str(ticket["status"]))
        priority = TicketPriority(str(ticket["priority"]))
        return {
            "ticket_id": ticket["ticket_id"],
            "asset_id": ticket["asset_id"],
            "issue_description": ticket["issue_description"],
            "priority": PRIORITY_LABELS[priority],
            "status": LEGACY_STATUS_LABELS[status],
            "failure_category": FAILURE_TYPE_CODE_TO_VI[str(ticket["failure_category"])],
            "created_at": ticket["created_at"],
            "resolved_at": ticket.get("resolved_at"),
            "technician_id": ticket["technician_id"],
            "manager_note": ticket.get("manager_note"),
            "note": ticket.get("note"),
        }

    def _present(
        self,
        values: dict[str, Any],
        *,
        actor: CurrentUser,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        current = _aware_utc(as_of or _utc_now())
        result = dict(values)
        status = TicketStatus(result["status"])
        impact = Impact(result["impact"])
        urgency = Urgency(result["urgency"])
        priority = TicketPriority(result["priority"])
        result.update(
            {
                "status_display": TICKET_STATUS_LABELS[status],
                "impact_display": IMPACT_LABELS[impact],
                "urgency_display": URGENCY_LABELS[urgency],
                "priority_display": PRIORITY_LABELS[priority],
                "failure_category_display": FAILURE_TYPE_CODE_TO_VI[result["failure_category"]],
            }
        )
        if not actor.has(Permission.TICKET_PII_READ):
            result["reporter_name"] = None
            result["reporter_email"] = None
            result["reporter_phone"] = None
            result["reporter_redacted"] = True
        else:
            result["reporter_redacted"] = False
        comments = result.get("comments")
        if isinstance(comments, list) and not actor.has(Permission.TICKET_COMMENTS_INTERNAL):
            result["comments"] = [
                item for item in comments if item.get("visibility") == "requester"
            ]
        sla = result.get("sla")
        if sla:
            result["sla"] = self._present_sla(result, dict(sla), current)
        return result

    def _present_sla(
        self, ticket: dict[str, Any], sla: dict[str, Any], as_of: datetime
    ) -> dict[str, Any]:
        calendar = BusinessCalendarDefinition.from_snapshot(sla["calendar_snapshot"])
        paused = _parse_datetime(sla.get("paused_at"))
        stopped = ticket["status"] == TicketStatus.CANCELLED.value
        response_status = derive_clock_status(
            started_at=_parse_datetime(sla["started_at"]),
            due_at=_parse_datetime(sla["first_response_due_at"]),
            completed_at=_parse_datetime(ticket.get("first_response_at")),
            paused_at=paused,
            target_minutes=int(sla["first_response_target_minutes"]),
            as_of=as_of,
            calendar=calendar,
            due_soon_percent=int(sla["due_soon_percent"]),
            stopped=stopped,
        )
        resolution_status = derive_clock_status(
            started_at=_parse_datetime(sla["started_at"]),
            due_at=_parse_datetime(sla["resolution_due_at"]),
            completed_at=_parse_datetime(ticket.get("resolved_at")),
            paused_at=paused,
            target_minutes=int(sla["resolution_target_minutes"]),
            as_of=as_of,
            calendar=calendar,
            due_soon_percent=int(sla["due_soon_percent"]),
            stopped=stopped,
        )
        sla["first_response"] = _clock_values(
            response_status,
            due_at=sla["first_response_due_at"],
            completed_at=ticket.get("first_response_at"),
            remaining=(
                sla.get("first_response_remaining_minutes")
                if response_status is SlaClockStatus.PAUSED
                else remaining_minutes(
                    _parse_datetime(sla["first_response_due_at"]),
                    as_of,
                    calendar=calendar,
                )
            ),
        )
        sla["resolution"] = _clock_values(
            resolution_status,
            due_at=sla["resolution_due_at"],
            completed_at=ticket.get("resolved_at"),
            remaining=(
                sla.get("resolution_remaining_minutes")
                if resolution_status is SlaClockStatus.PAUSED
                else remaining_minutes(
                    _parse_datetime(sla["resolution_due_at"]),
                    as_of,
                    calendar=calendar,
                )
            ),
        )
        return sla

    def _validate_references(
        self,
        *,
        category_id: UUID | None,
        subcategory_id: UUID | None,
        source_id: UUID | None,
        group_id: UUID | None,
    ) -> None:
        category = (
            self.repository.get_reference(TicketCategory, category_id) if category_id else None
        )
        if category_id and (category is None or not category.values.get("is_active")):
            raise TicketNotFoundError("Không tìm thấy category đang hoạt động.")
        if subcategory_id:
            subcategory = self.repository.get_reference(TicketSubcategory, subcategory_id)
            if subcategory is None or not subcategory.values.get("is_active"):
                raise TicketNotFoundError("Không tìm thấy subcategory đang hoạt động.")
            if str(subcategory.values["category_id"]) != str(category_id):
                raise TicketConflictError("Subcategory không thuộc category đã chọn.")
        for identifier, model, label in (
            (source_id, TicketIntakeSource, "intake source"),
            (group_id, SupportGroup, "support group"),
        ):
            if identifier:
                record = self.repository.get_reference(model, identifier)
                if record is None or not record.values.get("is_active"):
                    raise TicketNotFoundError(f"Không tìm thấy {label} đang hoạt động.")

    def _active_assignee(self, user_id: UUID) -> StoredRecord:
        record = self.repository.get_user(user_id)
        if record is None or not record.values.get("is_active"):
            raise TicketNotFoundError("Không tìm thấy assignee đang hoạt động.")
        if record.values.get("role") not in {"chief_engineer", "technician", "helpdesk"}:
            raise TicketConflictError("Vai trò người dùng không thể nhận ticket.")
        return record

    def _sla_snapshot(
        self,
        policy: dict[str, Any],
        *,
        started_at: datetime,
        occurrence_number: int = 1,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        calendar_data = policy.get("calendar")
        targets = policy.get("targets") or []
        if not calendar_data or len(targets) != 1:
            raise TicketConflictError("SLA policy thiếu calendar hoặc target.")
        if policy["timezone"] != calendar_data["timezone"]:
            raise TicketConflictError("Timezone của SLA policy và calendar không khớp.")
        calendar = BusinessCalendarDefinition.from_snapshot(
            {
                "timezone": calendar_data["timezone"],
                "periods": calendar_data["periods"],
                "holidays": [item["holiday_date"] for item in calendar_data["holidays"]],
            }
        )
        target = targets[0]
        response_minutes = int(target["first_response_minutes"])
        resolution_minutes = int(target["resolution_minutes"])
        values = {
            "policy_id": UUID(policy["id"]),
            "policy_code": policy["code"],
            "policy_name": policy["name"],
            "calendar_id": UUID(policy["calendar_id"]),
            "calendar_code": policy["calendar_code"],
            "timezone": policy["timezone"],
            "calendar_snapshot": calendar.to_snapshot(),
            "pause_on_waiting": bool(policy["pause_on_waiting"]),
            "due_soon_percent": int(policy["due_soon_percent"]),
            "first_response_target_minutes": response_minutes,
            "resolution_target_minutes": resolution_minutes,
            "started_at": started_at,
            "first_response_due_at": calendar.add_working_minutes(started_at, response_minutes),
            "resolution_due_at": calendar.add_working_minutes(started_at, resolution_minutes),
            "first_response_remaining_minutes": None,
            "resolution_remaining_minutes": None,
            "paused_at": None,
            "resolution_stopped_at": None,
            "occurrence_number": occurrence_number,
        }
        events = [
            _sla_event(
                "policy_applied",
                started_at,
                occurrence_number,
                details={"policy_code": policy["code"]},
            ),
            _sla_event(
                "clock_started",
                started_at,
                occurrence_number,
                clock_type=SlaClockType.FIRST_RESPONSE.value,
            ),
            _sla_event(
                "clock_started",
                started_at,
                occurrence_number,
                clock_type=SlaClockType.RESOLUTION.value,
            ),
        ]
        return values, events

    def _sla_events_for_first_response(
        self, sla: dict[str, Any] | None, current: datetime
    ) -> list[dict[str, Any]]:
        if not sla:
            return []
        events = [
            _sla_event(
                "first_response_recorded",
                current,
                sla["occurrence_number"],
                clock_type=SlaClockType.FIRST_RESPONSE.value,
            )
        ]
        if current <= _parse_datetime(sla["first_response_due_at"]):
            events.append(
                _sla_event(
                    "target_met",
                    current,
                    sla["occurrence_number"],
                    clock_type=SlaClockType.FIRST_RESPONSE.value,
                )
            )
        return events

    def _calendar_values(self, request: dict[str, Any], *, actor: CurrentUser) -> dict[str, Any]:
        periods = [
            WorkingPeriod(
                weekday=int(item["weekday"]),
                start_time=_as_time(item["start_time"]),
                end_time=_as_time(item["end_time"]),
            )
            for item in request["periods"]
        ]
        holidays = frozenset(_as_date(item["holiday_date"]) for item in request["holidays"])
        definition = BusinessCalendarDefinition(
            timezone=str(request["timezone"]),
            periods=tuple(periods),
            holidays=holidays,
        )
        definition.validate()
        code = str(request.get("code") or "").strip().upper()
        if code and not CODE_PATTERN.fullmatch(code):
            raise TicketDomainError("Calendar code phải là mã in hoa 3-50 ký tự.")
        return {
            "code": code,
            "name": _plain_text(request["name"], "name", 160),
            "timezone": definition.timezone,
            "is_active": bool(request.get("is_active", True)),
            "created_by_user_id": actor.id,
            "updated_by_user_id": actor.id,
            "periods": [
                {
                    "weekday": item.weekday,
                    "start_time": item.start_time,
                    "end_time": item.end_time,
                }
                for item in periods
            ],
            "holidays": [
                {
                    "holiday_date": _as_date(item["holiday_date"]),
                    "name": _plain_text(item["name"], "holiday name", 160),
                }
                for item in request["holidays"]
            ],
        }

    def _policy_values(self, request: dict[str, Any], *, actor: CurrentUser) -> dict[str, Any]:
        calendar_id = UUID(str(request["calendar_id"]))
        calendars = {
            item["id"]: item
            for item in (record.values for record in self.repository.list_calendars())
        }
        calendar = calendars.get(str(calendar_id))
        if calendar is None:
            raise TicketNotFoundError("Không tìm thấy business calendar.")
        timezone_name = str(request["timezone"])
        if timezone_name != calendar["timezone"]:
            raise TicketConflictError("Timezone của policy phải khớp business calendar.")
        targets = [dict(item) for item in request["targets"]]
        priorities = {str(item["priority"]) for item in targets}
        if priorities != {item.value for item in TicketPriority} or len(targets) != 4:
            raise TicketDomainError("SLA policy cần đúng một target cho mỗi priority.")
        for item in targets:
            if int(item["first_response_minutes"]) <= 0 or int(item["resolution_minutes"]) <= 0:
                raise TicketDomainError("SLA target phải lớn hơn 0 phút.")
        code = str(request.get("code") or "").strip().upper()
        if code and not CODE_PATTERN.fullmatch(code):
            raise TicketDomainError("SLA policy code phải là mã in hoa 3-50 ký tự.")
        category_id = _uuid(request.get("category_id"), "category_id", required=False)
        if category_id and self.repository.get_reference(TicketCategory, category_id) is None:
            raise TicketNotFoundError("Không tìm thấy ticket category.")
        effective_from = _as_date(request["effective_from"])
        effective_to = _as_date(request["effective_to"]) if request.get("effective_to") else None
        if effective_to and effective_to < effective_from:
            raise TicketDomainError("effective_to không được sớm hơn effective_from.")
        return {
            "code": code,
            "name": _plain_text(request["name"], "name", 200),
            "calendar_id": calendar_id,
            "category_id": category_id,
            "timezone": timezone_name,
            "pause_on_waiting": bool(request.get("pause_on_waiting", True)),
            "due_soon_percent": int(request.get("due_soon_percent", 20)),
            "effective_from": effective_from,
            "effective_to": effective_to,
            "is_active": bool(request.get("is_active", True)),
            "created_by_user_id": actor.id,
            "updated_by_user_id": actor.id,
            "targets": [
                {
                    "priority": str(item["priority"]),
                    "first_response_minutes": int(item["first_response_minutes"]),
                    "resolution_minutes": int(item["resolution_minutes"]),
                }
                for item in targets
            ],
        }

    def _ticket_record(self, ticket_id: str, *, include_timeline: bool = False) -> StoredRecord:
        record = self.repository.get_ticket(ticket_id, include_timeline=include_timeline)
        if record is None:
            raise TicketNotFoundError(f"Không tìm thấy ticket: {ticket_id}")
        return record

    def _ticket_for_action(self, ticket_id: str, actor: CurrentUser) -> StoredRecord:
        record = self._ticket_record(ticket_id)
        self._require_ticket_access(actor, record.values)
        return record

    def _require_ticket_access(self, actor: CurrentUser, ticket: dict[str, Any]) -> None:
        if actor.role is Role.TECHNICIAN and not self._is_owned(actor, ticket):
            raise TicketAuthorizationError(
                "Ticket không được phân công cho kỹ thuật viên đang đăng nhập."
            )

    @staticmethod
    def _is_owned(actor: CurrentUser, ticket: dict[str, Any]) -> bool:
        return bool(
            ticket.get("assigned_user_id") == str(actor.id)
            or (actor.technician_id and ticket.get("technician_id") == actor.technician_id)
        )

    @staticmethod
    def _require_permission(actor: CurrentUser, permission: Permission) -> None:
        if not actor.has(permission):
            raise TicketAuthorizationError("Bạn không có quyền thực hiện thao tác ticket này.")

    @staticmethod
    def _in_queue(
        queue: TicketQueue,
        ticket: dict[str, Any],
        actor: CurrentUser,
        as_of: datetime,
    ) -> bool:
        if queue is TicketQueue.ALL:
            return True
        if queue is TicketQueue.UNASSIGNED:
            return ticket.get("assigned_user_id") is None
        if queue is TicketQueue.ASSIGNED_TO_ME:
            return ticket.get("assigned_user_id") == str(actor.id)
        if queue is TicketQueue.ASSIGNED_TO_QUEUE:
            return ticket.get("support_group_id") is not None
        if queue is TicketQueue.CRITICAL:
            return ticket["priority"] == TicketPriority.CRITICAL.value
        if queue is TicketQueue.DUE_SOON:
            return _has_sla_status(ticket, SlaClockStatus.DUE_SOON)
        if queue is TicketQueue.BREACHED:
            return _has_sla_status(ticket, SlaClockStatus.BREACHED)
        if queue is TicketQueue.WAITING:
            return ticket["status"] == TicketStatus.WAITING.value
        if queue is TicketQueue.RECENTLY_RESOLVED:
            resolved_at = _parse_datetime(ticket.get("resolved_at"))
            return bool(resolved_at and resolved_at >= as_of - timedelta(days=7))
        if queue is TicketQueue.REOPENED:
            return (
                ticket["status"] == TicketStatus.REOPENED.value or int(ticket["reopen_count"]) > 0
            )
        return False

    @staticmethod
    def _escalation_candidate(
        ticket: dict[str, Any],
        rule: EscalationRule,
        current: datetime,
        occurrence: int,
        clock_type: str | None,
        due_at: str | None,
    ) -> dict[str, Any]:
        sla = ticket.get("sla")
        return {
            "ticket_id": ticket["ticket_id"],
            "ticket_sla_id": UUID(sla["id"]) if sla else None,
            "rule_code": rule.value,
            "clock_type": clock_type,
            "occurrence_number": occurrence,
            "detected_at": current,
            "due_at": _parse_datetime(due_at),
            "details": {
                "priority": ticket["priority"],
                "status": ticket["status"],
            },
        }


def _sla_event(
    event_type: str,
    occurred_at: datetime,
    occurrence_number: int,
    *,
    clock_type: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "clock_type": clock_type,
        "occurrence_number": int(occurrence_number),
        "occurred_at": occurred_at,
        "details": details,
    }


def _clock_values(
    status: SlaClockStatus,
    *,
    due_at: str,
    completed_at: str | None,
    remaining: int | None,
) -> dict[str, Any]:
    return {
        "status": status.value,
        "status_display": SLA_STATUS_LABELS[status],
        "due_at": due_at,
        "completed_at": completed_at,
        "remaining_business_minutes": remaining,
    }


def _has_sla_status(ticket: dict[str, Any], status: SlaClockStatus) -> bool:
    sla = ticket.get("sla") or {}
    return any(
        (sla.get(clock) or {}).get("status") == status.value
        for clock in ("first_response", "resolution")
    )


def _queue_sort_key(ticket: dict[str, Any]) -> tuple[Any, ...]:
    sla = ticket.get("sla") or {}
    due_values = [
        _parse_datetime((sla.get(clock) or {}).get("due_at"))
        for clock in ("first_response", "resolution")
    ]
    due_values = [value for value in due_values if value is not None]
    nearest_due = min(due_values) if due_values else datetime.max.replace(tzinfo=timezone.utc)
    return (
        PRIORITY_RANK.get(str(ticket["priority"]), 9),
        nearest_due,
        -_parse_datetime(ticket["created_at"]).timestamp(),
        ticket["ticket_id"],
    )


def _options(labels: dict[Any, str]) -> list[dict[str, str]]:
    return [
        {"code": item.value if hasattr(item, "value") else str(item), "display_name": label}
        for item, label in labels.items()
    ]


def _plain_text(value: object, field: str, maximum: int, *, minimum: int = 1) -> str:
    normalized = str(value).strip()
    if len(normalized) < minimum or len(normalized) > maximum:
        raise TicketDomainError(f"{field} phải có {minimum}-{maximum} ký tự.")
    return normalized


def _optional_text(value: object, maximum: int) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise TicketDomainError(f"Nội dung không được vượt quá {maximum} ký tự.")
    return normalized


def _uuid(value: object, field: str, *, required: bool) -> UUID | None:
    if value is None or not str(value).strip():
        if required:
            raise TicketDomainError(f"{field} là bắt buộc.")
        return None
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise TicketDomainError(f"{field} không phải UUID hợp lệ.") from exc


def _parse_datetime(value: object) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return _aware_utc(parsed)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TicketDomainError("Timestamp phải có timezone.")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _as_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _as_time(value: object) -> time:
    return value if isinstance(value, time) else time.fromisoformat(str(value))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def build_ticket_workflow_service() -> TicketWorkflowService:
    """Compatibility builder delegated to the explicit composition root."""

    from src.composition.tickets import build_ticket_workflow_service as build

    return build()

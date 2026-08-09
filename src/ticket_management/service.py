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
from src.repositories.contracts import StoredRecord, TicketReferenceKind, TicketRepository
from src.security.audit import AuditContext
from src.security.permissions import Permission, Role
from src.security.principal import CurrentUser
from src.ticket_management.application.comment_service import TicketCommentService
from src.ticket_management.application.catalogue_service import TicketCatalogueService
from src.ticket_management.application.escalation_service import TicketEscalationService
from src.ticket_management.application.query_service import TicketQueryService
from src.ticket_management.application.assignment_service import TicketAssignmentService
from src.ticket_management.application.intake_service import TicketIntakeService
from src.ticket_management.application.lifecycle_service import TicketLifecycleService
from src.ticket_management.application.mutation_service import TicketMutationService
from src.ticket_management.application.sla_runtime_service import TicketSlaRuntimeService
from src.ticket_management.application.sla_service import TicketSlaAdministrationService
from src.ticket_management.errors import (
    TicketAuthorizationError,
    TicketConflictError,
    TicketDomainError,
    TicketNotFoundError,
)
from src.ticket_management.domain import (
    IMPACT_LABELS,
    LEGACY_STATUS_LABELS,
    PRIORITY_LABELS,
    TICKET_STATUS_LABELS,
    URGENCY_LABELS,
    Impact,
    SlaClockStatus,
    TicketPriority,
    TicketQueue,
    TicketStatus,
    Urgency,
    legacy_priority_dimensions,
)
from src.ticket_management.sla import BusinessCalendarDefinition, WorkingPeriod

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
        self.assignment = TicketAssignmentService(
            repository,
            require_permission=self._require_permission,
            ticket_record=self._ticket_record,
            active_assignee=self._active_assignee,
            present=self._present,
        )
        self.sla_runtime = TicketSlaRuntimeService(
            repository,
            require_permission=self._require_permission,
            ticket_record=self._ticket_record,
            parse_uuid=_uuid,
            normalize_datetime=_aware_utc,
            normalize_text=_plain_text,
            utc_now=_utc_now,
            facility_timezone=FACILITY_TIMEZONE,
        )
        self.escalation = TicketEscalationService(
            repository,
            require_permission=self._require_permission,
            normalize_datetime=_aware_utc,
            utc_now=_utc_now,
        )
        self.mutations = TicketMutationService(
            repository,
            require_permission=self._require_permission,
            ticket_record=self._ticket_record,
            normalize_text=_plain_text,
            present=self._present,
        )
        self._lifecycle_service = TicketLifecycleService(
            repository,
            require_permission=self._require_permission,
            ticket_record=self._ticket_record,
            ticket_for_action=self._ticket_for_action,
            sla_events_for_first_response=self.sla_runtime.events_for_first_response,
            sla_event=_sla_event,
            present=self._present,
            normalize_datetime=_aware_utc,
            parse_datetime=_parse_datetime,
            normalize_text=_plain_text,
            utc_now=_utc_now,
        )
        self._intake_service = TicketIntakeService(
            repository,
            require_permission=self._require_permission,
            validate_references=self._validate_references,
            active_assignee=self._active_assignee,
            sla_snapshot=self.sla_runtime.snapshot,
            present=self._present,
            normalize_text=_plain_text,
            optional_text=_optional_text,
            parse_uuid=_uuid,
            normalize_datetime=_aware_utc,
            utc_now=_utc_now,
            facility_timezone=FACILITY_TIMEZONE,
            failure_categories=FAILURE_CATEGORIES,
            email_pattern=EMAIL_PATTERN,
        )
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
        return self._intake_service.intake(
            request,
            actor=actor,
            audit_context=audit_context,
            now=now,
        )

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
        return self.assignment.assign(
            ticket_id,
            assigned_user_id=assigned_user_id,
            support_group_id=support_group_id,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
        )


    def acknowledge(
        self,
        ticket_id: str,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return self._lifecycle_service.acknowledge(
            ticket_id,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
            now=now,
        )

    def start(
        self,
        ticket_id: str,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return self._lifecycle_service.start(
            ticket_id,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
            now=now,
        )

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
        return self._lifecycle_service.hold(
            ticket_id,
            reason=reason,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
            now=now,
        )

    def resume(
        self,
        ticket_id: str,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return self._lifecycle_service.resume(
            ticket_id,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
            now=now,
        )

    def resolve(
        self,
        ticket_id: str,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        resolved_at: datetime | None = None,
    ) -> dict[str, Any]:
        return self._lifecycle_service.resolve(
            ticket_id,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
            resolved_at=resolved_at,
        )

    def close(
        self,
        ticket_id: str,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return self._lifecycle_service.close(
            ticket_id,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
            now=now,
        )

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
        return self._lifecycle_service.reopen(
            ticket_id,
            reason=reason,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
            now=now,
        )

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
        return self._lifecycle_service.cancel(
            ticket_id,
            reason=reason,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
            now=now,
        )

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
        return self.mutations.change_priority(
            ticket_id, impact=impact, urgency=urgency, reason=reason,
            expected_version=expected_version, actor=actor, audit_context=audit_context,
        )

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
        outcome = self.sla_runtime.override_policy(
            ticket_id,
            policy_id=policy_id,
            reason=reason,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
            now=now,
        )
        return self._present(
            outcome.record.values, actor=actor, as_of=outcome.occurred_at
        )

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
        return self.sla_runtime.summary(actor=actor, as_of=as_of)

    def evaluate_escalations(
        self,
        *,
        dry_run: bool,
        actor: CurrentUser,
        audit_context: AuditContext,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        return self.escalation.evaluate(
            dry_run=dry_run,
            actor=actor,
            audit_context=audit_context,
            as_of=as_of,
        )

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
            result["sla"] = self.sla_runtime.present(result, dict(sla), current)
        return result

    def _validate_references(
        self,
        *,
        category_id: UUID | None,
        subcategory_id: UUID | None,
        source_id: UUID | None,
        group_id: UUID | None,
    ) -> None:
        category = (
            self.repository.get_reference(TicketReferenceKind.CATEGORY, category_id)
            if category_id
            else None
        )
        if category_id and (category is None or not category.values.get("is_active")):
            raise TicketNotFoundError("Không tìm thấy category đang hoạt động.")
        if subcategory_id:
            subcategory = self.repository.get_reference(TicketReferenceKind.SUBCATEGORY, subcategory_id)
            if subcategory is None or not subcategory.values.get("is_active"):
                raise TicketNotFoundError("Không tìm thấy subcategory đang hoạt động.")
            if str(subcategory.values["category_id"]) != str(category_id):
                raise TicketConflictError("Subcategory không thuộc category đã chọn.")
        for identifier, kind, label in (
            (source_id, TicketReferenceKind.INTAKE_SOURCE, "intake source"),
            (group_id, TicketReferenceKind.SUPPORT_GROUP, "support group"),
        ):
            if identifier:
                record = self.repository.get_reference(kind, identifier)
                if record is None or not record.values.get("is_active"):
                    raise TicketNotFoundError(f"Không tìm thấy {label} đang hoạt động.")

    def _active_assignee(self, user_id: UUID) -> StoredRecord:
        record = self.repository.get_user(user_id)
        if record is None or not record.values.get("is_active"):
            raise TicketNotFoundError("Không tìm thấy assignee đang hoạt động.")
        if record.values.get("role") not in {"chief_engineer", "technician", "helpdesk"}:
            raise TicketConflictError("Vai trò người dùng không thể nhận ticket.")
        return record

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
        if (
            category_id
            and self.repository.get_reference(TicketReferenceKind.CATEGORY, category_id) is None
        ):
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

    from src.ticket_management.compatibility import build_ticket_workflow_service as build

    return build()

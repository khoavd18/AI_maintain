"""Business rules for preventive plans and standalone work orders."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from src.asset_management.storage import (
    AttachmentStorage,
)
from src.config.value_mappings import (
    MAINTENANCE_RESULT_CODE_TO_VI,
    MAINTENANCE_RESULT_VI_TO_CODE,
    PRIORITY_CODE_TO_VI,
)
from src.maintenance_management.domain import (
    WORK_ORDER_TRANSITIONS,
    ChecklistResponseType,
    ChecklistResultStatus,
    IntervalUnit,
    WorkOrderStatus,
    WorkOrderType,
)
from src.maintenance_management.recurrence import (
    MAX_OCCURRENCES,
    RecurrenceSpec,
    advance_occurrence,
    first_occurrence_on_or_after,
    occurrences_between,
)
from src.repositories.contracts import (
    MaintenancePlanningRepository,
    StoredPage,
    StoredRecord,
    UnsupportedStorageOperationError,
)
from src.security.audit import AuditContext
from src.security.permissions import Role
from src.security.principal import CurrentUser
from src.maintenance_management.application.catalogue_service import MaintenanceCatalogueService
from src.maintenance_management.application.evidence_service import (
    EvidenceDownload,
    MaintenanceEvidenceService,
)
from src.maintenance_management.application.query_service import MaintenanceQueryService
from src.maintenance_management.application.template_service import MaintenanceTemplateService
from src.maintenance_management.errors import (
    MaintenanceAuthorizationError,
    MaintenanceConflictError,
    MaintenanceDomainError,
    MaintenanceNotFoundError,
)

PLAN_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,49}$")
TEMPLATE_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,49}$")
MAX_CATCH_UP_DAYS = 366


class MaintenancePlanningService:
    """Canonical service boundary for plans, checklists, and work orders."""

    def __init__(
        self,
        repository: MaintenancePlanningRepository | None,
        attachment_storage: AttachmentStorage,
        *,
        attachment_max_size_bytes: int,
    ) -> None:
        self.repository = repository
        self.attachment_storage = attachment_storage
        self.attachment_max_size_bytes = attachment_max_size_bytes
        self.catalogue = MaintenanceCatalogueService(self._repository, self.get_plan)
        self.evidence = MaintenanceEvidenceService(
            self._repository,
            attachment_storage,
            attachment_max_size_bytes=attachment_max_size_bytes,
            get_work_order=self._work_order_record,
            require_work_order_access=self._require_work_order_access,
        )
        self.queries = MaintenanceQueryService(
            self._repository,
            get_plan=lambda plan_id: dict(self._plan_record(plan_id).values),
            get_work_order_record=self._work_order_record,
            require_work_order_access=self._require_work_order_access,
            scope_work_order=self._scope_work_order,
        )
        self.templates = MaintenanceTemplateService(
            self._repository,
            lambda value, field: _normalized_code(value, TEMPLATE_CODE_PATTERN, field),
            _plain_text,
            _optional_plain_text,
            _validate_template_items,
            _page_values,
        )

    def options(self) -> dict[str, Any]:
        return self.catalogue.options()

    def list_plans(
        self,
        *,
        asset_id: str | None,
        status: str | None,
        search: str | None,
        due_from: date | None,
        due_to: date | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self.queries.list_plans(
            asset_id=asset_id,
            status=status,
            search=search,
            due_from=due_from,
            due_to=due_to,
            page=page,
            page_size=page_size,
        )

    def get_plan(self, plan_id: UUID) -> dict[str, Any]:
        return self.queries.get_plan(plan_id)

    def create_plan(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        plan_code = _normalized_code(request["plan_code"], PLAN_CODE_PATTERN, "plan_code")
        asset = self._asset(request["asset_id"])
        self._require_asset_eligible(asset, "tạo maintenance plan")
        spec = _recurrence_spec(request)
        spec.validate()
        if request.get("recurrence_rule"):
            raise MaintenanceDomainError(
                "Milestone này chỉ nhận interval có kiểm soát, không nhận raw RRULE."
            )
        assignee_id = request.get("default_assignee_user_id")
        if assignee_id:
            self._require_eligible_technician(assignee_id)
        template_id = request.get("checklist_template_id")
        if template_id:
            self._require_template_usable(template_id, asset_type=asset["asset_type"])
        _require_priority_code(request["default_priority"])
        values = {
            **request,
            "plan_code": plan_code,
            "name": _plain_text(request["name"], "name", max_length=200),
            "description": _optional_plain_text(
                request.get("description"), "description", max_length=2000
            ),
            "instructions": _optional_plain_text(
                request.get("instructions"), "instructions", max_length=4000
            ),
            "schedule_type": "interval",
            "recurrence_rule": None,
            "next_due_date": spec.start_date,
            "last_generated_due_date": None,
            "status": "active",
            "is_active": True,
            "paused_at": None,
            "archived_at": None,
            "archive_reason": None,
            "created_by_user_id": actor.id,
            "updated_by_user_id": actor.id,
        }
        return dict(
            self._repository().create_plan(values, audit_context=audit_context).values
        )

    def update_plan(
        self,
        plan_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        if not updates:
            raise MaintenanceDomainError("Cần cung cấp ít nhất một trường cập nhật.")
        current = dict(self._plan_record(plan_id).values)
        if current["status"] == "archived":
            raise MaintenanceConflictError("Plan archived chỉ được đọc, không thể cập nhật.")
        nullable_fields = {
            "description",
            "end_date",
            "default_assignee_user_id",
            "checklist_template_id",
            "instructions",
        }
        invalid_null_fields = sorted(
            field
            for field, value in updates.items()
            if value is None and field not in nullable_fields
        )
        if invalid_null_fields:
            raise MaintenanceDomainError(
                "Không được để trống các trường bắt buộc: "
                + ", ".join(invalid_null_fields)
                + "."
            )
        merged = {**current, **updates}
        if "name" in updates:
            updates["name"] = _plain_text(updates["name"], "name", max_length=200)
        for field, limit in (("description", 2000), ("instructions", 4000)):
            if field in updates:
                updates[field] = _optional_plain_text(
                    updates[field], field, max_length=limit
                )
        if "default_priority" in updates:
            _require_priority_code(updates["default_priority"])
        schedule_fields = {
            "interval_value",
            "interval_unit",
            "start_date",
            "end_date",
            "local_timezone",
        }
        schedule_changed = bool(schedule_fields & updates.keys())
        if schedule_changed:
            spec = _recurrence_spec(merged)
            spec.validate()
            last_generated = _as_optional_date(current["last_generated_due_date"])
            if last_generated:
                next_due = first_occurrence_on_or_after(
                    spec, last_generated + timedelta(days=1)
                )
            else:
                next_due = spec.start_date
            updates["next_due_date"] = next_due
        if "default_assignee_user_id" in updates and updates["default_assignee_user_id"]:
            self._require_eligible_technician(updates["default_assignee_user_id"])
        if "checklist_template_id" in updates and updates["checklist_template_id"]:
            asset = self._asset(current["asset_id"])
            self._require_template_usable(
                updates["checklist_template_id"], asset_type=asset["asset_type"]
            )
        updates["updated_by_user_id"] = actor.id
        actions = ["maintenance_plan.updated"]
        if schedule_changed:
            actions.append("maintenance_plan.schedule_changed")
        return dict(
            self._repository()
            .update_plan(
                plan_id,
                updates,
                expected_version=expected_version,
                audit_actions=actions,
                audit_context=audit_context,
            )
            .values
        )

    def pause_plan(
        self,
        plan_id: UUID,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self.get_plan(plan_id)
        if current["status"] != "active":
            raise MaintenanceConflictError("Chỉ plan active mới có thể tạm dừng.")
        return dict(
            self._repository()
            .update_plan(
                plan_id,
                {
                    "status": "paused",
                    "is_active": False,
                    "paused_at": _utc_now(),
                    "updated_by_user_id": actor.id,
                },
                expected_version=expected_version,
                audit_actions=["maintenance_plan.paused"],
                audit_context=audit_context,
            )
            .values
        )

    def resume_plan(
        self,
        plan_id: UUID,
        *,
        expected_version: int,
        resume_date: date,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self.get_plan(plan_id)
        if current["status"] != "paused":
            raise MaintenanceConflictError("Chỉ plan paused mới có thể resume.")
        spec = _recurrence_spec(current)
        next_due = first_occurrence_on_or_after(spec, max(resume_date, spec.start_date))
        if next_due is None:
            raise MaintenanceConflictError(
                "Plan đã qua end_date; hãy cập nhật schedule trước khi resume."
            )
        return dict(
            self._repository()
            .update_plan(
                plan_id,
                {
                    "status": "active",
                    "is_active": True,
                    "paused_at": None,
                    "next_due_date": next_due,
                    "updated_by_user_id": actor.id,
                },
                expected_version=expected_version,
                audit_actions=["maintenance_plan.resumed"],
                audit_context=audit_context,
            )
            .values
        )

    def archive_plan(
        self,
        plan_id: UUID,
        *,
        expected_version: int,
        archive_reason: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self.get_plan(plan_id)
        if current["status"] == "archived":
            raise MaintenanceConflictError("Plan đã được archive.")
        reason = _required_text(archive_reason, "archive_reason", max_length=1000)
        return dict(
            self._repository()
            .update_plan(
                plan_id,
                {
                    "status": "archived",
                    "is_active": False,
                    "paused_at": None,
                    "archived_at": _utc_now(),
                    "archive_reason": reason,
                    "updated_by_user_id": actor.id,
                },
                expected_version=expected_version,
                audit_actions=["maintenance_plan.archived"],
                audit_context=audit_context,
            )
            .values
        )

    def preview_occurrences(
        self,
        plan_id: UUID,
        *,
        date_from: date,
        date_to: date,
        limit: int,
    ) -> dict[str, Any]:
        return self.catalogue.preview_occurrences(
            plan_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )

    def list_templates(
        self,
        *,
        status: str | None,
        asset_type: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self.templates.list_templates(
            status=status,
            asset_type=asset_type,
            search=search,
            page=page,
            page_size=page_size,
        )

    def get_template(self, template_id: UUID) -> dict[str, Any]:
        return self.templates.get_template(template_id)

    def create_template(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.templates.create_template(
            request, actor=actor, audit_context=audit_context
        )

    def version_template(
        self,
        template_id: UUID,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.templates.version_template(
            template_id,
            request,
            actor=actor,
            audit_context=audit_context,
        )

    def archive_template(
        self,
        template_id: UUID,
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.templates.archive_template(
            template_id,
            expected_version=expected_version,
            audit_context=audit_context,
        )

    def list_work_orders(
        self,
        *,
        actor: CurrentUser,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self.queries.list_work_orders(
            actor=actor,
            filters=filters,
            page=page,
            page_size=page_size,
        )

    def get_work_order(
        self, work_order_id: UUID, *, actor: CurrentUser
    ) -> dict[str, Any]:
        return self.queries.get_work_order(work_order_id, actor=actor)

    def create_work_order(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
        audit_action: str = "work_order.created",
    ) -> dict[str, Any]:
        asset = self._asset(request["asset_id"])
        self._require_asset_eligible(asset, "tạo work order")
        work_order_type = WorkOrderType(request["work_order_type"])
        plan_id = request.get("preventive_plan_id")
        ticket_id = request.get("source_ticket_id")
        if work_order_type is WorkOrderType.PREVENTIVE and not plan_id:
            raise MaintenanceDomainError(
                "Preventive work order phải tham chiếu maintenance plan."
            )
        if plan_id:
            plan = self.get_plan(plan_id)
            if plan["asset_id"] != asset["asset_id"]:
                raise MaintenanceConflictError("Maintenance plan không thuộc asset đã chọn.")
            if plan["status"] == "archived":
                raise MaintenanceConflictError("Không thể tạo work order từ plan archived.")
        if ticket_id:
            ticket = self._ticket(ticket_id)
            if ticket["asset_id"] != asset["asset_id"]:
                raise MaintenanceConflictError("Ticket không thuộc asset đã chọn.")
            if ticket["status"] == "resolved":
                raise MaintenanceConflictError("Ticket đã resolved không nhận work order mới.")
        assignee_id = request.get("assigned_to_user_id")
        if assignee_id:
            self._require_eligible_technician(assignee_id)
        template_id = request.get("checklist_template_id")
        checklist_items: list[dict[str, Any]] = []
        if template_id:
            template = self._require_template_usable(
                template_id, asset_type=asset["asset_type"]
            )
            checklist_items = _template_snapshot(template["items"])
        local_timezone = request.get("local_timezone") or "Asia/Ho_Chi_Minh"
        _require_priority_code(request["priority"])
        _recurrence_spec(
            {
                "interval_value": 1,
                "interval_unit": "day",
                "start_date": request["due_date"],
                "end_date": None,
                "local_timezone": local_timezone,
            }
        ).validate()
        scheduled_start = request.get("scheduled_start_at")
        scheduled_end = request.get("scheduled_end_at")
        _validate_utc_range(scheduled_start, scheduled_end)
        values = {
            "title": _plain_text(request["title"], "title", max_length=200),
            "description": _optional_plain_text(
                request.get("description"), "description", max_length=4000
            ),
            "work_order_type": work_order_type.value,
            "asset_id": asset["asset_id"],
            "preventive_plan_id": plan_id,
            "source_ticket_id": ticket_id,
            "assigned_to_user_id": assignee_id,
            "created_by_user_id": actor.id,
            "verified_by_user_id": None,
            "priority": request["priority"],
            "scheduled_start_at": scheduled_start,
            "scheduled_end_at": scheduled_end,
            "due_date": request["due_date"],
            "local_timezone": local_timezone,
            "grace_period_days": request.get("grace_period_days", 0),
            "estimated_duration_minutes": request["estimated_duration_minutes"],
            "started_at": None,
            "completed_at": None,
            "verified_at": None,
            "cancelled_at": None,
            "cancellation_reason": None,
            "completion_summary": None,
            "safety_notes": None,
            "labor_minutes": None,
            "status": "assigned" if assignee_id else "planned",
            "hold_reason": None,
        }
        return dict(
            self._repository()
            .create_work_order(
                values,
                checklist_items,
                audit_action=audit_action,
                audit_context=audit_context,
            )
            .values
        )

    def create_corrective_from_ticket(
        self,
        ticket_id: str,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        ticket = self._ticket(ticket_id)
        payload = {
            **request,
            "title": request.get("title") or f"Xử lý {ticket_id}",
            "description": request.get("description") or ticket["issue_description"],
            "work_order_type": "corrective",
            "asset_id": ticket["asset_id"],
            "preventive_plan_id": None,
            "source_ticket_id": ticket_id,
            "priority": request.get("priority") or ticket["priority"],
        }
        return self.create_work_order(
            payload,
            actor=actor,
            audit_context=audit_context,
            audit_action="work_order.created_from_ticket",
        )

    def update_work_order(
        self,
        work_order_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self.get_work_order(work_order_id, actor=actor)
        if current["status"] not in {"planned", "assigned"}:
            raise MaintenanceConflictError(
                "Chỉ work order planned/assigned mới được sửa thông tin kế hoạch."
            )
        if "title" in updates:
            updates["title"] = _plain_text(updates["title"], "title", max_length=200)
        if "description" in updates:
            updates["description"] = _optional_plain_text(
                updates["description"], "description", max_length=4000
            )
        _validate_utc_range(
            updates.get("scheduled_start_at", _as_optional_datetime(current["scheduled_start_at"])),
            updates.get("scheduled_end_at", _as_optional_datetime(current["scheduled_end_at"])),
        )
        return dict(
            self._repository()
            .update_work_order(
                work_order_id,
                updates,
                expected_version=expected_version,
                audit_action="work_order.updated",
                audit_context=audit_context,
            )
            .values
        )

    def assign_work_order(
        self,
        work_order_id: UUID,
        *,
        assigned_to_user_id: UUID,
        expected_version: int,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = dict(self._work_order_record(work_order_id).values)
        if current["status"] not in {"planned", "assigned"}:
            raise MaintenanceConflictError(
                "Chỉ work order planned/assigned mới có thể phân công."
            )
        self._require_eligible_technician(assigned_to_user_id)
        return dict(
            self._repository()
            .update_work_order(
                work_order_id,
                {"assigned_to_user_id": assigned_to_user_id, "status": "assigned"},
                expected_version=expected_version,
                audit_action="work_order.assigned",
                audit_context=audit_context,
            )
            .values
        )

    def transition_work_order(
        self,
        work_order_id: UUID,
        *,
        target_status: str,
        hold_reason: str | None,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        target = WorkOrderStatus(target_status)
        if target in {
            WorkOrderStatus.COMPLETED,
            WorkOrderStatus.VERIFIED,
            WorkOrderStatus.CANCELLED,
        }:
            raise MaintenanceDomainError("Hãy dùng endpoint action chuyên biệt.")
        current = dict(self._work_order_record(work_order_id).values)
        self._require_work_order_access(current, actor)
        source = WorkOrderStatus(current["status"])
        if target not in WORK_ORDER_TRANSITIONS[source]:
            raise MaintenanceConflictError(
                f"Transition không hợp lệ: {source.value} -> {target.value}."
            )
        if target is WorkOrderStatus.IN_PROGRESS and not current["assigned_to_user_id"]:
            raise MaintenanceConflictError(
                "Work order cần technician hợp lệ trước khi bắt đầu."
            )
        updates: dict[str, Any] = {"status": target.value, "hold_reason": None}
        action = "work_order.resumed"
        if target is WorkOrderStatus.IN_PROGRESS and current["started_at"] is None:
            updates["started_at"] = _utc_now()
            action = "work_order.started"
        elif target is WorkOrderStatus.ON_HOLD:
            updates["hold_reason"] = _required_text(
                hold_reason, "hold_reason", max_length=1000
            )
            action = "work_order.put_on_hold"
        elif target is WorkOrderStatus.ASSIGNED:
            action = "work_order.resumed_to_assigned"
        return dict(
            self._repository()
            .update_work_order(
                work_order_id,
                updates,
                expected_version=expected_version,
                audit_action=action,
                audit_context=audit_context,
            )
            .values
        )

    def update_checklist(
        self,
        work_order_id: UUID,
        responses: list[dict[str, Any]],
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self.get_work_order(work_order_id, actor=actor)
        if current["status"] not in {"in_progress", "on_hold"}:
            raise MaintenanceConflictError(
                "Checklist chỉ được ghi khi work order đang thực hiện hoặc tạm giữ."
            )
        by_id = {UUID(item["id"]): item for item in current["checklist"]}
        normalized = [
            _normalize_checklist_response(response, by_id, actor.id)
            for response in responses
        ]
        return dict(
            self._repository()
            .update_checklist(
                work_order_id,
                normalized,
                expected_version=expected_version,
                audit_context=audit_context,
            )
            .values
        )

    def complete_work_order(
        self,
        work_order_id: UUID,
        request: dict[str, Any],
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self.get_work_order(work_order_id, actor=actor)
        if current["status"] in {"completed", "verified"} and current["maintenance_log_id"]:
            return current
        if current["status"] != "in_progress":
            raise MaintenanceConflictError(
                "Work order phải ở trạng thái in_progress trước khi hoàn thành."
            )
        _validate_checklist_completion(current["checklist"])
        if not actor.technician_id:
            raise MaintenanceConflictError(
                "Người hoàn thành work order phải có technician_id hợp lệ."
            )
        asset = self._asset(current["asset_id"])
        maintenance_date = request["maintenance_date"]
        local_today = datetime.now(ZoneInfo(current["local_timezone"])).date()
        if maintenance_date > local_today:
            raise MaintenanceDomainError("maintenance_date không được nằm trong tương lai.")
        if maintenance_date < date.fromisoformat(asset["last_maintenance_date"]):
            raise MaintenanceConflictError(
                "maintenance_date không được sớm hơn maintenance date hiện tại của asset."
            )
        result_code = _maintenance_result_code(request["maintenance_result"])
        expected_follow_up = result_code != "resolved"
        if request["follow_up_required"] != expected_follow_up:
            raise MaintenanceDomainError(
                "follow_up_required không nhất quán với maintenance_result."
            )
        next_date = self._next_maintenance_date(current, asset, maintenance_date)
        log_values = {
            "ticket_id": current["source_ticket_id"],
            "asset_id": current["asset_id"],
            "maintenance_date": maintenance_date,
            "maintenance_type": current["work_order_type"],
            "technician_id": actor.technician_id,
            "inspection_result": _required_text(
                request["inspection_result"], "inspection_result", max_length=4000
            ),
            "actions_taken": _required_text(
                request["actions_taken"], "actions_taken", max_length=4000
            ),
            "parts_replaced": _optional_plain_text(
                request.get("parts_replaced"), "parts_replaced", max_length=2000
            ),
            "technician_note": _required_text(
                request["technician_note"], "technician_note", max_length=4000
            ),
            "maintenance_result": result_code,
            "follow_up_required": request["follow_up_required"],
            "next_maintenance_date": next_date,
        }
        updates = {
            "status": "completed",
            "completed_at": _utc_now(),
            "completion_summary": _required_text(
                request["completion_summary"], "completion_summary", max_length=4000
            ),
            "safety_notes": _optional_plain_text(
                request.get("safety_notes"), "safety_notes", max_length=4000
            ),
            "labor_minutes": request["labor_minutes"],
            "hold_reason": None,
        }
        return dict(
            self._repository()
            .complete_work_order(
                work_order_id,
                updates,
                log_values,
                expected_version=expected_version,
                audit_context=audit_context,
            )
            .values
        )

    def verify_work_order(
        self,
        work_order_id: UUID,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = dict(self._work_order_record(work_order_id).values)
        if current["status"] == "verified":
            return current
        if current["status"] != "completed":
            raise MaintenanceConflictError("Chỉ work order completed mới được verify.")
        if current["assigned_to_user_id"] == str(actor.id):
            raise MaintenanceAuthorizationError(
                "Người thực hiện không được tự verify work order của mình."
            )
        return dict(
            self._repository()
            .verify_work_order(
                work_order_id,
                expected_version=expected_version,
                verified_by_user_id=actor.id,
                audit_context=audit_context,
            )
            .values
        )

    def cancel_work_order(
        self,
        work_order_id: UUID,
        *,
        expected_version: int,
        cancellation_reason: str,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = dict(self._work_order_record(work_order_id).values)
        if WorkOrderStatus.CANCELLED not in WORK_ORDER_TRANSITIONS[
            WorkOrderStatus(current["status"])
        ]:
            raise MaintenanceConflictError(
                "Chỉ work order planned/assigned mới có thể hủy."
            )
        return dict(
            self._repository()
            .update_work_order(
                work_order_id,
                {
                    "status": "cancelled",
                    "cancelled_at": _utc_now(),
                    "cancellation_reason": _required_text(
                        cancellation_reason, "cancellation_reason", max_length=1000
                    ),
                    "hold_reason": None,
                },
                expected_version=expected_version,
                audit_action="work_order.cancelled",
                audit_context=audit_context,
            )
            .values
        )

    def reopen_work_order(
        self,
        work_order_id: UUID,
        *,
        expected_version: int,
        reason: str,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = dict(self._work_order_record(work_order_id).values)
        if current["status"] != "completed":
            raise MaintenanceConflictError(
                "Chỉ work order completed, chưa verify mới có thể reopen."
            )
        return dict(
            self._repository()
            .update_work_order(
                work_order_id,
                {
                    "status": "in_progress",
                    "completed_at": None,
                    "hold_reason": None,
                },
                expected_version=expected_version,
                audit_action="work_order.reopened",
                audit_context=audit_context,
                audit_metadata={
                    "reason": _required_text(reason, "reason", max_length=1000)
                },
            )
            .values
        )

    def generate(
        self,
        *,
        as_of_date: date,
        plan_id: UUID | None,
        dry_run: bool,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        if abs((as_of_date - today).days) > 366:
            raise MaintenanceDomainError(
                "as_of_date phải nằm trong phạm vi 366 ngày quanh ngày hiện tại."
            )
        plans = (
            [self.get_plan(plan_id)]
            if plan_id
            else self.list_plans(
                asset_id=None,
                status="active",
                search=None,
                due_from=None,
                due_to=None,
                page=1,
                page_size=1000,
            )["items"]
        )
        reports: list[dict[str, Any]] = []
        for plan in plans:
            report = self._generation_unit(
                plan,
                as_of_date=as_of_date,
                dry_run=dry_run,
                audit_context=audit_context,
            )
            reports.append(report)
        return {
            "dry_run": dry_run,
            "as_of_date": as_of_date.isoformat(),
            "requested_by_user_id": str(actor.id),
            "generated_count": sum(len(item.get("generated", [])) for item in reports),
            "would_generate_count": sum(
                len(item.get("would_generate_due_dates", [])) for item in reports
            ),
            "skipped_count": sum(
                len(item.get("skipped_due_dates", [])) for item in reports
            ),
            "plans": reports,
        }

    def schedule_view(
        self,
        *,
        actor: CurrentUser,
        date_from: date,
        date_to: date,
        asset_id: str | None,
        assigned_to_user_id: UUID | None,
    ) -> dict[str, Any]:
        if (date_to - date_from).days > 366 or date_to < date_from:
            raise MaintenanceDomainError("Calendar range phải nằm trong 0–366 ngày.")
        work_orders = self.list_work_orders(
            actor=actor,
            filters={
                "asset_id": asset_id,
                "assigned_to_user_id": assigned_to_user_id,
                "due_from": date_from,
                "due_to": date_to,
            },
            page=1,
            page_size=1000,
        )["items"]
        plans = self.list_plans(
            asset_id=asset_id,
            status="active",
            search=None,
            due_from=None,
            due_to=None,
            page=1,
            page_size=1000,
        )["items"]
        occurrences: list[dict[str, Any]] = []
        for plan in plans:
            preview = self.preview_occurrences(
                UUID(plan["id"]), date_from=date_from, date_to=date_to, limit=MAX_OCCURRENCES
            )
            occurrences.extend(
                {
                    **item,
                    "plan_id": plan["id"],
                    "plan_code": plan["plan_code"],
                    "plan_name": plan["name"],
                    "asset_id": plan["asset_id"],
                }
                for item in preview["items"]
            )
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "work_orders": work_orders,
            "upcoming_occurrences": occurrences,
        }

    def metrics(self, *, as_of_date: date) -> dict[str, Any]:
        page = self._repository().list_work_orders(
            filters={}, page=1, page_size=1000
        )
        items = [record.values for record in page.items]
        statuses = {
            status.value: sum(item["status"] == status.value for item in items)
            for status in WorkOrderStatus
        }
        completed = [item for item in items if item["status"] in {"completed", "verified"}]
        completed_on_time = sum(
            bool(item["completed_at"])
            and datetime.fromisoformat(item["completed_at"]).date()
            <= date.fromisoformat(item["due_date"])
            + timedelta(days=int(item["grace_period_days"]))
            for item in completed
        )
        workload: dict[str, dict[str, Any]] = {}
        for item in items:
            if not item["assigned_to_user_id"] or item["status"] in {"verified", "cancelled"}:
                continue
            key = item["assigned_to_user_id"]
            bucket = workload.setdefault(
                key,
                {"user_id": key, "display_name": item["assigned_to_name"], "open_count": 0},
            )
            bucket["open_count"] += 1
        return {
            "as_of_date": as_of_date.isoformat(),
            "total_work_orders": len(items),
            "by_status": statuses,
            "overdue_count": sum(
                item["status"] not in {"verified", "cancelled"}
                and date.fromisoformat(item["due_date"])
                + timedelta(days=int(item["grace_period_days"]))
                < as_of_date
                for item in items
            ),
            "upcoming_preventive_count": sum(
                item["work_order_type"] == "preventive"
                and item["status"] not in {"verified", "cancelled"}
                and as_of_date <= date.fromisoformat(item["due_date"])
                <= as_of_date + timedelta(days=30)
                for item in items
            ),
            "completed_count": len(completed),
            "verified_count": statuses["verified"],
            "completed_on_time_count": completed_on_time,
            "technician_workload": sorted(
                workload.values(), key=lambda item: (-item["open_count"], item["display_name"])
            ),
            "data_notice": "Chỉ số vận hành trên dữ liệu synthetic/internal-pilot.",
        }

    def list_evidence(
        self, work_order_id: UUID, *, actor: CurrentUser
    ) -> list[dict[str, Any]]:
        return self.evidence.list_evidence(work_order_id, actor=actor)

    def upload_evidence(
        self,
        work_order_id: UUID,
        *,
        category: str,
        filename: str,
        claimed_media_type: str | None,
        content: bytes,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.evidence.upload_evidence(
            work_order_id,
            category=category,
            filename=filename,
            claimed_media_type=claimed_media_type,
            content=content,
            actor=actor,
            audit_context=audit_context,
        )

    def download_evidence(
        self,
        work_order_id: UUID,
        attachment_id: UUID,
        *,
        actor: CurrentUser,
    ) -> EvidenceDownload:
        return self.evidence.download_evidence(
            work_order_id, attachment_id, actor=actor
        )

    def delete_evidence(
        self,
        work_order_id: UUID,
        attachment_id: UUID,
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.evidence.delete_evidence(
            work_order_id,
            attachment_id,
            actor=actor,
            audit_context=audit_context,
        )

    def linked_work_orders(
        self, ticket_id: str, *, actor: CurrentUser
    ) -> list[dict[str, Any]]:
        self._ticket(ticket_id)
        return self.list_work_orders(
            actor=actor,
            filters={"source_ticket_id": ticket_id},
            page=1,
            page_size=100,
        )["items"]

    def _generation_unit(
        self,
        plan: dict[str, Any],
        *,
        as_of_date: date,
        dry_run: bool,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        if plan["status"] != "active" or not plan["next_due_date"]:
            return {
                "plan_id": plan["id"],
                "plan_code": plan["plan_code"],
                "generated": [],
                "would_generate_due_dates": [],
                "skipped_due_dates": [],
                "reason": "Plan không active hoặc đã hết occurrence.",
            }
        asset = self._asset(plan["asset_id"])
        if asset["lifecycle_status"] in {"retired", "archived"}:
            return {
                "plan_id": plan["id"],
                "plan_code": plan["plan_code"],
                "generated": [],
                "would_generate_due_dates": [],
                "skipped_due_dates": [],
                "reason": "Asset retired hoặc archived.",
            }
        spec = _recurrence_spec(plan)
        first_due = date.fromisoformat(plan["next_due_date"])
        release_horizon = as_of_date + timedelta(days=int(plan["lead_time_days"]))
        catch_up_start = as_of_date - timedelta(days=MAX_CATCH_UP_DAYS)
        skipped_backlog: list[str] = []
        if first_due < catch_up_start:
            bounded_first = first_occurrence_on_or_after(spec, catch_up_start)
            skipped_backlog.append(f"before:{catch_up_start.isoformat()}")
        else:
            bounded_first = first_due
        if bounded_first is None or bounded_first > release_horizon:
            due_dates: list[date] = []
        else:
            due_dates = occurrences_between(
                spec,
                start=bounded_first,
                end=release_horizon,
                first_due=bounded_first,
                max_occurrences=MAX_OCCURRENCES,
            )
        existing = self._repository().list_generated_due_dates(UUID(plan["id"]))
        would_generate = [value for value in due_dates if value not in existing]
        skipped = sorted(value for value in due_dates if value in existing)
        next_due = (
            advance_occurrence(due_dates[-1], spec) if due_dates else first_due
        )
        if spec.end_date is not None and next_due > spec.end_date:
            next_due = None
        if dry_run:
            return {
                "plan_id": plan["id"],
                "plan_code": plan["plan_code"],
                "generated": [],
                "would_generate_due_dates": [value.isoformat() for value in would_generate],
                "skipped_due_dates": [value.isoformat() for value in skipped]
                + skipped_backlog,
                "reason": None,
            }
        result = self._repository().generate_plan_occurrences(
            UUID(plan["id"]),
            schedule_signature={
                "interval_value": int(plan["interval_value"]),
                "interval_unit": plan["interval_unit"],
                "start_date": date.fromisoformat(plan["start_date"]),
                "end_date": _as_optional_date(plan["end_date"]),
                "local_timezone": plan["local_timezone"],
                "status": "active",
            },
            due_dates=due_dates,
            next_due_date=next_due,
            audit_context=audit_context,
        )
        result["would_generate_due_dates"] = []
        result["skipped_due_dates"] = result["skipped_due_dates"] + skipped_backlog
        return result

    def _next_maintenance_date(
        self,
        work_order: dict[str, Any],
        asset: dict[str, Any],
        maintenance_date: date,
    ) -> date:
        if work_order["preventive_plan_id"]:
            plan = self.get_plan(UUID(work_order["preventive_plan_id"]))
            candidate = _as_optional_date(plan["next_due_date"])
            if candidate and candidate > maintenance_date:
                return candidate
            spec = _recurrence_spec(plan)
            candidate = advance_occurrence(
                date.fromisoformat(work_order["due_date"]), spec
            )
            if candidate > maintenance_date:
                return candidate
        return maintenance_date + timedelta(days=int(asset["maintenance_interval_days"]))

    def _asset(self, asset_id: str) -> dict[str, Any]:
        record = self._repository().get_asset_state(asset_id)
        if record is None:
            raise MaintenanceNotFoundError(f"Không tìm thấy asset: {asset_id}")
        return dict(record.values)

    def _ticket(self, ticket_id: str) -> dict[str, Any]:
        record = self._repository().get_ticket_state(ticket_id)
        if record is None:
            raise MaintenanceNotFoundError(f"Không tìm thấy ticket: {ticket_id}")
        return dict(record.values)

    def _plan_record(self, plan_id: UUID) -> StoredRecord:
        record = self._repository().get_plan(plan_id)
        if record is None:
            raise MaintenanceNotFoundError(f"Không tìm thấy maintenance plan: {plan_id}")
        return record

    def _work_order_record(self, work_order_id: UUID) -> StoredRecord:
        record = self._repository().get_work_order(work_order_id)
        if record is None:
            raise MaintenanceNotFoundError(f"Không tìm thấy work order: {work_order_id}")
        return record

    def _require_asset_eligible(self, asset: dict[str, Any], action: str) -> None:
        if asset["lifecycle_status"] in {"retired", "archived"}:
            raise MaintenanceConflictError(
                f"Asset retired hoặc archived không thể {action}."
            )

    def _require_eligible_technician(self, user_id: UUID) -> dict[str, Any]:
        record = self._repository().get_user_state(user_id)
        if record is None:
            raise MaintenanceNotFoundError(f"Không tìm thấy technician user: {user_id}")
        user = dict(record.values)
        if user["role"] != "technician" or not user["is_active"] or not user["technician_id"]:
            raise MaintenanceConflictError(
                "Assignee phải là technician active có technician_id."
            )
        return user

    def _require_template_usable(
        self, template_id: UUID, *, asset_type: str
    ) -> dict[str, Any]:
        template = self.get_template(template_id)
        if template["status"] != "active":
            raise MaintenanceConflictError("Checklist template archived không thể dùng mới.")
        if template["asset_type"] and template["asset_type"] != asset_type:
            raise MaintenanceConflictError(
                "Checklist template không áp dụng cho asset type đã chọn."
            )
        return template

    def _require_work_order_access(
        self, work_order: dict[str, Any], actor: CurrentUser
    ) -> None:
        if actor.role is Role.TECHNICIAN and work_order["assigned_to_user_id"] != str(actor.id):
            raise MaintenanceAuthorizationError(
                "Work order này không được phân công cho technician đang đăng nhập."
            )

    def _scope_work_order(
        self, work_order: dict[str, Any], actor: CurrentUser
    ) -> dict[str, Any]:
        result = dict(work_order)
        if actor.role in {Role.HELPDESK, Role.STOREKEEPER}:
            result["checklist"] = []
            result["history"] = []
            result["safety_notes"] = None
            result["completion_summary"] = None
        return result

    def _repository(self) -> MaintenancePlanningRepository:
        if self.repository is None:
            raise UnsupportedStorageOperationError(
                "Maintenance planning yêu cầu PostgreSQL product mode."
            )
        return self.repository


def build_maintenance_planning_service() -> MaintenancePlanningService:
    """Compatibility builder delegated to the explicit composition root."""

    from src.maintenance_management.compatibility import build_maintenance_planning_service as build

    return build()


def _recurrence_spec(values: dict[str, Any]) -> RecurrenceSpec:
    return RecurrenceSpec(
        interval_value=int(values["interval_value"]),
        interval_unit=IntervalUnit(values["interval_unit"]),
        start_date=_as_date(values["start_date"]),
        end_date=_as_optional_date(values.get("end_date")),
        local_timezone=str(values["local_timezone"]),
    )


def _validate_template_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        raise MaintenanceDomainError("Checklist template cần ít nhất một item.")
    if len(items) > 100:
        raise MaintenanceDomainError("Checklist template không được vượt quá 100 items.")
    ordered = sorted(items, key=lambda item: int(item["sequence"]))
    if [int(item["sequence"]) for item in ordered] != list(range(1, len(items) + 1)):
        raise MaintenanceDomainError("Checklist sequence phải liên tục từ 1.")
    normalized: list[dict[str, Any]] = []
    for item in ordered:
        response_type = ChecklistResponseType(item["response_type"])
        minimum = item.get("minimum_value")
        maximum = item.get("maximum_value")
        unit = _optional_plain_text(item.get("expected_unit"), "expected_unit", max_length=40)
        if response_type is not ChecklistResponseType.NUMERIC and any(
            value is not None for value in (minimum, maximum, unit)
        ):
            raise MaintenanceDomainError(
                "minimum/maximum/unit chỉ dùng cho numeric checklist item."
            )
        if minimum is not None and maximum is not None and minimum > maximum:
            raise MaintenanceDomainError("minimum_value không được lớn hơn maximum_value.")
        normalized.append(
            {
                "sequence": int(item["sequence"]),
                "instruction": _plain_text(
                    item["instruction"], "instruction", max_length=2000
                ),
                "response_type": response_type.value,
                "is_required": bool(item.get("is_required", True)),
                "safety_critical": bool(item.get("safety_critical", False)),
                "allow_not_applicable": bool(
                    item.get("allow_not_applicable", False)
                ),
                "expected_unit": unit,
                "minimum_value": minimum,
                "maximum_value": maximum,
                "guidance": _optional_plain_text(
                    item.get("guidance"), "guidance", max_length=2000
                ),
            }
        )
    return normalized


def _template_snapshot(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_template_item_id": UUID(item["id"]),
            "sequence": item["sequence"],
            "instruction": item["instruction"],
            "response_type": item["response_type"],
            "is_required": item["is_required"],
            "safety_critical": item["safety_critical"],
            "allow_not_applicable": item["allow_not_applicable"],
            "expected_unit": item["expected_unit"],
            "minimum_value": item["minimum_value"],
            "maximum_value": item["maximum_value"],
            "guidance": item["guidance"],
            "result_status": "pending",
            "boolean_value": None,
            "numeric_value": None,
            "text_value": None,
            "note": None,
            "completed_by_user_id": None,
            "completed_at": None,
        }
        for item in items
    ]


def _normalize_checklist_response(
    response: dict[str, Any],
    items: dict[UUID, dict[str, Any]],
    actor_user_id: UUID,
) -> dict[str, Any]:
    item_id = response["item_id"]
    item = items.get(item_id)
    if item is None:
        raise MaintenanceConflictError(f"Checklist item không thuộc work order: {item_id}")
    result = ChecklistResultStatus(response["result_status"])
    if result is ChecklistResultStatus.PENDING:
        raise MaintenanceDomainError("Không thể submit result_status=pending.")
    if result is ChecklistResultStatus.NOT_APPLICABLE:
        if not item["allow_not_applicable"]:
            raise MaintenanceDomainError("Checklist item này không cho phép not_applicable.")
        return {
            "item_id": item_id,
            "result_status": result.value,
            "boolean_value": None,
            "numeric_value": None,
            "text_value": None,
            "note": _optional_plain_text(response.get("note"), "note", max_length=1000),
            "completed_by_user_id": actor_user_id,
            "completed_at": _utc_now(),
        }
    response_type = ChecklistResponseType(item["response_type"])
    boolean_value = response.get("boolean_value")
    numeric_value = response.get("numeric_value")
    text_value = _optional_plain_text(
        response.get("text_value"), "text_value", max_length=2000
    )
    if response_type is ChecklistResponseType.CHECKBOX:
        if boolean_value is None or result is not ChecklistResultStatus.COMPLETED:
            raise MaintenanceDomainError(
                "Checkbox cần boolean_value và result_status=completed."
            )
    elif response_type is ChecklistResponseType.PASS_FAIL:
        if result not in {ChecklistResultStatus.PASS, ChecklistResultStatus.FAIL}:
            raise MaintenanceDomainError("Pass/fail item cần result_status pass hoặc fail.")
    elif response_type is ChecklistResponseType.NUMERIC:
        if numeric_value is None:
            raise MaintenanceDomainError("Numeric item cần numeric_value.")
        failed = (
            item["minimum_value"] is not None
            and numeric_value < item["minimum_value"]
        ) or (
            item["maximum_value"] is not None
            and numeric_value > item["maximum_value"]
        )
        result = ChecklistResultStatus.FAIL if failed else ChecklistResultStatus.COMPLETED
    elif not text_value:
        raise MaintenanceDomainError("Text item cần nội dung trả lời.")
    return {
        "item_id": item_id,
        "result_status": result.value,
        "boolean_value": boolean_value if response_type is ChecklistResponseType.CHECKBOX else None,
        "numeric_value": numeric_value if response_type is ChecklistResponseType.NUMERIC else None,
        "text_value": text_value if response_type is ChecklistResponseType.TEXT else None,
        "note": _optional_plain_text(response.get("note"), "note", max_length=1000),
        "completed_by_user_id": actor_user_id,
        "completed_at": _utc_now(),
    }


def _validate_checklist_completion(items: list[dict[str, Any]]) -> None:
    for item in items:
        if item["is_required"] and item["result_status"] == "pending":
            raise MaintenanceConflictError(
                f"Checklist bắt buộc #{item['sequence']} chưa hoàn thành."
            )
        failed = item["result_status"] == "fail" or (
            item["response_type"] == "checkbox" and item["boolean_value"] is False
        )
        if item["safety_critical"] and failed:
            raise MaintenanceConflictError(
                f"Checklist an toàn #{item['sequence']} không đạt; completion bị chặn."
            )


def _maintenance_result_code(value: str) -> str:
    if value in MAINTENANCE_RESULT_CODE_TO_VI:
        return value
    try:
        return MAINTENANCE_RESULT_VI_TO_CODE[value]
    except KeyError as exc:
        raise MaintenanceDomainError("maintenance_result không được hỗ trợ.") from exc


def _require_priority_code(value: object) -> str:
    normalized = str(value)
    if normalized not in PRIORITY_CODE_TO_VI:
        raise MaintenanceDomainError("priority không được hỗ trợ.")
    return normalized


def _normalized_code(value: str, pattern: re.Pattern[str], field: str) -> str:
    normalized = str(value).strip().upper()
    if not pattern.fullmatch(normalized):
        raise MaintenanceDomainError(
            f"{field} chỉ nhận 3–50 ký tự A-Z, 0-9, dấu gạch ngang hoặc gạch dưới."
        )
    return normalized


def _plain_text(value: object, field: str, *, max_length: int) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise MaintenanceDomainError(f"{field} không được để trống.")
    if len(normalized) > max_length:
        raise MaintenanceDomainError(f"{field} không được vượt quá {max_length} ký tự.")
    if "<" in normalized or ">" in normalized or "javascript:" in normalized.casefold():
        raise MaintenanceDomainError(f"{field} chỉ chấp nhận plain text an toàn.")
    return normalized


def _required_text(value: object, field: str, *, max_length: int) -> str:
    return _plain_text(value, field, max_length=max_length)


def _optional_plain_text(
    value: object | None, field: str, *, max_length: int
) -> str | None:
    if value is None or not str(value).strip():
        return None
    return _plain_text(value, field, max_length=max_length)


def _validate_utc_range(
    start: datetime | None, end: datetime | None
) -> None:
    for field, value in (("scheduled_start_at", start), ("scheduled_end_at", end)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise MaintenanceDomainError(f"{field} phải có timezone.")
    if start is not None and end is not None and end < start:
        raise MaintenanceDomainError(
            "scheduled_end_at không được sớm hơn scheduled_start_at."
        )


def _as_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _as_optional_date(value: object | None) -> date | None:
    if value is None or not str(value).strip():
        return None
    return _as_date(value)


def _as_optional_datetime(value: object | None) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _options(mapping: dict[Any, str]) -> list[dict[str, str]]:
    return [
        {"code": str(code.value if hasattr(code, "value") else code), "display_name": label}
        for code, label in mapping.items()
    ]


def _page_values(page: StoredPage) -> dict[str, Any]:
    total_pages = (page.total + page.page_size - 1) // page.page_size if page.total else 0
    return {
        "items": [dict(record.values) for record in page.items],
        "page": page.page,
        "page_size": page.page_size,
        "total": page.total,
        "total_pages": total_pages,
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

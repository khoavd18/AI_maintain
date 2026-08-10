"""Pre-execution work-order planning and assignment orchestration.

This collaborator validates work-order intake and planning commands, then
delegates one repository mutation. Work-order numbering, checklist persistence,
optimistic versions, audit/outbox writes, and commit/rollback remain owned by
the PostgreSQL repository.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from src.maintenance_management.domain import WorkOrderType
from src.maintenance_management.errors import MaintenanceConflictError, MaintenanceDomainError
from src.maintenance_management.recurrence import RecurrenceSpec
from src.repositories.contracts import MaintenancePlanningRepository
from src.security.audit_context import AuditContext
from src.security.principal import CurrentUser


class WorkOrderPlanningService:
    """Own work-order creation, pre-execution edits, and assignment intent."""

    def __init__(
        self,
        repository_provider: Callable[[], MaintenancePlanningRepository],
        *,
        get_asset: Callable[[str], dict[str, Any]],
        get_ticket: Callable[[str], dict[str, Any]],
        get_plan: Callable[[UUID], dict[str, Any]],
        get_work_order: Callable[..., dict[str, Any]],
        get_work_order_record: Callable[[UUID], Any],
        require_asset_eligible: Callable[[dict[str, Any], str], None],
        require_eligible_technician: Callable[[UUID], dict[str, Any]],
        require_template_usable: Callable[..., dict[str, Any]],
        template_snapshot: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
        normalize_text: Callable[..., str],
        normalize_optional_text: Callable[..., str | None],
        require_priority_code: Callable[[object], str],
        recurrence_spec: Callable[[dict[str, Any]], RecurrenceSpec],
        validate_utc_range: Callable[[datetime | None, datetime | None], None],
        as_optional_datetime: Callable[[object | None], datetime | None],
    ) -> None:
        self._repository_provider = repository_provider
        self._get_asset = get_asset
        self._get_ticket = get_ticket
        self._get_plan = get_plan
        self._get_work_order = get_work_order
        self._get_work_order_record = get_work_order_record
        self._require_asset_eligible = require_asset_eligible
        self._require_eligible_technician = require_eligible_technician
        self._require_template_usable = require_template_usable
        self._template_snapshot = template_snapshot
        self._normalize_text = normalize_text
        self._normalize_optional_text = normalize_optional_text
        self._require_priority_code = require_priority_code
        self._recurrence_spec = recurrence_spec
        self._validate_utc_range = validate_utc_range
        self._as_optional_datetime = as_optional_datetime

    def create_work_order(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
        audit_action: str = "work_order.created",
    ) -> dict[str, Any]:
        asset = self._get_asset(request["asset_id"])
        self._require_asset_eligible(asset, "tạo work order")
        work_order_type = WorkOrderType(request["work_order_type"])
        plan_id = request.get("preventive_plan_id")
        ticket_id = request.get("source_ticket_id")
        if work_order_type is WorkOrderType.PREVENTIVE and not plan_id:
            raise MaintenanceDomainError("Preventive work order phải tham chiếu maintenance plan.")
        if plan_id:
            plan = self._get_plan(plan_id)
            if plan["asset_id"] != asset["asset_id"]:
                raise MaintenanceConflictError("Maintenance plan không thuộc asset đã chọn.")
            if plan["status"] == "archived":
                raise MaintenanceConflictError("Không thể tạo work order từ plan archived.")
        if ticket_id:
            ticket = self._get_ticket(ticket_id)
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
            template = self._require_template_usable(template_id, asset_type=asset["asset_type"])
            checklist_items = self._template_snapshot(template["items"])
        local_timezone = request.get("local_timezone") or "Asia/Ho_Chi_Minh"
        self._require_priority_code(request["priority"])
        self._recurrence_spec(
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
        self._validate_utc_range(scheduled_start, scheduled_end)
        values = {
            "title": self._normalize_text(request["title"], "title", max_length=200),
            "description": self._normalize_optional_text(
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
            self._repository_provider()
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
        ticket = self._get_ticket(ticket_id)
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
        current = self._get_work_order(work_order_id, actor=actor)
        if current["status"] not in {"planned", "assigned"}:
            raise MaintenanceConflictError(
                "Chỉ work order planned/assigned mới được sửa thông tin kế hoạch."
            )
        if "title" in updates:
            updates["title"] = self._normalize_text(updates["title"], "title", max_length=200)
        if "description" in updates:
            updates["description"] = self._normalize_optional_text(
                updates["description"], "description", max_length=4000
            )
        self._validate_utc_range(
            updates.get(
                "scheduled_start_at",
                self._as_optional_datetime(current["scheduled_start_at"]),
            ),
            updates.get(
                "scheduled_end_at",
                self._as_optional_datetime(current["scheduled_end_at"]),
            ),
        )
        return dict(
            self._repository_provider()
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
        current = dict(self._get_work_order_record(work_order_id).values)
        if current["status"] not in {"planned", "assigned"}:
            raise MaintenanceConflictError("Chỉ work order planned/assigned mới có thể phân công.")
        self._require_eligible_technician(assigned_to_user_id)
        return dict(
            self._repository_provider()
            .update_work_order(
                work_order_id,
                {"assigned_to_user_id": assigned_to_user_id, "status": "assigned"},
                expected_version=expected_version,
                audit_action="work_order.assigned",
                audit_context=audit_context,
            )
            .values
        )

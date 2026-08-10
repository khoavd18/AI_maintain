"""Preventive-plan command orchestration.

This application service validates one plan command and delegates one atomic
repository mutation. PostgreSQL row locks, optimistic version checks, audit
writes, commit, rollback, and persistence error mapping remain repository-owned.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from src.maintenance_management.errors import (
    MaintenanceConflictError,
    MaintenanceDomainError,
)
from src.maintenance_management.recurrence import (
    RecurrenceSpec,
    first_occurrence_on_or_after,
)
from src.repositories.contracts import MaintenancePlanningRepository
from src.security.audit_context import AuditContext
from src.security.principal import CurrentUser


class PreventivePlanService:
    """Own plan creation, schedule changes, pause, resume, and archive intent."""

    def __init__(
        self,
        repository_provider: Callable[[], MaintenancePlanningRepository],
        *,
        get_plan: Callable[[UUID], dict[str, Any]],
        get_asset: Callable[[str], dict[str, Any]],
        require_asset_eligible: Callable[[dict[str, Any], str], None],
        require_eligible_technician: Callable[[UUID], dict[str, Any]],
        require_template_usable: Callable[..., dict[str, Any]],
        recurrence_spec: Callable[[dict[str, Any]], RecurrenceSpec],
        normalize_code: Callable[[str, str], str],
        normalize_text: Callable[..., str],
        normalize_optional_text: Callable[..., str | None],
        require_priority_code: Callable[[object], str],
        as_optional_date: Callable[[object | None], date | None],
        utc_now: Callable[[], datetime],
    ) -> None:
        self._repository_provider = repository_provider
        self._get_plan = get_plan
        self._get_asset = get_asset
        self._require_asset_eligible = require_asset_eligible
        self._require_eligible_technician = require_eligible_technician
        self._require_template_usable = require_template_usable
        self._recurrence_spec = recurrence_spec
        self._normalize_code = normalize_code
        self._normalize_text = normalize_text
        self._normalize_optional_text = normalize_optional_text
        self._require_priority_code = require_priority_code
        self._as_optional_date = as_optional_date
        self._utc_now = utc_now

    def create_plan(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        plan_code = self._normalize_code(request["plan_code"], "plan_code")
        asset = self._get_asset(request["asset_id"])
        self._require_asset_eligible(asset, "tạo maintenance plan")
        spec = self._recurrence_spec(request)
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
        self._require_priority_code(request["default_priority"])
        values = {
            **request,
            "plan_code": plan_code,
            "name": self._normalize_text(request["name"], "name", max_length=200),
            "description": self._normalize_optional_text(
                request.get("description"), "description", max_length=2000
            ),
            "instructions": self._normalize_optional_text(
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
            self._repository_provider().create_plan(values, audit_context=audit_context).values
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
        current = self._get_plan(plan_id)
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
                "Không được để trống các trường bắt buộc: " + ", ".join(invalid_null_fields) + "."
            )
        merged = {**current, **updates}
        if "name" in updates:
            updates["name"] = self._normalize_text(updates["name"], "name", max_length=200)
        for field, limit in (("description", 2000), ("instructions", 4000)):
            if field in updates:
                updates[field] = self._normalize_optional_text(
                    updates[field], field, max_length=limit
                )
        if "default_priority" in updates:
            self._require_priority_code(updates["default_priority"])
        schedule_fields = {
            "interval_value",
            "interval_unit",
            "start_date",
            "end_date",
            "local_timezone",
        }
        schedule_changed = bool(schedule_fields & updates.keys())
        if schedule_changed:
            spec = self._recurrence_spec(merged)
            spec.validate()
            last_generated = self._as_optional_date(current["last_generated_due_date"])
            if last_generated:
                next_due = first_occurrence_on_or_after(spec, last_generated + timedelta(days=1))
            else:
                next_due = spec.start_date
            updates["next_due_date"] = next_due
        if "default_assignee_user_id" in updates and updates["default_assignee_user_id"]:
            self._require_eligible_technician(updates["default_assignee_user_id"])
        if "checklist_template_id" in updates and updates["checklist_template_id"]:
            asset = self._get_asset(current["asset_id"])
            self._require_template_usable(
                updates["checklist_template_id"], asset_type=asset["asset_type"]
            )
        updates["updated_by_user_id"] = actor.id
        actions = ["maintenance_plan.updated"]
        if schedule_changed:
            actions.append("maintenance_plan.schedule_changed")
        return dict(
            self._repository_provider()
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
        current = self._get_plan(plan_id)
        if current["status"] != "active":
            raise MaintenanceConflictError("Chỉ plan active mới có thể tạm dừng.")
        return dict(
            self._repository_provider()
            .update_plan(
                plan_id,
                {
                    "status": "paused",
                    "is_active": False,
                    "paused_at": self._utc_now(),
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
        current = self._get_plan(plan_id)
        if current["status"] != "paused":
            raise MaintenanceConflictError("Chỉ plan paused mới có thể resume.")
        spec = self._recurrence_spec(current)
        next_due = first_occurrence_on_or_after(spec, max(resume_date, spec.start_date))
        if next_due is None:
            raise MaintenanceConflictError(
                "Plan đã qua end_date; hãy cập nhật schedule trước khi resume."
            )
        return dict(
            self._repository_provider()
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
        current = self._get_plan(plan_id)
        if current["status"] == "archived":
            raise MaintenanceConflictError("Plan đã được archive.")
        reason = self._normalize_text(archive_reason, "archive_reason", max_length=1000)
        return dict(
            self._repository_provider()
            .update_plan(
                plan_id,
                {
                    "status": "archived",
                    "is_active": False,
                    "paused_at": None,
                    "archived_at": self._utc_now(),
                    "archive_reason": reason,
                    "updated_by_user_id": actor.id,
                },
                expected_version=expected_version,
                audit_actions=["maintenance_plan.archived"],
                audit_context=audit_context,
            )
            .values
        )

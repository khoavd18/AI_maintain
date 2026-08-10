"""Work-order completion and independent verification orchestration.

The application collaborator validates completion intent and builds the linked
maintenance-log payload. The PostgreSQL repository remains the single atomic
transaction owner for work-order state, maintenance log, asset dates, audit,
outbox, locking, and rollback.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from uuid import UUID

from src.maintenance_management.errors import (
    MaintenanceAuthorizationError,
    MaintenanceConflictError,
    MaintenanceDomainError,
)
from src.repositories.contracts import MaintenancePlanningRepository, StoredRecord
from src.security.audit_context import AuditContext
from src.security.principal import CurrentUser


class WorkOrderCompletionService:
    """Own completion validation/log intent and independent verification."""

    def __init__(
        self,
        repository_provider: Callable[[], MaintenancePlanningRepository],
        *,
        get_work_order: Callable[..., dict[str, Any]],
        get_work_order_record: Callable[[UUID], StoredRecord],
        get_asset: Callable[[str], dict[str, Any]],
        validate_checklist_completion: Callable[[list[dict[str, Any]]], None],
        maintenance_result_code: Callable[[str], str],
        required_text: Callable[..., str],
        optional_text: Callable[..., str | None],
        utc_now: Callable[[], datetime],
        local_today: Callable[[str], date],
        next_maintenance_date: Callable[[dict[str, Any], dict[str, Any], date], date],
    ) -> None:
        self._repository_provider = repository_provider
        self._get_work_order = get_work_order
        self._get_work_order_record = get_work_order_record
        self._get_asset = get_asset
        self._validate_checklist_completion = validate_checklist_completion
        self._maintenance_result_code = maintenance_result_code
        self._required_text = required_text
        self._optional_text = optional_text
        self._utc_now = utc_now
        self._local_today = local_today
        self._next_maintenance_date = next_maintenance_date

    def complete_work_order(
        self,
        work_order_id: UUID,
        request: dict[str, Any],
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self._get_work_order(work_order_id, actor=actor)
        if current["status"] in {"completed", "verified"} and current["maintenance_log_id"]:
            return current
        if current["status"] != "in_progress":
            raise MaintenanceConflictError(
                "Work order phải ở trạng thái in_progress trước khi hoàn thành."
            )
        self._validate_checklist_completion(current["checklist"])
        if not actor.technician_id:
            raise MaintenanceConflictError(
                "Người hoàn thành work order phải có technician_id hợp lệ."
            )
        asset = self._get_asset(current["asset_id"])
        maintenance_date = request["maintenance_date"]
        if maintenance_date > self._local_today(current["local_timezone"]):
            raise MaintenanceDomainError("maintenance_date không được nằm trong tương lai.")
        if maintenance_date < date.fromisoformat(asset["last_maintenance_date"]):
            raise MaintenanceConflictError(
                "maintenance_date không được sớm hơn maintenance date hiện tại của asset."
            )
        result_code = self._maintenance_result_code(request["maintenance_result"])
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
            "inspection_result": self._required_text(
                request["inspection_result"], "inspection_result", max_length=4000
            ),
            "actions_taken": self._required_text(
                request["actions_taken"], "actions_taken", max_length=4000
            ),
            "parts_replaced": self._optional_text(
                request.get("parts_replaced"), "parts_replaced", max_length=2000
            ),
            "technician_note": self._required_text(
                request["technician_note"], "technician_note", max_length=4000
            ),
            "maintenance_result": result_code,
            "follow_up_required": request["follow_up_required"],
            "next_maintenance_date": next_date,
        }
        updates = {
            "status": "completed",
            "completed_at": self._utc_now(),
            "completion_summary": self._required_text(
                request["completion_summary"], "completion_summary", max_length=4000
            ),
            "safety_notes": self._optional_text(
                request.get("safety_notes"), "safety_notes", max_length=4000
            ),
            "labor_minutes": request["labor_minutes"],
            "hold_reason": None,
        }
        return dict(
            self._repository_provider()
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
        current = dict(self._get_work_order_record(work_order_id).values)
        if current["status"] == "verified":
            return current
        if current["status"] != "completed":
            raise MaintenanceConflictError("Chỉ work order completed mới được verify.")
        if current["assigned_to_user_id"] == str(actor.id):
            raise MaintenanceAuthorizationError(
                "Người thực hiện không được tự verify work order của mình."
            )
        return dict(
            self._repository_provider()
            .verify_work_order(
                work_order_id,
                expected_version=expected_version,
                verified_by_user_id=actor.id,
                audit_context=audit_context,
            )
            .values
        )

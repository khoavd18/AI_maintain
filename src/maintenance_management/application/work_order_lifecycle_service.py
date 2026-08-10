"""Work-order execution-state and checklist command orchestration.

The collaborator owns state-machine validation and checklist response intent.
The PostgreSQL repository remains the transaction owner for row locks, expected
versions, audit writes, and commit/rollback.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from src.maintenance_management.domain import WORK_ORDER_TRANSITIONS, WorkOrderStatus
from src.maintenance_management.errors import MaintenanceConflictError, MaintenanceDomainError
from src.repositories.contracts import MaintenancePlanningRepository, StoredRecord
from src.security.audit_context import AuditContext
from src.security.principal import CurrentUser


class WorkOrderLifecycleService:
    """Own named transitions, checklist updates, cancellation, and reopening."""

    def __init__(
        self,
        repository_provider: Callable[[], MaintenancePlanningRepository],
        *,
        get_work_order_record: Callable[[UUID], StoredRecord],
        get_work_order: Callable[..., dict[str, Any]],
        require_work_order_access: Callable[[dict[str, Any], CurrentUser], None],
        normalize_checklist_response: Callable[..., dict[str, Any]],
        required_text: Callable[..., str],
        utc_now: Callable[[], datetime],
    ) -> None:
        self._repository_provider = repository_provider
        self._get_work_order_record = get_work_order_record
        self._get_work_order = get_work_order
        self._require_work_order_access = require_work_order_access
        self._normalize_checklist_response = normalize_checklist_response
        self._required_text = required_text
        self._utc_now = utc_now

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
        current = dict(self._get_work_order_record(work_order_id).values)
        self._require_work_order_access(current, actor)
        source = WorkOrderStatus(current["status"])
        if target not in WORK_ORDER_TRANSITIONS[source]:
            raise MaintenanceConflictError(
                f"Transition không hợp lệ: {source.value} -> {target.value}."
            )
        if target is WorkOrderStatus.IN_PROGRESS and not current["assigned_to_user_id"]:
            raise MaintenanceConflictError("Work order cần technician hợp lệ trước khi bắt đầu.")
        updates: dict[str, Any] = {"status": target.value, "hold_reason": None}
        action = "work_order.resumed"
        if target is WorkOrderStatus.IN_PROGRESS and current["started_at"] is None:
            updates["started_at"] = self._utc_now()
            action = "work_order.started"
        elif target is WorkOrderStatus.ON_HOLD:
            updates["hold_reason"] = self._required_text(
                hold_reason, "hold_reason", max_length=1000
            )
            action = "work_order.put_on_hold"
        elif target is WorkOrderStatus.ASSIGNED:
            action = "work_order.resumed_to_assigned"
        return dict(
            self._repository_provider()
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
        current = self._get_work_order(work_order_id, actor=actor)
        if current["status"] not in {"in_progress", "on_hold"}:
            raise MaintenanceConflictError(
                "Checklist chỉ được ghi khi work order đang thực hiện hoặc tạm giữ."
            )
        by_id = {UUID(item["id"]): item for item in current["checklist"]}
        normalized = [
            self._normalize_checklist_response(response, by_id, actor.id) for response in responses
        ]
        return dict(
            self._repository_provider()
            .update_checklist(
                work_order_id,
                normalized,
                expected_version=expected_version,
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
        current = dict(self._get_work_order_record(work_order_id).values)
        if (
            WorkOrderStatus.CANCELLED
            not in WORK_ORDER_TRANSITIONS[WorkOrderStatus(current["status"])]
        ):
            raise MaintenanceConflictError("Chỉ work order planned/assigned mới có thể hủy.")
        return dict(
            self._repository_provider()
            .update_work_order(
                work_order_id,
                {
                    "status": "cancelled",
                    "cancelled_at": self._utc_now(),
                    "cancellation_reason": self._required_text(
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
        current = dict(self._get_work_order_record(work_order_id).values)
        if current["status"] != "completed":
            raise MaintenanceConflictError(
                "Chỉ work order completed, chưa verify mới có thể reopen."
            )
        return dict(
            self._repository_provider()
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
                audit_metadata={"reason": self._required_text(reason, "reason", max_length=1000)},
            )
            .values
        )

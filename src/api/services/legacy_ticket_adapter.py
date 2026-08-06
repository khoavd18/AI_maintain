"""Legacy ticket compatibility adapter."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import pandas as pd

from src.analytics.errors import TicketNotFoundError
from src.config.value_mappings import STATUS_CODE_TO_VI
from src.repositories.contracts import StoredRecord
from src.security.audit import AuditContext

from .analytics_snapshot import AnalyticsSnapshotService, FACILITY_TIMEZONE
from .analytics_support import (
    _filter_equals,
    _format_datetime,
    _records,
    _require_safe_datetime,
    _utc_now,
)
from .analytics_projection import AnalyticsProjectionService

if TYPE_CHECKING:
    from src.asset_management.service import AssetManagementService
    from src.security.service import CurrentUser
    from src.ticket_management.service import TicketWorkflowService


class LegacyTicketAdapter:
    """Preserve the original ticket API while isolating its compatibility rules."""

    def __init__(
        self,
        *,
        snapshot: AnalyticsSnapshotService,
        asset_queries: AnalyticsProjectionService,
        asset_management: "AssetManagementService",
        ticket_workflow: "TicketWorkflowService | None",
        maintenance_queries,
    ) -> None:
        self.snapshot = snapshot
        self.asset_queries = asset_queries
        self.asset_management = asset_management
        self.ticket_workflow = ticket_workflow
        self.maintenance_queries = maintenance_queries

    @property
    def repository(self):
        return self.snapshot.repository

    @property
    def tickets(self) -> pd.DataFrame:
        return self.snapshot.tickets

    @property
    def maintenance_logs(self) -> pd.DataFrame:
        return self.maintenance_queries.maintenance_logs

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        return self.asset_queries.get_asset(asset_id)

    def _get_ticket_stored_record(self, ticket_id: str) -> StoredRecord:
        record = self.repository.get_ticket(ticket_id)
        if record is None:
            raise TicketNotFoundError(f"Không tìm thấy ticket_id: {ticket_id}")
        return record

    def list_tickets(
        self,
        asset_id: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        failure_category: str | None = None,
        technician_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        frame = self.tickets
        if asset_id is not None:
            self.get_asset(asset_id)
        frame = _filter_equals(frame, "asset_id", asset_id)
        frame = _filter_equals(frame, "status", status)
        frame = _filter_equals(frame, "priority", priority)
        frame = _filter_equals(frame, "failure_category", failure_category)
        frame = _filter_equals(frame, "technician_id", technician_id)
        frame = frame.sort_values("created_at", ascending=False).head(limit)
        return _records(frame)

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        """Return one transactional ticket for authorization and workflow views."""

        return dict(self._get_ticket_stored_record(ticket_id).values)

    def create_ticket(
        self,
        *,
        asset_id: str,
        issue_description: str,
        priority: str,
        failure_category: str,
        technician_id: str,
        manager_note: str | None = None,
        audit_context: AuditContext | None = None,
        actor: "CurrentUser | None" = None,
    ) -> dict[str, Any]:
        """Create one open inspection ticket in configured transactional storage."""

        if self.ticket_workflow is not None:
            if actor is None or audit_context is None:
                raise ValueError("Ticket workflow PostgreSQL cần actor và audit context.")
            return self.ticket_workflow.legacy_intake(
                {
                    "asset_id": asset_id,
                    "issue_description": issue_description,
                    "priority": priority,
                    "failure_category": failure_category,
                    "technician_id": technician_id,
                    "manager_note": manager_note,
                },
                actor=actor,
                audit_context=audit_context,
            )

        self.get_asset(asset_id)
        if self.asset_management.repository is not None:
            self.asset_management.ensure_ticket_allowed(asset_id)
        created_at = _utc_now()
        record = self.repository.create_ticket(
            {
                "asset_id": asset_id,
                "issue_description": issue_description,
                "priority": priority,
                "status": STATUS_CODE_TO_VI["open"],
                "failure_category": failure_category,
                "created_at": _format_datetime(created_at),
                "resolved_at": None,
                "technician_id": technician_id,
                "manager_note": manager_note,
                "note": None,
            },
            audit_context=audit_context,
        )
        return dict(record.values)

    def update_ticket(
        self,
        ticket_id: str,
        updates: dict[str, Any],
        audit_context: AuditContext | None = None,
        actor: "CurrentUser | None" = None,
    ) -> dict[str, Any]:
        """Apply a small validated ticket update and enforce linear status transitions."""

        if self.ticket_workflow is not None:
            if actor is None or audit_context is None:
                raise ValueError("Ticket workflow PostgreSQL cần actor và audit context.")
            return self.ticket_workflow.legacy_update(
                ticket_id,
                updates,
                actor=actor,
                audit_context=audit_context,
            )

        if not updates:
            raise ValueError("Cần cung cấp ít nhất một trường để cập nhật.")
        stored_ticket = self._get_ticket_stored_record(ticket_id)
        ticket = stored_ticket.values
        for field in ("status", "priority", "technician_id"):
            if field in updates and updates[field] is None:
                raise ValueError(f"{field} không được để trống khi cập nhật.")

        current_status = str(ticket["status"])
        target_status = str(updates.get("status") or current_status)
        allowed_statuses = {
            STATUS_CODE_TO_VI["open"]: {
                STATUS_CODE_TO_VI["open"],
                STATUS_CODE_TO_VI["in_progress"],
            },
            STATUS_CODE_TO_VI["in_progress"]: {
                STATUS_CODE_TO_VI["in_progress"],
                STATUS_CODE_TO_VI["resolved"],
            },
            STATUS_CODE_TO_VI["resolved"]: {STATUS_CODE_TO_VI["resolved"]},
        }
        if target_status not in allowed_statuses.get(current_status, set()):
            raise ValueError(
                f"Chuyển trạng thái không hợp lệ: {current_status} -> {target_status}."
            )

        normalized_updates = dict(updates)
        resolved_at = normalized_updates.get("resolved_at")
        if target_status == STATUS_CODE_TO_VI["resolved"]:
            linked_logs = self.maintenance_queries.maintenance_logs[
                self.maintenance_queries.maintenance_logs["ticket_id"].astype(str) == ticket_id
            ]
            if linked_logs.empty:
                raise ValueError("Ticket cần có maintenance log trước khi chuyển sang Đã xử lý.")
            resolution_time = resolved_at or _utc_now()
            resolution_time = _require_safe_datetime(resolution_time, field_name="resolved_at")
            created_at = datetime.fromisoformat(str(ticket["created_at"]))
            if resolution_time < created_at:
                raise ValueError("resolved_at không được sớm hơn created_at.")
            latest_log_date = max(
                date.fromisoformat(value) for value in linked_logs["maintenance_date"].astype(str)
            )
            if resolution_time.astimezone(FACILITY_TIMEZONE).date() < latest_log_date:
                raise ValueError("resolved_at không được sớm hơn maintenance log gần nhất.")
            normalized_updates["resolved_at"] = _format_datetime(resolution_time)
        elif "resolved_at" in normalized_updates:
            raise ValueError("resolved_at chỉ được dùng khi ticket ở trạng thái Đã xử lý.")

        updated = self.repository.update_ticket(
            ticket_id,
            normalized_updates,
            expected_version=stored_ticket.version,
            audit_context=audit_context,
        )
        return dict(updated.values)


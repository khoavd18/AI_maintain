"""Legacy maintenance-log compatibility adapter."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from src.analytics.errors import AssetNotFoundError, TicketNotFoundError
from src.config.value_mappings import (
    MAINTENANCE_RESULT_CODE_TO_VI,
    MAINTENANCE_TYPE_CODE_TO_VI,
    STATUS_CODE_TO_VI,
)
from src.repositories.contracts import StoredRecord
from src.security.audit import AuditContext

from .analytics_snapshot import AnalyticsSnapshotService, FACILITY_TIMEZONE
from .analytics_support import _filter_equals, _records

class LegacyMaintenanceAdapter:
    """Preserve legacy maintenance-log writes and projections."""

    def __init__(
        self,
        *,
        snapshot: AnalyticsSnapshotService,
        asset_queries,
    ) -> None:
        self.snapshot = snapshot
        self.asset_queries = asset_queries

    @property
    def repository(self):
        return self.snapshot.repository

    @property
    def maintenance_logs(self) -> pd.DataFrame:
        return self.snapshot.maintenance_logs

    def list_maintenance_logs(
        self,
        asset_id: str | None = None,
        maintenance_result: str | None = None,
        follow_up_required: bool | None = None,
        technician_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        frame = self.maintenance_logs
        if asset_id is not None:
            self.asset_queries.get_asset(asset_id)
        frame = _filter_equals(frame, "asset_id", asset_id)
        frame = _filter_equals(frame, "maintenance_result", maintenance_result)
        if follow_up_required is not None:
            frame = frame[frame["follow_up_required"] == follow_up_required]
        frame = _filter_equals(frame, "technician_id", technician_id)
        frame = frame.sort_values("maintenance_date", ascending=False).head(limit)
        return _records(frame)

    def _get_asset_record(self, asset_id: str) -> StoredRecord:
        record = self.repository.get_asset(asset_id)
        if record is None:
            raise AssetNotFoundError(f"Unknown asset_id: {asset_id}")
        return record

    def _get_ticket_stored_record(self, ticket_id: str) -> StoredRecord:
        record = self.repository.get_ticket(ticket_id)
        if record is None:
            raise TicketNotFoundError(f"Không tìm thấy ticket_id: {ticket_id}")
        return record

    def _get_maintenance_log_record(self, log_id: str) -> dict[str, Any]:
        record = self.repository.get_maintenance_log(log_id)
        if record is None:
            raise ValueError(f"Không tìm thấy log_id vừa tạo: {log_id}")
        return dict(record.values)

    def create_maintenance_log(
        self,
        *,
        ticket_id: str,
        asset_id: str,
        maintenance_date: date,
        inspection_result: str,
        actions_taken: str,
        parts_replaced: str | None,
        technician_note: str,
        maintenance_result: str,
        follow_up_required: bool,
        next_maintenance_date: date,
        audit_context: AuditContext | None = None,
    ) -> dict[str, Any]:
        """Record one technician result without recalculating batch analytics."""

        stored_asset = self._get_asset_record(asset_id)
        asset = stored_asset.values
        stored_ticket = self._get_ticket_stored_record(ticket_id)
        ticket = stored_ticket.values
        if ticket["asset_id"] != asset_id:
            raise ValueError("asset_id không khớp với ticket đã chọn.")
        if ticket["status"] != STATUS_CODE_TO_VI["in_progress"]:
            raise ValueError("Ticket phải ở trạng thái Đang xử lý trước khi ghi kết quả.")
        if maintenance_date > datetime.now(FACILITY_TIMEZONE).date():
            raise ValueError("maintenance_date không được nằm trong tương lai.")
        created_date = (
            datetime.fromisoformat(str(ticket["created_at"])).astimezone(FACILITY_TIMEZONE).date()
        )
        if maintenance_date < created_date:
            raise ValueError("maintenance_date không được sớm hơn ngày tạo ticket.")

        interval_days = int(asset["maintenance_interval_days"])
        expected_next_date = maintenance_date + timedelta(days=interval_days)
        if next_maintenance_date != expected_next_date:
            raise ValueError(
                "next_maintenance_date phải bằng maintenance_date cộng chu kỳ bảo trì "
                f"{interval_days} ngày ({expected_next_date.isoformat()})."
            )
        current_last_date = date.fromisoformat(str(asset["last_maintenance_date"]))
        if maintenance_date < current_last_date:
            raise ValueError("maintenance_date không được sớm hơn lần bảo trì gần nhất của asset.")
        expected_follow_up = maintenance_result != MAINTENANCE_RESULT_CODE_TO_VI["resolved"]
        if follow_up_required != expected_follow_up:
            raise ValueError("follow_up_required không nhất quán với maintenance_result.")

        created = self.repository.create_maintenance_log(
            {
                "ticket_id": ticket_id,
                "asset_id": asset_id,
                "maintenance_date": maintenance_date.isoformat(),
                "maintenance_type": MAINTENANCE_TYPE_CODE_TO_VI["corrective"],
                "technician_id": ticket["technician_id"],
                "inspection_result": inspection_result,
                "actions_taken": actions_taken,
                "parts_replaced": parts_replaced,
                "technician_note": technician_note,
                "maintenance_result": maintenance_result,
                "follow_up_required": follow_up_required,
                "next_maintenance_date": next_maintenance_date.isoformat(),
            },
            last_maintenance_date=maintenance_date,
            next_maintenance_date=next_maintenance_date,
            expected_asset_version=stored_asset.version,
            expected_ticket_version=stored_ticket.version,
            audit_context=audit_context,
        )
        return dict(created.values)

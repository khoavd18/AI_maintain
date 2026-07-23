"""Storage-neutral transactional services plus CSV-backed batch analytics."""

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from src.asset_management.service import AssetManagementService
from src.asset_management.storage import LocalAttachmentStorage
from src.config.value_mappings import (
    MAINTENANCE_RESULT_CODE_TO_VI,
    MAINTENANCE_TYPE_CODE_TO_VI,
    RISK_LEVEL_CODE_TO_VI,
    STATUS_CODE_TO_VI,
)
from src.config.settings import get_settings
from src.database.session import get_session_factory
from src.repositories.contracts import MaintenanceRepository, StoredRecord
from src.repositories.csv import (
    ASSET_REQUIRED_COLUMNS,
    MAINTENANCE_LOG_REQUIRED_COLUMNS,
    TICKET_REQUIRED_COLUMNS,
    CsvMaintenanceRepository,
)
from src.repositories.postgres import PostgresMaintenanceRepository
from src.repositories.postgres_assets import PostgresAssetRepository
from src.security.audit import AuditContext

if TYPE_CHECKING:
    from src.security.service import CurrentUser
    from src.ticket_management.service import TicketWorkflowService

__all__ = [
    "ASSET_REQUIRED_COLUMNS",
    "MAINTENANCE_LOG_REQUIRED_COLUMNS",
    "TICKET_REQUIRED_COLUMNS",
    "ProcessedDataService",
    "get_processed_data_service",
]

RAW_DATA_DIR = Path("data/raw")
PROCESSED_DATA_DIR = Path("data/processed")

ASSET_FILE = RAW_DATA_DIR / "assets.csv"
TICKET_FILE = RAW_DATA_DIR / "maintenance_tickets.csv"
MAINTENANCE_LOG_FILE = RAW_DATA_DIR / "maintenance_logs.csv"
FEATURE_FILE = PROCESSED_DATA_DIR / "asset_daily_features.csv"
ANOMALY_FILE = PROCESSED_DATA_DIR / "anomaly_results.csv"
RISK_FILE = PROCESSED_DATA_DIR / "risk_scores.csv"
PREVENTIVE_FILE = PROCESSED_DATA_DIR / "preventive_maintenance_status.csv"
RECURRING_ISSUE_FILE = PROCESSED_DATA_DIR / "recurring_issues.csv"
MAINTENANCE_KPI_FILE = PROCESSED_DATA_DIR / "maintenance_kpis.csv"
FACILITY_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

ASSET_COLUMNS = [
    "asset_id",
    "asset_name",
    "asset_type",
    "location",
    "criticality",
    "status",
    "installation_date",
    "last_maintenance_date",
    "maintenance_interval_days",
    "next_maintenance_date",
]
TICKET_COLUMNS = [
    "ticket_id",
    "asset_id",
    "issue_description",
    "priority",
    "status",
    "failure_category",
    "created_at",
    "resolved_at",
    "technician_id",
    "manager_note",
    "note",
]
MAINTENANCE_LOG_COLUMNS = [
    "log_id",
    "ticket_id",
    "asset_id",
    "maintenance_date",
    "maintenance_type",
    "technician_id",
    "inspection_result",
    "actions_taken",
    "parts_replaced",
    "technician_note",
    "maintenance_result",
    "follow_up_required",
    "next_maintenance_date",
]


class ProcessedDataNotFoundError(FileNotFoundError):
    """Raised when a required CSV source is missing or stale."""


class AssetNotFoundError(ValueError):
    """Raised when an asset_id cannot be found in the asset master."""


class TicketNotFoundError(ValueError):
    """Raised when a ticket_id cannot be found in the ticket CSV."""


class ProcessedDataService:
    """Compose transactional persistence with immutable batch analytics snapshots."""

    def __init__(
        self,
        feature_path: Path = FEATURE_FILE,
        anomaly_path: Path = ANOMALY_FILE,
        risk_path: Path = RISK_FILE,
        asset_path: Path = ASSET_FILE,
        ticket_path: Path = TICKET_FILE,
        maintenance_log_path: Path = MAINTENANCE_LOG_FILE,
        preventive_path: Path = PREVENTIVE_FILE,
        recurring_issue_path: Path = RECURRING_ISSUE_FILE,
        maintenance_kpi_path: Path = MAINTENANCE_KPI_FILE,
        repository: MaintenanceRepository | None = None,
        asset_management: AssetManagementService | None = None,
        ticket_workflow: "TicketWorkflowService | None" = None,
    ) -> None:
        self.feature_path = feature_path
        self.anomaly_path = anomaly_path
        self.risk_path = risk_path
        self.asset_path = asset_path
        self.ticket_path = ticket_path
        self.maintenance_log_path = maintenance_log_path
        self.preventive_path = preventive_path
        self.recurring_issue_path = recurring_issue_path
        self.maintenance_kpi_path = maintenance_kpi_path
        self.repository = repository or CsvMaintenanceRepository(
            asset_path=asset_path,
            ticket_path=ticket_path,
            maintenance_log_path=maintenance_log_path,
        )
        self.ticket_workflow = ticket_workflow
        settings = get_settings()
        if asset_management is not None:
            self.asset_management = asset_management
        else:
            session_factory = getattr(self.repository, "session_factory", None)
            asset_repository = (
                PostgresAssetRepository(session_factory) if session_factory is not None else None
            )
            self.asset_management = AssetManagementService(
                asset_repository,
                LocalAttachmentStorage(settings.attachment_storage_root),
                attachment_max_size_bytes=settings.attachment_max_size_bytes,
                frontend_base_url=settings.frontend_base_url,
            )

    @property
    def assets(self) -> pd.DataFrame:
        return _repository_frame(self.repository.list_assets(), ASSET_COLUMNS)

    @property
    def tickets(self) -> pd.DataFrame:
        return _repository_frame(self.repository.list_tickets(), TICKET_COLUMNS)

    @property
    def maintenance_logs(self) -> pd.DataFrame:
        return _repository_frame(
            self.repository.list_maintenance_logs(),
            MAINTENANCE_LOG_COLUMNS,
        )

    @property
    def features(self) -> pd.DataFrame:
        return _load_csv(
            self.feature_path,
            "daily features",
            date_columns=[
                "feature_date",
                "last_maintenance_date",
                "next_maintenance_date",
            ],
        )

    @property
    def anomalies(self) -> pd.DataFrame:
        frame = _load_csv(
            self.anomaly_path,
            "anomaly results",
            date_columns=["feature_date", "date"],
        )
        if "is_anomaly" in frame.columns:
            frame["is_anomaly"] = _boolean_series(frame["is_anomaly"])
        return frame

    @property
    def risks(self) -> pd.DataFrame:
        return _load_csv(
            self.risk_path,
            "risk results",
            date_columns=["feature_date", "date"],
        )

    @property
    def preventive_status(self) -> pd.DataFrame:
        return _load_csv(
            self.preventive_path,
            "preventive maintenance status",
            date_columns=[
                "as_of_date",
                "last_maintenance_date",
                "next_maintenance_date",
            ],
        )

    @property
    def recurring_issues(self) -> pd.DataFrame:
        frame = _load_csv(
            self.recurring_issue_path,
            "recurring issue analysis",
            datetime_columns=["first_occurrence", "last_occurrence"],
        )
        if "recurrence_flag" in frame.columns:
            frame["recurrence_flag"] = _boolean_series(frame["recurrence_flag"])
        return frame

    @property
    def maintenance_kpis(self) -> pd.DataFrame:
        return _load_csv(
            self.maintenance_kpi_path,
            "maintenance KPI snapshot",
            date_columns=["as_of_date"],
        )

    def get_health(self) -> dict[str, object]:
        """Return availability without making optional RAG a health dependency."""

        try:
            self.repository.check_health()
            raw_available = True
        except (OSError, RuntimeError, ValueError):
            raw_available = False
        analytics_available = self._analytics_available()
        return {
            "status": "ok" if raw_available and analytics_available else "degraded",
            "raw_data_available": raw_available,
            "analytics_available": analytics_available,
        }

    def get_summary(self) -> dict[str, Any]:
        """Build the backward-compatible summary from the latest analytics date."""

        self._ensure_analytics_current()
        risks = self.risks
        anomalies = self.anomalies
        latest_date = _latest_date(risks, "date")
        latest_risks = _filter_by_date(risks, latest_date) if latest_date else risks
        latest_anomalies = _filter_by_date(anomalies, latest_date) if latest_date else anomalies

        return _clean_record(
            {
                "total_assets": int(risks["asset_id"].nunique()),
                "total_records": int(len(risks)),
                "high_risk_count": int(
                    (latest_risks["risk_level"] == RISK_LEVEL_CODE_TO_VI["high"]).sum()
                ),
                "urgent_risk_count": int(
                    (latest_risks["risk_level"] == RISK_LEVEL_CODE_TO_VI["critical"]).sum()
                ),
                "anomaly_count": int(latest_anomalies["is_anomaly"].sum()),
                "latest_date": latest_date,
                "average_risk_score": round(float(latest_risks["final_risk_score"].mean()), 2)
                if not latest_risks.empty
                else 0.0,
            }
        )

    def list_assets(
        self,
        asset_type: str | None = None,
        location: str | None = None,
        criticality: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return asset master rows enriched with latest analytics signals."""

        self._ensure_analytics_current()
        assets = self.assets
        assets = _filter_equals(assets, "asset_type", asset_type)
        assets = _filter_equals(assets, "location", location)
        assets = _filter_equals(assets, "criticality", criticality)
        assets = _filter_equals(assets, "status", status)

        risks = _latest_rows(self.risks, "date")
        risk_columns = [
            "asset_id",
            "risk_score",
            "risk_level_code",
            "risk_level",
            "contributing_factors",
            "recommended_action",
        ]
        preventive = self.preventive_status[
            [
                "asset_id",
                "maintenance_status",
                "maintenance_status_display",
                "days_until_due",
                "days_overdue",
            ]
        ]
        features = _latest_rows(self.features, "feature_date")[
            ["asset_id", "unresolved_ticket_count"]
        ]
        overview = (
            assets.merge(risks[risk_columns], on="asset_id", how="left")
            .merge(preventive, on="asset_id", how="left")
            .merge(features, on="asset_id", how="left")
            .sort_values(["risk_score", "asset_id"], ascending=[False, True], na_position="last")
        )
        return _records(overview)

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        return dict(self._get_asset_record(asset_id).values)

    def list_risks(
        self,
        risk_level: str | None = None,
        asset_type: str | None = None,
        location: str | None = None,
        date: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self._ensure_analytics_current()
        frame = self.risks
        frame = _filter_equals(frame, "risk_level", risk_level)
        frame = _filter_equals(frame, "asset_type", asset_type)
        frame = _filter_equals(frame, "location", location)
        frame = _filter_equals(frame, "date", date)
        frame = frame.sort_values("final_risk_score", ascending=False).head(limit)
        return _records(frame)

    def list_top_risks(self, limit: int = 10, date: str | None = None) -> list[dict[str, Any]]:
        self._ensure_analytics_current()
        frame = self.risks
        selected_date = date or _latest_date(frame, "date")
        frame = _filter_by_date(frame, selected_date)
        frame = frame.sort_values("final_risk_score", ascending=False).head(limit)
        return _records(frame)

    def get_asset_risk_history(self, asset_id: str) -> list[dict[str, Any]]:
        self._ensure_analytics_current()
        self.get_asset(asset_id)
        history = self.risks[self.risks["asset_id"] == asset_id].sort_values("date")
        return _records(history)

    def list_anomalies(
        self,
        asset_type: str | None = None,
        anomaly_type: str | None = None,
        date: str | None = None,
        only_anomalies: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._ensure_analytics_current()
        frame = self.anomalies
        frame = _filter_equals(frame, "asset_type", asset_type)
        frame = _filter_equals(frame, "anomaly_type", anomaly_type)
        frame = _filter_equals(frame, "date", date)
        if only_anomalies:
            frame = frame[frame["is_anomaly"]]
        frame = frame.sort_values("anomaly_score", ascending=False).head(limit)
        return _records(frame)

    def get_asset_anomaly_history(self, asset_id: str) -> list[dict[str, Any]]:
        self._ensure_analytics_current()
        self.get_asset(asset_id)
        history = self.anomalies[self.anomalies["asset_id"] == asset_id].sort_values("date")
        return _records(history)

    def list_preventive_maintenance(
        self,
        maintenance_status: str | None = None,
        asset_type: str | None = None,
        criticality: str | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_analytics_current()
        asset_columns = ["asset_id", "asset_name", "asset_type", "location", "criticality"]
        frame = self.preventive_status.merge(self.assets[asset_columns], on="asset_id", how="left")
        frame = _filter_equals(frame, "maintenance_status", maintenance_status)
        frame = _filter_equals(frame, "asset_type", asset_type)
        frame = _filter_equals(frame, "criticality", criticality)
        frame = frame.sort_values(["days_overdue", "days_until_due"], ascending=[False, True])
        return _records(frame)

    def list_recurring_issues(
        self,
        asset_id: str | None = None,
        failure_category: str | None = None,
        recurrence_flag: bool | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_analytics_current()
        frame = self.recurring_issues
        if asset_id is not None:
            self.get_asset(asset_id)
        frame = _filter_equals(frame, "asset_id", asset_id)
        frame = _filter_equals(frame, "failure_category", failure_category)
        if recurrence_flag is not None:
            frame = frame[frame["recurrence_flag"] == recurrence_flag]
        frame = frame.sort_values(
            ["recurrence_flag", "occurrence_count", "asset_id"],
            ascending=[False, False, True],
        )
        return _records(frame)

    def get_maintenance_kpis(self) -> dict[str, Any]:
        self._ensure_analytics_current()
        frame = self.maintenance_kpis
        if len(frame) != 1:
            raise ProcessedDataNotFoundError(
                "Maintenance KPI snapshot is unavailable or invalid. Regenerate analytics outputs."
            )
        return _records(frame)[0]

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
            self.get_asset(asset_id)
        frame = _filter_equals(frame, "asset_id", asset_id)
        frame = _filter_equals(frame, "maintenance_result", maintenance_result)
        if follow_up_required is not None:
            frame = frame[frame["follow_up_required"] == follow_up_required]
        frame = _filter_equals(frame, "technician_id", technician_id)
        frame = frame.sort_values("maintenance_date", ascending=False).head(limit)
        return _records(frame)

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
            linked_logs = self.maintenance_logs[
                self.maintenance_logs["ticket_id"].astype(str) == ticket_id
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

    def _get_ticket_record(self, ticket_id: str) -> dict[str, Any]:
        return dict(self._get_ticket_stored_record(ticket_id).values)

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

    def get_asset_details(self, asset_id: str, limit: int = 10) -> dict[str, Any]:
        """Return the manager-facing consolidated asset workflow payload."""

        self._ensure_analytics_current()
        asset_profile = self.get_asset(asset_id)
        risk_history = self.risks[self.risks["asset_id"] == asset_id].sort_values("date")
        latest_risk_records = _records(risk_history.tail(1))
        latest_risk = latest_risk_records[0] if latest_risk_records else None

        anomaly_history = self.anomalies
        anomaly_history = anomaly_history[
            (anomaly_history["asset_id"] == asset_id) & anomaly_history["is_anomaly"]
        ].sort_values("date", ascending=False)
        preventive = self.preventive_status[self.preventive_status["asset_id"] == asset_id]
        preventive_record = _records(preventive.head(1))

        return {
            "asset_profile": asset_profile,
            "latest_risk": latest_risk,
            "risk_contributing_factors": latest_risk.get("contributing_factors")
            if latest_risk
            else None,
            "recommended_action": latest_risk.get("recommended_action") if latest_risk else None,
            "preventive_maintenance": preventive_record[0] if preventive_record else None,
            "risk_history": _records(risk_history),
            "recent_anomalies": _records(anomaly_history.head(limit)),
            "recent_tickets": self.list_tickets(asset_id=asset_id, limit=limit),
            "recent_maintenance_logs": self.list_maintenance_logs(asset_id=asset_id, limit=limit),
            "recurring_issues": self.list_recurring_issues(asset_id=asset_id),
        }

    def get_asset_context(self, asset_id: str, limit: int = 10) -> dict[str, Any]:
        """Return the backward-compatible context used by the current Copilot."""

        self._ensure_analytics_current()
        self.get_asset(asset_id)
        risk_history = self.risks[self.risks["asset_id"] == asset_id].sort_values(
            "date", ascending=False
        )
        latest_risk = _records(risk_history.head(1))[0]
        anomaly_history = self.anomalies
        anomaly_history = anomaly_history[anomaly_history["asset_id"] == asset_id].sort_values(
            "date", ascending=False
        )
        feature_history = self.features
        feature_history = feature_history[feature_history["asset_id"] == asset_id].sort_values(
            "feature_date", ascending=False
        )
        return {
            "asset_id": asset_id,
            "latest_risk": latest_risk,
            "recent_anomalies": _records(anomaly_history.head(limit)),
            "recent_features": _records(feature_history.head(limit)),
            "latest_recommendation": latest_risk.get("recommended_action"),
        }

    def _analytics_paths(self) -> list[Path]:
        return [
            self.feature_path,
            self.anomaly_path,
            self.risk_path,
            self.preventive_path,
            self.recurring_issue_path,
            self.maintenance_kpi_path,
        ]

    def _analytics_available(self) -> bool:
        if not all(path.exists() for path in self._analytics_paths()):
            return False
        try:
            return self._analytics_dates_are_current()
        except (ValueError, KeyError, pd.errors.ParserError):
            return False

    def _ensure_analytics_current(self) -> None:
        if not all(path.exists() for path in self._analytics_paths()):
            raise ProcessedDataNotFoundError(
                "Required analytics output is unavailable. Regenerate the CSV analytics pipeline."
            )
        if not self._analytics_dates_are_current():
            raise ProcessedDataNotFoundError(
                "Analytics outputs are stale or inconsistent. Regenerate the CSV analytics pipeline."
            )

    def _analytics_dates_are_current(self) -> bool:
        latest_dates = {
            _latest_date(self.features, "feature_date"),
            _latest_date(self.anomalies, "date"),
            _latest_date(self.risks, "date"),
            _latest_date(self.preventive_status, "as_of_date"),
            _latest_date(self.maintenance_kpis, "as_of_date"),
        }
        return None not in latest_dates and len(latest_dates) == 1


@lru_cache(maxsize=1)
def get_processed_data_service() -> ProcessedDataService:
    settings = get_settings()
    if settings.storage_backend == "csv":
        repository: MaintenanceRepository = CsvMaintenanceRepository(
            asset_path=ASSET_FILE,
            ticket_path=TICKET_FILE,
            maintenance_log_path=MAINTENANCE_LOG_FILE,
        )
    else:
        session_factory = get_session_factory(settings.database_url)
        repository = PostgresMaintenanceRepository(session_factory)
        from src.repositories.postgres_tickets import PostgresTicketRepository
        from src.ticket_management.service import TicketWorkflowService

        ticket_workflow = TicketWorkflowService(PostgresTicketRepository(session_factory))
        return ProcessedDataService(
            repository=repository,
            ticket_workflow=ticket_workflow,
        )
    return ProcessedDataService(repository=repository)


def _repository_frame(
    records: list[StoredRecord],
    columns: list[str],
) -> pd.DataFrame:
    return pd.DataFrame([record.values for record in records], columns=columns)


def _load_csv(
    path: Path,
    label: str,
    date_columns: list[str] | None = None,
    datetime_columns: list[str] | None = None,
) -> pd.DataFrame:
    if not path.exists():
        raise ProcessedDataNotFoundError(
            f"Required data source is unavailable: {label}. Regenerate the CSV pipeline."
        )
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError) as exc:
        raise ProcessedDataNotFoundError(
            f"Required data source could not be read: {label}. Regenerate the CSV pipeline."
        ) from exc
    for column in date_columns or []:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="raise").dt.date.astype(str)
    for column in datetime_columns or []:
        if column in frame.columns:
            frame[column] = _iso_datetime_series(frame[column])
    return frame.replace([np.inf, -np.inf], np.nan)


def _iso_datetime_series(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    invalid = values.notna() & values.astype(str).str.strip().ne("") & parsed.isna()
    if invalid.any():
        raise ValueError(f"Invalid timestamp value: {values.loc[invalid].iloc[0]!r}")
    return parsed.map(lambda value: value.isoformat() if pd.notna(value) else None)


def _boolean_series(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.astype(bool)
    normalized = values.astype(str).str.strip().str.lower()
    invalid = ~normalized.isin(["true", "false"])
    if invalid.any():
        raise ValueError(f"Invalid boolean value: {values.loc[invalid].iloc[0]!r}")
    return normalized.eq("true")


def _filter_equals(frame: pd.DataFrame, column: str, value: object | None) -> pd.DataFrame:
    if value is None:
        return frame
    return frame[frame[column] == value]


def _filter_by_date(frame: pd.DataFrame, date: str | None) -> pd.DataFrame:
    if date is None:
        return frame
    return frame[frame["date"] == date]


def _latest_rows(frame: pd.DataFrame, date_column: str) -> pd.DataFrame:
    latest_date = _latest_date(frame, date_column)
    return frame[frame[date_column] == latest_date].copy() if latest_date else frame.iloc[0:0]


def _latest_date(frame: pd.DataFrame, column: str) -> str | None:
    if frame.empty:
        return None
    values = frame[column].dropna().astype(str)
    return str(values.max()) if not values.empty else None


def _ensure_asset_exists(asset_id: str, frame: pd.DataFrame) -> None:
    if asset_id not in set(frame["asset_id"].astype(str)):
        raise AssetNotFoundError(f"Unknown asset_id: {asset_id}")


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [_clean_record(record) for record in frame.to_dict(orient="records")]


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: _clean_value(value) for key, value in record.items()}


def _clean_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _require_safe_datetime(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} phải có timezone.")
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    if normalized > _utc_now() + timedelta(minutes=5):
        raise ValueError(f"{field_name} không được nằm trong tương lai.")
    return normalized


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

"""Batch analytics snapshot service."""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.analytics.errors import ProcessedDataNotFoundError
from src.repositories.contracts import MaintenanceRepository

from .analytics_support import (
    _boolean_series,
    _latest_date,
    _load_csv,
    _repository_frame,
)

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


class AnalyticsSnapshotService:
    """Own immutable CSV snapshot loading and freshness validation."""

    def __init__(
        self,
        *,
        repository: MaintenanceRepository,
        feature_path: Path = FEATURE_FILE,
        anomaly_path: Path = ANOMALY_FILE,
        risk_path: Path = RISK_FILE,
        asset_path: Path = ASSET_FILE,
        ticket_path: Path = TICKET_FILE,
        maintenance_log_path: Path = MAINTENANCE_LOG_FILE,
        preventive_path: Path = PREVENTIVE_FILE,
        recurring_issue_path: Path = RECURRING_ISSUE_FILE,
        maintenance_kpi_path: Path = MAINTENANCE_KPI_FILE,
    ) -> None:
        self.repository = repository
        self.feature_path = feature_path
        self.anomaly_path = anomaly_path
        self.risk_path = risk_path
        self.asset_path = asset_path
        self.ticket_path = ticket_path
        self.maintenance_log_path = maintenance_log_path
        self.preventive_path = preventive_path
        self.recurring_issue_path = recurring_issue_path
        self.maintenance_kpi_path = maintenance_kpi_path

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

    def ensure_analytics_current(self) -> None:
        """Require that all batch analytics outputs represent one current snapshot."""

        self._ensure_analytics_current()

    def _analytics_dates_are_current(self) -> bool:
        latest_dates = {
            _latest_date(self.features, "feature_date"),
            _latest_date(self.anomalies, "date"),
            _latest_date(self.risks, "date"),
            _latest_date(self.preventive_status, "as_of_date"),
            _latest_date(self.maintenance_kpis, "as_of_date"),
        }
        return None not in latest_dates and len(latest_dates) == 1

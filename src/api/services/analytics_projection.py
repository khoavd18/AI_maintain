"""Analytics projection service for legacy read models."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.analytics.errors import AssetNotFoundError, ProcessedDataNotFoundError
from src.config.value_mappings import RISK_LEVEL_CODE_TO_VI
from src.repositories.contracts import StoredRecord

from .analytics_snapshot import AnalyticsSnapshotService
from .analytics_support import (
    _filter_by_date,
    _filter_equals,
    _latest_date,
    _latest_rows,
    _clean_record,
    _records,
)


class AnalyticsProjectionService:
    """Own analytics filters, sorting, and legacy read-model projections."""

    def __init__(self, snapshot: AnalyticsSnapshotService) -> None:
        self.snapshot = snapshot

    @property
    def assets(self) -> pd.DataFrame:
        return self.snapshot.assets

    @property
    def tickets(self) -> pd.DataFrame:
        return self.snapshot.tickets

    @property
    def maintenance_logs(self) -> pd.DataFrame:
        return self.snapshot.maintenance_logs

    @property
    def features(self) -> pd.DataFrame:
        return self.snapshot.features

    @property
    def anomalies(self) -> pd.DataFrame:
        return self.snapshot.anomalies

    @property
    def risks(self) -> pd.DataFrame:
        return self.snapshot.risks

    @property
    def preventive_status(self) -> pd.DataFrame:
        return self.snapshot.preventive_status

    @property
    def recurring_issues(self) -> pd.DataFrame:
        return self.snapshot.recurring_issues

    @property
    def maintenance_kpis(self) -> pd.DataFrame:
        return self.snapshot.maintenance_kpis

    def _ensure_analytics_current(self) -> None:
        self.snapshot.ensure_analytics_current()

    def _get_asset_record(self, asset_id: str) -> StoredRecord:
        record = self.snapshot.repository.get_asset(asset_id)
        if record is None:
            raise AssetNotFoundError(f"Unknown asset_id: {asset_id}")
        return record

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

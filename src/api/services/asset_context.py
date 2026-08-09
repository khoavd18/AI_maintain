"""Read-only asset context projections used by manager views and RAG."""

from __future__ import annotations

from typing import Any

from .analytics_projection import AnalyticsProjectionService
from .analytics_snapshot import AnalyticsSnapshotService
from .analytics_support import _records


class AssetContextQueryService:
    """Compose asset analytics and legacy workflow context without writes."""

    def __init__(
        self,
        *,
        snapshot: AnalyticsSnapshotService,
        projections: AnalyticsProjectionService,
        tickets,
        maintenance_logs,
    ) -> None:
        self.snapshot = snapshot
        self.projections = projections
        self.tickets = tickets
        self.maintenance_logs = maintenance_logs

    def get_asset_details(self, asset_id: str, limit: int = 10) -> dict[str, Any]:
        """Return the manager-facing consolidated asset workflow payload."""

        self.snapshot.ensure_analytics_current()
        asset_profile = self.projections.get_asset(asset_id)
        risk_history = self.snapshot.risks[self.snapshot.risks["asset_id"] == asset_id].sort_values(
            "date"
        )
        latest_risk_records = _records(risk_history.tail(1))
        latest_risk = latest_risk_records[0] if latest_risk_records else None

        anomaly_history = self.snapshot.anomalies
        anomaly_history = anomaly_history[
            (anomaly_history["asset_id"] == asset_id) & anomaly_history["is_anomaly"]
        ].sort_values("date", ascending=False)
        preventive = self.snapshot.preventive_status[
            self.snapshot.preventive_status["asset_id"] == asset_id
        ]
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
            "recent_tickets": self.tickets.list_tickets(asset_id=asset_id, limit=limit),
            "recent_maintenance_logs": self.maintenance_logs.list_maintenance_logs(
                asset_id=asset_id, limit=limit
            ),
            "recurring_issues": self.projections.list_recurring_issues(asset_id=asset_id),
        }

    def get_asset_context(self, asset_id: str, limit: int = 10) -> dict[str, Any]:
        """Return the backward-compatible context consumed by the Copilot."""

        self.snapshot.ensure_analytics_current()
        self.projections.get_asset(asset_id)
        risk_history = self.snapshot.risks[self.snapshot.risks["asset_id"] == asset_id].sort_values(
            "date", ascending=False
        )
        latest_risk = _records(risk_history.head(1))[0]
        anomaly_history = self.snapshot.anomalies
        anomaly_history = anomaly_history[anomaly_history["asset_id"] == asset_id].sort_values(
            "date", ascending=False
        )
        feature_history = self.snapshot.features
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

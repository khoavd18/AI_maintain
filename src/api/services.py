"""CSV-backed data access services for the FastAPI layer."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.config.value_mappings import RISK_LEVEL_CODE_TO_VI

PROCESSED_DATA_DIR = Path("data/processed")
FEATURE_FILE = PROCESSED_DATA_DIR / "asset_daily_features.csv"
ANOMALY_FILE = PROCESSED_DATA_DIR / "anomaly_results.csv"
RISK_FILE = PROCESSED_DATA_DIR / "risk_scores.csv"


class ProcessedDataNotFoundError(FileNotFoundError):
    """Raised when a required processed CSV file is missing."""


class AssetNotFoundError(ValueError):
    """Raised when an asset_id cannot be found in processed outputs."""


class ProcessedDataService:
    """Read and query processed feature, anomaly, and risk CSV outputs."""

    def __init__(
        self,
        feature_path: Path = FEATURE_FILE,
        anomaly_path: Path = ANOMALY_FILE,
        risk_path: Path = RISK_FILE,
    ) -> None:
        self.feature_path = feature_path
        self.anomaly_path = anomaly_path
        self.risk_path = risk_path

    @property
    def features(self) -> pd.DataFrame:
        """Return processed daily feature rows."""

        return _load_csv(self.feature_path, date_columns=["feature_date"])

    @property
    def anomalies(self) -> pd.DataFrame:
        """Return processed anomaly result rows."""

        frame = _load_csv(self.anomaly_path, date_columns=["date"])
        if "is_anomaly" in frame.columns:
            frame["is_anomaly"] = frame["is_anomaly"].astype(bool)
        return frame

    @property
    def risks(self) -> pd.DataFrame:
        """Return processed risk score rows."""

        return _load_csv(self.risk_path, date_columns=["date"])

    def get_summary(self) -> dict[str, Any]:
        """Build a current maintenance summary from the latest processed date."""

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

    def list_risks(
        self,
        risk_level: str | None = None,
        asset_type: str | None = None,
        location: str | None = None,
        date: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List risk records with optional filters."""

        frame = self.risks
        frame = _filter_equals(frame, "risk_level", risk_level)
        frame = _filter_equals(frame, "asset_type", asset_type)
        frame = _filter_equals(frame, "location", location)
        frame = _filter_equals(frame, "date", date)
        frame = frame.sort_values("final_risk_score", ascending=False).head(limit)
        return _records(frame)

    def list_top_risks(self, limit: int = 10, date: str | None = None) -> list[dict[str, Any]]:
        """Return top risky assets for the selected date."""

        frame = self.risks
        selected_date = date or _latest_date(frame, "date")
        frame = _filter_by_date(frame, selected_date)
        frame = frame.sort_values("final_risk_score", ascending=False).head(limit)
        return _records(frame)

    def get_asset_risk_history(self, asset_id: str) -> list[dict[str, Any]]:
        """Return sorted risk history for one asset."""

        frame = self.risks
        _ensure_asset_exists(asset_id, frame)
        history = frame[frame["asset_id"] == asset_id].sort_values("date")
        return _records(history)

    def list_anomalies(
        self,
        asset_type: str | None = None,
        anomaly_type: str | None = None,
        date: str | None = None,
        only_anomalies: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List anomaly records with optional filters."""

        frame = self.anomalies
        frame = _filter_equals(frame, "asset_type", asset_type)
        frame = _filter_equals(frame, "anomaly_type", anomaly_type)
        frame = _filter_equals(frame, "date", date)
        if only_anomalies:
            frame = frame[frame["is_anomaly"]]
        frame = frame.sort_values("anomaly_score", ascending=False).head(limit)
        return _records(frame)

    def get_asset_anomaly_history(self, asset_id: str) -> list[dict[str, Any]]:
        """Return sorted anomaly history for one asset."""

        frame = self.anomalies
        _ensure_asset_exists(asset_id, frame)
        history = frame[frame["asset_id"] == asset_id].sort_values("date")
        return _records(history)

    def get_asset_context(self, asset_id: str, limit: int = 10) -> dict[str, Any]:
        """Return combined risk, anomaly, feature, and recommendation context."""

        risks = self.risks
        _ensure_asset_exists(asset_id, risks)
        risk_history = risks[risks["asset_id"] == asset_id].sort_values("date", ascending=False)
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


@lru_cache(maxsize=1)
def get_processed_data_service() -> ProcessedDataService:
    """Return cached processed-data service for FastAPI dependencies."""

    return ProcessedDataService()


def _load_csv(path: Path, date_columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        raise ProcessedDataNotFoundError(f"Processed data file not found: {path}")
    frame = pd.read_csv(path)
    for column in date_columns:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="raise").dt.date.astype(str)
    return frame.replace([np.inf, -np.inf], np.nan)


def _filter_equals(frame: pd.DataFrame, column: str, value: str | None) -> pd.DataFrame:
    if value is None:
        return frame
    return frame[frame[column] == value]


def _filter_by_date(frame: pd.DataFrame, date: str | None) -> pd.DataFrame:
    if date is None:
        return frame
    return frame[frame["date"] == date]


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
    cleaned: dict[str, Any] = {}
    for key, value in record.items():
        cleaned[key] = _clean_value(value)
    return cleaned


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value

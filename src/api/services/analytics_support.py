"""Shared analytics frame loading, filtering, and serialization helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.analytics.errors import AssetNotFoundError, ProcessedDataNotFoundError
from src.repositories.contracts import StoredRecord


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


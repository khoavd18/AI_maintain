"""Validation for generated maintenance CSV datasets before ingestion."""

from pathlib import Path

import pandas as pd

from src.config.value_mappings import (
    ANOMALY_TYPE_CODE_TO_VI,
    ASSET_TYPE_CODE_TO_VI,
    CRITICALITY_CODE_TO_VI,
    DOCUMENT_TYPE_CODE_TO_VI,
    FAILURE_TYPE_CODE_TO_VI,
    MAINTENANCE_TYPE_CODE_TO_VI,
    PRIORITY_CODE_TO_VI,
    RISK_LEVEL_CODE_TO_VI,
    STATUS_CODE_TO_VI,
)
from src.data_generation.generate_data import DATASET_FILENAMES

REQUIRED_COLUMNS = {
    "assets": {
        "asset_id",
        "asset_name",
        "asset_type",
        "location",
        "floor",
        "criticality",
        "installation_date",
        "last_maintenance_date",
        "maintenance_frequency_days",
        "status",
    },
    "sensor_readings": {
        "reading_id",
        "asset_id",
        "timestamp",
        "energy_kwh",
        "temperature",
        "vibration",
        "runtime_hours",
        "pressure",
        "status",
        "anomaly_type",
    },
    "maintenance_tickets": {
        "ticket_id",
        "asset_id",
        "issue_description",
        "priority",
        "status",
        "created_at",
        "resolved_at",
        "technician_note",
        "failure_type",
    },
    "maintenance_logs": {
        "log_id",
        "asset_id",
        "maintenance_date",
        "maintenance_type",
        "technician_name",
        "actions_taken",
        "parts_replaced",
        "next_maintenance_date",
        "note",
    },
    "risk_scores": {
        "risk_id",
        "asset_id",
        "score_date",
        "anomaly_score",
        "failure_probability",
        "maintenance_overdue_score",
        "ticket_score",
        "criticality_score",
        "runtime_score",
        "final_risk_score",
        "risk_level",
        "main_reasons",
        "recommended_action",
    },
    "documents": {
        "doc_id",
        "title",
        "doc_type",
        "asset_type",
        "source",
        "raw_text",
        "clean_text",
        "created_at",
    },
}

DATE_COLUMNS = {
    "assets": ["installation_date", "last_maintenance_date"],
    "maintenance_logs": ["maintenance_date", "next_maintenance_date"],
    "risk_scores": ["score_date"],
}

DATETIME_COLUMNS = {
    "sensor_readings": ["timestamp"],
    "maintenance_tickets": ["created_at", "resolved_at"],
    "documents": ["created_at"],
}

NUMERIC_COLUMNS = {
    "assets": ["floor", "maintenance_frequency_days"],
    "sensor_readings": ["energy_kwh", "temperature", "vibration", "runtime_hours", "pressure"],
    "risk_scores": [
        "anomaly_score",
        "failure_probability",
        "maintenance_overdue_score",
        "ticket_score",
        "criticality_score",
        "runtime_score",
        "final_risk_score",
    ],
}

ASSET_REFERENCE_TABLES = [
    "sensor_readings",
    "maintenance_tickets",
    "maintenance_logs",
    "risk_scores",
]

VIETNAMESE_VALUE_COLUMNS = {
    "assets": {
        "asset_type": set(ASSET_TYPE_CODE_TO_VI.values()),
        "criticality": set(CRITICALITY_CODE_TO_VI.values()),
        "status": set(STATUS_CODE_TO_VI.values()),
    },
    "sensor_readings": {
        "status": set(STATUS_CODE_TO_VI.values()),
        "anomaly_type": set(ANOMALY_TYPE_CODE_TO_VI.values()),
    },
    "maintenance_tickets": {
        "priority": set(PRIORITY_CODE_TO_VI.values()),
        "status": set(STATUS_CODE_TO_VI.values()),
        "failure_type": set(FAILURE_TYPE_CODE_TO_VI.values()),
    },
    "maintenance_logs": {
        "maintenance_type": set(MAINTENANCE_TYPE_CODE_TO_VI.values()),
    },
    "risk_scores": {
        "risk_level": set(RISK_LEVEL_CODE_TO_VI.values()),
    },
    "documents": {
        "doc_type": set(DOCUMENT_TYPE_CODE_TO_VI.values()),
        "asset_type": set(ASSET_TYPE_CODE_TO_VI.values()),
    },
}


class DatasetValidationError(ValueError):
    """Raised when generated CSV data fails validation."""


def validate_csv_dataset(input_dir: Path = Path("data/raw")) -> dict[str, pd.DataFrame]:
    """Read and validate all generated CSV files."""

    frames = _read_required_files(input_dir)
    _validate_required_columns(frames)
    _validate_parseable_dates(frames)
    _validate_numeric_columns(frames)
    _validate_asset_references(frames)
    _validate_anomaly_records(frames["sensor_readings"])
    _validate_vietnamese_business_values(frames)
    return frames


def _read_required_files(input_dir: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    missing_files: list[Path] = []

    for dataset_name, filename in DATASET_FILENAMES.items():
        csv_path = input_dir / filename
        if not csv_path.exists():
            missing_files.append(csv_path)
            continue
        frames[dataset_name] = pd.read_csv(csv_path, keep_default_na=False)

    if missing_files:
        missing = ", ".join(str(path) for path in missing_files)
        raise DatasetValidationError(f"Missing required CSV files: {missing}")

    return frames


def _validate_required_columns(frames: dict[str, pd.DataFrame]) -> None:
    for dataset_name, required_columns in REQUIRED_COLUMNS.items():
        missing = required_columns - set(frames[dataset_name].columns)
        if missing:
            raise DatasetValidationError(
                f"{dataset_name} missing required columns: {sorted(missing)}"
            )


def _validate_parseable_dates(frames: dict[str, pd.DataFrame]) -> None:
    for dataset_name, columns in DATE_COLUMNS.items():
        for column in columns:
            _parse_datetime_column(frames[dataset_name], dataset_name, column, allow_blank=False)

    for dataset_name, columns in DATETIME_COLUMNS.items():
        for column in columns:
            allow_blank = dataset_name == "maintenance_tickets" and column == "resolved_at"
            _parse_datetime_column(frames[dataset_name], dataset_name, column, allow_blank=allow_blank)


def _parse_datetime_column(
    frame: pd.DataFrame,
    dataset_name: str,
    column: str,
    allow_blank: bool,
) -> None:
    values = frame[column].astype(str)
    parse_values = values[values.str.strip() != ""] if allow_blank else values
    parsed = pd.to_datetime(parse_values, errors="coerce", utc=True)
    if parsed.isna().any():
        raise DatasetValidationError(f"{dataset_name}.{column} contains unparseable timestamps")


def _validate_numeric_columns(frames: dict[str, pd.DataFrame]) -> None:
    for dataset_name, columns in NUMERIC_COLUMNS.items():
        for column in columns:
            numeric_values = pd.to_numeric(frames[dataset_name][column], errors="coerce")
            if numeric_values.isna().any():
                raise DatasetValidationError(f"{dataset_name}.{column} contains null or non-numeric values")


def _validate_asset_references(frames: dict[str, pd.DataFrame]) -> None:
    asset_ids = set(frames["assets"]["asset_id"].astype(str))
    if not asset_ids:
        raise DatasetValidationError("assets.csv does not contain any asset_id values")

    for dataset_name in ASSET_REFERENCE_TABLES:
        referenced_ids = set(frames[dataset_name]["asset_id"].astype(str))
        unknown_ids = referenced_ids - asset_ids
        if unknown_ids:
            raise DatasetValidationError(
                f"{dataset_name}.asset_id contains unknown assets: {sorted(unknown_ids)[:10]}"
            )


def _validate_anomaly_records(sensor_readings: pd.DataFrame) -> None:
    anomaly_type_none = ANOMALY_TYPE_CODE_TO_VI["none"]
    anomaly_count = (sensor_readings["anomaly_type"] != anomaly_type_none).sum()
    if anomaly_count == 0:
        raise DatasetValidationError("sensor_readings.csv does not contain anomaly records")


def _validate_vietnamese_business_values(frames: dict[str, pd.DataFrame]) -> None:
    for dataset_name, columns in VIETNAMESE_VALUE_COLUMNS.items():
        frame = frames[dataset_name]
        for column, allowed_values in columns.items():
            values = set(frame[column].astype(str))
            unknown_values = values - allowed_values
            if unknown_values:
                raise DatasetValidationError(
                    f"{dataset_name}.{column} contains unknown Vietnamese labels: "
                    f"{sorted(unknown_values)[:10]}"
                )

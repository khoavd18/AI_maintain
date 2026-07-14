"""Validation for focused synthetic maintenance CSV datasets."""

from datetime import timedelta
from pathlib import Path

import pandas as pd

from src.config.value_mappings import (
    DOCUMENT_TYPE_CODE_TO_VI,
    FAILURE_TYPE_CODE_TO_VI,
    MAINTENANCE_RESULT_CODE_TO_VI,
    MAINTENANCE_TYPE_CODE_TO_VI,
    PRIORITY_CODE_TO_VI,
    STATUS_CODE_TO_VI,
)
from src.data_generation.generate_data import (
    ASSET_CRITICALITY_VALUES,
    ASSET_STATUS_VALUES,
    DATASET_FILENAMES,
    MAINTENANCE_RESULT_VALUES,
    SUPPORTED_ASSET_TYPES,
    TICKET_STATUS_VALUES,
)

REQUIRED_COLUMNS = {
    "assets": {
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
    },
    "sensor_readings": {
        "reading_id",
        "asset_id",
        "timestamp",
        "energy_kwh",
        "runtime_hours",
        "temperature",
        "vibration",
        "status",
    },
    "maintenance_tickets": {
        "ticket_id",
        "asset_id",
        "issue_description",
        "priority",
        "status",
        "failure_category",
        "created_at",
        "resolved_at",
        "technician_id",
    },
    "maintenance_logs": {
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

IDENTIFIER_COLUMNS = {
    "assets": "asset_id",
    "sensor_readings": "reading_id",
    "maintenance_tickets": "ticket_id",
    "maintenance_logs": "log_id",
    "documents": "doc_id",
}

DATE_COLUMNS = {
    "assets": [
        "installation_date",
        "last_maintenance_date",
        "next_maintenance_date",
    ],
    "maintenance_logs": ["maintenance_date", "next_maintenance_date"],
}

DATETIME_COLUMNS = {
    "sensor_readings": ["timestamp"],
    "maintenance_tickets": ["created_at", "resolved_at"],
    "documents": ["created_at"],
}

NUMERIC_COLUMNS = {
    "assets": ["maintenance_interval_days"],
    "sensor_readings": ["energy_kwh", "runtime_hours", "temperature", "vibration"],
}

OPTIONAL_BLANK_FIELDS = {
    ("maintenance_tickets", "resolved_at"),
    ("maintenance_logs", "ticket_id"),
    ("maintenance_logs", "parts_replaced"),
}

ENUM_COLUMNS = {
    "assets": {
        "asset_type": SUPPORTED_ASSET_TYPES,
        "criticality": ASSET_CRITICALITY_VALUES,
        "status": ASSET_STATUS_VALUES,
    },
    "sensor_readings": {
        "status": {STATUS_CODE_TO_VI["normal"]},
    },
    "maintenance_tickets": {
        "priority": set(PRIORITY_CODE_TO_VI.values()),
        "status": TICKET_STATUS_VALUES,
        "failure_category": set(FAILURE_TYPE_CODE_TO_VI.values()),
    },
    "maintenance_logs": {
        "maintenance_type": set(MAINTENANCE_TYPE_CODE_TO_VI.values()),
        "maintenance_result": MAINTENANCE_RESULT_VALUES,
    },
    "documents": {
        "doc_type": set(DOCUMENT_TYPE_CODE_TO_VI.values()),
        "asset_type": SUPPORTED_ASSET_TYPES,
    },
}

FORBIDDEN_READING_COLUMNS = {
    "anomaly_type",
    "is_anomaly",
    "pressure",
    "failure_probability",
}


class DatasetValidationError(ValueError):
    """Raised when generated CSV data fails validation."""


def validate_csv_dataset(input_dir: Path = Path("data/raw")) -> dict[str, pd.DataFrame]:
    """Read and validate all focused raw CSV files."""

    frames = _read_required_files(input_dir)
    _validate_required_columns(frames)
    _validate_required_values(frames)
    _validate_unique_identifiers(frames)
    _validate_parseable_dates(frames)
    _validate_numeric_columns(frames)
    _validate_enums(frames)
    _validate_asset_references(frames)
    _validate_asset_chronology(frames)
    _validate_sensor_readings(frames["sensor_readings"])
    _validate_ticket_consistency(frames["maintenance_tickets"])
    _validate_maintenance_logs(frames)
    return frames


def validate_feature_overdue_days(features: pd.DataFrame) -> None:
    """Validate point-in-time maintenance dates and overdue calculations."""

    required = {
        "asset_id",
        "feature_date",
        "last_maintenance_date",
        "next_maintenance_date",
        "days_since_last_maintenance",
        "days_overdue",
    }
    missing = required - set(features.columns)
    if missing:
        raise DatasetValidationError(
            f"asset_daily_features row=- field=columns reason=missing {sorted(missing)}"
        )

    feature_dates = pd.to_datetime(features["feature_date"], errors="coerce")
    last_dates = pd.to_datetime(features["last_maintenance_date"], errors="coerce")
    next_dates = pd.to_datetime(features["next_maintenance_date"], errors="coerce")
    for index in features.index:
        if pd.isna(feature_dates.loc[index]):
            _raise_row_error("asset_daily_features", index, "feature_date", "invalid date")
        if pd.isna(last_dates.loc[index]):
            _raise_row_error(
                "asset_daily_features", index, "last_maintenance_date", "invalid date"
            )
        if pd.isna(next_dates.loc[index]):
            _raise_row_error(
                "asset_daily_features", index, "next_maintenance_date", "invalid date"
            )
        if last_dates.loc[index] > feature_dates.loc[index]:
            _raise_row_error(
                "asset_daily_features",
                index,
                "last_maintenance_date",
                "future maintenance event used for feature row",
            )

        expected_since = int((feature_dates.loc[index] - last_dates.loc[index]).days)
        expected_overdue = max(0, int((feature_dates.loc[index] - next_dates.loc[index]).days))
        if int(features.at[index, "days_since_last_maintenance"]) != expected_since:
            _raise_row_error(
                "asset_daily_features",
                index,
                "days_since_last_maintenance",
                f"expected {expected_since}",
            )
        if int(features.at[index, "days_overdue"]) != expected_overdue:
            _raise_row_error(
                "asset_daily_features",
                index,
                "days_overdue",
                f"expected {expected_overdue}",
            )


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
        raise DatasetValidationError(
            f"dataset=- row=- field=file reason=missing required CSV files: {missing}"
        )
    return frames


def _validate_required_columns(frames: dict[str, pd.DataFrame]) -> None:
    for dataset_name, required_columns in REQUIRED_COLUMNS.items():
        frame = frames[dataset_name]
        missing = required_columns - set(frame.columns)
        if missing:
            raise DatasetValidationError(
                f"{dataset_name} row=- field=columns reason=missing required columns "
                f"{sorted(missing)}"
            )

    forbidden = FORBIDDEN_READING_COLUMNS & set(frames["sensor_readings"].columns)
    if forbidden:
        raise DatasetValidationError(
            "sensor_readings row=- field=columns reason=label or non-MVP columns are not "
            f"allowed: {sorted(forbidden)}"
        )


def _validate_required_values(frames: dict[str, pd.DataFrame]) -> None:
    for dataset_name, required_columns in REQUIRED_COLUMNS.items():
        frame = frames[dataset_name]
        for column in required_columns:
            if (dataset_name, column) in OPTIONAL_BLANK_FIELDS:
                continue
            blank = frame[column].astype(str).str.strip().eq("")
            if blank.any():
                _raise_row_error(
                    dataset_name,
                    blank[blank].index[0],
                    column,
                    "required value is blank",
                )


def _validate_unique_identifiers(frames: dict[str, pd.DataFrame]) -> None:
    for dataset_name, column in IDENTIFIER_COLUMNS.items():
        frame = frames[dataset_name]
        duplicates = frame[column].astype(str).duplicated(keep=False)
        if duplicates.any():
            index = duplicates[duplicates].index[0]
            _raise_row_error(
                dataset_name,
                index,
                column,
                f"duplicate identifier {frame.at[index, column]!r}",
            )


def _validate_parseable_dates(frames: dict[str, pd.DataFrame]) -> None:
    for dataset_name, columns in DATE_COLUMNS.items():
        for column in columns:
            _validate_datetime_column(frames[dataset_name], dataset_name, column, False)

    for dataset_name, columns in DATETIME_COLUMNS.items():
        for column in columns:
            allow_blank = (dataset_name, column) in OPTIONAL_BLANK_FIELDS
            _validate_datetime_column(
                frames[dataset_name], dataset_name, column, allow_blank
            )


def _validate_datetime_column(
    frame: pd.DataFrame,
    dataset_name: str,
    column: str,
    allow_blank: bool,
) -> None:
    values = frame[column].astype(str)
    mask = values.str.strip().ne("") if allow_blank else pd.Series(True, index=frame.index)
    parsed = pd.to_datetime(values.where(mask), errors="coerce", utc=True)
    invalid = mask & parsed.isna()
    if invalid.any():
        _raise_row_error(
            dataset_name,
            invalid[invalid].index[0],
            column,
            "unparseable date or timestamp",
        )


def _validate_numeric_columns(frames: dict[str, pd.DataFrame]) -> None:
    for dataset_name, columns in NUMERIC_COLUMNS.items():
        frame = frames[dataset_name]
        for column in columns:
            values = pd.to_numeric(frame[column], errors="coerce")
            invalid = values.isna()
            if invalid.any():
                _raise_row_error(
                    dataset_name,
                    invalid[invalid].index[0],
                    column,
                    "null or non-numeric value",
                )


def _validate_enums(frames: dict[str, pd.DataFrame]) -> None:
    for dataset_name, columns in ENUM_COLUMNS.items():
        frame = frames[dataset_name]
        for column, allowed_values in columns.items():
            invalid = ~frame[column].isin(allowed_values)
            if invalid.any():
                index = invalid[invalid].index[0]
                _raise_row_error(
                    dataset_name,
                    index,
                    column,
                    f"unsupported value {frame.at[index, column]!r}",
                )


def _validate_asset_references(frames: dict[str, pd.DataFrame]) -> None:
    asset_ids = set(frames["assets"]["asset_id"].astype(str))
    for dataset_name in ["sensor_readings", "maintenance_tickets", "maintenance_logs"]:
        frame = frames[dataset_name]
        invalid = ~frame["asset_id"].astype(str).isin(asset_ids)
        if invalid.any():
            index = invalid[invalid].index[0]
            _raise_row_error(
                dataset_name,
                index,
                "asset_id",
                f"unknown asset {frame.at[index, 'asset_id']!r}",
            )


def _validate_asset_chronology(frames: dict[str, pd.DataFrame]) -> None:
    assets = frames["assets"]
    readings = frames["sensor_readings"]
    logs = frames["maintenance_logs"]
    observation_start = pd.to_datetime(readings["timestamp"], utc=True).min().date()

    log_dates = pd.to_datetime(logs["maintenance_date"], errors="raise").dt.date
    for index, asset in assets.iterrows():
        installation_date = pd.Timestamp(asset["installation_date"]).date()
        last_date = pd.Timestamp(asset["last_maintenance_date"]).date()
        next_date = pd.Timestamp(asset["next_maintenance_date"]).date()
        interval_days = int(asset["maintenance_interval_days"])

        if installation_date >= observation_start:
            _raise_row_error(
                "assets", index, "installation_date", "must precede observation window"
            )
        if last_date > next_date:
            _raise_row_error(
                "assets", index, "last_maintenance_date", "must not be after next date"
            )
        expected_next = last_date + timedelta(days=interval_days)
        if next_date != expected_next:
            _raise_row_error(
                "assets",
                index,
                "next_maintenance_date",
                f"expected {expected_next.isoformat()} from maintenance interval",
            )

        asset_logs = logs[logs["asset_id"] == asset["asset_id"]]
        asset_log_dates = log_dates.loc[asset_logs.index]
        if asset_logs.empty or not (asset_log_dates <= observation_start).any():
            _raise_row_error(
                "assets",
                index,
                "last_maintenance_date",
                "no maintenance event exists on or before observation start",
            )
        latest_index = asset_log_dates.sort_values().index[-1]
        if str(logs.at[latest_index, "maintenance_date"]) != str(asset["last_maintenance_date"]):
            _raise_row_error(
                "assets",
                index,
                "last_maintenance_date",
                "does not match latest maintenance log",
            )
        if str(logs.at[latest_index, "next_maintenance_date"]) != str(
            asset["next_maintenance_date"]
        ):
            _raise_row_error(
                "assets",
                index,
                "next_maintenance_date",
                "does not match latest maintenance log",
            )


def _validate_sensor_readings(readings: pd.DataFrame) -> None:
    duplicate_pairs = readings.duplicated(["asset_id", "timestamp"], keep=False)
    if duplicate_pairs.any():
        index = duplicate_pairs[duplicate_pairs].index[0]
        _raise_row_error(
            "sensor_readings",
            index,
            "timestamp",
            "duplicate asset/timestamp reading",
        )

    for column in ["energy_kwh", "runtime_hours", "temperature", "vibration"]:
        values = pd.to_numeric(readings[column], errors="coerce")
        invalid = values.lt(0)
        if invalid.any():
            _raise_row_error(
                "sensor_readings",
                invalid[invalid].index[0],
                column,
                "negative value is not allowed",
            )
    runtime = pd.to_numeric(readings["runtime_hours"], errors="coerce")
    invalid_runtime = runtime.gt(24)
    if invalid_runtime.any():
        _raise_row_error(
            "sensor_readings",
            invalid_runtime[invalid_runtime].index[0],
            "runtime_hours",
            "value cannot exceed 24 hours per reading period",
        )


def _validate_ticket_consistency(tickets: pd.DataFrame) -> None:
    created = pd.to_datetime(tickets["created_at"], errors="raise", utc=True)
    resolved = pd.to_datetime(tickets["resolved_at"], errors="coerce", utc=True)
    resolved_status = tickets["status"].eq(STATUS_CODE_TO_VI["resolved"])
    has_resolved_at = tickets["resolved_at"].astype(str).str.strip().ne("")

    mismatch = resolved_status & ~has_resolved_at
    if mismatch.any():
        _raise_row_error(
            "maintenance_tickets",
            mismatch[mismatch].index[0],
            "resolved_at",
            "resolved ticket requires a timestamp",
        )
    mismatch = ~resolved_status & has_resolved_at
    if mismatch.any():
        _raise_row_error(
            "maintenance_tickets",
            mismatch[mismatch].index[0],
            "resolved_at",
            "unresolved ticket must have an empty timestamp",
        )
    invalid_order = resolved_status & resolved.lt(created)
    if invalid_order.any():
        _raise_row_error(
            "maintenance_tickets",
            invalid_order[invalid_order].index[0],
            "resolved_at",
            "must not be earlier than created_at",
        )


def _validate_maintenance_logs(frames: dict[str, pd.DataFrame]) -> None:
    assets = frames["assets"].set_index("asset_id")
    tickets = frames["maintenance_tickets"].set_index("ticket_id")
    logs = frames["maintenance_logs"]
    linked_ids = logs["ticket_id"].astype(str).str.strip()
    unknown_ticket = linked_ids.ne("") & ~linked_ids.isin(tickets.index.astype(str))
    if unknown_ticket.any():
        index = unknown_ticket[unknown_ticket].index[0]
        _raise_row_error(
            "maintenance_logs",
            index,
            "ticket_id",
            f"unknown ticket {logs.at[index, 'ticket_id']!r}",
        )

    for index, log in logs.iterrows():
        maintenance_date = pd.Timestamp(log["maintenance_date"]).date()
        next_date = pd.Timestamp(log["next_maintenance_date"]).date()
        interval_days = int(assets.at[log["asset_id"], "maintenance_interval_days"])
        expected_next = maintenance_date + timedelta(days=interval_days)
        if next_date != expected_next:
            _raise_row_error(
                "maintenance_logs",
                index,
                "next_maintenance_date",
                f"expected {expected_next.isoformat()} from maintenance interval",
            )

        result = str(log["maintenance_result"])
        follow_up = _as_bool(log["follow_up_required"])
        expected_follow_up = result != MAINTENANCE_RESULT_CODE_TO_VI["resolved"]
        if follow_up != expected_follow_up:
            _raise_row_error(
                "maintenance_logs",
                index,
                "follow_up_required",
                f"must be {expected_follow_up} for maintenance_result {result!r}",
            )

        ticket_id = str(log["ticket_id"]).strip()
        if not ticket_id:
            continue
        ticket = tickets.loc[ticket_id]
        if str(ticket["asset_id"]) != str(log["asset_id"]):
            _raise_row_error(
                "maintenance_logs",
                index,
                "asset_id",
                "does not match linked ticket asset",
            )
        created_date = pd.Timestamp(ticket["created_at"]).date()
        if maintenance_date < created_date:
            _raise_row_error(
                "maintenance_logs",
                index,
                "maintenance_date",
                "precedes linked ticket creation date",
            )
        if ticket["status"] == STATUS_CODE_TO_VI["resolved"]:
            resolved_date = pd.Timestamp(ticket["resolved_at"]).date()
            if maintenance_date > resolved_date:
                _raise_row_error(
                    "maintenance_logs",
                    index,
                    "maintenance_date",
                    "occurs after linked ticket resolution date",
                )

    resolved_ticket_ids = set(
        frames["maintenance_tickets"].loc[
            frames["maintenance_tickets"]["status"] == STATUS_CODE_TO_VI["resolved"],
            "ticket_id",
        ]
    )
    linked_ticket_ids = set(linked_ids[linked_ids.ne("")])
    missing_logs = resolved_ticket_ids - linked_ticket_ids
    if missing_logs:
        ticket_id = sorted(missing_logs)[0]
        ticket_index = frames["maintenance_tickets"].index[
            frames["maintenance_tickets"]["ticket_id"] == ticket_id
        ][0]
        _raise_row_error(
            "maintenance_tickets",
            ticket_index,
            "ticket_id",
            "resolved ticket has no linked maintenance log",
        )


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise DatasetValidationError(
        f"maintenance_logs row=- field=follow_up_required reason=invalid boolean {value!r}"
    )


def _raise_row_error(dataset: str, index: object, field: str, reason: str) -> None:
    try:
        row_number = int(index) + 2
    except (TypeError, ValueError):
        row_number = index
    raise DatasetValidationError(
        f"{dataset} row={row_number} field={field} reason={reason}"
    )

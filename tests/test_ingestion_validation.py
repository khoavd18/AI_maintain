"""Tests for focused CSV validation and diagnostic error messages."""

from pathlib import Path

import pandas as pd
import pytest

from src.config.value_mappings import STATUS_CODE_TO_VI
from src.data_generation.generate_data import generate_dataset, save_dataset
from src.ingestion.validation import DatasetValidationError, validate_csv_dataset


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    save_dataset(generate_dataset(asset_count=12, days=10, seed=11), tmp_path)
    return tmp_path


def test_validate_csv_dataset_accepts_generated_data(raw_dir: Path) -> None:
    frames = validate_csv_dataset(raw_dir)

    assert set(frames) == {
        "assets",
        "sensor_readings",
        "maintenance_tickets",
        "maintenance_logs",
        "documents",
    }


def test_validation_errors_identify_dataset_row_field_and_reason(raw_dir: Path) -> None:
    assets = pd.read_csv(raw_dir / "assets.csv", keep_default_na=False)
    assets.loc[1, "asset_id"] = assets.loc[0, "asset_id"]
    assets.to_csv(raw_dir / "assets.csv", index=False)

    with pytest.raises(
        DatasetValidationError,
        match=r"assets row=2 field=asset_id reason=duplicate identifier",
    ):
        validate_csv_dataset(raw_dir)


def test_rejects_missing_file_and_required_column(raw_dir: Path) -> None:
    (raw_dir / "documents.csv").unlink()
    with pytest.raises(DatasetValidationError, match="missing required CSV files"):
        validate_csv_dataset(raw_dir)


def test_rejects_orphan_asset_reference(raw_dir: Path) -> None:
    tickets = pd.read_csv(raw_dir / "maintenance_tickets.csv", keep_default_na=False)
    tickets.loc[0, "asset_id"] = "UNKNOWN_999"
    tickets.to_csv(raw_dir / "maintenance_tickets.csv", index=False)

    with pytest.raises(
        DatasetValidationError,
        match=r"maintenance_tickets row=2 field=asset_id reason=unknown asset",
    ):
        validate_csv_dataset(raw_dir)


def test_rejects_duplicate_reading_and_negative_measurement(raw_dir: Path) -> None:
    readings = pd.read_csv(raw_dir / "sensor_readings.csv", keep_default_na=False)
    readings.loc[1, ["asset_id", "timestamp"]] = readings.loc[0, ["asset_id", "timestamp"]]
    readings.to_csv(raw_dir / "sensor_readings.csv", index=False)

    with pytest.raises(DatasetValidationError, match="duplicate asset/timestamp reading"):
        validate_csv_dataset(raw_dir)


def test_rejects_negative_measurement(raw_dir: Path) -> None:
    readings = pd.read_csv(raw_dir / "sensor_readings.csv", keep_default_na=False)
    readings.loc[0, "energy_kwh"] = -0.1
    readings.to_csv(raw_dir / "sensor_readings.csv", index=False)

    with pytest.raises(
        DatasetValidationError,
        match=r"sensor_readings row=2 field=energy_kwh reason=negative value",
    ):
        validate_csv_dataset(raw_dir)


def test_rejects_invalid_ticket_resolution_semantics(raw_dir: Path) -> None:
    tickets = pd.read_csv(raw_dir / "maintenance_tickets.csv", keep_default_na=False)
    unresolved_index = tickets.index[tickets["status"] != STATUS_CODE_TO_VI["resolved"]][0]
    tickets.loc[unresolved_index, "resolved_at"] = tickets.loc[unresolved_index, "created_at"]
    tickets.to_csv(raw_dir / "maintenance_tickets.csv", index=False)

    with pytest.raises(
        DatasetValidationError,
        match=r"maintenance_tickets row=.* field=resolved_at reason=unresolved ticket",
    ):
        validate_csv_dataset(raw_dir)


def test_rejects_maintenance_before_linked_ticket(raw_dir: Path) -> None:
    logs = pd.read_csv(raw_dir / "maintenance_logs.csv", keep_default_na=False)
    linked_index = logs.index[logs["ticket_id"].astype(str).str.strip().ne("")][0]
    logs.loc[linked_index, "maintenance_date"] = "2025-01-01"
    logs.loc[linked_index, "next_maintenance_date"] = "2025-04-01"
    logs.to_csv(raw_dir / "maintenance_logs.csv", index=False)

    with pytest.raises(
        DatasetValidationError,
        match=r"maintenance_logs row=.* field=maintenance_date reason=precedes linked ticket",
    ):
        validate_csv_dataset(raw_dir)


def test_rejects_invalid_maintenance_interval(raw_dir: Path) -> None:
    logs = pd.read_csv(raw_dir / "maintenance_logs.csv", keep_default_na=False)
    ordered = logs.sort_values(["asset_id", "maintenance_date", "log_id"])
    log_counts = ordered.groupby("asset_id").size()
    asset_with_history = log_counts[log_counts > 1].index[0]
    historical_index = ordered[ordered["asset_id"] == asset_with_history].index[0]
    logs.loc[historical_index, "next_maintenance_date"] = "2099-01-01"
    logs.to_csv(raw_dir / "maintenance_logs.csv", index=False)

    with pytest.raises(
        DatasetValidationError,
        match=r"maintenance_logs row=.* field=next_maintenance_date reason=expected",
    ):
        validate_csv_dataset(raw_dir)


def test_rejects_invalid_maintenance_result(raw_dir: Path) -> None:
    logs = pd.read_csv(raw_dir / "maintenance_logs.csv", keep_default_na=False)
    logs.loc[0, "maintenance_result"] = "Hoàn tất tự động"
    logs.to_csv(raw_dir / "maintenance_logs.csv", index=False)

    with pytest.raises(
        DatasetValidationError,
        match=r"maintenance_logs row=2 field=maintenance_result reason=unsupported value",
    ):
        validate_csv_dataset(raw_dir)


def test_rejects_label_leakage_columns(raw_dir: Path) -> None:
    readings = pd.read_csv(raw_dir / "sensor_readings.csv", keep_default_na=False)
    readings["is_anomaly"] = False
    readings.to_csv(raw_dir / "sensor_readings.csv", index=False)

    with pytest.raises(DatasetValidationError, match="label or non-MVP columns are not allowed"):
        validate_csv_dataset(raw_dir)

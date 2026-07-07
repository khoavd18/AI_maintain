"""Tests for generated CSV validation before database loading."""

from pathlib import Path

import pandas as pd
import pytest

from src.data_generation.generate_data import generate_dataset, save_dataset
from src.ingestion.validation import DatasetValidationError, validate_csv_dataset


def test_validate_csv_dataset_accepts_generated_data(tmp_path: Path) -> None:
    """Generated CSV files should pass schema and data-quality validation."""

    dataset = generate_dataset(asset_count=12, days=5, seed=11)
    save_dataset(dataset, tmp_path)

    frames = validate_csv_dataset(tmp_path)

    assert set(frames) == {
        "assets",
        "sensor_readings",
        "maintenance_tickets",
        "maintenance_logs",
        "risk_scores",
        "documents",
    }


def test_validate_csv_dataset_rejects_missing_files(tmp_path: Path) -> None:
    """All required raw CSV files must exist before loading."""

    dataset = generate_dataset(asset_count=12, days=5, seed=11)
    save_dataset(dataset, tmp_path)
    (tmp_path / "assets.csv").unlink()

    with pytest.raises(DatasetValidationError, match="Missing required CSV files"):
        validate_csv_dataset(tmp_path)


def test_validate_csv_dataset_rejects_missing_columns(tmp_path: Path) -> None:
    """Required columns should be validated before ingestion."""

    dataset = generate_dataset(asset_count=12, days=5, seed=11)
    save_dataset(dataset, tmp_path)
    assets = pd.read_csv(tmp_path / "assets.csv")
    assets.drop(columns=["criticality"]).to_csv(tmp_path / "assets.csv", index=False)

    with pytest.raises(DatasetValidationError, match="missing required columns"):
        validate_csv_dataset(tmp_path)


def test_validate_csv_dataset_rejects_broken_asset_references(tmp_path: Path) -> None:
    """Asset-scoped tables should not reference unknown asset IDs."""

    dataset = generate_dataset(asset_count=12, days=5, seed=11)
    save_dataset(dataset, tmp_path)
    tickets = pd.read_csv(tmp_path / "maintenance_tickets.csv")
    tickets.loc[0, "asset_id"] = "UNKNOWN_999"
    tickets.to_csv(tmp_path / "maintenance_tickets.csv", index=False)

    with pytest.raises(DatasetValidationError, match="unknown assets"):
        validate_csv_dataset(tmp_path)


def test_validate_csv_dataset_rejects_missing_numeric_values(tmp_path: Path) -> None:
    """Required numeric fields should not be null or unparseable."""

    dataset = generate_dataset(asset_count=12, days=5, seed=11)
    save_dataset(dataset, tmp_path)
    readings = pd.read_csv(tmp_path / "sensor_readings.csv")
    readings["energy_kwh"] = readings["energy_kwh"].astype(object)
    readings.loc[0, "energy_kwh"] = ""
    readings.to_csv(tmp_path / "sensor_readings.csv", index=False)

    with pytest.raises(DatasetValidationError, match="non-numeric"):
        validate_csv_dataset(tmp_path)

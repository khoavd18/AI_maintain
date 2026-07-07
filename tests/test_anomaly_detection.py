"""Tests for anomaly detection over engineered daily asset features."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.config.value_mappings import ANOMALY_TYPE_CODE_TO_VI
from src.data_generation.generate_data import generate_dataset, save_dataset
from src.features.build_features import build_features_from_csv
from src.models.anomaly_detection import (
    ANOMALY_OUTPUT_COLUMNS,
    build_anomaly_results,
    detect_rule_based_anomalies,
    run_anomaly_detection,
)


@pytest.fixture(scope="module")
def anomaly_fixture(tmp_path_factory: pytest.TempPathFactory) -> dict[str, pd.DataFrame | Path]:
    """Build a compact deterministic dataset for anomaly-detection tests."""

    base_dir = tmp_path_factory.mktemp("anomaly_detection")
    raw_dir = base_dir / "raw"
    feature_path = base_dir / "processed" / "asset_daily_features.csv"
    output_path = base_dir / "processed" / "anomaly_results.csv"

    dataset = generate_dataset(asset_count=24, days=20, seed=31)
    save_dataset(dataset, raw_dir)
    features = build_features_from_csv(input_dir=raw_dir, output_path=feature_path)
    results = run_anomaly_detection(input_path=feature_path, output_path=output_path)

    return {
        "dataset": dataset,
        "features": features,
        "results": results,
        "output_path": output_path,
    }


def test_anomaly_results_csv_is_generated(
    anomaly_fixture: dict[str, pd.DataFrame | Path],
) -> None:
    """The anomaly detector should write anomaly_results.csv."""

    output_path = anomaly_fixture["output_path"]

    assert isinstance(output_path, Path)
    assert output_path.exists()


def test_anomaly_results_have_required_columns(
    anomaly_fixture: dict[str, pd.DataFrame | Path],
) -> None:
    """Anomaly output should expose the expected schema."""

    results = anomaly_fixture["results"]

    assert isinstance(results, pd.DataFrame)
    assert list(results.columns) == ANOMALY_OUTPUT_COLUMNS


def test_anomaly_score_bounds_and_boolean_flag(
    anomaly_fixture: dict[str, pd.DataFrame | Path],
) -> None:
    """Scores should stay bounded and is_anomaly should be boolean."""

    results = anomaly_fixture["results"]

    assert isinstance(results, pd.DataFrame)
    assert results["anomaly_score"].between(0, 100).all()
    assert pd.api.types.is_bool_dtype(results["is_anomaly"])


def test_vietnamese_anomaly_types_and_reasons(
    anomaly_fixture: dict[str, pd.DataFrame | Path],
) -> None:
    """Anomaly labels and explanations should use Vietnamese business values."""

    results = anomaly_fixture["results"]

    assert isinstance(results, pd.DataFrame)
    assert set(results["anomaly_type"]).issubset(set(ANOMALY_TYPE_CODE_TO_VI.values()))

    anomalous = results[results["is_anomaly"]]
    assert not anomalous.empty
    assert (anomalous["anomaly_reasons"].astype(str).str.strip() != "").all()
    assert anomalous["anomaly_reasons"].str.contains("bất thường|tăng|Độ rung|Nhiệt độ").any()


def test_injected_anomaly_records_score_higher_than_normal_records(
    anomaly_fixture: dict[str, pd.DataFrame | Path],
) -> None:
    """Synthetic injected anomaly days should generally receive higher scores."""

    dataset = anomaly_fixture["dataset"]
    results = anomaly_fixture["results"]
    assert isinstance(dataset, dict)
    assert isinstance(results, pd.DataFrame)

    sensor_readings = dataset["sensor_readings"].copy()
    sensor_readings["date"] = pd.to_datetime(sensor_readings["timestamp"], utc=True).dt.date.astype(str)
    injected_days = (
        sensor_readings[sensor_readings["anomaly_type"] != ANOMALY_TYPE_CODE_TO_VI["none"]]
        [["asset_id", "date"]]
        .drop_duplicates()
    )

    scored = results.merge(injected_days.assign(injected=True), on=["asset_id", "date"], how="left")
    scored["injected"] = scored["injected"].eq(True)

    assert scored.loc[scored["injected"], "anomaly_score"].mean() > scored.loc[
        ~scored["injected"], "anomaly_score"
    ].mean()


def test_rule_based_energy_spike_is_detected() -> None:
    """Energy delta over the threshold should produce an energy anomaly label."""

    features = pd.DataFrame(
        [
            {
                "asset_id": "HVAC_999",
                "feature_date": "2026-05-01",
                "asset_type": "Máy lạnh",
                "location": "Phòng máy thử nghiệm",
                "energy_kwh": 240.0,
                "temperature": 28.0,
                "vibration": 0.2,
                "runtime_hours": 20.0,
                "pressure": 90.0,
                "energy_delta_percent": 62.4,
                "temperature_delta": 0.5,
                "vibration_delta": 0.01,
                "runtime_delta_percent": 5.0,
                "ticket_count_7d": 0,
                "ticket_count_30d": 0,
                "days_overdue": 0,
                "criticality_score": 4,
            }
        ]
    )

    rule_results = detect_rule_based_anomalies(features)

    assert rule_results.loc[0, "rule_based_score"] >= 90
    assert rule_results.loc[0, "rule_anomaly_type"] == ANOMALY_TYPE_CODE_TO_VI["energy_spike"]
    assert "Điện năng tiêu thụ tăng 62.4%" in rule_results.loc[0, "rule_reasons"][0]


def test_no_nan_or_infinite_values_in_anomaly_output(
    anomaly_fixture: dict[str, pd.DataFrame | Path],
) -> None:
    """Anomaly output should be safe for downstream CSV loading and dashboards."""

    results = anomaly_fixture["results"]

    assert isinstance(results, pd.DataFrame)
    assert results.isna().sum().sum() == 0
    numeric_values = results.select_dtypes(include=[np.number]).to_numpy()
    assert np.isfinite(numeric_values).all()


def test_build_anomaly_results_handles_missing_numeric_values() -> None:
    """Missing numeric inputs should be filled safely before Isolation Forest."""

    features = pd.DataFrame(
        [
            {
                "asset_id": f"HVAC_{index:03d}",
                "feature_date": "2026-05-01",
                "asset_type": "Máy lạnh",
                "location": "Phòng máy thử nghiệm",
                "energy_kwh": np.nan if index == 1 else 100.0 + index,
                "temperature": 25.0,
                "vibration": 0.2,
                "runtime_hours": 12.0,
                "pressure": 90.0,
                "energy_delta_percent": 0.0,
                "temperature_delta": 0.0,
                "vibration_delta": 0.0,
                "runtime_delta_percent": 0.0,
                "ticket_count_7d": 0,
                "ticket_count_30d": 0,
                "days_overdue": 0,
                "criticality_score": 3,
            }
            for index in range(1, 10)
        ]
    )

    results = build_anomaly_results(features)

    assert results.isna().sum().sum() == 0
    assert results["anomaly_score"].between(0, 100).all()

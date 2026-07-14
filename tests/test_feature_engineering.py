"""Tests for daily asset-level feature engineering."""

from pathlib import Path

import pandas as pd
import pytest

from src.config.value_mappings import PRIORITY_CODE_TO_VI, criticality_score
from src.data_generation.generate_data import generate_dataset, save_dataset
from src.features.build_features import (
    FEATURE_COLUMNS,
    build_daily_asset_features,
    build_features_from_csv,
)
from src.ingestion.validation import validate_feature_overdue_days


def test_daily_feature_output_columns() -> None:
    """The feature builder should expose the expected daily model features."""

    dataset = generate_dataset(asset_count=12, days=10, seed=21)

    features = build_daily_asset_features(
        assets=dataset["assets"],
        sensor_readings=dataset["sensor_readings"],
        maintenance_tickets=dataset["maintenance_tickets"],
        maintenance_logs=dataset["maintenance_logs"],
    )

    assert list(features.columns) == FEATURE_COLUMNS
    assert len(features) == 12 * 10


def test_rolling_energy_features_match_manual_calculation() -> None:
    """Rolling energy features should be calculated per asset and day."""

    dataset = generate_dataset(asset_count=12, days=10, seed=21)
    features = build_daily_asset_features(
        assets=dataset["assets"],
        sensor_readings=dataset["sensor_readings"],
        maintenance_tickets=dataset["maintenance_tickets"],
        maintenance_logs=dataset["maintenance_logs"],
    )
    asset_id = features["asset_id"].iloc[0]
    asset_features = features[features["asset_id"] == asset_id].reset_index(drop=True)

    readings = dataset["sensor_readings"].copy()
    readings["feature_date"] = pd.to_datetime(readings["timestamp"], utc=True).dt.date.astype(str)
    daily_energy = (
        readings[readings["asset_id"] == asset_id]
        .groupby("feature_date")["energy_kwh"]
        .sum()
        .sort_index()
        .reset_index(drop=True)
    )

    assert asset_features.loc[0, "rolling_avg_energy_7d"] == daily_energy.iloc[0]
    assert asset_features.loc[0, "rolling_std_energy_7d"] == 0
    assert asset_features.loc[7, "rolling_avg_energy_7d"] == daily_energy.iloc[1:8].mean()


def test_ticket_count_features_match_manual_windows() -> None:
    """Ticket count windows should include tickets created in the previous 7/30 feature days."""

    dataset = generate_dataset(asset_count=12, days=10, seed=21)
    features = build_daily_asset_features(
        assets=dataset["assets"],
        sensor_readings=dataset["sensor_readings"],
        maintenance_tickets=dataset["maintenance_tickets"],
        maintenance_logs=dataset["maintenance_logs"],
    )

    tickets = dataset["maintenance_tickets"].copy()
    tickets["feature_date"] = pd.to_datetime(tickets["created_at"], utc=True).dt.date.astype(str)
    ticket_row = tickets.iloc[0]
    asset_id = ticket_row["asset_id"]
    feature_date = ticket_row["feature_date"]
    asset_features = features[features["asset_id"] == asset_id].set_index("feature_date")

    ticket_dates = pd.to_datetime(tickets[tickets["asset_id"] == asset_id]["feature_date"])
    current_date = pd.Timestamp(feature_date)
    manual_7d_count = ((ticket_dates >= current_date - pd.Timedelta(days=6)) & (ticket_dates <= current_date)).sum()
    manual_30d_count = (
        (ticket_dates >= current_date - pd.Timedelta(days=29)) & (ticket_dates <= current_date)
    ).sum()

    assert asset_features.loc[feature_date, "ticket_count_7d"] == manual_7d_count
    assert asset_features.loc[feature_date, "ticket_count_30d"] == manual_30d_count


def test_high_priority_ticket_feature_and_criticality_mapping() -> None:
    """Vietnamese priority and criticality labels should map into numeric features."""

    dataset = generate_dataset(asset_count=12, days=10, seed=21)
    ticket_asset = dataset["maintenance_tickets"].iloc[0]["asset_id"]
    dataset["maintenance_tickets"].loc[0, "priority"] = PRIORITY_CODE_TO_VI["critical"]

    features = build_daily_asset_features(
        assets=dataset["assets"],
        sensor_readings=dataset["sensor_readings"],
        maintenance_tickets=dataset["maintenance_tickets"],
        maintenance_logs=dataset["maintenance_logs"],
    )
    ticket_date = pd.to_datetime(dataset["maintenance_tickets"].iloc[0]["created_at"], utc=True).date()
    feature_row = features[
        (features["asset_id"] == ticket_asset) & (features["feature_date"] == str(ticket_date))
    ].iloc[0]
    asset_row = dataset["assets"][dataset["assets"]["asset_id"] == ticket_asset].iloc[0]

    assert feature_row["high_priority_ticket_count_30d"] >= 1
    assert feature_row["criticality_score"] == criticality_score(asset_row["criticality"])


def test_build_features_from_csv_writes_output(tmp_path: Path) -> None:
    """The CLI-facing feature function should validate raw CSVs and write processed output."""

    dataset = generate_dataset(asset_count=12, days=10, seed=21)
    input_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "asset_daily_features.csv"
    save_dataset(dataset, input_dir)

    features = build_features_from_csv(input_dir=input_dir, output_path=output_path)

    assert output_path.exists()
    assert len(features) == 12 * 10


def test_maintenance_features_use_latest_event_available_on_each_day() -> None:
    """Feature rows must not use a maintenance event that occurs in the future."""

    dataset = generate_dataset(asset_count=12, days=45, seed=21)
    features = build_daily_asset_features(
        assets=dataset["assets"],
        sensor_readings=dataset["sensor_readings"],
        maintenance_tickets=dataset["maintenance_tickets"],
        maintenance_logs=dataset["maintenance_logs"],
    )
    logs = dataset["maintenance_logs"].copy()
    logs["maintenance_date"] = pd.to_datetime(logs["maintenance_date"])

    for feature in features.itertuples(index=False):
        feature_date = pd.Timestamp(feature.feature_date)
        eligible = logs[
            (logs["asset_id"] == feature.asset_id)
            & (logs["maintenance_date"] <= feature_date)
        ].sort_values(["maintenance_date", "log_id"])
        expected = eligible.iloc[-1]
        assert pd.Timestamp(feature.last_maintenance_date) == expected["maintenance_date"]
        assert pd.Timestamp(feature.next_maintenance_date) == pd.Timestamp(
            expected["next_maintenance_date"]
        )
        assert feature.days_since_last_maintenance == (
            feature_date - pd.Timestamp(feature.last_maintenance_date)
        ).days
        assert feature.days_overdue == max(
            0, (feature_date - pd.Timestamp(feature.next_maintenance_date)).days
        )

    validate_feature_overdue_days(features)


def test_feature_builder_rejects_future_only_maintenance_history() -> None:
    dataset = generate_dataset(asset_count=3, days=2, seed=21)
    future_logs = dataset["maintenance_logs"].copy()
    future_logs["maintenance_date"] = "2026-02-01"
    future_logs["next_maintenance_date"] = "2026-05-01"

    with pytest.raises(ValueError, match="No point-in-time maintenance event"):
        build_daily_asset_features(
            assets=dataset["assets"],
            sensor_readings=dataset["sensor_readings"],
            maintenance_tickets=dataset["maintenance_tickets"],
            maintenance_logs=future_logs,
        )


def test_missing_raw_pressure_preserves_downstream_feature_contract() -> None:
    dataset = generate_dataset(asset_count=3, days=2, seed=21)
    assert "pressure" not in dataset["sensor_readings"].columns

    features = build_daily_asset_features(
        assets=dataset["assets"],
        sensor_readings=dataset["sensor_readings"],
        maintenance_tickets=dataset["maintenance_tickets"],
        maintenance_logs=dataset["maintenance_logs"],
    )

    assert (features["pressure"] == 0.0).all()

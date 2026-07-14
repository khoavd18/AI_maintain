"""Contract tests for the focused synthetic maintenance dataset."""

import unicodedata

import pandas as pd
import pytest

from src.config.value_mappings import (
    ASSET_TYPE_CODE_TO_VI,
    CRITICALITY_VI_TO_SCORE,
    DOCUMENT_TYPE_CODE_TO_VI,
    FAILURE_TYPE_CODE_TO_VI,
    MAINTENANCE_RESULT_CODE_TO_VI,
    PRIORITY_VI_TO_SCORE,
    STATUS_CODE_TO_VI,
    criticality_score,
    priority_score,
)
from src.data_generation.generate_data import (
    CONTROLLED_ANOMALY_DAYS,
    DEFAULT_ASSET_COUNT,
    DEFAULT_DAYS,
    MAINTENANCE_RESULT_VALUES,
    SUPPORTED_ASSET_TYPES,
    generate_dataset,
)


def _contains_vietnamese(text: str) -> bool:
    normalized = unicodedata.normalize("NFD", text)
    return "đ" in text.lower() or any(unicodedata.combining(char) for char in normalized)


@pytest.fixture(scope="module")
def default_dataset() -> dict[str, pd.DataFrame]:
    return generate_dataset()


def test_generation_is_deterministic_for_fixed_seed() -> None:
    first = generate_dataset(asset_count=9, days=5, seed=17)
    second = generate_dataset(asset_count=9, days=5, seed=17)

    assert set(first) == set(second)
    for dataset_name in first:
        pd.testing.assert_frame_equal(first[dataset_name], second[dataset_name])


def test_default_dataset_is_small_and_focused(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    assert set(default_dataset) == {
        "assets",
        "sensor_readings",
        "maintenance_tickets",
        "maintenance_logs",
        "documents",
    }
    assert len(default_dataset["assets"]) == DEFAULT_ASSET_COUNT == 27
    assert len(default_dataset["sensor_readings"]) == DEFAULT_ASSET_COUNT * DEFAULT_DAYS * 24
    assert len(default_dataset["documents"]) == 6
    assert set(default_dataset["assets"]["asset_type"]) == set(SUPPORTED_ASSET_TYPES)
    assert set(default_dataset["documents"]["asset_type"]) == set(SUPPORTED_ASSET_TYPES)


def test_dataset_exposes_minimum_mvp_fields(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    expected_columns = {
        "assets": {
            "asset_id", "asset_name", "asset_type", "location", "criticality",
            "status", "installation_date", "last_maintenance_date",
            "maintenance_interval_days", "next_maintenance_date",
        },
        "sensor_readings": {
            "reading_id", "asset_id", "timestamp", "energy_kwh", "runtime_hours",
            "temperature", "vibration", "status",
        },
        "maintenance_tickets": {
            "ticket_id", "asset_id", "issue_description", "priority", "status",
            "failure_category", "created_at", "resolved_at", "technician_id",
        },
        "maintenance_logs": {
            "log_id", "ticket_id", "asset_id", "maintenance_date", "maintenance_type",
            "technician_id", "inspection_result", "actions_taken", "parts_replaced",
            "technician_note", "maintenance_result", "follow_up_required",
            "next_maintenance_date",
        },
        "documents": {
            "doc_id", "title", "doc_type", "asset_type", "source", "raw_text",
            "clean_text", "created_at",
        },
    }

    for dataset_name, columns in expected_columns.items():
        assert set(default_dataset[dataset_name].columns) == columns
        assert all(column.isascii() for column in columns)


def test_ids_and_references_are_consistent(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    assets = default_dataset["assets"]
    tickets = default_dataset["maintenance_tickets"]
    logs = default_dataset["maintenance_logs"]
    asset_ids = set(assets["asset_id"])

    assert assets["asset_id"].str.match(r"^(HVAC|PUMP|GENERATOR)_\d{3}$").all()
    for name in ["sensor_readings", "maintenance_tickets", "maintenance_logs"]:
        assert set(default_dataset[name]["asset_id"]).issubset(asset_ids)
    linked_logs = logs[logs["ticket_id"].astype(str).str.strip().ne("")]
    assert set(linked_logs["ticket_id"]).issubset(set(tickets["ticket_id"]))


def test_sensor_readings_have_no_label_leakage_or_invalid_measurements(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    readings = default_dataset["sensor_readings"]

    assert {"anomaly_type", "is_anomaly", "failure_probability", "pressure"}.isdisjoint(
        readings.columns
    )
    assert not readings.duplicated(["asset_id", "timestamp"]).any()
    assert (readings[["energy_kwh", "runtime_hours", "temperature", "vibration"]] >= 0).all().all()
    assert (readings["runtime_hours"] <= 1).all()
    assert set(readings["status"]) == {STATUS_CODE_TO_VI["normal"]}


def test_controlled_numeric_anomalies_are_visible_without_raw_labels(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    readings = default_dataset["sensor_readings"].copy()
    readings["date"] = pd.to_datetime(readings["timestamp"], utc=True).dt.normalize()
    daily = readings.groupby(["asset_id", "date"], as_index=False).agg(
        energy_kwh=("energy_kwh", "sum"),
        vibration=("vibration", "mean"),
        runtime_hours=("runtime_hours", "sum"),
    )

    for asset_id, measurement in [
        ("HVAC_001", "energy_kwh"),
        ("PUMP_001", "vibration"),
        ("GENERATOR_001", "runtime_hours"),
    ]:
        values = daily[daily["asset_id"] == asset_id].sort_values("date")
        baseline = values.head(CONTROLLED_ANOMALY_DAYS)[measurement].mean()
        controlled = values.tail(CONTROLLED_ANOMALY_DAYS)[measurement].mean()
        assert controlled > baseline * 1.25


def test_ticket_status_timestamps_and_recurring_issues_are_consistent(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    tickets = default_dataset["maintenance_tickets"]
    resolved = tickets["status"] == STATUS_CODE_TO_VI["resolved"]
    has_resolved_at = tickets["resolved_at"].astype(str).str.strip().ne("")

    assert resolved.equals(has_resolved_at)
    assert (
        pd.to_datetime(tickets.loc[resolved, "resolved_at"], utc=True)
        >= pd.to_datetime(tickets.loc[resolved, "created_at"], utc=True)
    ).all()
    recurring_counts = tickets.groupby(["asset_id", "failure_category"]).size()
    assert (recurring_counts >= 3).sum() >= 4
    assert tickets["technician_id"].str.match(r"^TECH_\d{3}$").all()
    assert set(tickets["failure_category"]).issubset(set(FAILURE_TYPE_CODE_TO_VI.values()))


def test_maintenance_history_is_chronological_and_traceable(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    assets = default_dataset["assets"].set_index("asset_id")
    tickets = default_dataset["maintenance_tickets"].set_index("ticket_id")
    logs = default_dataset["maintenance_logs"]

    assert set(logs["maintenance_result"]).issubset(MAINTENANCE_RESULT_VALUES)
    expected_follow_up = logs["maintenance_result"] != MAINTENANCE_RESULT_CODE_TO_VI["resolved"]
    assert logs["follow_up_required"].astype(bool).equals(expected_follow_up)

    for log in logs.itertuples(index=False):
        maintenance_date = pd.Timestamp(log.maintenance_date)
        interval = int(assets.at[log.asset_id, "maintenance_interval_days"])
        assert pd.Timestamp(log.next_maintenance_date) == maintenance_date + pd.Timedelta(days=interval)
        if not str(log.ticket_id).strip():
            continue
        ticket = tickets.loc[log.ticket_id]
        assert ticket["asset_id"] == log.asset_id
        assert maintenance_date >= pd.Timestamp(ticket["created_at"]).tz_localize(None).normalize()

    latest_logs = logs.sort_values(["maintenance_date", "log_id"]).groupby("asset_id").tail(1)
    latest_logs = latest_logs.set_index("asset_id")
    assert assets["last_maintenance_date"].sort_index().equals(
        latest_logs["maintenance_date"].sort_index()
    )
    assert assets["next_maintenance_date"].sort_index().equals(
        latest_logs["next_maintenance_date"].sort_index()
    )


def test_vietnamese_business_values_and_mapping_helpers(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    natural_text = {
        "assets": ["asset_name", "location"],
        "maintenance_tickets": ["issue_description"],
        "maintenance_logs": ["inspection_result", "actions_taken", "technician_note"],
        "documents": ["title", "source", "raw_text", "clean_text"],
    }
    for dataset_name, columns in natural_text.items():
        for column in columns:
            values = default_dataset[dataset_name][column].astype(str)
            assert values.str.strip().ne("").all()
            assert values.map(_contains_vietnamese).all()

    assert priority_score("Khẩn cấp") == 4
    assert criticality_score("Rất quan trọng") == 4
    assert PRIORITY_VI_TO_SCORE["Trung bình"] == 2
    assert CRITICALITY_VI_TO_SCORE["Cao"] == 3
    assert set(default_dataset["documents"]["doc_type"]).issubset(
        set(DOCUMENT_TYPE_CODE_TO_VI.values())
    )
    assert set(default_dataset["documents"]["asset_type"]).issubset(
        {ASSET_TYPE_CODE_TO_VI["hvac"], ASSET_TYPE_CODE_TO_VI["pump"], ASSET_TYPE_CODE_TO_VI["generator"]}
    )

"""Tests for deterministic facility-maintenance synthetic data."""

import unicodedata

import pandas as pd
import pytest

from src.data_generation.generate_data import (
    DEFAULT_ASSET_COUNT,
    DEFAULT_DAYS,
    generate_dataset,
)
from src.config.value_mappings import (
    ANOMALY_TYPE_CODE_TO_VI,
    ASSET_TYPE_CODE_TO_VI,
    ASSET_TYPE_VI_TO_CODE,
    CRITICALITY_VI_TO_SCORE,
    DOCUMENT_TYPE_CODE_TO_VI,
    FAILURE_TYPE_CODE_TO_VI,
    PRIORITY_VI_TO_SCORE,
    RISK_LEVEL_CODE_TO_VI,
    STATUS_CODE_TO_VI,
    criticality_score,
    priority_score,
)

# Natural-language business fields that must be generated in Vietnamese.
VIETNAMESE_TEXT_FIELDS = {
    "assets": ["asset_name", "location"],
    "maintenance_tickets": ["issue_description", "technician_note"],
    "maintenance_logs": ["actions_taken", "note"],
    "documents": ["title", "source", "raw_text", "clean_text"],
}

# Business-label fields must be Vietnamese; mapping utilities convert them
# into stable internal codes and scores for downstream processing.
VIETNAMESE_BUSINESS_FIELDS = {
    "assets": ["asset_type", "criticality", "status"],
    "sensor_readings": ["status", "anomaly_type"],
    "maintenance_tickets": ["priority", "status", "failure_type"],
    "maintenance_logs": ["maintenance_type"],
    "risk_scores": ["risk_level", "main_reasons", "recommended_action"],
    "documents": ["doc_type", "asset_type"],
}

# Placeholder English strings from the previous version that must no longer appear.
ENGLISH_PLACEHOLDER_SNIPPETS = [
    "requires inspection",
    "Energy consumption is above baseline",
    "Vibration readings exceed",
    "Preventive maintenance interval",
    "Inspected filters, coils",
    "Asset returned to service",
    "Preventive Maintenance Checklist",
    "Troubleshooting SOP",
    "Continue monitoring and review",
]

FORBIDDEN_OLD_ENUM_VALUES = {
    "hvac",
    "water_pump",
    "pump",
    "elevator",
    "generator",
    "lighting",
    "energy_meter",
    "open",
    "in_progress",
    "resolved",
    "closed",
    "normal",
    "warning",
    "anomaly",
    "fault",
    "low",
    "medium",
    "high",
    "critical",
    "preventive",
    "corrective",
    "inspection",
    "sop",
    "checklist",
    "cooling_issue",
    "vibration_issue",
    "electrical_issue",
    "pressure_issue",
    "runtime_issue",
    "sensor_issue",
    "false_alarm",
    "no_failure",
    "energy_spike",
    "vibration_increase",
    "runtime_abnormal",
    "temperature_high",
    "pressure_drop",
    "electrical_overheat",
}

VIETNAMESE_CHARACTERS = set(
    "ăâđêôơưáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩị"
    "óòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
    "ĂÂĐÊÔƠƯÁÀẢÃẠẮẰẲẴẶẤẦẨẪẬÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊ"
    "ÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ"
)


def _contains_vietnamese(text: str) -> bool:
    """Return True if the string carries Vietnamese diacritics or đ/Đ."""

    if "đ" in text or "Đ" in text:
        return True
    decomposed = unicodedata.normalize("NFD", text)
    return any(char in VIETNAMESE_CHARACTERS for char in text) or any(
        unicodedata.combining(char) for char in decomposed
    )


@pytest.fixture(scope="module")
def default_dataset() -> dict[str, pd.DataFrame]:
    """Generate the default dataset once for data-quality tests."""

    return generate_dataset()


def test_synthetic_data_has_expected_row_counts(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    """Default generation should produce 100 assets and 60 days of hourly readings."""

    assert len(default_dataset["assets"]) == DEFAULT_ASSET_COUNT
    assert len(default_dataset["sensor_readings"]) == DEFAULT_ASSET_COUNT * DEFAULT_DAYS * 24
    assert len(default_dataset["risk_scores"]) == DEFAULT_ASSET_COUNT
    assert len(default_dataset["documents"]) == 10
    assert len(default_dataset["maintenance_logs"]) >= DEFAULT_ASSET_COUNT
    assert len(default_dataset["maintenance_tickets"]) > 0


def test_asset_ids_are_consistent_across_tables(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    """All asset-scoped tables should reference known asset IDs."""

    asset_ids = set(default_dataset["assets"]["asset_id"])

    for table_name in [
        "sensor_readings",
        "maintenance_tickets",
        "maintenance_logs",
        "risk_scores",
    ]:
        table_asset_ids = set(default_dataset[table_name]["asset_id"])
        assert table_asset_ids.issubset(asset_ids)

    assert set(default_dataset["risk_scores"]["asset_id"]) == asset_ids


def test_asset_id_prefixes_remain_english(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    """Technical asset IDs should keep English prefixes and readable numbering."""

    asset_ids = default_dataset["assets"]["asset_id"].astype(str)

    assert asset_ids.str.match(
        r"^(HVAC|PUMP|ELEVATOR|GENERATOR|LIGHTING|PANEL|TANK|FIRE)_\d{3}$"
    ).all()


def test_generated_data_contains_injected_anomalies(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    """Synthetic data should include anomaly rows and high-risk assets."""

    sensor_readings = default_dataset["sensor_readings"]
    tickets = default_dataset["maintenance_tickets"]
    risk_scores = default_dataset["risk_scores"]

    assert (sensor_readings["status"] == STATUS_CODE_TO_VI["fault"]).sum() > 0
    assert {
        FAILURE_TYPE_CODE_TO_VI["cooling_issue"],
        FAILURE_TYPE_CODE_TO_VI["vibration_issue"],
        FAILURE_TYPE_CODE_TO_VI["electrical_issue"],
        FAILURE_TYPE_CODE_TO_VI["runtime_issue"],
    }.issubset(
        set(tickets["failure_type"])
    )
    assert risk_scores["risk_level"].isin([RISK_LEVEL_CODE_TO_VI["high"], RISK_LEVEL_CODE_TO_VI["critical"]]).any()


def test_old_english_enum_values_do_not_appear(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    """Old English business enum values should not appear in generated data."""

    for table_name, columns in VIETNAMESE_BUSINESS_FIELDS.items():
        frame = default_dataset[table_name]
        for column in columns:
            values = set(frame[column].astype(str))
            assert values.isdisjoint(FORBIDDEN_OLD_ENUM_VALUES), f"{table_name}.{column}: {values}"


def test_mapping_utilities_convert_vietnamese_values() -> None:
    """Mappings should convert Vietnamese labels into internal codes and scores."""

    assert ASSET_TYPE_VI_TO_CODE["Máy lạnh"] == "hvac"
    assert priority_score("Khẩn cấp") == 4
    assert criticality_score("Rất quan trọng") == 4
    assert PRIORITY_VI_TO_SCORE["Trung bình"] == 2
    assert CRITICALITY_VI_TO_SCORE["Cao"] == 3


def test_vietnamese_text_fields_are_populated_and_vietnamese(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    """Every natural-language field must be non-empty and contain Vietnamese text."""

    for table_name, columns in VIETNAMESE_TEXT_FIELDS.items():
        frame = default_dataset[table_name]
        for column in columns:
            values = frame[column].astype(str)
            assert (values.str.strip() != "").all(), f"{table_name}.{column} has empty values"
            assert values.map(_contains_vietnamese).all(), (
                f"{table_name}.{column} contains non-Vietnamese (likely placeholder) text"
            )


def test_parts_replaced_is_vietnamese_when_present(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    """parts_replaced may be blank, but populated values must be Vietnamese, not English."""

    parts = default_dataset["maintenance_logs"]["parts_replaced"].astype(str)
    populated = parts[parts.str.strip() != ""]

    assert not populated.empty, "expected at least one maintenance log with replaced parts"
    assert populated.map(_contains_vietnamese).all()


def test_no_english_placeholder_text_remains(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    """The old English placeholder strings must not leak into any Vietnamese field."""

    for table_name, columns in VIETNAMESE_TEXT_FIELDS.items():
        blob = "\n".join(
            default_dataset[table_name][column].astype(str).str.cat(sep="\n")
            for column in columns
        )
        for snippet in ENGLISH_PLACEHOLDER_SNIPPETS:
            assert snippet not in blob, f"placeholder '{snippet}' found in {table_name}"


def test_business_values_are_vietnamese_and_column_names_remain_english(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    """Business values are Vietnamese, but engineering column names stay English."""

    for table_name, columns in VIETNAMESE_BUSINESS_FIELDS.items():
        frame = default_dataset[table_name]
        for column in columns:
            assert column.isascii(), f"{table_name}.{column} column name is not English"
            values = frame[column].astype(str)
            assert values.map(_contains_vietnamese).any(), (
                f"{table_name}.{column} does not contain Vietnamese business values"
            )


def test_sensor_readings_have_anomaly_type_column(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    """sensor_readings must expose a separate anomaly_type enum column."""

    sensor_readings = default_dataset["sensor_readings"]

    assert "anomaly_type" in sensor_readings.columns
    assert "status" in sensor_readings.columns
    # anomaly_type is a distinct column, not a copy of the operational status enum.
    assert not sensor_readings["anomaly_type"].equals(sensor_readings["status"])
    assert set(sensor_readings["anomaly_type"]).issubset(set(ANOMALY_TYPE_CODE_TO_VI.values()))


def test_injected_anomalies_have_specific_anomaly_type(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    """Rows flagged as anomalies must carry a specific (non-'none') anomaly_type."""

    sensor_readings = default_dataset["sensor_readings"]
    injected = sensor_readings[sensor_readings["status"] == STATUS_CODE_TO_VI["fault"]]

    assert not injected.empty, "expected injected anomaly rows in the dataset"
    assert (injected["anomaly_type"] != ANOMALY_TYPE_CODE_TO_VI["none"]).all()
    # The specific injected categories should all be represented.
    assert {
        ANOMALY_TYPE_CODE_TO_VI["energy_spike"],
        ANOMALY_TYPE_CODE_TO_VI["vibration_increase"],
        ANOMALY_TYPE_CODE_TO_VI["runtime_abnormal"],
    }.issubset(
        set(injected["anomaly_type"])
    )


def test_normal_records_mostly_have_anomaly_type_none(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    """The vast majority of readings are normal and must default to anomaly_type='none'."""

    sensor_readings = default_dataset["sensor_readings"]
    none_ratio = (sensor_readings["anomaly_type"] == ANOMALY_TYPE_CODE_TO_VI["none"]).mean()

    assert none_ratio > 0.9, f"expected mostly no-anomaly readings, got ratio {none_ratio:.3f}"
    # Every non-'none' anomaly_type row must be a flagged (warning/anomaly) record.
    flagged = sensor_readings[sensor_readings["anomaly_type"] != ANOMALY_TYPE_CODE_TO_VI["none"]]
    assert flagged["status"].isin([STATUS_CODE_TO_VI["fault"], STATUS_CODE_TO_VI["warning"]]).all()


def test_documents_have_requested_columns_and_vietnamese_business_values(
    default_dataset: dict[str, pd.DataFrame],
) -> None:
    """Documents keep English column names and Vietnamese user-facing values."""

    documents = default_dataset["documents"]

    assert {
        "doc_id",
        "title",
        "doc_type",
        "asset_type",
        "source",
        "raw_text",
        "clean_text",
        "created_at",
    }.issubset(documents.columns)
    assert "source_path" not in documents.columns

    source = documents["source"].astype(str)

    assert source.map(_contains_vietnamese).all()
    assert set(documents["doc_type"]).issubset(set(DOCUMENT_TYPE_CODE_TO_VI.values()))
    assert set(documents["asset_type"]).issubset(set(ASSET_TYPE_CODE_TO_VI.values()))

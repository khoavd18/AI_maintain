"""Tests for MVP and daily equipment risk scoring."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.config.value_mappings import RISK_LEVEL_CODE_TO_VI
from src.data_generation.generate_data import generate_dataset, save_dataset
from src.features.build_features import build_features_from_csv
from src.models.anomaly_detection import run_anomaly_detection
from src.risk.risk_scoring import (
    RISK_OUTPUT_COLUMNS,
    assign_risk_level,
    assign_risk_level_code,
    build_risk_scores,
    calculate_final_risk_score,
    calculate_follow_up_score,
    calculate_maintenance_overdue_score,
    calculate_recent_ticket_score,
    calculate_recurring_issue_score,
    calculate_runtime_score,
    calculate_unresolved_ticket_score,
    normalize_criticality_score,
    run_risk_scoring,
)


@pytest.fixture(scope="module")
def risk_fixture(tmp_path_factory: pytest.TempPathFactory) -> dict[str, pd.DataFrame | Path]:
    """Build compact deterministic risk-scoring inputs."""

    base_dir = tmp_path_factory.mktemp("risk_scoring")
    raw_dir = base_dir / "raw"
    feature_path = base_dir / "processed" / "asset_daily_features.csv"
    anomaly_path = base_dir / "processed" / "anomaly_results.csv"
    risk_path = base_dir / "processed" / "risk_scores.csv"

    dataset = generate_dataset(asset_count=24, days=20, seed=41)
    save_dataset(dataset, raw_dir)
    features = build_features_from_csv(input_dir=raw_dir, output_path=feature_path)
    anomalies = run_anomaly_detection(input_path=feature_path, output_path=anomaly_path)
    risks = run_risk_scoring(
        feature_path=feature_path,
        anomaly_path=anomaly_path,
        output_path=risk_path,
    )

    return {
        "features": features,
        "anomalies": anomalies,
        "risks": risks,
        "risk_path": risk_path,
    }


def test_risk_scores_csv_is_generated(risk_fixture: dict[str, pd.DataFrame | Path]) -> None:
    """The risk scorer should write risk_scores.csv."""

    risk_path = risk_fixture["risk_path"]

    assert isinstance(risk_path, Path)
    assert risk_path.exists()


def test_risk_score_output_columns(risk_fixture: dict[str, pd.DataFrame | Path]) -> None:
    """Risk scoring output should expose the requested schema."""

    risks = risk_fixture["risks"]

    assert isinstance(risks, pd.DataFrame)
    assert list(risks.columns) == RISK_OUTPUT_COLUMNS
    assert (risks["feature_date"] == risks["date"]).all()
    assert (risks["risk_score"] == risks["final_risk_score"]).all()
    assert not risks.duplicated(["asset_id", "feature_date"]).any()


def test_risk_component_scores_are_bounded(risk_fixture: dict[str, pd.DataFrame | Path]) -> None:
    """All risk component scores should stay within 0-100."""

    risks = risk_fixture["risks"]
    component_columns = [
        "anomaly_score",
        "maintenance_overdue_score",
        "unresolved_ticket_score",
        "recent_ticket_score",
        "recurring_issue_score",
        "criticality_score",
        "follow_up_score",
        "runtime_score",
        "final_risk_score",
    ]

    assert isinstance(risks, pd.DataFrame)
    for column in component_columns:
        assert risks[column].between(0, 100).all()


def test_risk_level_uses_vietnamese_values_only(risk_fixture: dict[str, pd.DataFrame | Path]) -> None:
    """Risk levels should be Vietnamese business labels."""

    risks = risk_fixture["risks"]

    assert isinstance(risks, pd.DataFrame)
    assert set(risks["risk_level"]).issubset(set(RISK_LEVEL_CODE_TO_VI.values()))
    assert set(risks["risk_level_code"]).issubset({"low", "medium", "high", "critical"})


def test_risk_reasons_and_actions_are_vietnamese_and_non_empty(
    risk_fixture: dict[str, pd.DataFrame | Path],
) -> None:
    """User-facing risk explanations and actions should be Vietnamese."""

    risks = risk_fixture["risks"]

    assert isinstance(risks, pd.DataFrame)
    assert (risks["main_reasons"].astype(str).str.strip() != "").all()
    assert (risks["recommended_action"].astype(str).str.strip() != "").all()
    assert (risks["contributing_factors"].astype(str).str.strip() != "").all()
    assert risks["main_reasons"].str.contains("Thiết bị|Điểm|Runtime|ticket|Tài sản").any()
    assert risks["recommended_action"].str.contains("Kiểm tra|Theo dõi|Ưu tiên|Lên lịch").any()


def test_higher_anomaly_score_increases_final_risk_score() -> None:
    """With other components equal, higher anomaly score should increase final risk."""

    features = _manual_feature_frame()
    anomalies = _manual_anomaly_frame([10.0, 90.0])

    risks = build_risk_scores(features, anomalies).sort_values("asset_id")

    assert risks.iloc[1]["final_risk_score"] > risks.iloc[0]["final_risk_score"]


def test_risk_results_are_deterministic(
    risk_fixture: dict[str, pd.DataFrame | Path],
) -> None:
    features = risk_fixture["features"]
    anomalies = risk_fixture["anomalies"]
    assert isinstance(features, pd.DataFrame)
    assert isinstance(anomalies, pd.DataFrame)

    first = build_risk_scores(features, anomalies)
    second = build_risk_scores(features, anomalies)

    pd.testing.assert_frame_equal(first, second)


def test_canonical_risk_formula_uses_documented_weights() -> None:
    score = calculate_final_risk_score(
        anomaly_score=80,
        maintenance_overdue_score=60,
        unresolved_ticket_score=50,
        recent_ticket_score=40,
        recurring_issue_score=70,
        criticality_score=100,
        follow_up_score=70,
        runtime_score=20,
    )

    assert score == 64.25


def test_overdue_maintenance_increases_overdue_component() -> None:
    """Maintenance overdue score should follow the requested thresholds."""

    assert calculate_maintenance_overdue_score(0) == 0
    assert calculate_maintenance_overdue_score(7) == 30
    assert calculate_maintenance_overdue_score(14) == 60
    assert calculate_maintenance_overdue_score(31) == 100


def test_recent_tickets_increase_recent_ticket_score() -> None:
    """Recent tickets and high-priority tickets should increase ticket score."""

    assert calculate_recent_ticket_score(0, 0) == 0
    assert calculate_recent_ticket_score(1, 0) == 30
    assert calculate_recent_ticket_score(3, 0) == 60
    assert calculate_recent_ticket_score(4, 0) == 80
    assert calculate_recent_ticket_score(4, 1) == 100


def test_critical_assets_get_higher_criticality_score() -> None:
    """Criticality scores should normalize from 1-4 into 25-100."""

    assert normalize_criticality_score(1) == 25
    assert normalize_criticality_score(4) == 100


def test_runtime_score_thresholds() -> None:
    """Runtime score should follow the requested thresholds."""

    assert calculate_runtime_score(10) == 0
    assert calculate_runtime_score(25) == 30
    assert calculate_runtime_score(50) == 70
    assert calculate_runtime_score(51) == 100


def test_new_maintenance_risk_factor_thresholds() -> None:
    assert calculate_unresolved_ticket_score(0) == 0
    assert calculate_unresolved_ticket_score(1) == 50
    assert calculate_unresolved_ticket_score(3) == 100
    assert calculate_recurring_issue_score(0) == 0
    assert calculate_recurring_issue_score(1) == 70
    assert calculate_follow_up_score(0) == 0
    assert calculate_follow_up_score(2) == 100


def test_risk_level_thresholds() -> None:
    """Risk level should follow the requested Vietnamese score bands."""

    assert assign_risk_level(30) == RISK_LEVEL_CODE_TO_VI["low"]
    assert assign_risk_level(60) == RISK_LEVEL_CODE_TO_VI["medium"]
    assert assign_risk_level(80) == RISK_LEVEL_CODE_TO_VI["high"]
    assert assign_risk_level(81) == RISK_LEVEL_CODE_TO_VI["critical"]
    assert assign_risk_level_code(30) == "low"
    assert assign_risk_level_code(31) == "medium"
    assert assign_risk_level_code(61) == "high"
    assert assign_risk_level_code(81) == "critical"


def test_risk_output_has_no_nan_or_infinite_values(
    risk_fixture: dict[str, pd.DataFrame | Path],
) -> None:
    """Risk scoring output should be safe for downstream APIs and dashboards."""

    risks = risk_fixture["risks"]

    assert isinstance(risks, pd.DataFrame)
    assert risks.isna().sum().sum() == 0
    assert np.isfinite(risks.select_dtypes(include=[np.number]).to_numpy()).all()


def _manual_feature_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _manual_feature_row("A_001", anomaly_date="2026-05-01"),
            _manual_feature_row("A_002", anomaly_date="2026-05-01"),
        ]
    )


def _manual_feature_row(asset_id: str, anomaly_date: str) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "feature_date": anomaly_date,
        "asset_name": f"Thiết bị {asset_id}",
        "asset_type": "Máy lạnh",
        "location": "Phòng máy thử nghiệm",
        "days_overdue": 0,
        "ticket_count_30d": 0,
        "high_priority_ticket_count_30d": 0,
        "criticality_score": 2,
        "runtime_delta_percent": 0,
    }


def _manual_anomaly_frame(scores: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": f"A_{index:03d}",
                "date": "2026-05-01",
                "anomaly_score": score,
                "anomaly_type": "Không bất thường",
                "anomaly_reasons": "Không phát hiện dấu hiệu bất thường đáng kể.",
            }
            for index, score in enumerate(scores, start=1)
        ]
    )

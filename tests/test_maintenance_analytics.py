"""Tests for preventive, recurring-issue, and maintenance KPI analytics."""

from pathlib import Path

import pandas as pd

from src.config.value_mappings import (
    FAILURE_TYPE_CODE_TO_VI,
    STATUS_CODE_TO_VI,
)
from src.data_generation.generate_data import generate_dataset, save_dataset
from src.features.build_features import (
    RECURRENCE_THRESHOLD,
    build_maintenance_analytics_from_csv,
    build_preventive_maintenance_status,
    build_recurring_issue_analysis,
    calculate_maintenance_kpis,
)


def test_preventive_maintenance_status_classification() -> None:
    assets = pd.DataFrame(
        [
            _asset_date_row("A_001", "2026-03-01", "2026-04-20"),
            _asset_date_row("A_002", "2026-03-15", "2026-05-10"),
            _asset_date_row("A_003", "2026-04-01", "2026-06-15"),
        ]
    )

    results = build_preventive_maintenance_status(assets, "2026-04-30")
    by_asset = results.set_index("asset_id")

    assert by_asset.at["A_001", "maintenance_status"] == "overdue"
    assert by_asset.at["A_001", "days_overdue"] == 10
    assert by_asset.at["A_002", "maintenance_status"] == "due_soon"
    assert by_asset.at["A_002", "days_until_due"] == 10
    assert by_asset.at["A_003", "maintenance_status"] == "not_due"
    assert by_asset.at["A_003", "days_until_due"] == 46


def test_recurring_issue_grouping_and_threshold_behavior() -> None:
    tickets = pd.DataFrame(
        [
            _ticket_row("T1", "A_001", "cooling_issue", "2026-01-01", "resolved"),
            _ticket_row("T2", "A_001", "cooling_issue", "2026-02-01", "open"),
            _ticket_row("T3", "A_001", "cooling_issue", "2026-03-01", "resolved"),
            _ticket_row("T4", "A_001", "sensor_issue", "2026-03-10", "open"),
            _ticket_row("T5", "A_002", "sensor_issue", "2026-01-10", "resolved"),
            _ticket_row("T6", "A_002", "sensor_issue", "2026-02-10", "resolved"),
        ]
    )

    results = build_recurring_issue_analysis(tickets)
    recurring = results[
        (results["asset_id"] == "A_001")
        & (results["failure_category"] == FAILURE_TYPE_CODE_TO_VI["cooling_issue"])
    ].iloc[0]
    below_threshold = results[
        (results["asset_id"] == "A_002")
        & (results["failure_category"] == FAILURE_TYPE_CODE_TO_VI["sensor_issue"])
    ].iloc[0]

    assert recurring["occurrence_count"] == RECURRENCE_THRESHOLD
    assert recurring["resolved_count"] == 2
    assert recurring["unresolved_count"] == 1
    assert bool(recurring["recurrence_flag"])
    assert not bool(below_threshold["recurrence_flag"])


def test_maintenance_kpi_calculations() -> None:
    tickets = pd.DataFrame(
        [
            _ticket_row("T1", "A_001", "cooling_issue", "2026-01-01", "resolved", 24),
            _ticket_row("T2", "A_001", "cooling_issue", "2026-02-01", "resolved", 72),
            _ticket_row("T3", "A_002", "sensor_issue", "2026-03-01", "open"),
        ]
    )
    logs = pd.DataFrame({"follow_up_required": [False, True, True]})
    preventive = pd.DataFrame(
        {
            "as_of_date": ["2026-04-30"] * 3,
            "maintenance_status": ["overdue", "due_soon", "not_due"],
        }
    )
    recurring = pd.DataFrame({"recurrence_flag": [True, False]})
    risks = pd.DataFrame(
        {
            "asset_id": ["A_001", "A_002", "A_003", "A_001"],
            "feature_date": ["2026-04-30", "2026-04-30", "2026-04-30", "2026-04-29"],
            "risk_level_code": ["high", "critical", "low", "critical"],
        }
    )

    kpis = calculate_maintenance_kpis(tickets, logs, preventive, recurring, risks).iloc[0]

    assert kpis["total_tickets"] == 3
    assert kpis["open_tickets"] == 1
    assert kpis["resolved_tickets"] == 2
    assert kpis["ticket_resolution_rate_percent"] == 66.67
    assert kpis["average_resolution_time_hours"] == 48.0
    assert kpis["median_resolution_time_hours"] == 48.0
    assert kpis["overdue_asset_count"] == 1
    assert kpis["due_soon_asset_count"] == 1
    assert kpis["recurring_issue_count"] == 1
    assert kpis["follow_up_required_maintenance_count"] == 2
    assert kpis["high_critical_risk_asset_count"] == 2


def test_maintenance_analytics_outputs_use_asset_master_ids(tmp_path: Path) -> None:
    dataset = generate_dataset(asset_count=9, days=10, seed=31)
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    risk_path = processed_dir / "risk_scores.csv"
    save_dataset(dataset, raw_dir)
    processed_dir.mkdir()
    pd.DataFrame(
        {
            "asset_id": dataset["assets"]["asset_id"],
            "feature_date": ["2026-01-10"] * 9,
            "risk_level_code": ["low"] * 9,
        }
    ).to_csv(risk_path, index=False)

    outputs = build_maintenance_analytics_from_csv(
        input_dir=raw_dir,
        risk_path=risk_path,
        processed_dir=processed_dir,
    )
    asset_ids = set(dataset["assets"]["asset_id"])

    assert set(outputs["preventive_maintenance_status"]["asset_id"]) == asset_ids
    assert set(outputs["recurring_issues"]["asset_id"]).issubset(asset_ids)
    assert len(outputs["maintenance_kpis"]) == 1
    assert (processed_dir / "preventive_maintenance_status.csv").exists()
    assert (processed_dir / "recurring_issues.csv").exists()
    assert (processed_dir / "maintenance_kpis.csv").exists()


def test_production_pipeline_does_not_import_legacy_risk_formula() -> None:
    root = Path(__file__).resolve().parents[1]
    canonical_paths = [
        root / "src/features/build_features.py",
        root / "src/models/anomaly_detection.py",
        root / "src/risk/risk_scoring.py",
    ]

    for path in canonical_paths:
        assert "src.risk.scoring" not in path.read_text(encoding="utf-8")


def _asset_date_row(asset_id: str, last_date: str, next_date: str) -> dict[str, str]:
    return {
        "asset_id": asset_id,
        "last_maintenance_date": last_date,
        "next_maintenance_date": next_date,
    }


def _ticket_row(
    ticket_id: str,
    asset_id: str,
    failure_code: str,
    created_at: str,
    status_code: str,
    resolution_hours: int | None = None,
) -> dict[str, str]:
    created = pd.Timestamp(created_at, tz="UTC")
    resolved_at = ""
    if resolution_hours is not None:
        resolved_at = (created + pd.Timedelta(hours=resolution_hours)).isoformat()
    elif status_code == "resolved":
        resolved_at = (created + pd.Timedelta(days=1)).isoformat()
    return {
        "ticket_id": ticket_id,
        "asset_id": asset_id,
        "failure_category": FAILURE_TYPE_CODE_TO_VI[failure_code],
        "created_at": created.isoformat(),
        "resolved_at": resolved_at,
        "status": STATUS_CODE_TO_VI[status_code],
    }

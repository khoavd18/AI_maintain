"""Tests for FastAPI routes serving processed maintenance intelligence data."""

import math
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api.routes import _service
from src.api.services import ProcessedDataService
from src.data_generation.generate_data import generate_dataset, save_dataset
from src.features.build_features import (
    build_features_from_csv,
    build_maintenance_analytics_from_csv,
)
from src.models.anomaly_detection import run_anomaly_detection
from src.risk.risk_scoring import run_risk_scoring


@pytest.fixture(scope="module")
def api_fixture(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Create a temporary processed dataset and TestClient for API tests."""

    base_dir = tmp_path_factory.mktemp("api_routes")
    raw_dir = base_dir / "raw"
    processed_dir = base_dir / "processed"
    feature_path = processed_dir / "asset_daily_features.csv"
    anomaly_path = processed_dir / "anomaly_results.csv"
    risk_path = processed_dir / "risk_scores.csv"

    dataset = generate_dataset(asset_count=24, days=20, seed=51)
    save_dataset(dataset, raw_dir)
    features = build_features_from_csv(input_dir=raw_dir, output_path=feature_path)
    anomalies = run_anomaly_detection(input_path=feature_path, output_path=anomaly_path)
    risks = run_risk_scoring(
        feature_path=feature_path,
        anomaly_path=anomaly_path,
        output_path=risk_path,
    )
    maintenance_outputs = build_maintenance_analytics_from_csv(
        input_dir=raw_dir,
        risk_path=risk_path,
        processed_dir=processed_dir,
    )

    service = ProcessedDataService(
        feature_path=feature_path,
        anomaly_path=anomaly_path,
        risk_path=risk_path,
        asset_path=raw_dir / "assets.csv",
        ticket_path=raw_dir / "maintenance_tickets.csv",
        maintenance_log_path=raw_dir / "maintenance_logs.csv",
        preventive_path=processed_dir / "preventive_maintenance_status.csv",
        recurring_issue_path=processed_dir / "recurring_issues.csv",
        maintenance_kpi_path=processed_dir / "maintenance_kpis.csv",
    )
    app = create_app()
    app.dependency_overrides[_service] = lambda: service
    client = TestClient(app)

    return {
        "client": client,
        "features": features,
        "anomalies": anomalies,
        "risks": risks,
        "maintenance_outputs": maintenance_outputs,
        "service": service,
        "raw_dir": raw_dir,
        "processed_dir": processed_dir,
    }


def test_summary_endpoint(api_fixture: dict[str, Any]) -> None:
    """The summary endpoint should return current maintenance metrics."""

    client: TestClient = api_fixture["client"]
    response = client.get("/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_assets"] == 24
    assert payload["total_records"] == 24 * 20
    assert payload["latest_date"]
    assert 0 <= payload["average_risk_score"] <= 100
    assert {"high_risk_count", "urgent_risk_count", "anomaly_count"}.issubset(payload)


def test_assets_risk_endpoint(api_fixture: dict[str, Any]) -> None:
    """Risk listing should return sorted risk rows."""

    client: TestClient = api_fixture["client"]
    response = client.get("/assets/risk", params={"limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 5
    assert payload[0]["final_risk_score"] >= payload[-1]["final_risk_score"]
    assert {"asset_id", "risk_level", "recommended_action"}.issubset(payload[0])


def test_assets_risk_top_endpoint(api_fixture: dict[str, Any]) -> None:
    """Top risk endpoint should default to latest date."""

    client: TestClient = api_fixture["client"]
    risks: pd.DataFrame = api_fixture["risks"]
    latest_date = risks["date"].max()
    response = client.get("/assets/risk/top", params={"limit": 3})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 3
    assert {row["date"] for row in payload} == {latest_date}
    assert payload[0]["final_risk_score"] >= payload[1]["final_risk_score"]


def test_asset_risk_history_endpoint(api_fixture: dict[str, Any]) -> None:
    """Risk history should return one asset sorted by date."""

    client: TestClient = api_fixture["client"]
    risks: pd.DataFrame = api_fixture["risks"]
    asset_id = str(risks["asset_id"].iloc[0])
    response = client.get(f"/assets/risk/{asset_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert {row["asset_id"] for row in payload} == {asset_id}
    assert [row["date"] for row in payload] == sorted(row["date"] for row in payload)


def test_assets_anomalies_endpoint(api_fixture: dict[str, Any]) -> None:
    """Anomaly endpoint should return anomalous rows by default."""

    client: TestClient = api_fixture["client"]
    response = client.get("/assets/anomalies", params={"limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert all(row["is_anomaly"] for row in payload)
    assert payload[0]["anomaly_score"] >= payload[-1]["anomaly_score"]


def test_asset_anomaly_history_endpoint(api_fixture: dict[str, Any]) -> None:
    """Anomaly history should return one asset sorted by date."""

    client: TestClient = api_fixture["client"]
    anomalies: pd.DataFrame = api_fixture["anomalies"]
    asset_id = str(anomalies["asset_id"].iloc[0])
    response = client.get(f"/assets/anomalies/{asset_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert {row["asset_id"] for row in payload} == {asset_id}
    assert [row["date"] for row in payload] == sorted(row["date"] for row in payload)


def test_asset_context_endpoint(api_fixture: dict[str, Any]) -> None:
    """Asset context should combine risk, anomaly, feature, and recommendation data."""

    client: TestClient = api_fixture["client"]
    risks: pd.DataFrame = api_fixture["risks"]
    asset_id = str(risks["asset_id"].iloc[0])
    response = client.get(f"/assets/{asset_id}/context")

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == asset_id
    assert payload["latest_risk"]["asset_id"] == asset_id
    assert payload["recent_anomalies"]
    assert payload["recent_features"]
    assert payload["latest_recommendation"]


def test_filter_by_vietnamese_risk_level(api_fixture: dict[str, Any]) -> None:
    """Risk endpoint should filter using Vietnamese business labels."""

    client: TestClient = api_fixture["client"]
    risks: pd.DataFrame = api_fixture["risks"]
    risk_level = str(risks["risk_level"].value_counts().index[0])
    response = client.get("/assets/risk", params={"risk_level": risk_level, "limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert {row["risk_level"] for row in payload} == {risk_level}


def test_unknown_asset_returns_404(api_fixture: dict[str, Any]) -> None:
    """Unknown asset IDs should return a clear 404."""

    client: TestClient = api_fixture["client"]
    response = client.get("/assets/risk/UNKNOWN_999")

    assert response.status_code == 404


def test_json_responses_do_not_contain_nan(api_fixture: dict[str, Any]) -> None:
    """JSON responses should not expose NaN values."""

    client: TestClient = api_fixture["client"]

    for path in ["/summary", "/assets/risk?limit=10", "/assets/anomalies?limit=10"]:
        response = client.get(path)
        assert response.status_code == 200
        _assert_no_nan(response.json())


def test_asset_listing_and_filtering(api_fixture: dict[str, Any]) -> None:
    client: TestClient = api_fixture["client"]
    service: ProcessedDataService = api_fixture["service"]
    asset_type = str(service.assets["asset_type"].iloc[0])

    response = client.get("/assets", params={"asset_type": asset_type})

    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert {row["asset_type"] for row in payload} == {asset_type}
    assert {
        "criticality",
        "status",
        "risk_score",
        "maintenance_status",
        "unresolved_ticket_count",
    }.issubset(payload[0])


def test_asset_master_and_unknown_asset(api_fixture: dict[str, Any]) -> None:
    client: TestClient = api_fixture["client"]
    response = client.get("/assets/HVAC_001")

    assert response.status_code == 200
    assert response.json()["asset_id"] == "HVAC_001"
    assert client.get("/assets/UNKNOWN_999").status_code == 404


def test_consolidated_asset_details(api_fixture: dict[str, Any]) -> None:
    client: TestClient = api_fixture["client"]
    response = client.get("/assets/HVAC_001/details", params={"limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_profile"]["asset_id"] == "HVAC_001"
    assert payload["latest_risk"]["asset_id"] == "HVAC_001"
    assert payload["risk_contributing_factors"]
    assert payload["recommended_action"]
    assert payload["preventive_maintenance"]["asset_id"] == "HVAC_001"
    assert len(payload["risk_history"]) == 20
    assert len(payload["recent_tickets"]) <= 5
    assert len(payload["recent_maintenance_logs"]) <= 5


def test_preventive_and_recurring_issue_filters(api_fixture: dict[str, Any]) -> None:
    client: TestClient = api_fixture["client"]
    preventive = api_fixture["maintenance_outputs"]["preventive_maintenance_status"]
    status = str(preventive["maintenance_status"].iloc[0])

    preventive_response = client.get(
        "/maintenance/preventive", params={"maintenance_status": status}
    )
    recurring_response = client.get(
        "/maintenance/recurring-issues", params={"recurrence_flag": True}
    )

    assert preventive_response.status_code == 200
    assert {row["maintenance_status"] for row in preventive_response.json()} == {status}
    assert recurring_response.status_code == 200
    assert recurring_response.json()
    assert all(row["recurrence_flag"] for row in recurring_response.json())


def test_kpi_ticket_and_maintenance_log_endpoints(api_fixture: dict[str, Any]) -> None:
    client: TestClient = api_fixture["client"]
    service: ProcessedDataService = api_fixture["service"]
    ticket_status = str(service.tickets["status"].iloc[0])

    kpi_response = client.get("/maintenance/kpis")
    ticket_response = client.get("/tickets", params={"status": ticket_status})
    log_response = client.get(
        "/maintenance/logs", params={"follow_up_required": True}
    )

    assert kpi_response.status_code == 200
    assert kpi_response.json()["total_tickets"] == len(service.tickets)
    assert ticket_response.status_code == 200
    assert {row["status"] for row in ticket_response.json()} == {ticket_status}
    unresolved = [row for row in ticket_response.json() if row["status"] != "Đã xử lý"]
    assert all(row["resolved_at"] is None for row in unresolved)
    assert log_response.status_code == 200
    assert log_response.json()
    assert all(row["follow_up_required"] for row in log_response.json())


def test_missing_analytics_file_returns_safe_503(
    api_fixture: dict[str, Any], tmp_path: Path
) -> None:
    original: ProcessedDataService = api_fixture["service"]
    service = ProcessedDataService(
        feature_path=original.feature_path,
        anomaly_path=original.anomaly_path,
        risk_path=original.risk_path,
        asset_path=original.asset_path,
        ticket_path=original.ticket_path,
        maintenance_log_path=original.maintenance_log_path,
        preventive_path=tmp_path / "missing-preventive.csv",
        recurring_issue_path=original.recurring_issue_path,
        maintenance_kpi_path=original.maintenance_kpi_path,
    )
    app = create_app()
    app.dependency_overrides[_service] = lambda: service
    response = TestClient(app).get("/maintenance/preventive")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "unavailable" in detail
    assert str(tmp_path) not in detail


def test_stale_analytics_file_returns_clear_503(
    api_fixture: dict[str, Any], tmp_path: Path
) -> None:
    original: ProcessedDataService = api_fixture["service"]
    stale_kpi_path = tmp_path / "maintenance_kpis.csv"
    stale_kpis = pd.read_csv(original.maintenance_kpi_path)
    stale_kpis["as_of_date"] = "2099-01-01"
    stale_kpis.to_csv(stale_kpi_path, index=False)
    service = ProcessedDataService(
        feature_path=original.feature_path,
        anomaly_path=original.anomaly_path,
        risk_path=original.risk_path,
        asset_path=original.asset_path,
        ticket_path=original.ticket_path,
        maintenance_log_path=original.maintenance_log_path,
        preventive_path=original.preventive_path,
        recurring_issue_path=original.recurring_issue_path,
        maintenance_kpi_path=stale_kpi_path,
    )
    app = create_app()
    app.dependency_overrides[_service] = lambda: service
    response = TestClient(app).get("/summary")

    assert response.status_code == 503
    assert "stale or inconsistent" in response.json()["detail"]


def _assert_no_nan(value: Any) -> None:
    if isinstance(value, float):
        assert not math.isnan(value)
    elif isinstance(value, dict):
        for nested in value.values():
            _assert_no_nan(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_nan(nested)

"""Tests for dashboard API client helpers."""

import json
from typing import Any

import httpx
import pandas as pd
import pytest

from src.dashboard.api_client import (
    DEFAULT_API_BASE_URL,
    ApiClientError,
    MaintenanceApiClient,
    get_api_base_url,
    records_to_dataframe,
)
from src.dashboard.app import _distribution, _filter_frame, _format_hours, _format_percent


def test_get_api_base_url_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dashboard should default to the local FastAPI service."""

    monkeypatch.delenv("API_BASE_URL", raising=False)

    assert get_api_base_url() == DEFAULT_API_BASE_URL


def test_get_api_base_url_trims_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trailing slashes should not leak into request URL construction."""

    monkeypatch.setenv("API_BASE_URL", "http://api.local/")

    assert get_api_base_url() == "http://api.local"


def test_records_to_dataframe_accepts_list_and_object() -> None:
    """API JSON payloads should convert cleanly into display DataFrames."""

    list_frame = records_to_dataframe([{"asset_id": "A_001", "final_risk_score": 75.0}])
    object_frame = records_to_dataframe({"asset_id": "A_002", "final_risk_score": 81.0})

    assert list(list_frame.columns) == ["asset_id", "final_risk_score"]
    assert list_frame.loc[0, "asset_id"] == "A_001"
    assert object_frame.loc[0, "asset_id"] == "A_002"
    assert records_to_dataframe(None).empty
    assert records_to_dataframe([]).empty


def test_client_sends_clean_query_parameters() -> None:
    """None filters should be omitted while selected dashboard filters are preserved."""

    seen_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    client = MaintenanceApiClient(
        "http://api.local/",
        transport=httpx.MockTransport(handler),
    )

    payload = client.list_risks(
        risk_level="Cao",
        asset_type=None,
        location="Zone A",
        date="2026-06-30",
        limit=5,
    )

    assert payload == []
    assert seen_params == {
        "risk_level": "Cao",
        "location": "Zone A",
        "date": "2026-06-30",
        "limit": "5",
    }


def test_client_raises_readable_error_for_api_status_failure() -> None:
    """Dashboard errors should include the API status and detail."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "Processed data file not found"})

    client = MaintenanceApiClient(
        "http://api.local",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ApiClientError, match="503"):
        client.get_summary()


def test_client_posts_copilot_question() -> None:
    """Dashboard client should call POST /copilot/ask with the expected payload."""

    seen_payload: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payload.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "answer": "Trả lời dựa trên SOP.",
                "asset_context": {"asset_id": "HVAC_001"},
                "sources": [],
                "retrieved_chunks": [],
            },
        )

    client = MaintenanceApiClient(
        "http://api.local",
        transport=httpx.MockTransport(handler),
    )

    payload = client.ask_copilot(
        question="Cần kiểm tra gì?",
        asset_id="HVAC_001",
        top_k=3,
    )

    assert payload["answer"] == "Trả lời dựa trên SOP."
    assert seen_payload == {
        "question": "Cần kiểm tra gì?",
        "asset_id": "HVAC_001",
        "top_k": 3,
    }


def test_client_supports_all_manager_workflow_methods() -> None:
    """New dashboard methods should use the focused API paths and clean parameters."""

    requests: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        requests.append((path, dict(request.url.params)))
        if path in {"/assets/HVAC_001", "/assets/HVAC_001/details", "/maintenance/kpis"}:
            return httpx.Response(200, json={})
        return httpx.Response(200, json=[])

    client = MaintenanceApiClient(
        "http://api.local",
        transport=httpx.MockTransport(handler),
    )

    assert client.list_assets(asset_type="Máy lạnh", location=None) == []
    assert client.get_asset("HVAC_001") == {}
    assert client.get_asset_details("HVAC_001", limit=5) == {}
    assert client.list_preventive_maintenance(maintenance_status="overdue") == []
    assert client.list_recurring_issues(recurrence_flag=False) == []
    assert client.get_maintenance_kpis() == {}
    assert client.list_tickets(status="Mới tạo", limit=25) == []
    assert client.list_maintenance_logs(follow_up_required=True, limit=25) == []

    request_map = {path: params for path, params in requests}
    assert request_map["/assets"] == {"asset_type": "Máy lạnh"}
    assert request_map["/assets/HVAC_001/details"] == {"limit": "5"}
    assert request_map["/maintenance/preventive"] == {"maintenance_status": "overdue"}
    assert request_map["/maintenance/recurring-issues"] == {"recurrence_flag": "false"}
    assert request_map["/tickets"] == {"status": "Mới tạo", "limit": "25"}
    assert request_map["/maintenance/logs"] == {
        "follow_up_required": "true",
        "limit": "25",
    }


def test_client_rejects_wrong_response_shape_for_new_methods() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json="wrong-shape")

    client = MaintenanceApiClient(
        "http://api.local",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ApiClientError, match="Expected a list response"):
        client.list_assets()
    with pytest.raises(ApiClientError, match="Expected an object response"):
        client.get_maintenance_kpis()


def test_dashboard_pure_formatting_and_filter_helpers() -> None:
    frame = pd.DataFrame(
        {
            "risk_level": ["Cao", "Thấp", "Cao", None],
            "asset_id": ["A", "B", "C", "D"],
        }
    )

    assert _distribution(frame, "risk_level").to_dict() == {"Cao": 2, "Thấp": 1}
    assert _filter_frame(frame, "risk_level", "Cao")["asset_id"].tolist() == ["A", "C"]
    assert _filter_frame(frame, "risk_level", None).equals(frame)
    assert _format_percent(57.14) == "57.14%"
    assert _format_hours(54) == "54.0 giờ"

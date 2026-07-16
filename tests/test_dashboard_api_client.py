"""Tests for dashboard API client helpers."""

import json
from datetime import date
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
from src.dashboard.app import (
    _allowed_ticket_statuses,
    _build_copilot_context,
    _build_copilot_question,
    _calculate_next_maintenance_date,
    _distribution,
    _filter_frame,
    _format_hours,
    _format_percent,
    _maintenance_follow_up,
    _ticket_form_defaults,
)


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


def test_client_sends_write_workflow_requests() -> None:
    requests: list[tuple[str, str, dict[str, Any]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        requests.append((request.method, request.url.path, payload))
        if request.url.path == "/maintenance/logs":
            return httpx.Response(201, json={"log_id": "LOG-000101"})
        return httpx.Response(201 if request.method == "POST" else 200, json={
            "ticket_id": "TCK-000101"
        })

    client = MaintenanceApiClient(
        "http://api.local",
        transport=httpx.MockTransport(handler),
    )
    client.create_ticket(
        asset_id="GENERATOR_002",
        issue_description="Kiểm tra khả năng khởi động.",
        priority="Cao",
        failure_category="Lỗi điện",
        technician_id="TECH_001",
        manager_note=None,
    )
    client.update_ticket(
        "TCK-000101",
        status="Đang xử lý",
        technician_id="TECH_002",
    )
    client.create_maintenance_log(
        ticket_id="TCK-000101",
        asset_id="GENERATOR_002",
        maintenance_date="2026-07-15",
        inspection_result="Ắc quy yếu.",
        actions_taken="Vệ sinh đầu cực.",
        parts_replaced=None,
        technician_note="Đã chạy thử.",
        maintenance_result="Đã xử lý",
        follow_up_required=False,
        next_maintenance_date="2026-11-12",
    )

    assert [(method, path) for method, path, _ in requests] == [
        ("POST", "/tickets"),
        ("PATCH", "/tickets/TCK-000101"),
        ("POST", "/maintenance/logs"),
    ]
    assert "manager_note" not in requests[0][2]
    assert requests[1][2] == {
        "status": "Đang xử lý",
        "technician_id": "TECH_002",
    }
    assert requests[2][2]["follow_up_required"] is False


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


def test_dashboard_workflow_form_helpers() -> None:
    details = {
        "asset_profile": {
            "asset_id": "GENERATOR_002",
            "asset_name": "Máy phát điện dự phòng 002",
            "asset_type": "Máy phát điện dự phòng",
        },
        "latest_risk": {"risk_level": "Cao"},
        "risk_contributing_factors": "Bảo trì quá hạn 159 ngày",
        "recommended_action": "Kiểm tra trong tuần.",
        "recent_tickets": [
            {
                "failure_category": "Lỗi điện",
                "technician_id": "TECH_004",
            }
        ],
    }
    defaults = _ticket_form_defaults(details)
    ticket = {
        "ticket_id": "TCK-000099",
        "failure_category": "Lỗi điện",
        "issue_description": "Máy phát không khởi động.",
    }
    context = _build_copilot_context(details, ticket)
    question = _build_copilot_question(context)

    assert defaults["asset_id"] == "GENERATOR_002"
    assert defaults["priority"] == "Cao"
    assert defaults["failure_category"] == "Lỗi điện"
    assert "Bảo trì quá hạn 159 ngày" in defaults["issue_description"]
    assert _allowed_ticket_statuses("Mới tạo") == ["Mới tạo", "Đang xử lý"]
    assert _allowed_ticket_statuses("Đang xử lý") == ["Đang xử lý", "Đã xử lý"]
    assert _allowed_ticket_statuses("Đã xử lý") == ["Đã xử lý"]
    assert _maintenance_follow_up("Đã xử lý") is False
    assert _maintenance_follow_up("Cần theo dõi") is True
    assert _calculate_next_maintenance_date(date(2026, 7, 15), 120) == date(
        2026, 11, 12
    )
    assert context["asset_type"] == "Máy phát điện dự phòng"
    assert context["failure_category"] == "Lỗi điện"
    assert "TCK-000099" in question
    assert "Bảo trì quá hạn 159 ngày" in question

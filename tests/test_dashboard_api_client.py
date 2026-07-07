"""Tests for dashboard API client helpers."""

import json
from typing import Any

import httpx
import pytest

from src.dashboard.api_client import (
    DEFAULT_API_BASE_URL,
    ApiClientError,
    MaintenanceApiClient,
    get_api_base_url,
    records_to_dataframe,
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

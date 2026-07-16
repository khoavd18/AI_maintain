"""Tests for the local CSV-first maintenance decision workflow."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.csv_repository import (
    CsvWriteError,
    CsvWriteRepository,
    DuplicateRecordError,
)
from src.api.main import create_app
from src.api.routes import _service
from src.api.services import (
    MAINTENANCE_LOG_REQUIRED_COLUMNS,
    TICKET_REQUIRED_COLUMNS,
    ProcessedDataService,
)


@pytest.fixture
def workflow(tmp_path: Path) -> dict[str, Any]:
    """Create the smallest valid writable CSV contract and API client."""

    asset_path = tmp_path / "assets.csv"
    ticket_path = tmp_path / "maintenance_tickets.csv"
    log_path = tmp_path / "maintenance_logs.csv"
    pd.DataFrame(
        [
            {
                "asset_id": "GENERATOR_002",
                "asset_name": "Máy phát điện dự phòng 002",
                "asset_type": "Máy phát điện dự phòng",
                "location": "Sân thượng phía Đông",
                "criticality": "Rất quan trọng",
                "status": "Cảnh báo",
                "installation_date": "2023-01-01",
                "last_maintenance_date": "2026-01-01",
                "maintenance_interval_days": 30,
                "next_maintenance_date": "2026-01-31",
            },
            {
                "asset_id": "HVAC_001",
                "asset_name": "Máy lạnh 001",
                "asset_type": "Máy lạnh",
                "location": "Tầng 1",
                "criticality": "Cao",
                "status": "Bình thường",
                "installation_date": "2023-01-01",
                "last_maintenance_date": "2026-01-01",
                "maintenance_interval_days": 30,
                "next_maintenance_date": "2026-01-31",
            },
        ]
    ).to_csv(asset_path, index=False)
    pd.DataFrame(columns=sorted(TICKET_REQUIRED_COLUMNS)).to_csv(ticket_path, index=False)
    pd.DataFrame(columns=sorted(MAINTENANCE_LOG_REQUIRED_COLUMNS)).to_csv(
        log_path, index=False
    )

    service = ProcessedDataService(
        asset_path=asset_path,
        ticket_path=ticket_path,
        maintenance_log_path=log_path,
    )
    app = create_app()
    app.dependency_overrides[_service] = lambda: service
    return {
        "client": TestClient(app),
        "service": service,
        "asset_path": asset_path,
        "ticket_path": ticket_path,
        "log_path": log_path,
    }


def test_ticket_creation_uses_unique_id_and_open_status(workflow: dict[str, Any]) -> None:
    client: TestClient = workflow["client"]

    first = client.post("/tickets", json=_ticket_payload()).json()
    second = client.post("/tickets", json=_ticket_payload()).json()

    assert first["ticket_id"] == "TCK-000001"
    assert second["ticket_id"] == "TCK-000002"
    assert first["status"] == "Mới tạo"
    assert first["resolved_at"] is None
    assert first["manager_note"] == "Ưu tiên kiểm tra trong tuần."
    assert datetime.fromisoformat(first["created_at"]).utcoffset() is not None
    assert len(pd.read_csv(workflow["ticket_path"])) == 2


def test_ticket_creation_rejects_invalid_asset_without_writing(
    workflow: dict[str, Any],
) -> None:
    client: TestClient = workflow["client"]
    payload = _ticket_payload(asset_id="UNKNOWN_999")

    response = client.post("/tickets", json=payload)

    assert response.status_code == 404
    assert pd.read_csv(workflow["ticket_path"]).empty


def test_ticket_update_and_resolution_after_log(workflow: dict[str, Any]) -> None:
    client: TestClient = workflow["client"]
    ticket = _create_in_progress_ticket(client)
    log_response = client.post(
        "/maintenance/logs",
        json=_maintenance_payload(ticket["ticket_id"]),
    )

    response = client.patch(
        f"/tickets/{ticket['ticket_id']}",
        json={
            "status": "Đã xử lý",
            "priority": "Trung bình",
            "technician_id": "TECH_006",
            "note": "Đã chạy thử có tải.",
        },
    )

    assert log_response.status_code == 201
    assert response.status_code == 200
    updated = response.json()
    assert updated["status"] == "Đã xử lý"
    assert updated["priority"] == "Trung bình"
    assert updated["technician_id"] == "TECH_006"
    assert updated["note"] == "Đã chạy thử có tải."
    assert updated["resolved_at"] is not None


def test_invalid_status_transition_does_not_change_ticket(
    workflow: dict[str, Any],
) -> None:
    client: TestClient = workflow["client"]
    ticket = client.post("/tickets", json=_ticket_payload()).json()
    before = workflow["ticket_path"].read_bytes()

    response = client.patch(
        f"/tickets/{ticket['ticket_id']}",
        json={"status": "Đã xử lý"},
    )

    assert response.status_code == 400
    assert "không hợp lệ" in response.json()["detail"]
    assert workflow["ticket_path"].read_bytes() == before


def test_maintenance_log_creation_preserves_ticket_relationship(
    workflow: dict[str, Any],
) -> None:
    client: TestClient = workflow["client"]
    ticket = _create_in_progress_ticket(client)

    response = client.post(
        "/maintenance/logs",
        json=_maintenance_payload(ticket["ticket_id"]),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["log_id"] == "LOG-000001"
    assert payload["ticket_id"] == ticket["ticket_id"]
    assert payload["asset_id"] == ticket["asset_id"]
    assert payload["maintenance_type"] == "Bảo trì sửa chữa"
    assert payload["technician_id"] == ticket["technician_id"]
    assert payload["follow_up_required"] is False
    assets = pd.read_csv(workflow["asset_path"])
    asset = assets[assets["asset_id"] == "GENERATOR_002"].iloc[0]
    assert asset["last_maintenance_date"] == date.today().isoformat()
    assert asset["next_maintenance_date"] == (
        date.today() + timedelta(days=30)
    ).isoformat()


def test_follow_up_result_keeps_ticket_in_progress(workflow: dict[str, Any]) -> None:
    client: TestClient = workflow["client"]
    ticket = _create_in_progress_ticket(client)
    payload = _maintenance_payload(ticket["ticket_id"])
    payload["maintenance_result"] = "Cần theo dõi"
    payload["follow_up_required"] = True

    response = client.post("/maintenance/logs", json=payload)
    current_ticket = client.get(
        "/tickets", params={"asset_id": "GENERATOR_002", "status": "Đang xử lý"}
    )

    assert response.status_code == 201
    assert response.json()["follow_up_required"] is True
    assert current_ticket.json()[0]["ticket_id"] == ticket["ticket_id"]


def test_maintenance_log_rejects_ticket_asset_mismatch(
    workflow: dict[str, Any],
) -> None:
    client: TestClient = workflow["client"]
    ticket = _create_in_progress_ticket(client)
    payload = _maintenance_payload(ticket["ticket_id"])
    payload["asset_id"] = "HVAC_001"
    before = workflow["log_path"].read_bytes()

    response = client.post("/maintenance/logs", json=payload)

    assert response.status_code == 400
    assert "không khớp" in response.json()["detail"]
    assert workflow["log_path"].read_bytes() == before


def test_maintenance_log_rejects_invalid_chronology(workflow: dict[str, Any]) -> None:
    client: TestClient = workflow["client"]
    ticket = _create_in_progress_ticket(client)
    previous_date = date.today() - timedelta(days=1)
    payload = _maintenance_payload(ticket["ticket_id"])
    payload["maintenance_date"] = previous_date.isoformat()
    payload["next_maintenance_date"] = (previous_date + timedelta(days=30)).isoformat()

    response = client.post("/maintenance/logs", json=payload)

    assert response.status_code == 400
    assert "sớm hơn ngày tạo ticket" in response.json()["detail"]


def test_repository_rejects_duplicate_id_without_changing_file(tmp_path: Path) -> None:
    path = tmp_path / "tickets.csv"
    pd.DataFrame([{"ticket_id": "TCK-000001", "asset_id": "A_001"}]).to_csv(
        path, index=False
    )
    repository = CsvWriteRepository(
        path,
        id_column="ticket_id",
        required_columns={"ticket_id", "asset_id"},
    )
    before = path.read_bytes()

    with pytest.raises(DuplicateRecordError, match="đã tồn tại"):
        repository.append({"ticket_id": "TCK-000001", "asset_id": "A_002"})

    assert path.read_bytes() == before


def test_failed_atomic_replace_leaves_original_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tickets.csv"
    pd.DataFrame([{"ticket_id": "TCK-000001", "asset_id": "A_001"}]).to_csv(
        path, index=False
    )
    repository = CsvWriteRepository(
        path,
        id_column="ticket_id",
        required_columns={"ticket_id", "asset_id"},
    )
    before = path.read_bytes()

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("src.api.csv_repository.os.replace", fail_replace)
    with pytest.raises(CsvWriteError, match="file gốc không bị thay đổi"):
        repository.append({"ticket_id": "TCK-000002", "asset_id": "A_002"})

    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_failed_second_file_replace_rolls_back_log_and_asset(
    workflow: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client: TestClient = workflow["client"]
    ticket = _create_in_progress_ticket(client)
    log_before = workflow["log_path"].read_bytes()
    asset_before = workflow["asset_path"].read_bytes()
    real_replace = os.replace
    replace_count = 0

    def fail_second_replace(source: Path, destination: Path) -> None:
        nonlocal replace_count
        replace_count += 1
        if replace_count == 2:
            raise OSError("simulated second replace failure")
        real_replace(source, destination)

    monkeypatch.setattr("src.api.csv_repository.os.replace", fail_second_replace)
    response = client.post(
        "/maintenance/logs",
        json=_maintenance_payload(ticket["ticket_id"]),
    )

    assert response.status_code == 503
    assert workflow["log_path"].read_bytes() == log_before
    assert workflow["asset_path"].read_bytes() == asset_before


def test_existing_read_endpoints_remain_backward_compatible(
    workflow: dict[str, Any],
) -> None:
    client: TestClient = workflow["client"]
    ticket = client.post("/tickets", json=_ticket_payload()).json()

    response = client.get("/tickets", params={"asset_id": "GENERATOR_002"})
    log_response = client.get("/maintenance/logs")

    assert response.status_code == 200
    assert {
        "ticket_id",
        "asset_id",
        "issue_description",
        "priority",
        "status",
        "failure_category",
        "created_at",
        "resolved_at",
        "technician_id",
    }.issubset(response.json()[0])
    assert response.json()[0]["ticket_id"] == ticket["ticket_id"]
    assert log_response.status_code == 200
    assert log_response.json() == []


def _ticket_payload(asset_id: str = "GENERATOR_002") -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "issue_description": "Kiểm tra khả năng khởi động theo tín hiệu risk batch.",
        "priority": "Cao",
        "failure_category": "Lỗi điện",
        "technician_id": "TECH_001",
        "manager_note": "Ưu tiên kiểm tra trong tuần.",
    }


def _create_in_progress_ticket(client: TestClient) -> dict[str, Any]:
    ticket = client.post("/tickets", json=_ticket_payload()).json()
    response = client.patch(
        f"/tickets/{ticket['ticket_id']}",
        json={"status": "Đang xử lý", "technician_id": "TECH_002"},
    )
    assert response.status_code == 200
    return response.json()


def _maintenance_payload(ticket_id: str) -> dict[str, Any]:
    maintenance_date = date.today()
    return {
        "ticket_id": ticket_id,
        "asset_id": "GENERATOR_002",
        "maintenance_date": maintenance_date.isoformat(),
        "inspection_result": "Ắc quy yếu, đầu cực có dấu hiệu oxy hóa.",
        "actions_taken": "Vệ sinh đầu cực và kiểm tra điện áp ắc quy.",
        "parts_replaced": "Không thay vật tư",
        "technician_note": "Đã chạy thử khởi động tại chỗ.",
        "maintenance_result": "Đã xử lý",
        "follow_up_required": False,
        "next_maintenance_date": (maintenance_date + timedelta(days=30)).isoformat(),
    }

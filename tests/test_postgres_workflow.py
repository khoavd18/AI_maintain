"""PostgreSQL transaction, integrity, concurrency, and API compatibility tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from src.api.main import create_app
from src.api.routes import _service
from src.api.services import FACILITY_TIMEZONE, ProcessedDataService
from src.database.models import Asset
from src.database.session import build_engine, get_session_factory
from src.repositories.contracts import IntegrityViolationError, StaleRecordError
from src.repositories.postgres import PostgresMaintenanceRepository
from tests.auth_helpers import authorize_app, build_test_user, persist_test_user


@pytest.fixture
def postgres_repository(
    clean_postgres_database: str,
) -> PostgresMaintenanceRepository:
    engine = build_engine(clean_postgres_database)
    today = datetime.now(FACILITY_TIMEZONE).date()
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                Asset(
                    asset_id="GENERATOR_002",
                    asset_name="Máy phát điện dự phòng 002",
                    asset_type="generator",
                    location="Sân thượng phía Đông",
                    criticality="critical",
                    status="warning",
                    installation_date=date(2023, 1, 1),
                    last_maintenance_date=today - timedelta(days=30),
                    maintenance_interval_days=30,
                    next_maintenance_date=today,
                ),
                Asset(
                    asset_id="HVAC_001",
                    asset_name="Máy lạnh 001",
                    asset_type="hvac",
                    location="Tầng 1",
                    criticality="high",
                    status="normal",
                    installation_date=date(2023, 1, 1),
                    last_maintenance_date=today - timedelta(days=30),
                    maintenance_interval_days=30,
                    next_maintenance_date=today,
                ),
            ]
        )
    engine.dispose()
    return PostgresMaintenanceRepository(get_session_factory(clean_postgres_database))


@pytest.fixture
def postgres_service(
    postgres_repository: PostgresMaintenanceRepository,
) -> ProcessedDataService:
    return ProcessedDataService(repository=postgres_repository)


@pytest.mark.postgres
def test_concurrent_ticket_creation_uses_unique_generated_ids(
    postgres_service: ProcessedDataService,
) -> None:
    def create(index: int) -> str:
        return str(
            postgres_service.create_ticket(
                **_ticket_request(technician_id=f"TECH_{index:03d}")
            )["ticket_id"]
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        identifiers = list(executor.map(create, range(16)))

    assert len(identifiers) == 16
    assert len(set(identifiers)) == 16
    assert sorted(identifiers)[0] == "TCK-000001"
    assert sorted(identifiers)[-1] == "TCK-000016"


@pytest.mark.postgres
def test_invalid_foreign_key_rolls_back_ticket(
    postgres_repository: PostgresMaintenanceRepository,
) -> None:
    values = {
        **_ticket_request(asset_id="UNKNOWN_999"),
        "status": "Mới tạo",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved_at": None,
        "note": None,
    }

    with pytest.raises(IntegrityViolationError, match="foreign key"):
        postgres_repository.create_ticket(values)

    assert postgres_repository.list_tickets() == []


@pytest.mark.postgres
def test_valid_status_transition_and_log_before_resolution_rule(
    postgres_service: ProcessedDataService,
) -> None:
    ticket = postgres_service.create_ticket(**_ticket_request())
    in_progress = postgres_service.update_ticket(
        str(ticket["ticket_id"]),
        {"status": "Đang xử lý", "technician_id": "TECH_002"},
    )
    assert in_progress["status"] == "Đang xử lý"

    with pytest.raises(ValueError, match="maintenance log"):
        postgres_service.update_ticket(
            str(ticket["ticket_id"]),
            {"status": "Đã xử lý"},
        )


@pytest.mark.postgres
def test_atomic_maintenance_workflow_synchronizes_asset_and_allows_resolution(
    postgres_service: ProcessedDataService,
    postgres_repository: PostgresMaintenanceRepository,
) -> None:
    ticket = _create_in_progress_ticket(postgres_service)
    today = datetime.now(FACILITY_TIMEZONE).date()
    ticket_before_log = postgres_repository.get_ticket(str(ticket["ticket_id"]))
    assert ticket_before_log is not None

    log = postgres_service.create_maintenance_log(
        **_maintenance_request(str(ticket["ticket_id"]), today)
    )
    ticket_after_log = postgres_repository.get_ticket(str(ticket["ticket_id"]))
    resolved = postgres_service.update_ticket(
        str(ticket["ticket_id"]),
        {"status": "Đã xử lý"},
    )
    asset = postgres_service.get_asset("GENERATOR_002")

    assert log["log_id"] == "LOG-000001"
    assert ticket_after_log is not None
    assert ticket_after_log.version == ticket_before_log.version + 1
    assert asset["last_maintenance_date"] == today.isoformat()
    assert asset["next_maintenance_date"] == (today + timedelta(days=30)).isoformat()
    assert resolved["status"] == "Đã xử lý"
    assert resolved["resolved_at"] is not None


@pytest.mark.postgres
def test_maintenance_transaction_rolls_back_every_write_on_failure(
    postgres_service: ProcessedDataService,
    postgres_repository: PostgresMaintenanceRepository,
    clean_postgres_database: str,
) -> None:
    ticket = _create_in_progress_ticket(postgres_service)
    today = datetime.now(FACILITY_TIMEZONE).date()
    before = postgres_service.get_asset("GENERATOR_002")
    ticket_before = postgres_repository.get_ticket(str(ticket["ticket_id"]))
    assert ticket_before is not None
    engine = build_engine(clean_postgres_database)

    def fail_asset_update(
        conn,
        cursor,
        statement: str,
        parameters,
        context,
        executemany,
    ) -> None:
        del conn, cursor, parameters, context, executemany
        if statement.lstrip().upper().startswith("UPDATE ASSETS"):
            raise RuntimeError("simulated asset update failure")

    event.listen(engine, "before_cursor_execute", fail_asset_update)
    original_factory = postgres_repository.session_factory
    postgres_repository.session_factory = get_session_factory(clean_postgres_database)
    bound_engine = postgres_repository.session_factory.kw["bind"]
    event.listen(bound_engine, "before_cursor_execute", fail_asset_update)
    try:
        with pytest.raises(RuntimeError, match="simulated"):
            postgres_service.create_maintenance_log(
                **_maintenance_request(str(ticket["ticket_id"]), today)
            )
    finally:
        event.remove(bound_engine, "before_cursor_execute", fail_asset_update)
        event.remove(engine, "before_cursor_execute", fail_asset_update)
        postgres_repository.session_factory = original_factory
        engine.dispose()

    assert postgres_service.list_maintenance_logs() == []
    assert postgres_service.get_asset("GENERATOR_002") == before
    ticket_after = postgres_repository.get_ticket(str(ticket["ticket_id"]))
    assert ticket_after is not None
    assert ticket_after.version == ticket_before.version


@pytest.mark.postgres
def test_stale_ticket_update_is_rejected(
    postgres_repository: PostgresMaintenanceRepository,
) -> None:
    created = postgres_repository.create_ticket(
        {
            **_ticket_request(),
            "status": "Mới tạo",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": None,
            "note": None,
        }
    )
    postgres_repository.update_ticket(
        str(created.values["ticket_id"]),
        {"status": "Đang xử lý"},
        expected_version=created.version,
    )

    with pytest.raises(StaleRecordError, match="thay đổi"):
        postgres_repository.update_ticket(
            str(created.values["ticket_id"]),
            {"priority": "Khẩn cấp"},
            expected_version=created.version,
        )


@pytest.mark.postgres
def test_api_contract_is_unchanged_with_postgresql_storage(
    postgres_service: ProcessedDataService,
) -> None:
    app = create_app()
    app.dependency_overrides[_service] = lambda: postgres_service
    actor = build_test_user()
    persist_test_user(postgres_service.repository.session_factory, actor)
    authorize_app(app, actor)
    client = TestClient(app)

    response = client.post("/tickets", json=_ticket_request())
    assets = client.get("/assets")

    assert response.status_code == 201
    assert set(response.json()) == {
        "ticket_id",
        "asset_id",
        "issue_description",
        "priority",
        "status",
        "failure_category",
        "created_at",
        "resolved_at",
        "technician_id",
        "manager_note",
        "note",
    }
    assert response.json()["status"] == "Mới tạo"
    assert assets.status_code == 200
    assert assets.json()[0]["asset_type"] in {"Máy lạnh", "Máy phát điện dự phòng"}


def _ticket_request(
    *,
    asset_id: str = "GENERATOR_002",
    technician_id: str = "TECH_001",
) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "issue_description": "Kiểm tra khả năng khởi động theo tín hiệu risk batch.",
        "priority": "Cao",
        "failure_category": "Lỗi điện",
        "technician_id": technician_id,
        "manager_note": "Ưu tiên kiểm tra trong tuần.",
    }


def _create_in_progress_ticket(service: ProcessedDataService) -> dict[str, Any]:
    ticket = service.create_ticket(**_ticket_request())
    return service.update_ticket(
        str(ticket["ticket_id"]),
        {"status": "Đang xử lý", "technician_id": "TECH_002"},
    )


def _maintenance_request(ticket_id: str, maintenance_date: date) -> dict[str, Any]:
    return {
        "ticket_id": ticket_id,
        "asset_id": "GENERATOR_002",
        "maintenance_date": maintenance_date,
        "inspection_result": "Ắc quy yếu, đầu cực có dấu hiệu oxy hóa.",
        "actions_taken": "Vệ sinh đầu cực và kiểm tra điện áp ắc quy.",
        "parts_replaced": "Không thay vật tư",
        "technician_note": "Đã chạy thử khởi động tại chỗ.",
        "maintenance_result": "Đã xử lý",
        "follow_up_required": False,
        "next_maintenance_date": maintenance_date + timedelta(days=30),
    }

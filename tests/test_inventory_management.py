"""PostgreSQL integration tests for inventory and work-order stock control."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from src.asset_management.storage import LocalAttachmentStorage
from src.api.main import create_app
from src.database.models import (
    Asset,
    AuditLog,
    InventoryMovement,
    InventoryOperation,
)
from src.database.session import build_engine, get_session_factory
from src.inventory_management.service import (
    InventoryAuthorizationError,
    InventoryConflictError,
    InventoryManagementService,
)
from src.inventory_management.cli import seed_development_inventory
from src.inventory_management.routes import get_inventory_management_service
from src.maintenance_management.service import MaintenancePlanningService
from src.repositories.contracts import (
    DuplicateIdentifierError,
    IntegrityViolationError,
    StaleRecordError,
)
from src.repositories.postgres_inventory import PostgresInventoryRepository
from src.repositories.postgres_maintenance import (
    PostgresMaintenancePlanningRepository,
)
from src.security.audit import AuditContext
from src.security.permissions import Role
from src.security.service import CurrentUser
from tests.auth_helpers import (
    authorize_app,
    build_test_user,
    persist_test_user,
)

STOREKEEPER_ID = UUID("60000000-0000-4000-8000-000000000001")
ENGINEER_ID = UUID("60000000-0000-4000-8000-000000000002")
TECHNICIAN_ID = UUID("60000000-0000-4000-8000-000000000003")
HELPDESK_ID = UUID("60000000-0000-4000-8000-000000000004")


@pytest.fixture
def inventory_context(
    clean_postgres_database: str, tmp_path: Path
) -> dict[str, object]:
    session_factory = get_session_factory(clean_postgres_database)
    storekeeper = _actor(Role.STOREKEEPER, STOREKEEPER_ID, "storekeeper.inventory")
    engineer = _actor(Role.CHIEF_ENGINEER, ENGINEER_ID, "engineer.inventory")
    technician = _actor(
        Role.TECHNICIAN,
        TECHNICIAN_ID,
        "technician.inventory",
        technician_id="TECH_002",
    )
    helpdesk = _actor(Role.HELPDESK, HELPDESK_ID, "helpdesk.inventory")
    for actor in (storekeeper, engineer, technician, helpdesk):
        persist_test_user(session_factory, actor)

    today = date.today()
    engine = build_engine(clean_postgres_database)
    with Session(engine) as session, session.begin():
        session.add(
            Asset(
                asset_id="GENERATOR_002",
                asset_name="Máy phát điện dự phòng 002",
                asset_type="generator",
                location="Sân thượng phía Đông",
                criticality="critical",
                status="normal",
                installation_date=date(2023, 1, 1),
                last_maintenance_date=today - timedelta(days=30),
                maintenance_interval_days=30,
                next_maintenance_date=today,
            )
        )
    engine.dispose()

    maintenance_service = MaintenancePlanningService(
        PostgresMaintenancePlanningRepository(session_factory),
        LocalAttachmentStorage(tmp_path / "work-order-evidence"),
        attachment_max_size_bytes=1024 * 1024,
    )
    work_order = maintenance_service.create_work_order(
        {
            "title": "Kiểm tra máy phát điện",
            "description": "Work order dùng để kiểm tra luồng vật tư.",
            "work_order_type": "inspection",
            "asset_id": "GENERATOR_002",
            "preventive_plan_id": None,
            "source_ticket_id": None,
            "assigned_to_user_id": technician.id,
            "priority": "high",
            "scheduled_start_at": None,
            "scheduled_end_at": None,
            "due_date": today,
            "local_timezone": "Asia/Ho_Chi_Minh",
            "grace_period_days": 0,
            "estimated_duration_minutes": 60,
            "checklist_template_id": None,
        },
        actor=engineer,
        audit_context=_audit(engineer, "setup-work-order"),
    )
    repository = PostgresInventoryRepository(session_factory)
    service = InventoryManagementService(
        repository,
        LocalAttachmentStorage(tmp_path / "inventory-evidence"),
        attachment_max_size_bytes=1024 * 1024,
    )
    category = service.create_category(
        {
            "code": "GENERATOR",
            "name_vi": "Vật tư máy phát điện",
            "name_en": "Generator parts",
            "description": None,
        },
        actor=storekeeper,
        audit_context=_audit(storekeeper, "setup-category"),
    )
    unit = service.create_unit(
        {
            "code": "EA",
            "name_vi": "Cái",
            "name_en": "Each",
            "symbol": "cái",
            "quantity_precision": 0,
        },
        actor=storekeeper,
        audit_context=_audit(storekeeper, "setup-uom"),
    )
    part = service.create_part(
        {
            "part_number": "GEN-FILTER-001",
            "name_vi": "Lọc nhiên liệu máy phát",
            "name_en": "Generator fuel filter",
            "category_id": category["id"],
            "unit_of_measure_id": unit["id"],
            "manufacturer_reference": "GF-001",
            "compatible_asset_types": ["generator"],
            "minimum_stock": Decimal("2"),
            "reorder_point": Decimal("4"),
            "maximum_stock": Decimal("12"),
            "unit_cost": Decimal("250000"),
            "currency_code": "VND",
        },
        actor=storekeeper,
        audit_context=_audit(storekeeper, "setup-part"),
    )
    main_location = service.create_stock_location(
        {
            "code": "MAIN",
            "name": "Kho chính",
            "location_type": "main_store",
            "description": None,
        },
        actor=storekeeper,
        audit_context=_audit(storekeeper, "setup-location-main"),
    )
    engineering_location = service.create_stock_location(
        {
            "code": "ENGINEERING",
            "name": "Kho kỹ thuật",
            "location_type": "engineering_store",
            "description": None,
        },
        actor=storekeeper,
        audit_context=_audit(storekeeper, "setup-location-engineering"),
    )
    opening_request = {
        "part_id": part["id"],
        "stock_location_id": main_location["id"],
        "quantity": Decimal("10"),
        "business_reference": "OPENING-TEST",
        "occurred_at": None,
        "reason": "Số dư kiểm thử ban đầu",
        "unit_cost_snapshot": None,
    }
    opening = service.create_opening_balance(
        opening_request,
        idempotency_key="test-opening-generator-filter",
        actor=storekeeper,
        audit_context=_audit(storekeeper, "setup-opening"),
    )
    requirement = service.create_requirement(
        UUID(work_order["id"]),
        {
            "part_id": part["id"],
            "planned_quantity": Decimal("6"),
            "required_by_date": today,
            "source_stock_location_id": main_location["id"],
            "notes": "Kế hoạch vật tư kiểm thử",
        },
        actor=engineer,
        audit_context=_audit(engineer, "setup-requirement"),
    )
    return {
        "database_url": clean_postgres_database,
        "session_factory": session_factory,
        "maintenance_service": maintenance_service,
        "service": service,
        "repository": repository,
        "storekeeper": storekeeper,
        "engineer": engineer,
        "technician": technician,
        "helpdesk": helpdesk,
        "work_order": work_order,
        "part": part,
        "main_location": main_location,
        "engineering_location": engineering_location,
        "opening_request": opening_request,
        "opening": opening,
        "requirement": requirement,
    }


@pytest.mark.postgres
def test_opening_balance_is_idempotent_and_payload_protected(
    inventory_context: dict[str, object],
) -> None:
    service = _service(inventory_context)
    storekeeper = _user(inventory_context, "storekeeper")
    replay = service.create_opening_balance(
        dict(inventory_context["opening_request"]),
        idempotency_key="test-opening-generator-filter",
        actor=storekeeper,
        audit_context=_audit(storekeeper, "replay-opening"),
    )
    assert replay["id"] == inventory_context["opening"]["id"]

    conflicting = dict(inventory_context["opening_request"])
    conflicting["quantity"] = Decimal("9")
    with pytest.raises(DuplicateIdentifierError):
        service.create_opening_balance(
            conflicting,
            idempotency_key="test-opening-generator-filter",
            actor=storekeeper,
            audit_context=_audit(storekeeper, "conflict-opening"),
        )

    session_factory = inventory_context["session_factory"]
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(InventoryMovement)) == 1
        assert session.scalar(select(func.count()).select_from(InventoryOperation)) == 1


@pytest.mark.postgres
def test_requirement_reservation_issue_consumption_and_return_are_distinct(
    inventory_context: dict[str, object],
) -> None:
    service = _service(inventory_context)
    storekeeper = _user(inventory_context, "storekeeper")
    technician = _user(inventory_context, "technician")
    requirement = dict(inventory_context["requirement"])
    reservation_request = {
        "quantity": Decimal("4"),
        "expires_at": None,
        "reason": "Giữ vật tư cho công việc đã lên kế hoạch",
        "expected_requirement_version": requirement["version"],
    }
    reservation = service.reserve_stock(
        UUID(requirement["id"]),
        reservation_request,
        idempotency_key="test-reserve-generator-filter",
        actor=storekeeper,
        audit_context=_audit(storekeeper, "reserve"),
    )
    replay = service.reserve_stock(
        UUID(requirement["id"]),
        reservation_request,
        idempotency_key="test-reserve-generator-filter",
        actor=storekeeper,
        audit_context=_audit(storekeeper, "reserve-replay"),
    )
    assert replay["id"] == reservation["id"]

    balance = _main_balance(inventory_context)
    assert balance["on_hand_quantity"] == Decimal("10.000")
    assert balance["reserved_quantity"] == Decimal("4.000")
    assert balance["available_quantity"] == Decimal("6.000")

    issue_request = {
        "part_id": inventory_context["part"]["id"],
        "stock_location_id": inventory_context["main_location"]["id"],
        "quantity": Decimal("3"),
        "requirement_id": requirement["id"],
        "reservation_id": reservation["id"],
        "issued_to_user_id": technician.id,
        "issued_at": None,
        "reason": "Xuất vật tư cho kỹ thuật viên",
    }
    issue = service.issue_stock(
        UUID(inventory_context["work_order"]["id"]),
        issue_request,
        idempotency_key="test-issue-generator-filter",
        actor=storekeeper,
        audit_context=_audit(storekeeper, "issue"),
    )
    issue_replay = service.issue_stock(
        UUID(inventory_context["work_order"]["id"]),
        issue_request,
        idempotency_key="test-issue-generator-filter",
        actor=storekeeper,
        audit_context=_audit(storekeeper, "issue-replay"),
    )
    assert issue_replay["id"] == issue["id"]
    summary = service.work_order_parts(
        UUID(inventory_context["work_order"]["id"]), actor=technician
    )
    assert summary["has_unresolved_issued_stock"] is True
    assert summary["completion_policy"] == "warning_only"

    consumption = service.consume_issue(
        UUID(issue["id"]),
        {
            "quantity": Decimal("2"),
            "consumed_at": None,
            "note": "Đã lắp hai bộ lọc",
        },
        idempotency_key="test-consume-generator-filter",
        actor=technician,
        audit_context=_audit(technician, "consume"),
    )
    assert consumption["quantity"] == Decimal("2.000")
    returned = service.return_issue(
        UUID(issue["id"]),
        {
            "stock_location_id": inventory_context["main_location"]["id"],
            "quantity": Decimal("1"),
            "returned_at": None,
            "reason": "Hoàn trả vật tư chưa sử dụng",
        },
        idempotency_key="test-return-generator-filter",
        actor=storekeeper,
        audit_context=_audit(storekeeper, "return"),
    )
    assert returned["quantity"] == Decimal("1.000")
    with pytest.raises(IntegrityViolationError):
        service.return_issue(
            UUID(issue["id"]),
            {
                "stock_location_id": inventory_context["main_location"]["id"],
                "quantity": Decimal("1"),
                "returned_at": None,
                "reason": "Không còn vật tư để hoàn trả",
            },
            idempotency_key="test-return-over-limit",
            actor=storekeeper,
            audit_context=_audit(storekeeper, "return-over-limit"),
        )

    balance = _main_balance(inventory_context)
    assert balance["on_hand_quantity"] == Decimal("8.000")
    assert balance["reserved_quantity"] == Decimal("1.000")
    assert balance["available_quantity"] == Decimal("7.000")
    summary = service.work_order_parts(
        UUID(inventory_context["work_order"]["id"]), actor=technician
    )
    assert summary["net_consumed_quantity"] == Decimal("2.000")
    assert summary["total_returned_quantity"] == Decimal("1.000")
    assert summary["has_unresolved_issued_stock"] is False


@pytest.mark.postgres
def test_negative_transfer_rolls_back_and_inactive_location_rejects_receipt(
    inventory_context: dict[str, object],
) -> None:
    service = _service(inventory_context)
    storekeeper = _user(inventory_context, "storekeeper")
    with pytest.raises(IntegrityViolationError):
        service.transfer_stock(
            {
                "part_id": inventory_context["part"]["id"],
                "source_stock_location_id": inventory_context["main_location"]["id"],
                "destination_stock_location_id": inventory_context[
                    "engineering_location"
                ]["id"],
                "quantity": Decimal("11"),
                "business_reference": "TRANSFER-TOO-LARGE",
                "occurred_at": None,
                "reason": "Kiểm tra rollback khi không đủ tồn kho",
            },
            idempotency_key="test-transfer-negative-stock",
            actor=storekeeper,
            audit_context=_audit(storekeeper, "transfer-negative"),
        )
    assert _main_balance(inventory_context)["on_hand_quantity"] == Decimal("10.000")
    balances = service.list_balances(
        actor=storekeeper,
        filters={},
        sort_by="part_number",
        sort_direction="asc",
        page=1,
        page_size=20,
    )["items"]
    engineering = [
        item
        for item in balances
        if item["stock_location_code"] == "ENGINEERING"
    ]
    assert not engineering

    location = dict(inventory_context["engineering_location"])
    inactive = service.change_stock_location_lifecycle(
        UUID(location["id"]),
        action="deactivate",
        expected_version=location["version"],
        reason=None,
        actor=storekeeper,
        audit_context=_audit(storekeeper, "deactivate-location"),
    )
    assert inactive["lifecycle_status"] == "inactive"
    with pytest.raises(IntegrityViolationError):
        service.receive_stock(
            {
                "part_id": inventory_context["part"]["id"],
                "stock_location_id": location["id"],
                "quantity": Decimal("1"),
                "business_reference": "RECEIPT-INACTIVE",
                "occurred_at": None,
                "reason": "Không được nhập vào kho inactive",
                "unit_cost_snapshot": None,
            },
            idempotency_key="test-receipt-inactive-location",
            actor=storekeeper,
            audit_context=_audit(storekeeper, "receipt-inactive"),
        )


@pytest.mark.postgres
def test_archived_part_stale_write_and_append_only_guard(
    inventory_context: dict[str, object],
) -> None:
    service = _service(inventory_context)
    storekeeper = _user(inventory_context, "storekeeper")
    part = dict(inventory_context["part"])
    archived = service.change_part_lifecycle(
        UUID(part["id"]),
        action="archive",
        expected_version=part["version"],
        reason="Ngừng sử dụng mã vật tư thử nghiệm",
        actor=storekeeper,
        audit_context=_audit(storekeeper, "archive-part"),
    )
    assert archived["lifecycle_status"] == "archived"
    with pytest.raises(InventoryConflictError):
        service.create_requirement(
            UUID(inventory_context["work_order"]["id"]),
            {
                "part_id": part["id"],
                "planned_quantity": Decimal("1"),
                "required_by_date": date.today(),
                "source_stock_location_id": inventory_context["main_location"]["id"],
                "notes": None,
            },
            actor=_user(inventory_context, "engineer"),
            audit_context=_audit(
                _user(inventory_context, "engineer"), "archived-requirement"
            ),
        )
    with pytest.raises(StaleRecordError):
        service.change_part_lifecycle(
            UUID(part["id"]),
            action="restore",
            expected_version=part["version"],
            reason=None,
            actor=storekeeper,
            audit_context=_audit(storekeeper, "stale-part"),
        )

    movement_id = UUID(inventory_context["opening"]["id"])
    engine = build_engine(str(inventory_context["database_url"]))
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE inventory_movements SET reason = 'mutated' WHERE id = :id"
            ),
            {"id": movement_id},
        )
    engine.dispose()


@pytest.mark.postgres
def test_concurrent_reservations_do_not_oversubscribe(
    inventory_context: dict[str, object],
) -> None:
    service = _service(inventory_context)
    storekeeper = _user(inventory_context, "storekeeper")
    engineer = _user(inventory_context, "engineer")
    technician = _user(inventory_context, "technician")
    maintenance_service = inventory_context["maintenance_service"]
    assert isinstance(maintenance_service, MaintenancePlanningService)
    second_work_order = maintenance_service.create_work_order(
        {
            "title": "Kiểm tra concurrent reservation",
            "description": None,
            "work_order_type": "inspection",
            "asset_id": "GENERATOR_002",
            "preventive_plan_id": None,
            "source_ticket_id": None,
            "assigned_to_user_id": technician.id,
            "priority": "medium",
            "scheduled_start_at": None,
            "scheduled_end_at": None,
            "due_date": date.today(),
            "local_timezone": "Asia/Ho_Chi_Minh",
            "grace_period_days": 0,
            "estimated_duration_minutes": 30,
            "checklist_template_id": None,
        },
        actor=engineer,
        audit_context=_audit(engineer, "concurrent-work-order"),
    )
    second_requirement = service.create_requirement(
        UUID(second_work_order["id"]),
        {
            "part_id": inventory_context["part"]["id"],
            "planned_quantity": Decimal("6"),
            "required_by_date": date.today(),
            "source_stock_location_id": inventory_context["main_location"]["id"],
            "notes": None,
        },
        actor=engineer,
        audit_context=_audit(engineer, "concurrent-requirement"),
    )
    requirements = [
        dict(inventory_context["requirement"]),
        second_requirement,
    ]

    def reserve(requirement: dict[str, object], key: str) -> str:
        result = service.reserve_stock(
            UUID(requirement["id"]),
            {
                "quantity": Decimal("6"),
                "expires_at": None,
                "reason": "Kiểm tra concurrent reservation",
                "expected_requirement_version": requirement["version"],
            },
            idempotency_key=key,
            actor=storekeeper,
            audit_context=_audit(storekeeper, key),
        )
        return str(result["id"])

    outcomes: list[str] = []
    errors: list[Exception] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                reserve,
                requirements[0],
                "test-concurrent-reservation-a",
            ),
            executor.submit(
                reserve,
                requirements[1],
                "test-concurrent-reservation-b",
            ),
        ]
        for future in futures:
            try:
                outcomes.append(future.result())
            except Exception as exc:  # noqa: BLE001 - test records competing outcome
                errors.append(exc)
    assert len(outcomes) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], IntegrityViolationError)
    balance = _main_balance(inventory_context)
    assert balance["reserved_quantity"] == Decimal("6.000")
    assert balance["available_quantity"] == Decimal("4.000")


@pytest.mark.postgres
def test_technician_ownership_and_transactional_audit(
    inventory_context: dict[str, object],
) -> None:
    service = _service(inventory_context)
    technician = _user(inventory_context, "technician")
    other = replace(
        technician,
        id=UUID("60000000-0000-4000-8000-000000000099"),
        username="technician.other",
        technician_id="TECH_003",
        session_id=UUID("60000000-0000-4000-8000-000000000098"),
    )
    persist_test_user(inventory_context["session_factory"], other)
    with pytest.raises(InventoryAuthorizationError):
        service.work_order_parts(
            UUID(inventory_context["work_order"]["id"]), actor=other
        )

    session_factory = inventory_context["session_factory"]
    with session_factory() as session:
        actions = set(session.scalars(select(AuditLog.action)).all())
        assert "inventory.part_created" in actions
        assert "inventory.opening_balance_created" in actions
        assert "work_order.created" in actions


@pytest.mark.postgres
def test_inventory_evidence_is_protected_and_soft_deleted(
    inventory_context: dict[str, object],
) -> None:
    service = _service(inventory_context)
    storekeeper = _user(inventory_context, "storekeeper")
    technician = _user(inventory_context, "technician")
    issue = service.issue_stock(
        UUID(inventory_context["work_order"]["id"]),
        {
            "part_id": inventory_context["part"]["id"],
            "stock_location_id": inventory_context["main_location"]["id"],
            "quantity": Decimal("1"),
            "requirement_id": inventory_context["requirement"]["id"],
            "reservation_id": None,
            "issued_to_user_id": technician.id,
            "issued_at": None,
            "reason": "Xuất vật tư để kiểm tra evidence",
        },
        idempotency_key="test-evidence-issue",
        actor=storekeeper,
        audit_context=_audit(storekeeper, "evidence-issue"),
    )
    pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"
    evidence = service.upload_evidence(
        UUID(issue["movement_id"]),
        category="other",
        filename="issue-evidence.pdf",
        claimed_media_type="application/pdf",
        content=pdf,
        actor=storekeeper,
        audit_context=_audit(storekeeper, "evidence-upload"),
    )
    assert "storage_key" not in evidence
    assert service.download_evidence(
        UUID(issue["movement_id"]),
        UUID(evidence["id"]),
        actor=technician,
    ).content == pdf

    other = replace(
        technician,
        id=UUID("60000000-0000-4000-8000-000000000095"),
        username="technician.evidence.other",
        technician_id="TECH_003",
        session_id=UUID("60000000-0000-4000-8000-000000000094"),
    )
    with pytest.raises(InventoryAuthorizationError):
        service.list_evidence(UUID(issue["movement_id"]), actor=other)
    deleted = service.delete_evidence(
        UUID(issue["movement_id"]),
        UUID(evidence["id"]),
        actor=storekeeper,
        audit_context=_audit(storekeeper, "evidence-delete"),
    )
    assert deleted["deleted_at"] is not None


@pytest.mark.postgres
def test_development_inventory_seed_is_idempotent(
    inventory_context: dict[str, object],
) -> None:
    service = _service(inventory_context)
    first = seed_development_inventory(
        service,
        storekeeper=_user(inventory_context, "storekeeper"),
        engineer=_user(inventory_context, "engineer"),
        session_factory=inventory_context["session_factory"],
    )
    session_factory = inventory_context["session_factory"]
    with session_factory() as session:
        first_counts = {
            "operations": session.scalar(
                select(func.count()).select_from(InventoryOperation)
            ),
            "movements": session.scalar(
                select(func.count()).select_from(InventoryMovement)
            ),
        }
    second = seed_development_inventory(
        service,
        storekeeper=_user(inventory_context, "storekeeper"),
        engineer=_user(inventory_context, "engineer"),
        session_factory=inventory_context["session_factory"],
    )
    with session_factory() as session:
        second_counts = {
            "operations": session.scalar(
                select(func.count()).select_from(InventoryOperation)
            ),
            "movements": session.scalar(
                select(func.count()).select_from(InventoryMovement)
            ),
        }
    assert first["created_parts"] == 8
    assert first["created_requirements"] == 1
    assert first["created_reservations"] == 1
    assert second["created_categories"] == 0
    assert second["created_units"] == 0
    assert second["created_locations"] == 0
    assert second["created_parts"] == 0
    assert second["created_reorder_configurations"] == 0
    assert second["created_requirements"] == 0
    assert second["created_reservations"] == 0
    assert second_counts == first_counts


@pytest.mark.postgres
def test_inventory_api_contract_idempotency_and_rbac(
    inventory_context: dict[str, object],
) -> None:
    app = create_app()
    app.dependency_overrides[get_inventory_management_service] = lambda: _service(
        inventory_context
    )
    storekeeper = _user(inventory_context, "storekeeper")
    authorize_app(app, storekeeper)
    client = TestClient(app)

    metrics = client.get("/inventory/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["total_active_parts"] == 1
    missing_key = client.post(
        "/inventory/receipts",
        json={
            "part_id": inventory_context["part"]["id"],
            "stock_location_id": inventory_context["main_location"]["id"],
            "quantity": 2,
            "business_reference": "API-RECEIPT-001",
            "reason": "Nhập kho qua API kiểm thử",
        },
    )
    assert missing_key.status_code == 422
    payload = {
        "part_id": inventory_context["part"]["id"],
        "stock_location_id": inventory_context["main_location"]["id"],
        "quantity": 2,
        "business_reference": "API-RECEIPT-001",
        "reason": "Nhập kho qua API kiểm thử",
    }
    headers = {"Idempotency-Key": "test-api-receipt-001"}
    created = client.post("/inventory/receipts", json=payload, headers=headers)
    replay = client.post("/inventory/receipts", json=payload, headers=headers)
    assert created.status_code == replay.status_code == 201
    assert created.json()["id"] == replay.json()["id"]

    authorize_app(app, _user(inventory_context, "helpdesk"))
    visible = client.get("/parts")
    assert visible.status_code == 200
    assert visible.json()["items"][0]["unit_cost"] is None
    denied = client.post(
        "/inventory/adjustments",
        headers={"Idempotency-Key": "test-api-helpdesk-adjust"},
        json={
            "part_id": inventory_context["part"]["id"],
            "stock_location_id": inventory_context["main_location"]["id"],
            "quantity": 1,
            "adjustment_type": "increase",
            "business_reference": "DENIED-ADJUSTMENT",
            "reason": "Helpdesk không được điều chỉnh",
            "supporting_note": "Yêu cầu này phải bị từ chối.",
        },
    )
    assert denied.status_code == 403


@pytest.mark.postgres
def test_assigned_technician_inventory_api_ownership(
    inventory_context: dict[str, object],
) -> None:
    app = create_app()
    app.dependency_overrides[get_inventory_management_service] = lambda: _service(
        inventory_context
    )
    technician = _user(inventory_context, "technician")
    authorize_app(app, technician)
    client = TestClient(app)
    work_order_id = inventory_context["work_order"]["id"]
    assert client.get(f"/work-orders/{work_order_id}/parts").status_code == 200
    assert client.get("/inventory/options").status_code == 200

    other = replace(
        technician,
        id=UUID("60000000-0000-4000-8000-000000000097"),
        username="technician.api.other",
        technician_id="TECH_003",
        session_id=UUID("60000000-0000-4000-8000-000000000096"),
    )
    authorize_app(app, other)
    denied = client.get(f"/work-orders/{work_order_id}/parts")
    assert denied.status_code == 403


def test_pm6_openapi_is_additive_to_legacy_contract() -> None:
    paths = set(create_app().openapi()["paths"])
    legacy_paths = {
        "/health",
        "/summary",
        "/assets/risk",
        "/assets/risk/top",
        "/assets/risk/{asset_id}",
        "/assets/anomalies",
        "/assets/anomalies/{asset_id}",
        "/assets/{asset_id}/context",
        "/tickets",
        "/tickets/{ticket_id}",
        "/maintenance/logs",
        "/copilot/ask",
        "/auth/login",
        "/work-orders",
        "/tickets/intake",
    }
    assert legacy_paths <= paths
    assert {
        "/parts",
        "/inventory/balances",
        "/inventory/movements",
        "/inventory/receipts",
        "/inventory/transfers",
        "/inventory/adjustments",
        "/work-orders/{work_order_id}/parts",
    } <= paths


def _actor(
    role: Role,
    actor_id: UUID,
    username: str,
    *,
    technician_id: str | None = None,
) -> CurrentUser:
    base = build_test_user(role, technician_id=technician_id)
    return replace(
        base,
        id=actor_id,
        username=username,
        display_name=username,
        session_id=UUID(
            f"{actor_id.hex[:8]}-{actor_id.hex[8:12]}-4{actor_id.hex[13:16]}-"
            f"8{actor_id.hex[17:20]}-{actor_id.hex[20:]}"
        ),
    )


def _audit(actor: CurrentUser, request_id: str) -> AuditContext:
    return AuditContext(actor.id, actor.display_name, request_id)


def _service(context: dict[str, object]) -> InventoryManagementService:
    service = context["service"]
    assert isinstance(service, InventoryManagementService)
    return service


def _user(context: dict[str, object], key: str) -> CurrentUser:
    user = context[key]
    assert isinstance(user, CurrentUser)
    return user


def _main_balance(context: dict[str, object]) -> dict[str, object]:
    service = _service(context)
    storekeeper = _user(context, "storekeeper")
    items = service.list_balances(
        actor=storekeeper,
        filters={
            "part_id": UUID(context["part"]["id"]),
            "stock_location_id": UUID(context["main_location"]["id"]),
        },
        sort_by="part_number",
        sort_direction="asc",
        page=1,
        page_size=20,
    )["items"]
    assert len(items) == 1
    return items[0]

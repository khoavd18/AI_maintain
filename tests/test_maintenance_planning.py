"""PostgreSQL integration tests for preventive planning and work orders."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.main import create_app
from src.asset_management.storage import LocalAttachmentStorage
from src.database.models import (
    Asset,
    AuditLog,
    MaintenanceLog,
    PreventiveMaintenancePlan,
    Ticket,
    WorkOrder,
)
from src.database.session import build_engine, get_session_factory
from src.maintenance_management.routes import get_maintenance_planning_service
from src.maintenance_management.service import (
    MaintenanceAuthorizationError,
    MaintenanceConflictError,
    MaintenancePlanningService,
)
from src.repositories.contracts import DuplicateIdentifierError, StaleRecordError
from src.repositories.postgres_maintenance import PostgresMaintenancePlanningRepository
from src.security.audit import AuditContext
from src.security.permissions import Permission, ROLE_PERMISSIONS, Role
from tests.auth_helpers import authorize_app, build_test_user, persist_test_user

TECHNICIAN_USER_ID = UUID("33333333-3333-4333-8333-333333333333")


@pytest.fixture
def planning_context(
    clean_postgres_database: str, tmp_path: Path
) -> dict[str, object]:
    chief = build_test_user(Role.CHIEF_ENGINEER)
    technician = replace(
        build_test_user(Role.TECHNICIAN, technician_id="TECH_002"),
        id=TECHNICIAN_USER_ID,
        username="technician.planning",
        display_name="Kỹ thuật viên kế hoạch",
        session_id=UUID("44444444-4444-4444-8444-444444444444"),
    )
    session_factory = get_session_factory(clean_postgres_database)
    persist_test_user(session_factory, chief)
    persist_test_user(session_factory, technician)
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
    repository = PostgresMaintenancePlanningRepository(session_factory)
    service = MaintenancePlanningService(
        repository,
        LocalAttachmentStorage(tmp_path / "attachments"),
        attachment_max_size_bytes=1024 * 1024,
    )
    return {
        "database_url": clean_postgres_database,
        "service": service,
        "repository": repository,
        "chief": chief,
        "technician": technician,
        "chief_audit": AuditContext(chief.id, chief.display_name, "test-chief"),
        "technician_audit": AuditContext(
            technician.id, technician.display_name, "test-technician"
        ),
        "today": today,
    }


@pytest.mark.postgres
def test_preventive_generation_execution_verification_is_atomic_and_idempotent(
    planning_context: dict[str, object],
) -> None:
    service = planning_context["service"]
    assert isinstance(service, MaintenancePlanningService)
    chief = planning_context["chief"]
    technician = planning_context["technician"]
    chief_audit = planning_context["chief_audit"]
    technician_audit = planning_context["technician_audit"]
    today = planning_context["today"]

    template = service.create_template(
        {
            "code": "GENERATOR_MONTHLY",
            "name": "Kiểm tra máy phát điện hàng tháng",
            "asset_type": "generator",
            "description": "Checklist an toàn trước khi chạy thử.",
            "items": [
                {
                    "sequence": 1,
                    "instruction": "Xác nhận khu vực đã được cô lập an toàn.",
                    "response_type": "checkbox",
                    "is_required": True,
                    "safety_critical": True,
                    "allow_not_applicable": False,
                    "expected_unit": None,
                    "minimum_value": None,
                    "maximum_value": None,
                    "guidance": "Tuân thủ lockout/tagout tại hiện trường.",
                },
                {
                    "sequence": 2,
                    "instruction": "Đánh giá tình trạng rò rỉ nhiên liệu.",
                    "response_type": "pass_fail",
                    "is_required": True,
                    "safety_critical": True,
                    "allow_not_applicable": False,
                    "expected_unit": None,
                    "minimum_value": None,
                    "maximum_value": None,
                    "guidance": None,
                },
            ],
        },
        actor=chief,
        audit_context=chief_audit,
    )
    plan = service.create_plan(
        _plan_request(
            today=today,
            template_id=UUID(template["id"]),
            technician_id=TECHNICIAN_USER_ID,
        ),
        actor=chief,
        audit_context=chief_audit,
    )
    dry_run = service.generate(
        as_of_date=today,
        plan_id=UUID(plan["id"]),
        dry_run=True,
        actor=chief,
        audit_context=chief_audit,
    )
    assert dry_run["would_generate_count"] == 1

    generated = service.generate(
        as_of_date=today,
        plan_id=UUID(plan["id"]),
        dry_run=False,
        actor=chief,
        audit_context=chief_audit,
    )
    assert generated["generated_count"] == 1
    second = service.generate(
        as_of_date=today,
        plan_id=UUID(plan["id"]),
        dry_run=False,
        actor=chief,
        audit_context=chief_audit,
    )
    assert second["generated_count"] == 0

    work_order = service.list_work_orders(
        actor=technician,
        filters={},
        page=1,
        page_size=20,
    )["items"][0]
    assert work_order["status"] == "assigned"
    started = service.transition_work_order(
        UUID(work_order["id"]),
        target_status="in_progress",
        hold_reason=None,
        expected_version=work_order["version"],
        actor=technician,
        audit_context=technician_audit,
    )
    checked = service.update_checklist(
        UUID(started["id"]),
        [
            {
                "item_id": UUID(started["checklist"][0]["id"]),
                "result_status": "completed",
                "boolean_value": True,
                "numeric_value": None,
                "text_value": None,
                "note": None,
            },
            {
                "item_id": UUID(started["checklist"][1]["id"]),
                "result_status": "pass",
                "boolean_value": None,
                "numeric_value": None,
                "text_value": None,
                "note": "Không phát hiện rò rỉ.",
            },
        ],
        expected_version=started["version"],
        actor=technician,
        audit_context=technician_audit,
    )
    completed = service.complete_work_order(
        UUID(checked["id"]),
        _completion_request(today),
        expected_version=checked["version"],
        actor=technician,
        audit_context=technician_audit,
    )
    assert completed["status"] == "completed"
    assert completed["maintenance_log_id"] is not None
    repeated = service.complete_work_order(
        UUID(completed["id"]),
        _completion_request(today),
        expected_version=checked["version"],
        actor=technician,
        audit_context=technician_audit,
    )
    assert repeated["maintenance_log_id"] == completed["maintenance_log_id"]
    with pytest.raises(MaintenanceAuthorizationError, match="tự verify"):
        service.verify_work_order(
            UUID(completed["id"]),
            expected_version=completed["version"],
            actor=technician,
            audit_context=technician_audit,
        )
    engine = build_engine(planning_context["database_url"])
    with Session(engine) as session, session.begin():
        stored_plan = session.get(PreventiveMaintenancePlan, UUID(plan["id"]))
        assert stored_plan is not None
        stored_plan.start_date = today - timedelta(days=2)
        stored_plan.last_generated_due_date = today - timedelta(days=2)
        stored_plan.next_due_date = today - timedelta(days=1)
    verified = service.verify_work_order(
        UUID(completed["id"]),
        expected_version=completed["version"],
        actor=chief,
        audit_context=chief_audit,
    )
    assert verified["status"] == "verified"

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WorkOrder)) == 1
        assert session.scalar(select(func.count()).select_from(MaintenanceLog)) == 1
        asset = session.get(Asset, "GENERATOR_002")
        assert asset is not None
        assert asset.last_maintenance_date == today
        maintenance_log = session.scalar(
            select(MaintenanceLog).where(MaintenanceLog.work_order_id == UUID(completed["id"]))
        )
        assert maintenance_log is not None
        assert asset.next_maintenance_date == maintenance_log.next_maintenance_date
        actions = set(session.scalars(select(AuditLog.action)).all())
        assert {
            "maintenance_plan.created",
            "work_order.generated",
            "work_order.started",
            "work_order.checklist_updated",
            "work_order.completed",
            "work_order.verified",
            "asset.maintenance_dates_updated",
        }.issubset(actions)
    engine.dispose()


@pytest.mark.postgres
def test_safety_failure_blocks_completion_without_partial_log(
    planning_context: dict[str, object],
) -> None:
    service = planning_context["service"]
    chief = planning_context["chief"]
    technician = planning_context["technician"]
    today = planning_context["today"]
    template = service.create_template(
        {
            "code": "SAFETY_BLOCK",
            "name": "Kiểm tra an toàn",
            "asset_type": "generator",
            "description": None,
            "items": [
                {
                    "sequence": 1,
                    "instruction": "Xác nhận không có rò rỉ nhiên liệu.",
                    "response_type": "pass_fail",
                    "is_required": True,
                    "safety_critical": True,
                    "allow_not_applicable": False,
                    "expected_unit": None,
                    "minimum_value": None,
                    "maximum_value": None,
                    "guidance": None,
                }
            ],
        },
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    work_order = service.create_work_order(
        {
            "title": "Kiểm tra an toàn máy phát",
            "description": None,
            "work_order_type": "inspection",
            "asset_id": "GENERATOR_002",
            "preventive_plan_id": None,
            "source_ticket_id": None,
            "assigned_to_user_id": TECHNICIAN_USER_ID,
            "priority": "high",
            "scheduled_start_at": None,
            "scheduled_end_at": None,
            "due_date": today,
            "local_timezone": "Asia/Ho_Chi_Minh",
            "grace_period_days": 0,
            "estimated_duration_minutes": 30,
            "checklist_template_id": UUID(template["id"]),
        },
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    started = service.transition_work_order(
        UUID(work_order["id"]),
        target_status="in_progress",
        hold_reason=None,
        expected_version=work_order["version"],
        actor=technician,
        audit_context=planning_context["technician_audit"],
    )
    failed = service.update_checklist(
        UUID(started["id"]),
        [
            {
                "item_id": UUID(started["checklist"][0]["id"]),
                "result_status": "fail",
                "boolean_value": None,
                "numeric_value": None,
                "text_value": None,
                "note": "Phát hiện dấu hiệu rò rỉ.",
            }
        ],
        expected_version=started["version"],
        actor=technician,
        audit_context=planning_context["technician_audit"],
    )
    with pytest.raises(MaintenanceConflictError, match="an toàn"):
        service.complete_work_order(
            UUID(failed["id"]),
            _completion_request(today),
            expected_version=failed["version"],
            actor=technician,
            audit_context=planning_context["technician_audit"],
        )
    engine = build_engine(planning_context["database_url"])
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(MaintenanceLog)) == 0
        entity = session.get(WorkOrder, UUID(failed["id"]))
        assert entity is not None and entity.status == "in_progress"
    engine.dispose()


@pytest.mark.postgres
def test_corrective_work_order_does_not_resolve_ticket_and_permissions_are_enforced(
    planning_context: dict[str, object],
) -> None:
    service = planning_context["service"]
    chief = planning_context["chief"]
    technician = planning_context["technician"]
    today = planning_context["today"]
    engine = build_engine(planning_context["database_url"])
    with Session(engine) as session, session.begin():
        session.add(
            Ticket(
                ticket_id="TCK-000001",
                asset_id="GENERATOR_002",
                issue_description="Máy phát rung bất thường.",
                priority="high",
                impact="high",
                urgency="high",
                status="in_progress",
                failure_category="vibration_issue",
                created_at=datetime.now(timezone.utc) - timedelta(days=1),
                resolved_at=None,
                technician_id="TECH_002",
            )
        )
    work_order = service.create_corrective_from_ticket(
        "TCK-000001",
        {
            "title": None,
            "description": None,
            "assigned_to_user_id": TECHNICIAN_USER_ID,
            "priority": None,
            "scheduled_start_at": None,
            "scheduled_end_at": None,
            "due_date": today,
            "local_timezone": "Asia/Ho_Chi_Minh",
            "grace_period_days": 0,
            "estimated_duration_minutes": 60,
            "checklist_template_id": None,
        },
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    with pytest.raises(DuplicateIdentifierError, match="corrective work order"):
        service.create_corrective_from_ticket(
            "TCK-000001",
            {
                "title": "Trùng active corrective",
                "description": None,
                "assigned_to_user_id": TECHNICIAN_USER_ID,
                "priority": "high",
                "scheduled_start_at": None,
                "scheduled_end_at": None,
                "due_date": today,
                "local_timezone": "Asia/Ho_Chi_Minh",
                "grace_period_days": 0,
                "estimated_duration_minutes": 60,
                "checklist_template_id": None,
            },
            actor=chief,
            audit_context=planning_context["chief_audit"],
        )
    started = service.transition_work_order(
        UUID(work_order["id"]),
        target_status="in_progress",
        hold_reason=None,
        expected_version=work_order["version"],
        actor=technician,
        audit_context=planning_context["technician_audit"],
    )
    completed = service.complete_work_order(
        UUID(started["id"]),
        _completion_request(today),
        expected_version=started["version"],
        actor=technician,
        audit_context=planning_context["technician_audit"],
    )
    service.verify_work_order(
        UUID(completed["id"]),
        expected_version=completed["version"],
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    with Session(engine) as session:
        ticket = session.get(Ticket, "TCK-000001")
        assert ticket is not None and ticket.status == "in_progress"
        assert session.scalar(select(func.count()).select_from(MaintenanceLog)) == 1
    engine.dispose()

    helpdesk = build_test_user(Role.HELPDESK)
    app = create_app()
    app.dependency_overrides[get_maintenance_planning_service] = lambda: service
    authorize_app(app, helpdesk)
    client = TestClient(app)
    assert client.get("/work-orders").status_code == 200
    assert client.post(
        "/maintenance-plans",
        json={
            **_plan_request(
                today=today,
                template_id=None,
                technician_id=None,
            ),
            "start_date": today.isoformat(),
            "end_date": None,
        },
    ).status_code == 403


@pytest.mark.postgres
def test_concurrent_generation_creates_one_work_order_per_occurrence(
    planning_context: dict[str, object],
) -> None:
    service = planning_context["service"]
    chief = planning_context["chief"]
    today = planning_context["today"]
    plan = service.create_plan(
        _plan_request(
            today=today,
            template_id=None,
            technician_id=TECHNICIAN_USER_ID,
        ),
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )

    def generate_once(index: int) -> dict[str, object]:
        return service.generate(
            as_of_date=today,
            plan_id=UUID(plan["id"]),
            dry_run=False,
            actor=chief,
            audit_context=AuditContext(chief.id, chief.display_name, f"concurrent-{index}"),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        reports = list(executor.map(generate_once, range(2)))
    assert sum(report["generated_count"] for report in reports) == 1
    engine = build_engine(planning_context["database_url"])
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WorkOrder)) == 1
    engine.dispose()


@pytest.mark.postgres
def test_concurrent_manual_work_orders_receive_unique_numbers(
    planning_context: dict[str, object],
) -> None:
    service = planning_context["service"]
    assert isinstance(service, MaintenancePlanningService)
    chief = planning_context["chief"]
    today = planning_context["today"]

    def create_once(index: int) -> dict[str, object]:
        return service.create_work_order(
            {
                **_manual_work_order_request(
                    today=today, technician_id=TECHNICIAN_USER_ID
                ),
                "title": f"Kiểm tra đồng thời {index}",
            },
            actor=chief,
            audit_context=AuditContext(
                chief.id, chief.display_name, f"manual-concurrent-{index}"
            ),
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        work_orders = list(executor.map(create_once, range(4)))
    numbers = {item["work_order_number"] for item in work_orders}
    identifiers = {item["id"] for item in work_orders}
    assert len(numbers) == 4
    assert len(identifiers) == 4


@pytest.mark.postgres
def test_paused_plan_and_retired_asset_are_skipped_without_backlog_writes(
    planning_context: dict[str, object],
) -> None:
    service = planning_context["service"]
    assert isinstance(service, MaintenancePlanningService)
    chief = planning_context["chief"]
    today = planning_context["today"]
    plan = service.create_plan(
        _plan_request(
            today=today,
            template_id=None,
            technician_id=TECHNICIAN_USER_ID,
        ),
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    paused = service.pause_plan(
        UUID(plan["id"]),
        expected_version=plan["version"],
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    paused_report = service.generate(
        as_of_date=today + timedelta(days=60),
        plan_id=UUID(plan["id"]),
        dry_run=False,
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    assert paused_report["generated_count"] == 0
    resumed = service.resume_plan(
        UUID(plan["id"]),
        expected_version=paused["version"],
        resume_date=today + timedelta(days=60),
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    engine = build_engine(planning_context["database_url"])
    with Session(engine) as session, session.begin():
        asset = session.get(Asset, "GENERATOR_002")
        assert asset is not None
        asset.lifecycle_status = "retired"
        asset.retired_at = datetime.now(timezone.utc)
    retired_report = service.generate(
        as_of_date=date.fromisoformat(resumed["next_due_date"]),
        plan_id=UUID(plan["id"]),
        dry_run=False,
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    assert retired_report["generated_count"] == 0
    assert retired_report["plans"][0]["reason"] == "Asset retired hoặc archived."
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WorkOrder)) == 0
    engine.dispose()


def test_product_milestone_four_permission_matrix() -> None:
    assert Permission.MAINTENANCE_GENERATION_RUN in ROLE_PERMISSIONS[Role.CHIEF_ENGINEER]
    assert Permission.WORK_ORDERS_VERIFY in ROLE_PERMISSIONS[Role.PROPERTY_MANAGER]
    assert Permission.WORK_ORDERS_COMPLETE in ROLE_PERMISSIONS[Role.TECHNICIAN]
    assert Permission.WORK_ORDERS_VERIFY not in ROLE_PERMISSIONS[Role.TECHNICIAN]
    assert Permission.MAINTENANCE_PLANS_CREATE not in ROLE_PERMISSIONS[Role.HELPDESK]
    assert Permission.WORK_ORDERS_READ in ROLE_PERMISSIONS[Role.STOREKEEPER]


@pytest.mark.postgres
def test_work_order_state_machine_stale_versions_cancel_and_reopen(
    planning_context: dict[str, object],
) -> None:
    service = planning_context["service"]
    assert isinstance(service, MaintenancePlanningService)
    chief = planning_context["chief"]
    technician = planning_context["technician"]
    today = planning_context["today"]
    work_order = service.create_work_order(
        _manual_work_order_request(today=today, technician_id=None),
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    assert work_order["status"] == "planned"
    with pytest.raises(MaintenanceConflictError, match="planned -> in_progress"):
        service.transition_work_order(
            UUID(work_order["id"]),
            target_status="in_progress",
            hold_reason=None,
            expected_version=work_order["version"],
            actor=chief,
            audit_context=planning_context["chief_audit"],
        )

    assigned = service.assign_work_order(
        UUID(work_order["id"]),
        assigned_to_user_id=TECHNICIAN_USER_ID,
        expected_version=work_order["version"],
        audit_context=planning_context["chief_audit"],
    )
    with pytest.raises(StaleRecordError, match="đã thay đổi"):
        service.assign_work_order(
            UUID(work_order["id"]),
            assigned_to_user_id=TECHNICIAN_USER_ID,
            expected_version=work_order["version"],
            audit_context=planning_context["chief_audit"],
        )
    started = service.transition_work_order(
        UUID(assigned["id"]),
        target_status="in_progress",
        hold_reason=None,
        expected_version=assigned["version"],
        actor=technician,
        audit_context=planning_context["technician_audit"],
    )
    completed = service.complete_work_order(
        UUID(started["id"]),
        _completion_request(today),
        expected_version=started["version"],
        actor=technician,
        audit_context=planning_context["technician_audit"],
    )
    reopened = service.reopen_work_order(
        UUID(completed["id"]),
        expected_version=completed["version"],
        reason="Cần kiểm tra lại độ rung sau chạy thử.",
        audit_context=planning_context["chief_audit"],
    )
    assert reopened["status"] == "in_progress"
    assert reopened["maintenance_log_id"] == completed["maintenance_log_id"]
    recompleted = service.complete_work_order(
        UUID(reopened["id"]),
        _completion_request(today),
        expected_version=reopened["version"],
        actor=technician,
        audit_context=planning_context["technician_audit"],
    )
    assert recompleted["maintenance_log_id"] == completed["maintenance_log_id"]

    cancellable = service.create_work_order(
        {
            **_manual_work_order_request(today=today, technician_id=None),
            "title": "Kiểm tra trực quan có thể hủy",
        },
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    cancelled = service.cancel_work_order(
        UUID(cancellable["id"]),
        expected_version=cancellable["version"],
        cancellation_reason="Không còn yêu cầu kiểm tra tại kỳ này.",
        audit_context=planning_context["chief_audit"],
    )
    assert cancelled["status"] == "cancelled"
    with pytest.raises(MaintenanceConflictError):
        service.transition_work_order(
            UUID(cancelled["id"]),
            target_status="in_progress",
            hold_reason=None,
            expected_version=cancelled["version"],
            actor=chief,
            audit_context=planning_context["chief_audit"],
        )

    engine = build_engine(planning_context["database_url"])
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(MaintenanceLog)) == 1
    engine.dispose()


@pytest.mark.postgres
def test_plan_code_uniqueness_and_template_version_preservation(
    planning_context: dict[str, object],
) -> None:
    service = planning_context["service"]
    assert isinstance(service, MaintenancePlanningService)
    chief = planning_context["chief"]
    today = planning_context["today"]
    original = service.create_template(
        {
            "code": "GENERATOR_IMMUTABLE",
            "name": "Checklist máy phát",
            "asset_type": "generator",
            "description": None,
            "items": [
                {
                    "sequence": 1,
                    "instruction": "Kiểm tra mức nhiên liệu.",
                    "response_type": "pass_fail",
                    "is_required": True,
                    "safety_critical": False,
                    "allow_not_applicable": False,
                    "expected_unit": None,
                    "minimum_value": None,
                    "maximum_value": None,
                    "guidance": None,
                }
            ],
        },
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    versioned = service.version_template(
        UUID(original["id"]),
        {
            "name": "Checklist máy phát cập nhật",
            "items": [
                {
                    "sequence": 1,
                    "instruction": "Kiểm tra mức nhiên liệu và dấu hiệu rò rỉ.",
                    "response_type": "pass_fail",
                    "is_required": True,
                    "safety_critical": True,
                    "allow_not_applicable": False,
                    "expected_unit": None,
                    "minimum_value": None,
                    "maximum_value": None,
                    "guidance": None,
                }
            ],
        },
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    assert versioned["version_number"] == 2
    unchanged = service.get_template(UUID(original["id"]))
    assert unchanged["version_number"] == 1
    assert unchanged["items"][0]["instruction"] == "Kiểm tra mức nhiên liệu."

    request = _plan_request(
        today=today,
        template_id=UUID(original["id"]),
        technician_id=TECHNICIAN_USER_ID,
    )
    service.create_plan(
        request,
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    with pytest.raises(DuplicateIdentifierError, match="plan_code"):
        service.create_plan(
            request,
            actor=chief,
            audit_context=planning_context["chief_audit"],
        )


@pytest.mark.postgres
def test_work_order_evidence_security_and_soft_delete(
    planning_context: dict[str, object],
) -> None:
    service = planning_context["service"]
    repository = planning_context["repository"]
    assert isinstance(service, MaintenancePlanningService)
    assert isinstance(repository, PostgresMaintenancePlanningRepository)
    chief = planning_context["chief"]
    today = planning_context["today"]
    work_order = service.create_work_order(
        _manual_work_order_request(today=today, technician_id=TECHNICIAN_USER_ID),
        actor=chief,
        audit_context=planning_context["chief_audit"],
    )
    app = create_app()
    app.dependency_overrides[get_maintenance_planning_service] = lambda: service
    authorize_app(app, chief)
    client = TestClient(app)
    pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"
    uploaded = client.post(
        f"/work-orders/{work_order['id']}/attachments",
        data={"category": "inspection_document"},
        files={"file": ("inspection.pdf", pdf, "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    metadata = uploaded.json()
    assert metadata["checksum"]
    assert "storage_key" not in str(metadata)
    downloaded = client.get(
        f"/work-orders/{work_order['id']}/attachments/{metadata['id']}"
    )
    assert downloaded.status_code == 200
    assert downloaded.content == pdf
    assert downloaded.headers["x-content-type-options"] == "nosniff"

    traversal = client.post(
        f"/work-orders/{work_order['id']}/attachments",
        data={"category": "inspection_document"},
        files={"file": ("..\\secret.pdf", pdf, "application/pdf")},
    )
    assert traversal.status_code == 422
    unsafe = client.post(
        f"/work-orders/{work_order['id']}/attachments",
        data={"category": "inspection_document"},
        files={"file": ("payload.exe", b"MZ", "application/octet-stream")},
    )
    assert unsafe.status_code == 422

    authorize_app(app, build_test_user(Role.HELPDESK))
    assert TestClient(app).get(
        f"/work-orders/{work_order['id']}/attachments/{metadata['id']}"
    ).status_code == 403
    authorize_app(app, chief)
    deleted = client.delete(
        f"/work-orders/{work_order['id']}/attachments/{metadata['id']}"
    )
    assert deleted.status_code == 200
    assert client.get(
        f"/work-orders/{work_order['id']}/attachments/{metadata['id']}"
    ).status_code == 404

    engine = build_engine(planning_context["database_url"])
    with Session(engine) as session:
        attachment_audits = session.scalars(
            select(AuditLog).where(AuditLog.action.like("work_order.attachment_%"))
        ).all()
    engine.dispose()
    assert {row.action for row in attachment_audits} == {
        "work_order.attachment_uploaded",
        "work_order.attachment_deleted",
    }
    assert all("storage" not in str(row.after_state).lower() for row in attachment_audits)


def _plan_request(
    *, today: date, template_id: UUID | None, technician_id: UUID | None
) -> dict[str, object]:
    return {
        "plan_code": "PM-GENERATOR-001",
        "name": "Bảo trì máy phát hàng tháng",
        "description": "Kế hoạch preventive có kiểm soát.",
        "asset_id": "GENERATOR_002",
        "interval_value": 1,
        "interval_unit": "month",
        "start_date": today,
        "end_date": today + timedelta(days=365),
        "local_timezone": "Asia/Ho_Chi_Minh",
        "lead_time_days": 7,
        "grace_period_days": 1,
        "estimated_duration_minutes": 90,
        "default_priority": "high",
        "default_assignee_user_id": technician_id,
        "checklist_template_id": template_id,
        "instructions": "Kiểm tra an toàn trước khi khởi động.",
        "recurrence_rule": None,
    }


def _completion_request(today: date) -> dict[str, object]:
    return {
        "maintenance_date": today,
        "inspection_result": "Thiết bị đủ điều kiện kiểm tra và vận hành thử.",
        "actions_taken": "Vệ sinh, siết đầu nối và chạy thử có tải.",
        "parts_replaced": None,
        "technician_note": "Theo dõi độ rung trong lần vận hành tiếp theo.",
        "maintenance_result": "resolved",
        "follow_up_required": False,
        "completion_summary": "Hoàn thành checklist và chạy thử ổn định.",
        "safety_notes": "Đã áp dụng quy trình cô lập năng lượng.",
        "labor_minutes": 75,
    }


def _manual_work_order_request(
    *, today: date, technician_id: UUID | None
) -> dict[str, object]:
    return {
        "title": "Kiểm tra thủ công máy phát",
        "description": "Work order kiểm tra độc lập.",
        "work_order_type": "inspection",
        "asset_id": "GENERATOR_002",
        "preventive_plan_id": None,
        "source_ticket_id": None,
        "assigned_to_user_id": technician_id,
        "priority": "medium",
        "scheduled_start_at": None,
        "scheduled_end_at": None,
        "due_date": today,
        "local_timezone": "Asia/Ho_Chi_Minh",
        "grace_period_days": 0,
        "estimated_duration_minutes": 45,
        "checklist_template_id": None,
    }

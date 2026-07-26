"""PostgreSQL integration tests for PM5 ticket operations and SLA behavior."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from src.api.main import create_app
from src.api.routes import _service
from src.api.services import ProcessedDataService
from src.database.models import (
    Asset,
    MaintenanceLog,
    OutboxEvent,
    TicketComment,
    TicketEscalationEvent,
)
from src.database.session import build_engine, get_session_factory
from src.repositories.contracts import StaleRecordError
from src.repositories.postgres import PostgresMaintenanceRepository
from src.repositories.postgres_tickets import PostgresTicketRepository
from src.security.audit import AuditContext
from src.security.permissions import Role
from src.ticket_management.routes import get_ticket_workflow_service
from src.ticket_management.service import (
    TicketAuthorizationError,
    TicketWorkflowService,
)
from tests.auth_helpers import authorize_app, build_test_user, persist_test_user


@pytest.fixture
def ticket_context(clean_postgres_database: str) -> dict[str, object]:
    actors = {
        "admin": build_test_user(Role.ADMINISTRATOR),
        "manager": _actor(Role.PROPERTY_MANAGER, "33333333-3333-4333-8333-333333333333"),
        "helpdesk": _actor(Role.HELPDESK, "44444444-4444-4444-8444-444444444444"),
        "technician": _actor(
            Role.TECHNICIAN,
            "55555555-5555-4555-8555-555555555555",
            technician_id="TECH_002",
        ),
        "other_technician": _actor(
            Role.TECHNICIAN,
            "66666666-6666-4666-8666-666666666666",
            technician_id="TECH_003",
        ),
        "storekeeper": _actor(Role.STOREKEEPER, "77777777-7777-4777-8777-777777777777"),
    }
    session_factory = get_session_factory(clean_postgres_database)
    for actor in actors.values():
        persist_test_user(session_factory, actor)
    engine = build_engine(clean_postgres_database)
    with Session(engine) as session, session.begin():
        session.add(
            Asset(
                asset_id="GENERATOR_002",
                asset_name="Máy phát điện dự phòng 002",
                asset_type="generator",
                location="Sân thượng phía Đông",
                criticality="critical",
                status="warning",
                installation_date=date(2023, 1, 1),
                last_maintenance_date=date(2026, 7, 1),
                maintenance_interval_days=30,
                next_maintenance_date=date(2026, 7, 31),
            )
        )
    engine.dispose()
    repository = PostgresTicketRepository(session_factory)
    service = TicketWorkflowService(repository)
    admin = actors["admin"]
    service.seed_defaults(actor=admin, audit_context=_audit(admin, "seed"))
    return {
        "database_url": clean_postgres_database,
        "session_factory": session_factory,
        "repository": repository,
        "service": service,
        **actors,
    }


@pytest.mark.postgres
def test_intake_priority_snapshot_pii_and_resource_ownership(
    ticket_context: dict[str, object],
) -> None:
    service = _ticket_service(ticket_context)
    helpdesk = ticket_context["helpdesk"]
    technician = ticket_context["technician"]
    manager = ticket_context["manager"]
    other = ticket_context["other_technician"]
    assert not isinstance(helpdesk, str)
    created = service.intake(
        _intake_request(service, helpdesk, technician, impact="high", urgency="immediate"),
        actor=helpdesk,
        audit_context=_audit(helpdesk, "intake"),
        now=datetime(2026, 7, 20, 1, 0, tzinfo=timezone.utc),
    )

    assert created["priority"] == "critical"
    assert created["status"] == "assigned"
    assert created["sla"]["policy_code"] == "DEFAULT_FACILITY"
    assert created["sla"]["first_response"]["status"] == "due_soon"
    assert created["reporter_email"] == "requester@example.com"
    session_factory = ticket_context["session_factory"]
    with session_factory() as session:
        events = session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == created["ticket_id"]
            )
        ).all()
        assert {event.event_type for event in events} == {
            "ticket.critical_created",
            "ticket.assigned",
        }
        assert all("reporter_email" not in event.payload for event in events)

    technician_view = service.get_ticket(created["ticket_id"], actor=technician)
    assert technician_view["reporter_redacted"] is True
    assert technician_view["reporter_email"] is None
    manager_view = service.get_ticket(created["ticket_id"], actor=manager)
    assert manager_view["reporter_email"] == "requester@example.com"
    with pytest.raises(TicketAuthorizationError, match="không được phân công"):
        service.get_ticket(created["ticket_id"], actor=other)


@pytest.mark.postgres
def test_named_lifecycle_pause_resume_reopen_and_sla_events(
    ticket_context: dict[str, object],
) -> None:
    service = _ticket_service(ticket_context)
    helpdesk = ticket_context["helpdesk"]
    technician = ticket_context["technician"]
    manager = ticket_context["manager"]
    created_at = datetime(2026, 7, 20, 1, 0, tzinfo=timezone.utc)
    ticket = service.intake(
        _intake_request(service, helpdesk, technician),
        actor=helpdesk,
        audit_context=_audit(helpdesk, "intake-lifecycle"),
        now=created_at,
    )
    started = service.start(
        ticket["ticket_id"],
        expected_version=ticket["version"],
        actor=technician,
        audit_context=_audit(technician, "start"),
        now=created_at + timedelta(minutes=5),
    )
    held = service.hold(
        ticket["ticket_id"],
        reason="Chờ cô lập nguồn điện an toàn",
        expected_version=started["version"],
        actor=technician,
        audit_context=_audit(technician, "hold"),
        now=created_at + timedelta(minutes=30),
    )
    assert held["status"] == "waiting"
    assert held["sla"]["resolution"]["status"] == "paused"

    resumed_at = datetime(2026, 7, 21, 1, 0, tzinfo=timezone.utc)
    resumed = service.resume(
        ticket["ticket_id"],
        expected_version=held["version"],
        actor=technician,
        audit_context=_audit(technician, "resume"),
        now=resumed_at,
    )
    assert resumed["status"] == "in_progress"
    assert resumed["sla"]["resolution_due_at"] > held["sla"]["resolution_due_at"]
    session_factory = ticket_context["session_factory"]
    with session_factory() as session:
        assert {
            event.event_type
            for event in session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == ticket["ticket_id"]
                )
            )
        }.issuperset({"ticket.held", "ticket.resumed"})

    _insert_maintenance_log(ticket_context, ticket["ticket_id"], resumed_at.date())
    resolved = service.resolve(
        ticket["ticket_id"],
        expected_version=resumed["version"],
        actor=technician,
        audit_context=_audit(technician, "resolve"),
        resolved_at=resumed_at + timedelta(hours=1),
    )
    closed = service.close(
        ticket["ticket_id"],
        expected_version=resolved["version"],
        actor=manager,
        audit_context=_audit(manager, "close"),
        now=resumed_at + timedelta(hours=1, minutes=5),
    )
    reopened = service.reopen(
        ticket["ticket_id"],
        reason="Thiết bị tái xuất hiện rung động sau chạy thử",
        expected_version=closed["version"],
        actor=manager,
        audit_context=_audit(manager, "reopen"),
        now=resumed_at + timedelta(hours=1, minutes=10),
    )

    assert reopened["status"] == "reopened"
    assert reopened["resolved_at"] is None
    assert reopened["reopen_count"] == 1
    assert reopened["sla"]["occurrence_number"] == 2
    detail = service.get_ticket(ticket["ticket_id"], actor=manager)
    event_types = [event["event_type"] for event in detail["sla_events"]]
    assert {"paused", "resumed", "resolved", "reopened"}.issubset(event_types)


@pytest.mark.postgres
def test_multiple_waiting_intervals_extend_the_snapshotted_resolution_clock(
    ticket_context: dict[str, object],
) -> None:
    service = _ticket_service(ticket_context)
    helpdesk = ticket_context["helpdesk"]
    technician = ticket_context["technician"]
    created_at = datetime(2026, 7, 20, 1, 0, tzinfo=timezone.utc)
    ticket = service.intake(
        _intake_request(service, helpdesk, technician),
        actor=helpdesk,
        audit_context=_audit(helpdesk, "multi-pause-intake"),
        now=created_at,
    )
    started = service.start(
        ticket["ticket_id"],
        expected_version=ticket["version"],
        actor=technician,
        audit_context=_audit(technician, "multi-pause-start"),
        now=created_at + timedelta(minutes=5),
    )
    initial_due_at = started["sla"]["resolution_due_at"]

    first_hold = service.hold(
        ticket["ticket_id"],
        reason="Chờ cô lập nguồn điện lần một.",
        expected_version=started["version"],
        actor=technician,
        audit_context=_audit(technician, "multi-pause-hold-one"),
        now=created_at + timedelta(minutes=30),
    )
    first_resume = service.resume(
        ticket["ticket_id"],
        expected_version=first_hold["version"],
        actor=technician,
        audit_context=_audit(technician, "multi-pause-resume-one"),
        now=datetime(2026, 7, 21, 1, 0, tzinfo=timezone.utc),
    )
    first_resumed_due_at = first_resume["sla"]["resolution_due_at"]

    second_hold = service.hold(
        ticket["ticket_id"],
        reason="Chờ giấy phép chạy thử lần hai.",
        expected_version=first_resume["version"],
        actor=technician,
        audit_context=_audit(technician, "multi-pause-hold-two"),
        now=datetime(2026, 7, 21, 2, 0, tzinfo=timezone.utc),
    )
    second_resume = service.resume(
        ticket["ticket_id"],
        expected_version=second_hold["version"],
        actor=technician,
        audit_context=_audit(technician, "multi-pause-resume-two"),
        now=datetime(2026, 7, 22, 1, 0, tzinfo=timezone.utc),
    )

    assert first_resumed_due_at > initial_due_at
    assert second_resume["sla"]["resolution_due_at"] > first_resumed_due_at
    assert second_resume["sla"]["resolution_due_at"] == "2026-07-22T03:30:00+00:00"
    detail = service.get_ticket(ticket["ticket_id"], actor=technician)
    event_types = [event["event_type"] for event in detail["sla_events"]]
    assert event_types.count("paused") == 2
    assert event_types.count("resumed") == 2


@pytest.mark.postgres
def test_comment_visibility_and_append_only_database_guard(
    ticket_context: dict[str, object],
) -> None:
    service = _ticket_service(ticket_context)
    helpdesk = ticket_context["helpdesk"]
    technician = ticket_context["technician"]
    storekeeper = ticket_context["storekeeper"]
    created = service.intake(
        _intake_request(service, helpdesk, technician),
        actor=helpdesk,
        audit_context=_audit(helpdesk, "comment-intake"),
    )
    internal = service.add_comment(
        created["ticket_id"],
        {"visibility": "internal", "body": "Đã kiểm tra an toàn khu vực."},
        actor=technician,
        audit_context=_audit(technician, "internal-comment"),
    )
    service.add_comment(
        created["ticket_id"],
        {"visibility": "requester", "body": "Kỹ thuật viên đã tiếp nhận yêu cầu."},
        actor=helpdesk,
        audit_context=_audit(helpdesk, "requester-comment"),
    )

    technician_view = service.get_ticket(created["ticket_id"], actor=technician)
    storekeeper_view = service.get_ticket(created["ticket_id"], actor=storekeeper)
    assert len(technician_view["comments"]) == 2
    assert [item["visibility"] for item in storekeeper_view["comments"]] == ["requester"]

    engine = build_engine(ticket_context["database_url"])
    with Session(engine) as session:
        with pytest.raises(DBAPIError, match="append-only"):
            session.execute(
                update(TicketComment)
                .where(TicketComment.id == UUID(internal["id"]))
                .values(body="Không được sửa")
            )
            session.commit()
        session.rollback()
    engine.dispose()


@pytest.mark.postgres
def test_policy_edit_does_not_rewrite_existing_ticket_sla_snapshot(
    ticket_context: dict[str, object],
) -> None:
    service = _ticket_service(ticket_context)
    helpdesk = ticket_context["helpdesk"]
    technician = ticket_context["technician"]
    admin = ticket_context["admin"]
    created_at = datetime(2026, 7, 20, 1, 0, tzinfo=timezone.utc)
    existing = service.intake(
        _intake_request(service, helpdesk, technician),
        actor=helpdesk,
        audit_context=_audit(helpdesk, "policy-snapshot-existing"),
        now=created_at,
    )
    original_due_at = existing["sla"]["resolution_due_at"]
    original_target = existing["sla"]["resolution_target_minutes"]

    policy = service.list_policies(actor=admin)[0]
    updated_targets = [
        {
            **target,
            "resolution_minutes": (
                300 if target["priority"] == "high" else target["resolution_minutes"]
            ),
        }
        for target in policy["targets"]
    ]
    updated_policy = service.update_policy(
        UUID(policy["id"]),
        {
            "code": policy["code"],
            "name": policy["name"],
            "calendar_id": policy["calendar_id"],
            "category_id": policy["category_id"],
            "timezone": policy["timezone"],
            "pause_on_waiting": policy["pause_on_waiting"],
            "due_soon_percent": policy["due_soon_percent"],
            "effective_from": policy["effective_from"],
            "effective_to": policy["effective_to"],
            "is_active": policy["is_active"],
            "targets": updated_targets,
        },
        expected_version=policy["version"],
        actor=admin,
        audit_context=_audit(admin, "policy-snapshot-update"),
    )
    assert updated_policy["version"] == policy["version"] + 1

    unchanged = service.get_ticket(existing["ticket_id"], actor=admin)
    assert unchanged["sla"]["resolution_target_minutes"] == original_target == 240
    assert unchanged["sla"]["resolution_due_at"] == original_due_at

    later = service.intake(
        _intake_request(service, helpdesk, technician),
        actor=helpdesk,
        audit_context=_audit(helpdesk, "policy-snapshot-later"),
        now=created_at,
    )
    assert later["sla"]["resolution_target_minutes"] == 300
    assert later["sla"]["resolution_due_at"] > original_due_at


@pytest.mark.postgres
def test_policy_snapshot_stale_version_and_idempotent_concurrent_escalation(
    ticket_context: dict[str, object],
) -> None:
    service = _ticket_service(ticket_context)
    helpdesk = ticket_context["helpdesk"]
    technician = ticket_context["technician"]
    other_technician = ticket_context["other_technician"]
    manager = ticket_context["manager"]
    created_at = datetime(2026, 7, 20, 1, 0, tzinfo=timezone.utc)
    ticket = service.intake(
        _intake_request(
            service,
            helpdesk,
            technician,
            impact="critical",
            urgency="immediate",
        ),
        actor=helpdesk,
        audit_context=_audit(helpdesk, "escalation-intake"),
        now=created_at,
    )
    assigned = service.assign(
        ticket["ticket_id"],
        assigned_user_id=other_technician.id,
        support_group_id=UUID(ticket["support_group_id"]),
        expected_version=ticket["version"],
        actor=manager,
        audit_context=_audit(manager, "assign-once"),
    )
    with pytest.raises(StaleRecordError):
        service.assign(
            ticket["ticket_id"],
            assigned_user_id=technician.id,
            support_group_id=UUID(ticket["support_group_id"]),
            expected_version=ticket["version"],
            actor=manager,
            audit_context=_audit(manager, "assign-stale"),
        )
    assert assigned["sla"]["first_response_target_minutes"] == 15

    def evaluate(index: int) -> int:
        result = service.evaluate_escalations(
            dry_run=False,
            actor=manager,
            audit_context=_audit(manager, f"escalate-{index}"),
            as_of=created_at + timedelta(minutes=1),
        )
        return int(result["created_count"])

    with ThreadPoolExecutor(max_workers=4) as executor:
        created_counts = list(executor.map(evaluate, range(4)))
    second = service.evaluate_escalations(
        dry_run=False,
        actor=manager,
        audit_context=_audit(manager, "escalate-again"),
        as_of=created_at + timedelta(minutes=1),
    )

    assert sum(created_counts) == 2
    assert second["created_count"] == 0
    engine = build_engine(ticket_context["database_url"])
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(TicketEscalationEvent)) == 2
    engine.dispose()


@pytest.mark.postgres
def test_legacy_ticket_api_contract_uses_pm5_service(
    ticket_context: dict[str, object],
) -> None:
    workflow = _ticket_service(ticket_context)
    repository = PostgresMaintenanceRepository(ticket_context["session_factory"])
    processed = ProcessedDataService(repository=repository, ticket_workflow=workflow)
    app = create_app()
    app.dependency_overrides[_service] = lambda: processed
    app.dependency_overrides[get_ticket_workflow_service] = lambda: workflow
    admin = ticket_context["admin"]
    authorize_app(app, admin)
    client = TestClient(app)

    response = client.post(
        "/tickets",
        json={
            "asset_id": "GENERATOR_002",
            "issue_description": "Kiểm tra cảnh báo điện áp máy phát.",
            "priority": "Cao",
            "failure_category": "Lỗi điện",
            "technician_id": "UNASSIGNED",
            "manager_note": "Tạo từ contract legacy.",
        },
    )

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
    assert response.json()["priority"] == "Cao"
    assert client.get("/tickets").status_code == 200


@pytest.mark.postgres
def test_typed_ticket_api_intake_queue_actions_comments_and_stale_conflict(
    ticket_context: dict[str, object],
) -> None:
    workflow = _ticket_service(ticket_context)
    repository = PostgresMaintenanceRepository(ticket_context["session_factory"])
    processed = ProcessedDataService(repository=repository, ticket_workflow=workflow)
    app = create_app()
    app.dependency_overrides[_service] = lambda: processed
    app.dependency_overrides[get_ticket_workflow_service] = lambda: workflow
    helpdesk = ticket_context["helpdesk"]
    technician = ticket_context["technician"]
    authorize_app(app, helpdesk)
    client = TestClient(app)

    preview = client.get(
        "/ticketing/priority-preview",
        params={"impact": "high", "urgency": "high"},
    )
    assert preview.status_code == 200
    assert preview.json()["priority"] == "high"

    intake = client.post(
        "/tickets/intake",
        json=_intake_request(workflow, helpdesk, technician),
    )
    assert intake.status_code == 201
    created = intake.json()
    assert created["status"] == "assigned"
    assert created["priority"] == "high"

    authorize_app(app, technician)
    queue = client.get(
        "/ticket-queues/assigned_to_me",
        params={"priority": "high", "search": "điện áp", "page": 1, "page_size": 10},
    )
    assert queue.status_code == 200
    assert queue.json()["total"] == 1
    assert queue.json()["items"][0]["ticket_id"] == created["ticket_id"]

    acknowledged = client.post(
        f"/tickets/{created['ticket_id']}/acknowledge",
        json={"expected_version": created["version"]},
    )
    assert acknowledged.status_code == 200
    acknowledged_ticket = acknowledged.json()
    assert acknowledged_ticket["first_response_at"] is not None

    stale = client.post(
        f"/tickets/{created['ticket_id']}/start",
        json={"expected_version": created["version"]},
    )
    assert stale.status_code == 409

    started = client.post(
        f"/tickets/{created['ticket_id']}/start",
        json={"expected_version": acknowledged_ticket["version"]},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"

    comment = client.post(
        f"/tickets/{created['ticket_id']}/comments",
        json={
            "visibility": "internal",
            "body": "Đã xác nhận phạm vi kiểm tra và biện pháp an toàn.",
        },
    )
    assert comment.status_code == 201
    assert comment.json()["author_user_id"] == str(technician.id)


def _ticket_service(context: dict[str, object]) -> TicketWorkflowService:
    service = context["service"]
    assert isinstance(service, TicketWorkflowService)
    return service


def _intake_request(
    service: TicketWorkflowService,
    actor,
    technician,
    *,
    impact: str = "high",
    urgency: str = "high",
) -> dict[str, object]:
    options = service.options(actor=actor)
    category = next(item for item in options["categories"] if item["code"] == "general")
    subcategory = next(
        item for item in options["subcategories"] if item["category_id"] == category["id"]
    )
    source = next(item for item in options["intake_sources"] if item["code"] == "web")
    group = next(item for item in options["support_groups"] if item["code"] == "ENGINEERING")
    return {
        "asset_id": "GENERATOR_002",
        "issue_description": "Máy phát có dấu hiệu điện áp không ổn định khi chạy thử.",
        "failure_category": "electrical_issue",
        "reporter_name": "Nguyễn Văn A",
        "reporter_email": "requester@example.com",
        "reporter_phone": "0900000000",
        "category_id": category["id"],
        "subcategory_id": subcategory["id"],
        "impact": impact,
        "urgency": urgency,
        "intake_source_id": source["id"],
        "support_group_id": group["id"],
        "assigned_user_id": str(technician.id),
        "manager_note": "Ưu tiên kiểm tra trong ca làm việc.",
    }


def _insert_maintenance_log(
    context: dict[str, object], ticket_id: str, maintenance_date: date
) -> None:
    engine = build_engine(context["database_url"])
    with Session(engine) as session, session.begin():
        session.add(
            MaintenanceLog(
                log_id="LOG-000001",
                ticket_id=ticket_id,
                asset_id="GENERATOR_002",
                maintenance_date=maintenance_date,
                maintenance_type="corrective",
                technician_id="TECH_002",
                inspection_result="Đã kiểm tra điện áp và đầu nối.",
                actions_taken="Siết đầu nối và chạy thử có tải.",
                parts_replaced=None,
                technician_note="Thông số ổn định sau xử lý.",
                maintenance_result="resolved",
                follow_up_required=False,
                next_maintenance_date=maintenance_date + timedelta(days=30),
            )
        )
    engine.dispose()


def _actor(role: Role, identifier: str, *, technician_id: str | None = None):
    base = build_test_user(role, technician_id=technician_id)
    suffix = role.value.replace("_", ".")
    return replace(
        base,
        id=UUID(identifier),
        username=f"{suffix}.{identifier[:8]}.ticket",
        display_name=f"{role.value} ticket",
        session_id=UUID(identifier),
    )


def _audit(actor, request_id: str) -> AuditContext:
    return AuditContext(actor.id, actor.display_name, request_id)

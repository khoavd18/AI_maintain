"""PostgreSQL integration tests for PM7 claims, outbox, and notifications."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from src.api.main import create_app
from src.config.settings import Settings
from src.database.models import (
    Notification,
    NotificationAlertState,
    OutboxDeliveryAttempt,
    OutboxEvent,
)
from src.database.session import get_session_factory
from src.operations.jobs import JobRunner
from src.operations.outbox import enqueue_outbox_event
from src.operations.service import OperationsService, build_operations_service
from src.repositories.contracts import IntegrityViolationError, RecordNotFoundError
from src.repositories.postgres_operations import PostgresOperationsRepository
from src.security.audit import AuditContext
from src.security.permissions import Role
from tests.auth_helpers import authorize_app, build_test_user, persist_test_user

pytestmark = pytest.mark.postgres


def _context(actor, suffix: str = "pm7") -> AuditContext:
    return AuditContext(
        actor_user_id=actor.id,
        actor_display_name=actor.display_name,
        request_id=f"test-{suffix}",
    )


def _actor(role: Role, identifier: int):
    base = build_test_user(
        role,
        technician_id=f"TECH-{identifier:03d}" if role is Role.TECHNICIAN else None,
    )
    return replace(
        base,
        id=UUID(f"00000000-0000-4000-8000-{identifier:012d}"),
        username=f"{role.value}.{identifier}",
        display_name=f"{role.value} {identifier}",
    )


def test_concurrent_workers_claim_once_and_failure_reaches_dead_letter(
    clean_postgres_database: str,
) -> None:
    session_factory = get_session_factory(clean_postgres_database)
    actor = _actor(Role.ADMINISTRATOR, 1)
    persist_test_user(session_factory, actor)
    repository = PostgresOperationsRepository(session_factory)
    execution, created = repository.trigger_job(
        "sla_escalation",
        idempotency_key="claim-once",
        actor=actor,
        audit_context=_context(actor),
    )
    assert created is True
    replay, replay_created = repository.trigger_job(
        "sla_escalation",
        idempotency_key="claim-once",
        actor=actor,
        audit_context=_context(actor),
    )
    assert replay_created is False
    assert replay["id"] == execution["id"]

    barrier = threading.Barrier(2)

    def claim(worker: str):
        barrier.wait()
        return repository.claim_execution(worker_identity=worker)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("worker-a", "worker-b")))
    claimed = [item for item in results if item is not None]
    assert len(claimed) == 1
    assert claimed[0]["id"] == execution["id"]

    current = datetime.now(timezone.utc)
    failed = repository.fail_execution(
        UUID(execution["id"]),
        worker_identity=claimed[0]["worker_identity"],
        error_code="test_failure",
        error_summary="Bounded test failure.",
        now=current,
    )
    assert failed["status"] == "retry_scheduled"

    while failed["status"] != "dead_lettered":
        claim_at = datetime.fromisoformat(failed["available_after"]) + timedelta(
            seconds=1
        )
        next_claim = repository.claim_execution(
            worker_identity="worker-retry", now=claim_at
        )
        assert next_claim is not None
        failed = repository.fail_execution(
            UUID(execution["id"]),
            worker_identity="worker-retry",
            error_code="test_failure",
            error_summary="Bounded test failure.",
            now=claim_at,
        )
    assert failed["attempt_number"] == 3
    assert failed["safe_error_summary"] == "Bounded test failure."


def test_disabled_schedule_overlap_and_expired_lease_recovery(
    clean_postgres_database: str,
) -> None:
    session_factory = get_session_factory(clean_postgres_database)
    actor = _actor(Role.ADMINISTRATOR, 2)
    persist_test_user(session_factory, actor)
    repository = PostgresOperationsRepository(session_factory)
    now = datetime.now(timezone.utc)

    assert repository.materialize_due_jobs(now=now + timedelta(days=1)) == {
        "created_count": 0,
        "skipped_count": 0,
    }
    job = next(
        item
        for item in repository.list_jobs()
        if item["job_key"] == "analytics_refresh"
    )
    repository.set_job_enabled(
        "analytics_refresh",
        enabled=True,
        expected_version=job["version"],
        actor=actor,
        audit_context=_context(actor, "enable"),
    )
    repository.trigger_job(
        "analytics_refresh",
        idempotency_key="active-analytics",
        actor=actor,
        audit_context=_context(actor, "manual"),
        now=now,
    )
    materialized = repository.materialize_due_jobs(now=now + timedelta(seconds=1))
    assert materialized["created_count"] == 0
    assert materialized["skipped_count"] == 1

    claimed = repository.claim_execution(worker_identity="lease-worker", now=now)
    assert claimed is not None
    recovered = repository.recover_expired_execution_leases(
        now=now + timedelta(hours=2)
    )
    assert recovered == 1
    execution_page = repository.list_executions(
        status="retry_scheduled",
        job_key="analytics_refresh",
        page=1,
        page_size=10,
    )
    assert execution_page["total"] == 1


def test_outbox_is_atomic_idempotent_claimed_once_and_recipient_isolated(
    clean_postgres_database: str,
) -> None:
    session_factory = get_session_factory(clean_postgres_database)
    admin = _actor(Role.ADMINISTRATOR, 3)
    chief = _actor(Role.CHIEF_ENGINEER, 4)
    technician = _actor(Role.TECHNICIAN, 5)
    for actor in (admin, chief, technician):
        persist_test_user(session_factory, actor)
    repository = PostgresOperationsRepository(session_factory)

    with session_factory() as session, session.begin():
        first_id, created = enqueue_outbox_event(
            session,
            event_type="ticket.assigned",
            aggregate_type="ticket",
            aggregate_id="TKT-PM7-001",
            payload={
                "ticket_id": "TKT-PM7-001",
                "asset_id": "GENERATOR_002",
                "assigned_user_id": str(technician.id),
            },
            idempotency_key="ticket-assigned-pm7-001",
        )
        duplicate_id, duplicate_created = enqueue_outbox_event(
            session,
            event_type="ticket.assigned",
            aggregate_type="ticket",
            aggregate_id="TKT-PM7-001",
            payload={
                "ticket_id": "TKT-PM7-001",
                "asset_id": "GENERATOR_002",
                "assigned_user_id": str(technician.id),
            },
            idempotency_key="ticket-assigned-pm7-001",
        )
    assert first_id == duplicate_id
    assert created is True
    assert duplicate_created is False

    with pytest.raises(RuntimeError, match="force rollback"):
        with session_factory() as session, session.begin():
            enqueue_outbox_event(
                session,
                event_type="ticket.critical_created",
                aggregate_type="ticket",
                aggregate_id="TKT-ROLLBACK",
                payload={
                    "ticket_id": "TKT-ROLLBACK",
                    "asset_id": "GENERATOR_002",
                    "priority": "critical",
                },
                idempotency_key="rollback-event",
            )
            raise RuntimeError("force rollback")
    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.idempotency_key == "rollback-event")
            )
            == 0
        )

    barrier = threading.Barrier(2)

    def claim(worker: str):
        barrier.wait()
        return repository.claim_outbox_event(
            worker_identity=worker, lease_seconds=60
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ("outbox-a", "outbox-b")))
    claimed = [item for item in claims if item is not None]
    assert len(claimed) == 1
    delivered = repository.deliver_outbox_event(
        first_id, worker_identity=claimed[0]["lease_owner"]
    )
    assert delivered == {
        "recipient_count": 1,
        "created_notification_count": 1,
    }
    assert repository.unread_notification_count(technician.id) == 1
    assert repository.unread_notification_count(admin.id) == 0

    page = repository.list_notifications(
        recipient_user_id=technician.id,
        unread_only=True,
        severity=None,
        page=1,
        page_size=10,
    )
    notification = page["items"][0]
    updated = repository.mutate_notification(
        UUID(notification["id"]),
        recipient_user_id=technician.id,
        action="read",
        expected_version=notification["version"],
    )
    assert updated["read_at"] is not None
    with pytest.raises(RecordNotFoundError):
        repository.mutate_notification(
            UUID(notification["id"]),
            recipient_user_id=admin.id,
            action="dismiss",
            expected_version=updated["version"],
        )

    with session_factory() as session:
        attempt = session.scalar(select(OutboxDeliveryAttempt))
        assert attempt is not None
        with pytest.raises(DBAPIError, match="append-only"):
            with session.begin_nested():
                session.execute(
                    text(
                        "UPDATE outbox_delivery_attempts "
                        "SET status = 'failed' WHERE id = :attempt_id"
                    ),
                    {"attempt_id": attempt.id},
                )

    with session_factory() as session, session.begin():
        critical_id, _ = enqueue_outbox_event(
            session,
            event_type="ticket.critical_created",
            aggregate_type="ticket",
            aggregate_id="TKT-PM7-CRITICAL",
            payload={
                "ticket_id": "TKT-PM7-CRITICAL",
                "asset_id": "GENERATOR_002",
                "priority": "critical",
            },
            idempotency_key="ticket-critical-role-recipients",
        )
    role_event = repository.claim_outbox_event(
        worker_identity="role-resolver",
        lease_seconds=60,
    )
    assert role_event is not None
    assert role_event["id"] == str(critical_id)
    role_delivery = repository.deliver_outbox_event(
        critical_id,
        worker_identity="role-resolver",
    )
    assert role_delivery == {
        "recipient_count": 2,
        "created_notification_count": 2,
    }
    assert repository.unread_notification_count(admin.id) == 1
    assert repository.unread_notification_count(chief.id) == 1
    assert repository.unread_notification_count(technician.id) == 0


def test_outbox_failure_retries_then_dead_letters(
    clean_postgres_database: str,
) -> None:
    session_factory = get_session_factory(clean_postgres_database)
    repository = PostgresOperationsRepository(session_factory)
    now = datetime.now(timezone.utc)
    event_id = uuid4()
    with session_factory() as session, session.begin():
        session.add(
            OutboxEvent(
                id=event_id,
                event_type="unsupported.event",
                aggregate_type="test",
                aggregate_id="TEST-1",
                payload={},
                payload_hash="0" * 64,
                created_at=now,
                available_after=now,
                status="pending",
                attempt_count=0,
                idempotency_key="unsupported-event",
                updated_at=now,
                version=1,
            )
        )

    status_value = "pending"
    claim_at = now
    for attempt in range(1, 6):
        claimed = repository.claim_outbox_event(
            worker_identity="failing-outbox",
            lease_seconds=60,
            now=claim_at,
        )
        assert claimed is not None
        with pytest.raises(IntegrityViolationError, match="Unsupported"):
            repository.deliver_outbox_event(
                event_id,
                worker_identity="failing-outbox",
                now=claim_at,
            )
        failed = repository.fail_outbox_event(
            event_id,
            worker_identity="failing-outbox",
            error_code="unsupported_event",
            error_summary="Unsupported event catalog entry.",
            now=claim_at,
        )
        status_value = failed["status"]
        if attempt < 5:
            assert status_value == "retry_scheduled"
            claim_at = datetime.fromisoformat(failed["available_after"]) + timedelta(
                seconds=1
            )
    assert status_value == "dead_lettered"
    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(OutboxDeliveryAttempt)
            )
            == 5
        )


def test_low_stock_alert_requires_recovery_before_new_cycle(
    clean_postgres_database: str,
) -> None:
    repository = PostgresOperationsRepository(
        get_session_factory(clean_postgres_database)
    )
    item = {
        "part_id": str(uuid4()),
        "part_number": "FILTER-PM7",
        "stock_location_id": str(uuid4()),
        "stock_location_code": "MAIN",
        "available_quantity": "2",
        "reorder_point": "5",
        "stock_state": "low_stock",
    }
    key = f"{item['part_id']}:{item['stock_location_id']}"
    first = repository.record_low_stock_cycles(
        low_stock_items=[item],
        observed_entity_keys={key},
        execution_id=uuid4(),
    )
    duplicate = repository.record_low_stock_cycles(
        low_stock_items=[item],
        observed_entity_keys={key},
        execution_id=uuid4(),
    )
    recovered = repository.record_low_stock_cycles(
        low_stock_items=[],
        observed_entity_keys={key},
        execution_id=uuid4(),
    )
    second = repository.record_low_stock_cycles(
        low_stock_items=[item],
        observed_entity_keys={key},
        execution_id=uuid4(),
    )

    assert first["alert_candidate_count"] == 1
    assert duplicate["alert_candidate_count"] == 0
    assert recovered["recovered_count"] == 1
    assert second["alert_candidate_count"] == 1
    session_factory = get_session_factory(clean_postgres_database)
    with session_factory() as session:
        state = session.scalar(select(NotificationAlertState))
        assert state is not None
        assert state.cycle_number == 2
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 2


def test_notification_api_enforces_current_user_ownership(
    clean_postgres_database: str,
) -> None:
    session_factory = get_session_factory(clean_postgres_database)
    admin = _actor(Role.ADMINISTRATOR, 6)
    technician = _actor(Role.TECHNICIAN, 7)
    persist_test_user(session_factory, admin)
    persist_test_user(session_factory, technician)
    now = datetime.now(timezone.utc)
    notification_id = uuid4()
    with session_factory() as session, session.begin():
        session.add(
            Notification(
                id=notification_id,
                recipient_user_id=technician.id,
                notification_type="ticket.assigned",
                title="Ticket được phân công",
                body="Ticket TKT-PM7 thuộc về kỹ thuật viên.",
                structured_content={"ticket_id": "TKT-PM7"},
                severity="info",
                related_entity_type="ticket",
                related_entity_id="TKT-PM7",
                created_at=now,
                deduplication_key="api-isolation",
                version=1,
            )
        )
    service = OperationsService(
        PostgresOperationsRepository(session_factory),
        worker_stale_seconds=60,
    )
    app = create_app()
    authorize_app(app, admin)
    app.dependency_overrides[build_operations_service] = lambda: service
    client = TestClient(app)

    assert client.get("/notifications").json()["total"] == 0
    response = client.post(
        f"/notifications/{notification_id}/read",
        json={"expected_version": 1},
    )
    assert response.status_code == 404


def test_worker_heartbeat_and_operator_api_rbac(
    clean_postgres_database: str,
) -> None:
    session_factory = get_session_factory(clean_postgres_database)
    admin = _actor(Role.ADMINISTRATOR, 8)
    technician = _actor(Role.TECHNICIAN, 9)
    persist_test_user(session_factory, admin)
    persist_test_user(session_factory, technician)
    repository = PostgresOperationsRepository(session_factory)
    now = datetime.now(timezone.utc)
    repository.heartbeat(
        worker_identity="pm7-test-worker",
        started_at=now,
        status="ready",
        current_execution_id=None,
        metadata={"catalog_version": "pm7"},
        now=now,
    )
    repository.heartbeat(
        worker_identity="pm7-stopping-worker",
        started_at=now,
        status="stopping",
        current_execution_id=None,
        now=now + timedelta(seconds=1),
    )
    assert repository.worker_health(
        stale_after_seconds=60,
        now=now + timedelta(seconds=5),
    ) == {
        "status": "ready",
        "ready": True,
        "worker_identity": "pm7-test-worker",
        "last_seen_at": now.isoformat(),
        "age_seconds": 5,
    }

    service = OperationsService(repository, worker_stale_seconds=60)
    admin_app = create_app()
    authorize_app(admin_app, admin)
    admin_app.dependency_overrides[build_operations_service] = lambda: service
    admin_client = TestClient(admin_app)
    assert admin_client.get("/operations/jobs").status_code == 200
    assert admin_client.get("/health/ready").json()["worker_ready"] is True

    technician_app = create_app()
    authorize_app(technician_app, technician)
    technician_app.dependency_overrides[build_operations_service] = lambda: service
    assert TestClient(technician_app).get("/operations/jobs").status_code == 403


def test_analytics_refresh_uses_isolated_output_and_preserves_canonical_files(
    clean_postgres_database: str,
    tmp_path: Path,
) -> None:
    from src.ingestion.load_data import import_csv_dataset

    import_csv_dataset(database_url=clean_postgres_database)
    canonical_paths = sorted(Path("data/processed").glob("*.csv"))
    before = {path: path.read_bytes() for path in canonical_paths}
    settings = Settings(
        _env_file=None,
        app_environment="test",
        token_signing_secret="test-secret-at-least-thirty-two-characters",
        database_url=clean_postgres_database,
        analytics_source_dir=Path("data/raw"),
        analytics_processed_dir=tmp_path / "processed",
    )
    repository = PostgresOperationsRepository(
        get_session_factory(clean_postgres_database)
    )
    result = JobRunner(
        settings=settings,
        operations_repository=repository,
    )._analytics_refresh()

    assert result["input_counts"]["assets"] == 27
    assert result["output_counts"]["risk_scores"] > 0
    assert sorted(path.name for path in (tmp_path / "processed").glob("*.csv"))
    assert {path: path.read_bytes() for path in canonical_paths} == before

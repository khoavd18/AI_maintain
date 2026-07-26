"""PostgreSQL-only PM8 contention, redrive, and alert-cycle validation."""

from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, TimeoutError as PoolTimeout

from src.config.settings import get_settings
from src.database.migrations import downgrade_database, upgrade_database
from src.database.models import (
    Notification,
    OutboxDeliveryAttempt,
    OutboxEvent,
    OutboxRedriveRequest,
    ReliabilityValidationRecord,
)
from src.database.session import build_engine, clear_database_caches, get_session_factory
from src.operations.outbox import enqueue_outbox_event
from src.repositories.postgres_operations import PostgresOperationsRepository
from src.security.audit import AuditContext
from src.security.permissions import Role, permissions_for_role
from src.security.service import CurrentUser
from tests.auth_helpers import persist_test_user

pytestmark = pytest.mark.postgres


def _actor(role: Role, seed: int) -> CurrentUser:
    now = datetime.now(timezone.utc)
    return CurrentUser(
        id=UUID(int=seed),
        username=f"pm8-{role.value}-{seed}",
        email=f"pm8-{seed}@example.test",
        display_name=f"PM8 {role.value}",
        role=role,
        permissions=permissions_for_role(role),
        technician_id=f"PM8-{seed}" if role == Role.TECHNICIAN else None,
        is_active=True,
        version=1,
        session_id=uuid4(),
        created_at=now,
        updated_at=now,
        last_login_at=None,
    )


def _audit(actor: CurrentUser) -> AuditContext:
    return AuditContext(
        actor_user_id=actor.id,
        actor_display_name=actor.display_name,
        request_id=f"pm8-{uuid4()}",
    )


def test_pool_exhaustion_and_statement_timeout_are_bounded(
    clean_postgres_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_POOL_SIZE", "1")
    monkeypatch.setenv("DATABASE_MAX_OVERFLOW", "0")
    monkeypatch.setenv("DATABASE_POOL_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("DATABASE_STATEMENT_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()
    clear_database_caches()
    engine = build_engine(clean_postgres_database)
    first = engine.connect()
    started = time.monotonic()
    try:
        with pytest.raises(PoolTimeout):
            engine.connect()
        assert time.monotonic() - started < 2.5
    finally:
        first.close()
        engine.dispose()

    engine = build_engine(clean_postgres_database)
    try:
        with engine.connect() as connection:
            started = time.monotonic()
            with pytest.raises(DBAPIError):
                connection.execute(text("SELECT pg_sleep(2)"))
            assert time.monotonic() - started < 2.5
    finally:
        engine.dispose()
        get_settings.cache_clear()
        clear_database_caches()


def test_advisory_lock_visibility_is_non_blocking(
    clean_postgres_database: str,
) -> None:
    engine = build_engine(clean_postgres_database)
    try:
        with engine.connect() as first, engine.connect() as second:
            assert first.scalar(text("SELECT pg_try_advisory_lock(827001)")) is True
            assert second.scalar(text("SELECT pg_try_advisory_lock(827001)")) is False
            assert first.scalar(text("SELECT pg_advisory_unlock(827001)")) is True
    finally:
        engine.dispose()


def test_transaction_visibility_lock_timeout_and_deadlock_are_bounded(
    clean_postgres_database: str,
) -> None:
    engine = build_engine(clean_postgres_database)
    try:
        first = engine.connect()
        second = engine.connect()
        first_transaction = first.begin()
        try:
            first.execute(
                text(
                    "UPDATE scheduled_jobs SET enabled = true "
                    "WHERE job_key = 'sla_escalation'"
                )
            )
            assert (
                second.scalar(
                    text(
                        "SELECT enabled FROM scheduled_jobs "
                        "WHERE job_key = 'sla_escalation'"
                    )
                )
                is False
            )
            second.rollback()
            second_transaction = second.begin()
            second.execute(text("SET LOCAL lock_timeout = '500ms'"))
            started = time.monotonic()
            with pytest.raises(DBAPIError):
                second.execute(
                    text(
                        "UPDATE scheduled_jobs SET enabled = true "
                        "WHERE job_key = 'sla_escalation'"
                    )
                )
            assert time.monotonic() - started < 2
            second_transaction.rollback()
        finally:
            first_transaction.rollback()
            first.close()
            second.close()

        barrier = threading.Barrier(2)

        def deadlock(first_key: str, second_key: str) -> str:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(
                        text(
                            "SELECT job_key FROM scheduled_jobs "
                            "WHERE job_key = :job_key FOR UPDATE"
                        ),
                        {"job_key": first_key},
                    )
                    barrier.wait(timeout=5)
                    connection.execute(
                        text(
                            "SELECT job_key FROM scheduled_jobs "
                            "WHERE job_key = :job_key FOR UPDATE"
                        ),
                        {"job_key": second_key},
                    )
                    transaction.commit()
                    return "committed"
                except DBAPIError:
                    transaction.rollback()
                    return "deadlock_rolled_back"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda keys: deadlock(*keys),
                    (
                        ("sla_escalation", "preventive_generation"),
                        ("preventive_generation", "sla_escalation"),
                    ),
                )
            )
        assert sorted(results) == ["committed", "deadlock_rolled_back"]
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM scheduled_jobs "
                        "WHERE job_key IN "
                        "('sla_escalation', 'preventive_generation')"
                    )
                )
                == 2
            )
    finally:
        engine.dispose()


def test_pm8_schema_constraints_and_append_only_triggers_exist(
    clean_postgres_database: str,
) -> None:
    engine = build_engine(clean_postgres_database)
    try:
        with engine.connect() as connection:
            constraints = set(
                connection.scalars(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid IN ("
                        "'outbox_events'::regclass, "
                        "'outbox_delivery_attempts'::regclass, "
                        "'outbox_redrive_requests'::regclass, "
                        "'notification_alert_states'::regclass, "
                        "'reliability_validation_records'::regclass"
                        ")"
                    )
                ).all()
            )
            assert {
                "ck_outbox_events_redrives",
                "ck_outbox_delivery_attempts_redrives",
                "uq_outbox_delivery_attempt_cycle_number",
                "ck_outbox_redrive_requests_prior_attempts",
                "ck_outbox_redrive_requests_redrive_number",
                "uq_outbox_redrive_requests_idempotency",
                "uq_outbox_redrive_requests_event_cycle",
                "ck_notification_alert_states_type",
                "uq_notification_alert_states_entity",
                "ck_reliability_validation_records_type",
                "ck_reliability_validation_records_status",
                "ck_reliability_validation_records_checksum",
                "ck_reliability_validation_records_summary",
            }.issubset(constraints)
            triggers = set(
                connection.scalars(
                    text(
                        "SELECT tgname FROM pg_trigger "
                        "WHERE NOT tgisinternal AND tgrelid IN ("
                        "'outbox_delivery_attempts'::regclass, "
                        "'outbox_redrive_requests'::regclass, "
                        "'reliability_validation_records'::regclass"
                        ")"
                    )
                ).all()
            )
            assert {
                "outbox_delivery_attempts_append_only",
                "trg_outbox_redrive_requests_append_only",
                "trg_reliability_validation_records_append_only",
            }.issubset(triggers)
    finally:
        engine.dispose()


def test_dead_letter_redrive_is_audited_idempotent_and_deduplicated(
    clean_postgres_database: str,
) -> None:
    factory = get_session_factory(clean_postgres_database)
    repository = PostgresOperationsRepository(factory)
    admin = _actor(Role.ADMINISTRATOR, 801)
    technician = _actor(Role.TECHNICIAN, 802)
    persist_test_user(factory, admin)
    persist_test_user(factory, technician)
    with factory() as session, session.begin():
        event_id, _ = enqueue_outbox_event(
            session,
            event_type="ticket.assigned",
            aggregate_type="ticket",
            aggregate_id="PM8-TICKET",
            payload={
                "ticket_id": "PM8-TICKET",
                "asset_id": "PM8-ASSET",
                "assigned_user_id": str(technician.id),
            },
            idempotency_key="pm8-redrive-event",
        )
        event = session.get(OutboxEvent, event_id)
        assert event is not None
        event.status = "dead_lettered"
        event.attempt_count = 5

    first, created = repository.redrive_outbox_event(
        event_id,
        idempotency_key="operator-intent-1",
        actor=admin,
        audit_context=_audit(admin),
    )
    replay, replay_created = repository.redrive_outbox_event(
        event_id,
        idempotency_key="operator-intent-1",
        actor=admin,
        audit_context=_audit(admin),
    )
    assert created is True
    assert replay_created is False
    assert first["redrive_count"] == replay["redrive_count"] == 1
    claim = repository.claim_outbox_event(
        worker_identity="pm8-redrive-worker", lease_seconds=60
    )
    assert claim is not None
    repository.deliver_outbox_event(
        event_id, worker_identity="pm8-redrive-worker"
    )
    with factory() as session:
        assert session.scalar(select(Notification)) is not None
        assert len(session.scalars(select(Notification)).all()) == 1
        assert len(session.scalars(select(OutboxRedriveRequest)).all()) == 1


def test_concurrent_same_key_redrive_returns_one_intent_and_one_replay(
    clean_postgres_database: str,
) -> None:
    factory = get_session_factory(clean_postgres_database)
    repository = PostgresOperationsRepository(factory)
    admin = _actor(Role.ADMINISTRATOR, 804)
    technician = _actor(Role.TECHNICIAN, 805)
    persist_test_user(factory, admin)
    persist_test_user(factory, technician)
    with factory() as session, session.begin():
        event_id, _ = enqueue_outbox_event(
            session,
            event_type="ticket.assigned",
            aggregate_type="ticket",
            aggregate_id="PM8-CONCURRENT-TICKET",
            payload={
                "ticket_id": "PM8-CONCURRENT-TICKET",
                "asset_id": "PM8-CONCURRENT-ASSET",
                "assigned_user_id": str(technician.id),
            },
            idempotency_key="pm8-concurrent-redrive-event",
        )
        event = session.get(OutboxEvent, event_id)
        assert event is not None
        event.status = "dead_lettered"
        event.attempt_count = 5

    barrier = threading.Barrier(2)

    def redrive() -> bool:
        barrier.wait(timeout=5)
        _, created = repository.redrive_outbox_event(
            event_id,
            idempotency_key="pm8-concurrent-operator-intent",
            actor=admin,
            audit_context=_audit(admin),
        )
        return created

    with ThreadPoolExecutor(max_workers=2) as pool:
        created_values = list(pool.map(lambda _: redrive(), range(2)))

    assert sorted(created_values) == [False, True]
    with factory() as session:
        assert len(session.scalars(select(OutboxRedriveRequest)).all()) == 1


def test_operational_alerts_deduplicate_and_recover(
    clean_postgres_database: str,
) -> None:
    factory = get_session_factory(clean_postgres_database)
    repository = PostgresOperationsRepository(factory)
    admin = _actor(Role.ADMINISTRATOR, 803)
    persist_test_user(factory, admin)
    now = datetime.now(timezone.utc)

    def evaluate() -> dict[str, int]:
        return repository.evaluate_operational_alerts(
            outbox_age_threshold_seconds=300,
            repeated_job_failure_threshold=3,
            analytics_stale_seconds=3600,
            backup_overdue_seconds=3600,
            worker_stale_seconds=60,
            now=now,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        initial_results = list(pool.map(lambda _: evaluate(), range(2)))
    duplicate = repository.evaluate_operational_alerts(
        outbox_age_threshold_seconds=300,
        repeated_job_failure_threshold=3,
        analytics_stale_seconds=3600,
        backup_overdue_seconds=3600,
        worker_stale_seconds=60,
        now=now,
    )
    assert sum(result["raised_count"] for result in initial_results) == 2
    assert duplicate["raised_count"] == 0

    repository.heartbeat(
        worker_identity="pm8-alert-worker",
        started_at=now,
        status="ready",
        current_execution_id=None,
        now=now,
    )
    with factory() as session, session.begin():
        session.add(
            ReliabilityValidationRecord(
                id=uuid4(),
                validation_type="backup_restore",
                status="passed",
                performed_at=now,
                source_revision="20260726_0008",
                backup_checksum="0" * 64,
                summary={"validated": True},
            )
        )
    recovered = repository.evaluate_operational_alerts(
        outbox_age_threshold_seconds=300,
        repeated_job_failure_threshold=3,
        analytics_stale_seconds=3600,
        backup_overdue_seconds=3600,
        worker_stale_seconds=60,
        now=now,
    )
    assert recovered["recovered_count"] == 2
    with factory() as session:
        events = session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_type == "operational_alert"
            )
        ).all()
        assert len(events) == 4


def test_pm8_data_bearing_downgrade_preserves_pm7_outbox_state(
    clean_postgres_database: str,
) -> None:
    factory = get_session_factory(clean_postgres_database)
    repository = PostgresOperationsRepository(factory)
    admin = _actor(Role.ADMINISTRATOR, 806)
    technician = _actor(Role.TECHNICIAN, 807)
    persist_test_user(factory, admin)
    persist_test_user(factory, technician)
    now = datetime.now(timezone.utc)

    with factory() as session, session.begin():
        business_event_id, _ = enqueue_outbox_event(
            session,
            event_type="ticket.assigned",
            aggregate_type="ticket",
            aggregate_id="PM8-DOWNGRADE-TICKET",
            payload={
                "ticket_id": "PM8-DOWNGRADE-TICKET",
                "asset_id": "PM8-DOWNGRADE-ASSET",
                "assigned_user_id": str(technician.id),
            },
            idempotency_key="pm8-downgrade-business-event",
        )
        alert_event_id, _ = enqueue_outbox_event(
            session,
            event_type="operations.alert_raised",
            aggregate_type="operational_alert",
            aggregate_id="worker_heartbeat_stale:primary",
            payload={
                "alert_type": "worker_heartbeat_stale",
                "alert_name": "Worker heartbeat quá hạn",
                "entity_key": "primary",
                "cycle_number": 1,
                "observed_value": 61,
                "threshold_value": 60,
            },
            idempotency_key="pm8-downgrade-alert-event",
        )
        for event_id in (business_event_id, alert_event_id):
            event = session.get(OutboxEvent, event_id)
            assert event is not None
            event.status = "dead_lettered"
            event.attempt_count = 5
        session.add_all(
            [
                OutboxDeliveryAttempt(
                    id=uuid4(),
                    outbox_event_id=business_event_id,
                    attempt_number=attempt_number,
                    redrive_number=0,
                    worker_identity="pm8-original-worker",
                    started_at=now,
                    completed_at=now,
                    status="failed",
                    safe_error_code="controlled_failure",
                    safe_error_summary="Controlled PM8 downgrade fixture.",
                )
                for attempt_number in range(1, 6)
            ]
        )

    for event_id, key in (
        (business_event_id, "pm8-downgrade-business-redrive"),
        (alert_event_id, "pm8-downgrade-alert-redrive"),
    ):
        repository.redrive_outbox_event(
            event_id,
            idempotency_key=key,
            actor=admin,
            audit_context=_audit(admin),
        )
    with factory() as session, session.begin():
        event = session.get(OutboxEvent, business_event_id)
        assert event is not None
        event.attempt_count = 1
        event.status = "retry_scheduled"
        session.add(
            OutboxDeliveryAttempt(
                id=uuid4(),
                outbox_event_id=business_event_id,
                attempt_number=1,
                redrive_number=1,
                worker_identity="pm8-redrive-worker",
                started_at=now,
                completed_at=now,
                status="failed",
                safe_error_code="controlled_failure",
                safe_error_summary="Controlled PM8 redrive fixture.",
            )
        )

    factory.kw["bind"].dispose()
    clear_database_caches()
    downgraded_engine = None
    try:
        downgrade_database(clean_postgres_database, "20260726_0007")
        downgraded_engine = build_engine(clean_postgres_database)
        with downgraded_engine.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == "20260726_0007"
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM outbox_events "
                    "WHERE event_type LIKE 'operations.alert_%'"
                )
            ) == 0
            status, attempt_count = connection.execute(
                text(
                    "SELECT status, attempt_count FROM outbox_events "
                    "WHERE id = :event_id"
                ),
                {"event_id": business_event_id},
            ).one()
            assert (status, attempt_count) == ("dead_lettered", 5)
            assert connection.execute(
                text(
                    "SELECT count(*), max(attempt_number) "
                    "FROM outbox_delivery_attempts "
                    "WHERE outbox_event_id = :event_id"
                ),
                {"event_id": business_event_id},
            ).one() == (5, 5)
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_name = 'outbox_delivery_attempts' "
                    "AND column_name = 'redrive_number'"
                )
            ) == 0
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name = 'outbox_redrive_requests'"
                )
            ) == 0
    finally:
        if downgraded_engine is not None:
            downgraded_engine.dispose()
        upgrade_database(clean_postgres_database, "20260726_0008")
        clear_database_caches()

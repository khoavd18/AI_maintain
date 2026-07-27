"""Exact PostgreSQL connection-termination tests for PM9 recovery boundaries."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import threading
import time
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from src.database.models import (
    Asset,
    JobExecution,
    Notification,
    OutboxDeliveryAttempt,
    OutboxEvent,
    Ticket,
)
from src.database.session import build_engine, get_session_factory
from src.operations.outbox import enqueue_outbox_event
from src.repositories.contracts import StorageUnavailableError
from src.repositories.postgres_operations import PostgresOperationsRepository
from src.security.audit import AuditContext
from src.security.permissions import Role
from tests.auth_helpers import build_test_user, persist_test_user

pytestmark = pytest.mark.postgres


def test_terminated_job_completion_recovers_after_lease_without_duplicate_execution(
    clean_postgres_database: str,
) -> None:
    session_factory = get_session_factory(clean_postgres_database)
    actor = build_test_user(Role.ADMINISTRATOR)
    persist_test_user(session_factory, actor)
    repository = PostgresOperationsRepository(session_factory)
    now = datetime.now(timezone.utc)
    execution, created = repository.trigger_job(
        "sla_escalation",
        idempotency_key="pm9-killed-job",
        actor=actor,
        audit_context=_context(actor.id, actor.display_name, "trigger"),
        now=now,
    )
    assert created is True
    claimed = repository.claim_execution(
        worker_identity="pm9-killed-worker",
        now=now,
    )
    assert claimed is not None
    execution_id = UUID(execution["id"])

    application_name = f"pm9-job-kill-{uuid4().hex}"
    interrupted_engine, interrupted_repository = _named_repository(
        clean_postgres_database,
        application_name,
    )
    interrupted_backend_checked_out = threading.Event()
    event.listen(
        interrupted_engine,
        "checkout",
        lambda *_args: interrupted_backend_checked_out.set(),
    )
    blocker_engine = build_engine(clean_postgres_database)
    try:
        with blocker_engine.connect() as blocker:
            transaction = blocker.begin()
            blocker.execute(
                text("SELECT id FROM job_executions WHERE id = :id FOR UPDATE"),
                {"id": execution_id},
            )
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    interrupted_repository.complete_execution,
                    execution_id,
                    worker_identity="pm9-killed-worker",
                    summary={"rehearsal": "interrupted-before-commit"},
                    now=now + timedelta(seconds=1),
                )
                assert interrupted_backend_checked_out.wait(timeout=5)
                assert _terminate_exact_test_backend(
                    database_url=clean_postgres_database,
                    application_name=application_name,
                )
                with pytest.raises(StorageUnavailableError):
                    future.result(timeout=5)
            transaction.rollback()

        with session_factory() as session:
            interrupted = session.get(JobExecution, execution_id)
            assert interrupted is not None
            assert interrupted.status == "running"
            assert interrupted.execution_summary is None
            assert interrupted.worker_identity == "pm9-killed-worker"

        lease_expiry = datetime.fromisoformat(str(claimed["lease_expires_at"]))
        assert (
            repository.recover_expired_execution_leases(now=lease_expiry + timedelta(seconds=1))
            == 1
        )
        replacement = repository.claim_execution(
            worker_identity="pm9-replacement-worker",
            now=lease_expiry + timedelta(hours=1),
        )
        assert replacement is not None
        assert replacement["id"] == str(execution_id)
        completed = repository.complete_execution(
            execution_id,
            worker_identity="pm9-replacement-worker",
            summary={"rehearsal": "recovered-once"},
            now=lease_expiry + timedelta(hours=1, seconds=1),
        )
        assert completed["status"] == "succeeded"
        assert completed["attempt_number"] == 2
        with session_factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(JobExecution)
                    .where(JobExecution.id == execution_id)
                )
                == 1
            )
    finally:
        interrupted_engine.dispose()
        blocker_engine.dispose()


def test_terminated_outbox_delivery_is_recovered_and_notified_exactly_once(
    clean_postgres_database: str,
) -> None:
    session_factory = get_session_factory(clean_postgres_database)
    technician = build_test_user(Role.TECHNICIAN, technician_id="TECH-PM9-KILL")
    persist_test_user(session_factory, technician)
    repository = PostgresOperationsRepository(session_factory)
    with session_factory() as session, session.begin():
        event_id, created = enqueue_outbox_event(
            session,
            event_type="ticket.assigned",
            aggregate_type="ticket",
            aggregate_id="TKT-PM9-KILL",
            payload={
                "ticket_id": "TKT-PM9-KILL",
                "asset_id": "ASSET-PM9-KILL",
                "assigned_user_id": str(technician.id),
            },
            idempotency_key="pm9-killed-outbox-delivery",
        )
    assert created is True
    now = datetime.now(timezone.utc)
    claimed = repository.claim_outbox_event(
        worker_identity="pm9-killed-outbox-worker",
        lease_seconds=30,
        now=now,
    )
    assert claimed is not None

    application_name = f"pm9-outbox-kill-{uuid4().hex}"
    interrupted_engine, interrupted_repository = _named_repository(
        clean_postgres_database,
        application_name,
    )
    interrupted_backend_checked_out = threading.Event()
    event.listen(
        interrupted_engine,
        "checkout",
        lambda *_args: interrupted_backend_checked_out.set(),
    )
    blocker_engine = build_engine(clean_postgres_database)
    try:
        with blocker_engine.connect() as blocker:
            transaction = blocker.begin()
            blocker.execute(
                text("SELECT id FROM outbox_events WHERE id = :id FOR UPDATE"),
                {"id": event_id},
            )
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    interrupted_repository.deliver_outbox_event,
                    event_id,
                    worker_identity="pm9-killed-outbox-worker",
                    now=now + timedelta(seconds=1),
                )
                assert interrupted_backend_checked_out.wait(timeout=5)
                assert _terminate_exact_test_backend(
                    database_url=clean_postgres_database,
                    application_name=application_name,
                )
                with pytest.raises(StorageUnavailableError):
                    future.result(timeout=5)
            transaction.rollback()

        with session_factory() as session:
            interrupted = session.get(OutboxEvent, event_id)
            assert interrupted is not None
            assert interrupted.status == "processing"
            assert interrupted.lease_owner == "pm9-killed-outbox-worker"
            assert session.scalar(select(func.count()).select_from(Notification)) == 0
            assert session.scalar(select(func.count()).select_from(OutboxDeliveryAttempt)) == 0

        lease_expiry = datetime.fromisoformat(str(claimed["lease_expires_at"]))
        assert (
            repository.recover_expired_outbox_leases(now=lease_expiry + timedelta(seconds=1)) == 1
        )
        replacement = repository.claim_outbox_event(
            worker_identity="pm9-replacement-outbox-worker",
            lease_seconds=30,
            now=lease_expiry + timedelta(hours=1),
        )
        assert replacement is not None
        assert replacement["id"] == str(event_id)
        delivered = repository.deliver_outbox_event(
            event_id,
            worker_identity="pm9-replacement-outbox-worker",
            now=lease_expiry + timedelta(hours=1, seconds=1),
        )
        assert delivered == {
            "recipient_count": 1,
            "created_notification_count": 1,
        }
        with session_factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.source_outbox_event_id == event_id)
                )
                == 1
            )
            attempts = session.scalars(
                select(OutboxDeliveryAttempt)
                .where(OutboxDeliveryAttempt.outbox_event_id == event_id)
                .order_by(OutboxDeliveryAttempt.attempt_number)
            ).all()
            assert [attempt.status for attempt in attempts] == ["failed", "succeeded"]
            assert [attempt.attempt_number for attempt in attempts] == [1, 2]
    finally:
        interrupted_engine.dispose()
        blocker_engine.dispose()


def test_terminated_business_transaction_commits_ticket_and_outbox_or_neither(
    clean_postgres_database: str,
) -> None:
    session_factory = get_session_factory(clean_postgres_database)
    now = datetime.now(timezone.utc)
    with session_factory() as session, session.begin():
        session.add(
            Asset(
                asset_id="ASSET-PM9-TX-KILL",
                asset_name="Thiết bị diễn tập giao dịch",
                asset_type="generator",
                location="Khu vực test cô lập",
                criticality="critical",
                status="warning",
                installation_date=date.today(),
                last_maintenance_date=date.today(),
                maintenance_interval_days=30,
                next_maintenance_date=date.today() + timedelta(days=30),
            )
        )

    application_name = f"pm9-business-kill-{uuid4().hex}"
    interrupted_engine, interrupted_factory = _named_session_factory(
        clean_postgres_database,
        application_name,
    )
    flushed = threading.Event()
    continue_after_termination = threading.Event()
    ticket_id = "TKT-PM9-TX-KILL"
    outbox_key = "pm9-ticket-critical-same-transaction"

    def interrupted_transaction() -> None:
        with interrupted_factory() as session, session.begin():
            session.add(
                Ticket(
                    ticket_id=ticket_id,
                    asset_id="ASSET-PM9-TX-KILL",
                    issue_description="Giao dịch test phải commit toàn bộ hoặc rollback toàn bộ.",
                    priority="critical",
                    status="open",
                    failure_category="electrical_issue",
                    impact="high",
                    urgency="immediate",
                    technician_id="UNASSIGNED",
                    created_at=now,
                    updated_at=now,
                )
            )
            enqueue_outbox_event(
                session,
                event_type="ticket.critical_created",
                aggregate_type="ticket",
                aggregate_id=ticket_id,
                payload={
                    "ticket_id": ticket_id,
                    "asset_id": "ASSET-PM9-TX-KILL",
                    "priority": "critical",
                },
                idempotency_key=outbox_key,
            )
            session.flush()
            flushed.set()
            if not continue_after_termination.wait(timeout=5):
                raise RuntimeError("Test coordinator did not release interrupted transaction.")
            session.execute(text("SELECT 1"))

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(interrupted_transaction)
            assert flushed.wait(timeout=5)
            assert _terminate_exact_test_backend(
                database_url=clean_postgres_database,
                application_name=application_name,
            )
            continue_after_termination.set()
            with pytest.raises(SQLAlchemyError):
                future.result(timeout=5)

        with session_factory() as session:
            assert session.get(Ticket, ticket_id) is None
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(OutboxEvent)
                    .where(OutboxEvent.idempotency_key == outbox_key)
                )
                == 0
            )
    finally:
        continue_after_termination.set()
        interrupted_engine.dispose()


def _context(actor_id: UUID, display_name: str, suffix: str) -> AuditContext:
    return AuditContext(
        actor_user_id=actor_id,
        actor_display_name=display_name,
        request_id=f"pm9-interruption-{suffix}",
    )


def _named_repository(
    database_url: str,
    application_name: str,
) -> tuple[Engine, PostgresOperationsRepository]:
    engine, factory = _named_session_factory(database_url, application_name)
    return engine, PostgresOperationsRepository(factory)


def _named_session_factory(
    database_url: str,
    application_name: str,
) -> tuple[Engine, sessionmaker]:
    parsed = make_url(database_url)
    if not (parsed.database or "").endswith("_test"):
        raise ValueError("Interruption tests require a database ending in _test.")
    named_url = parsed.update_query_dict({"application_name": application_name})
    engine = build_engine(named_url.render_as_string(hide_password=False))
    return engine, sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


def _terminate_exact_test_backend(
    *,
    database_url: str,
    application_name: str,
    timeout_seconds: float = 4.0,
) -> bool:
    parsed = make_url(database_url)
    if not (parsed.database or "").endswith("_test"):
        raise ValueError("Backend termination is restricted to a database ending in _test.")
    inspector = build_engine(database_url)
    deadline = time.monotonic() + timeout_seconds
    try:
        with inspector.connect() as connection:
            while time.monotonic() < deadline:
                pids = connection.scalars(
                    text(
                        "SELECT pid FROM pg_stat_activity "
                        "WHERE datname = current_database() "
                        "AND application_name = :application_name "
                        "AND pid <> pg_backend_pid()"
                    ),
                    {"application_name": application_name},
                ).all()
                if len(pids) == 1:
                    return bool(
                        connection.scalar(
                            text("SELECT pg_terminate_backend(:pid)"),
                            {"pid": int(pids[0])},
                        )
                    )
                if len(pids) > 1:
                    raise AssertionError("Refusing to terminate an ambiguous set of test backends.")
                # PostgreSQL can cache cumulative-statistics snapshots for the
                # current transaction. End the inspector transaction so the
                # next poll can observe a backend that connected concurrently.
                connection.commit()
                time.sleep(0.02)
    finally:
        inspector.dispose()
    return False

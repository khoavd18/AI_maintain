"""Independent PostgreSQL-backed worker for PM7 jobs and outbox delivery."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone
import logging
import os
import signal
import socket
import threading
import time
from typing import Any
from uuid import UUID, uuid4

from src.config.settings import Settings, get_settings
from src.database.session import get_session_factory
from src.operations.domain import safe_error
from src.operations.jobs import JobRunner
from src.operations.logging import configure_structured_logging, log_event
from src.repositories.contracts import RepositoryError
from src.repositories.postgres_operations import PostgresOperationsRepository

logger = logging.getLogger("maintenance.worker")


class BackgroundWorker:
    """Bounded worker loop with persisted leases and graceful shutdown."""

    def __init__(
        self,
        *,
        settings: Settings,
        worker_identity: str | None = None,
        stop_event: threading.Event | None = None,
        repository: PostgresOperationsRepository | None = None,
        runner: JobRunner | None = None,
    ) -> None:
        if settings.storage_backend != "postgresql":
            raise RuntimeError("Background worker requires STORAGE_BACKEND=postgresql.")
        self.settings = settings
        self.worker_identity = worker_identity or _default_worker_identity()
        self.stop_event = stop_event or threading.Event()
        self.started_at = datetime.now(timezone.utc)
        self.repository = repository or PostgresOperationsRepository(
            get_session_factory(settings.database_url)
        )
        self.runner = runner or JobRunner(
            settings=settings,
            operations_repository=self.repository,
        )

    def check_readiness(self) -> None:
        """Fail before polling when PostgreSQL or PM7 migrations are unavailable."""

        self.repository.check_health()

    def run_forever(self) -> None:
        """Poll until SIGINT/SIGTERM, keeping failures bounded and observable."""

        self.check_readiness()
        self._heartbeat("starting")
        log_event(
            logger,
            logging.INFO,
            "worker.started",
            "Background worker started.",
            worker_identity=self.worker_identity,
        )
        while not self.stop_event.is_set():
            started = time.monotonic()
            try:
                result = self.run_once()
                log_event(
                    logger,
                    logging.INFO,
                    "worker.iteration",
                    "Background worker iteration completed.",
                    worker_identity=self.worker_identity,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    created_count=result["scheduled_created_count"],
                    processed_count=(
                        result["job_processed_count"]
                        + result["outbox_processed_count"]
                    ),
                    recovered_count=(
                        result["execution_lease_recovered_count"]
                        + result["outbox_lease_recovered_count"]
                    ),
                )
            except (RepositoryError, OSError, ValueError, RuntimeError) as exc:
                code, summary = safe_error(exc)
                log_event(
                    logger,
                    logging.ERROR,
                    "worker.iteration_failed",
                    summary,
                    worker_identity=self.worker_identity,
                    error_code=code,
                )
                self._best_effort_heartbeat("error")
            self.stop_event.wait(self.settings.worker_poll_interval_seconds)
        self._best_effort_heartbeat("stopping")
        log_event(
            logger,
            logging.INFO,
            "worker.stopped",
            "Background worker stopped gracefully.",
            worker_identity=self.worker_identity,
        )

    def run_once(self) -> dict[str, int]:
        """Run one bounded scheduling, execution, and outbox cycle."""

        self._heartbeat("ready")
        execution_recovered = self.repository.recover_expired_execution_leases()
        outbox_recovered = self.repository.recover_expired_outbox_leases()
        materialized = self.repository.materialize_due_jobs(
            limit=self.settings.worker_batch_size
        )
        job_processed = 0
        execution = self.repository.claim_execution(
            worker_identity=self.worker_identity
        )
        if execution is not None:
            job_processed = 1
            self._execute_claimed_job(execution)

        outbox_processed = 0
        for _ in range(self.settings.worker_batch_size):
            event = self.repository.claim_outbox_event(
                worker_identity=self.worker_identity,
                lease_seconds=self.settings.worker_outbox_lease_seconds,
            )
            if event is None:
                break
            self._process_claimed_outbox(event)
            outbox_processed += 1
        self._heartbeat("ready")
        return {
            "scheduled_created_count": materialized["created_count"],
            "scheduled_skipped_count": materialized["skipped_count"],
            "execution_lease_recovered_count": execution_recovered,
            "outbox_lease_recovered_count": outbox_recovered,
            "job_processed_count": job_processed,
            "outbox_processed_count": outbox_processed,
        }

    def _execute_claimed_job(self, execution: dict[str, Any]) -> None:
        execution_id = UUID(str(execution["id"]))
        self._heartbeat("ready", current_execution_id=execution_id)
        started = time.monotonic()
        try:
            actor = self.repository.load_execution_actor(execution_id)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.runner.run, execution, actor=actor)
                while True:
                    try:
                        summary = future.result(
                            timeout=self.settings.worker_heartbeat_interval_seconds
                        )
                        break
                    except FutureTimeout:
                        self.repository.renew_execution_lease(
                            execution_id,
                            worker_identity=self.worker_identity,
                        )
                        self._heartbeat(
                            "ready", current_execution_id=execution_id
                        )
            completed = self.repository.complete_execution(
                execution_id,
                worker_identity=self.worker_identity,
                summary=summary,
            )
            log_event(
                logger,
                logging.INFO,
                "job.succeeded",
                "Background job execution succeeded.",
                worker_identity=self.worker_identity,
                job_key=execution["job_key"],
                execution_id=execution_id,
                attempt_number=completed["attempt_number"],
                duration_ms=int((time.monotonic() - started) * 1000),
                status=completed["status"],
                correlation_id=execution["correlation_id"],
            )
        except Exception as exc:
            code, summary = safe_error(exc)
            failed = self.repository.fail_execution(
                execution_id,
                worker_identity=self.worker_identity,
                error_code=code,
                error_summary=summary,
            )
            log_event(
                logger,
                logging.ERROR,
                "job.failed",
                summary,
                worker_identity=self.worker_identity,
                job_key=execution["job_key"],
                execution_id=execution_id,
                attempt_number=failed["attempt_number"],
                duration_ms=int((time.monotonic() - started) * 1000),
                status=failed["status"],
                error_code=code,
                correlation_id=execution["correlation_id"],
            )
        finally:
            self._best_effort_heartbeat("ready")

    def _process_claimed_outbox(self, event: dict[str, Any]) -> None:
        event_id = UUID(str(event["id"]))
        try:
            result = self.repository.deliver_outbox_event(
                event_id,
                worker_identity=self.worker_identity,
            )
            log_event(
                logger,
                logging.INFO,
                "outbox.processed",
                "Outbox event processed.",
                worker_identity=self.worker_identity,
                outbox_event_id=event_id,
                processed_count=result["created_notification_count"],
                attempt_number=event["attempt_count"],
            )
        except Exception as exc:
            code, summary = safe_error(exc)
            failed = self.repository.fail_outbox_event(
                event_id,
                worker_identity=self.worker_identity,
                error_code=code,
                error_summary=summary,
            )
            log_event(
                logger,
                logging.ERROR,
                "outbox.failed",
                summary,
                worker_identity=self.worker_identity,
                outbox_event_id=event_id,
                status=failed["status"],
                attempt_number=failed["attempt_count"],
                error_code=code,
            )

    def _heartbeat(
        self,
        status: str,
        *,
        current_execution_id: UUID | None = None,
    ) -> None:
        self.repository.heartbeat(
            worker_identity=self.worker_identity,
            started_at=self.started_at,
            status=status,
            current_execution_id=current_execution_id,
            metadata={"pid": os.getpid(), "catalog_version": "pm7"},
        )

    def _best_effort_heartbeat(self, status: str) -> None:
        try:
            self._heartbeat(status)
        except (RepositoryError, OSError, ValueError):
            return


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the durable AI Maintenance Copilot background worker."
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args()

    settings = get_settings()
    configure_structured_logging(settings.log_level)
    stop_event = threading.Event()
    worker = BackgroundWorker(
        settings=settings,
        worker_identity=args.worker_id,
        stop_event=stop_event,
    )
    _install_signal_handlers(stop_event)
    if args.once:
        result = _run_one_iteration(worker)
        print(
            "Worker iteration: "
            f"jobs={result['job_processed_count']} "
            f"outbox={result['outbox_processed_count']} "
            f"scheduled={result['scheduled_created_count']}"
        )
        return
    worker.run_forever()


def _run_one_iteration(worker: BackgroundWorker) -> dict[str, int]:
    """Run a one-shot worker without leaving a false-ready heartbeat."""

    worker.check_readiness()
    try:
        return worker.run_once()
    finally:
        worker._best_effort_heartbeat("stopping")


def _install_signal_handlers(stop_event: threading.Event) -> None:
    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)


def _default_worker_identity() -> str:
    host = socket.gethostname().split(".", maxsplit=1)[0][:40] or "local"
    return f"{host}-{os.getpid()}-{uuid4().hex[:8]}"


if __name__ == "__main__":
    main()

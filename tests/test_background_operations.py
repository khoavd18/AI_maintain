"""Focused unit tests for the closed PM7 worker and event catalogs."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.config.settings import Settings
from src.operations.domain import (
    JobType,
    safe_error,
    validate_job_configuration,
)
from src.operations.jobs import _validate_publication_paths
from src.operations.worker import _run_one_iteration
from src.repositories.postgres_operations import _next_due


def test_job_catalog_rejects_arbitrary_configuration_and_schedule() -> None:
    assert (
        validate_job_configuration(
            JobType.SLA_ESCALATION.value,
            interval_seconds=300,
            timezone_name="Asia/Ho_Chi_Minh",
            configuration_payload={},
        )
        is JobType.SLA_ESCALATION
    )

    with pytest.raises(ValueError, match="interval_seconds"):
        validate_job_configuration(
            JobType.SLA_ESCALATION.value,
            interval_seconds=1,
            timezone_name="Asia/Ho_Chi_Minh",
            configuration_payload={},
        )
    with pytest.raises(ValueError, match="không nhận cấu hình"):
        validate_job_configuration(
            JobType.SLA_ESCALATION.value,
            interval_seconds=300,
            timezone_name="Asia/Ho_Chi_Minh",
            configuration_payload={"module": "os"},
        )
    with pytest.raises(ValueError):
        validate_job_configuration(
            "arbitrary_python",
            interval_seconds=300,
            timezone_name="Asia/Ho_Chi_Minh",
            configuration_payload={},
        )


def test_safe_error_does_not_expose_exception_message_or_path() -> None:
    code, summary = safe_error(
        RuntimeError(r"C:\private\uploads\secret.bin token=do-not-log")
    )

    assert code == "RuntimeError"
    assert "secret" not in summary
    assert "token" not in summary
    assert "C:\\" not in summary


def test_analytics_publication_rejects_unsafe_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="root"):
        _validate_publication_paths(
            source_dir=tmp_path / "raw",
            target_dir=Path.cwd().resolve(),
        )
    with pytest.raises(ValueError, match="separate"):
        _validate_publication_paths(
            source_dir=tmp_path / "raw",
            target_dir=tmp_path / "raw",
        )


def test_worker_settings_require_stale_window_larger_than_heartbeat() -> None:
    with pytest.raises(ValueError, match="must exceed"):
        Settings(
            _env_file=None,
            app_environment="test",
            token_signing_secret="test-secret-at-least-thirty-two-characters",
            worker_heartbeat_interval_seconds=60,
            worker_heartbeat_stale_seconds=60,
        )


def test_schedule_advances_directly_past_a_long_worker_outage() -> None:
    scheduled_for = datetime(2025, 1, 1, tzinfo=timezone.utc)
    resumed_at = scheduled_for + timedelta(days=365, seconds=17)

    next_due = _next_due(scheduled_for, 300, resumed_at)

    assert next_due > resumed_at
    assert next_due - resumed_at <= timedelta(seconds=300)


def test_one_iteration_worker_never_leaves_a_ready_heartbeat() -> None:
    class StubWorker:
        def __init__(self) -> None:
            self.heartbeats: list[str] = []

        def check_readiness(self) -> None:
            return None

        def run_once(self) -> dict[str, int]:
            raise RuntimeError("iteration failed")

        def _best_effort_heartbeat(self, status: str) -> None:
            self.heartbeats.append(status)

    worker = StubWorker()

    with pytest.raises(RuntimeError, match="iteration failed"):
        _run_one_iteration(worker)  # type: ignore[arg-type]

    assert worker.heartbeats == ["stopping"]

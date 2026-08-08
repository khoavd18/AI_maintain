from pathlib import Path
from typing import Any

from src.operations.runtime import (
    DatabasePoolMetrics,
    OperationsRuntimeContext,
)
from src.operations.service import OperationsService
from src.release import ReleaseIdentity


class _PoolMetricsProvider:
    def snapshot(self) -> DatabasePoolMetrics:
        return DatabasePoolMetrics(size=5, checked_out=2, overflow=0)


class _Repository:
    def check_health(self) -> None:
        return None

    def worker_health(self, *, stale_after_seconds: int) -> dict[str, Any]:
        assert stale_after_seconds == 60
        return {"ready": True, "status": "ready"}

    def operational_metrics(self) -> dict[str, Any]:
        return {"pending_job_count": 0}


class _Operator:
    def has(self, _permission: object) -> bool:
        return True


def test_operations_service_uses_explicit_runtime_dependencies() -> None:
    service = OperationsService(  # type: ignore[arg-type]
        _Repository(),
        worker_stale_seconds=60,
        database_pool_metrics=_PoolMetricsProvider(),
        runtime_context=OperationsRuntimeContext(
            ReleaseIdentity("release-1", "0.1.0", "abc", "v0.1.0", "revision")
        ),
    )

    assert service.metrics(actor=_Operator())["database_pool"] == {
        "size": 5,
        "checked_out": 2,
        "overflow": 0,
    }
    assert service.readiness()["release"] == {
        "identifier": "release-1",
        "application_version": "0.1.0",
        "git_commit": "abc",
        "git_tag": "v0.1.0",
        "alembic_revision": "revision",
    }


def test_operations_service_source_has_no_configuration_or_session_factory_leak() -> None:
    source = Path("src/operations/service.py").read_text(encoding="utf-8")

    assert "get_settings" not in source
    assert "session_factory" not in source
    assert ".pool" not in source

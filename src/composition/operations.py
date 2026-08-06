"""Construction of durable PM7 operations dependencies."""

from __future__ import annotations

from functools import lru_cache

from src.config.settings import Settings, get_settings
from src.database.session import get_session_factory
from src.repositories.postgres_operations import PostgresOperationsRepository


def build_operations_repository(settings: Settings | None = None) -> PostgresOperationsRepository:
    """Construct the concrete durable operations repository for one settings graph."""

    settings = settings or get_settings()
    return PostgresOperationsRepository(get_session_factory(settings.database_url))


@lru_cache(maxsize=1)
def build_operations_service():
    """Build the cached PM7 application service and preserve one process graph."""

    settings = get_settings()
    if settings.storage_backend != "postgresql":
        raise RuntimeError("PM7 operations require STORAGE_BACKEND=postgresql.")
    from src.operations.service import OperationsService

    return OperationsService(
        build_operations_repository(settings),
        worker_stale_seconds=settings.worker_heartbeat_stale_seconds,
        outbox_age_alert_seconds=settings.operational_outbox_age_alert_seconds,
        repeated_job_failure_threshold=(
            settings.operational_repeated_job_failure_threshold
        ),
        analytics_stale_seconds=settings.operational_analytics_stale_seconds,
        backup_overdue_seconds=settings.operational_backup_overdue_seconds,
    )

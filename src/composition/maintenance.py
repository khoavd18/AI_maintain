"""Construction of the preventive-maintenance service graph."""

from __future__ import annotations

from pathlib import Path

from src.asset_management.storage import LocalAttachmentStorage
from src.config.settings import get_settings
from src.database.session import get_session_factory
from src.maintenance_management.service import MaintenancePlanningService
from src.repositories.contracts import MaintenancePlanningRepository
from src.repositories.postgres_maintenance import PostgresMaintenancePlanningRepository


def build_maintenance_planning_service() -> MaintenancePlanningService:
    """Build maintenance service dependencies from validated product settings."""

    settings = get_settings()
    repository: MaintenancePlanningRepository | None = None
    if settings.storage_backend == "postgresql":
        repository = PostgresMaintenancePlanningRepository(
            get_session_factory(settings.database_url)
        )
    return MaintenancePlanningService(
        repository,
        LocalAttachmentStorage(Path(settings.attachment_storage_root)),
        attachment_max_size_bytes=settings.attachment_max_size_bytes,
    )

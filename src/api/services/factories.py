"""Outer construction for the configured API service graph."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.asset_management.service import AssetManagementService
from src.asset_management.storage import LocalAttachmentStorage
from src.config.settings import get_settings
from src.database.session import get_session_factory
from src.repositories.csv import CsvMaintenanceRepository
from src.repositories.postgres import PostgresMaintenanceRepository
from src.repositories.postgres_assets import PostgresAssetRepository

from .analytics_snapshot import (
    ASSET_FILE,
    MAINTENANCE_LOG_FILE,
    TICKET_FILE,
)

if TYPE_CHECKING:
    from src.repositories.contracts import MaintenanceRepository
    from src.api.services.compatibility import ProcessedDataService


def build_asset_management_service(repository, settings=None) -> AssetManagementService:
    """Construct asset lifecycle dependencies for a selected repository."""

    settings = settings or get_settings()
    session_factory = getattr(repository, "session_factory", None)
    asset_repository = (
        PostgresAssetRepository(session_factory) if session_factory is not None else None
    )
    return AssetManagementService(
        asset_repository,
        LocalAttachmentStorage(settings.attachment_storage_root),
        attachment_max_size_bytes=settings.attachment_max_size_bytes,
        frontend_base_url=settings.frontend_base_url,
    )


def build_processed_data_service() -> "ProcessedDataService":
    """Select primary storage and construct the complete compatibility graph."""

    from src.api.services.compatibility import ProcessedDataService

    settings = get_settings()
    if settings.storage_backend == "csv":
        repository: MaintenanceRepository = CsvMaintenanceRepository(
            asset_path=ASSET_FILE,
            ticket_path=TICKET_FILE,
            maintenance_log_path=MAINTENANCE_LOG_FILE,
        )
        return ProcessedDataService(repository=repository)

    session_factory = get_session_factory(settings.database_url)
    repository = PostgresMaintenanceRepository(session_factory)
    from src.repositories.postgres_tickets import PostgresTicketRepository
    from src.ticket_management.service import TicketWorkflowService

    ticket_workflow = TicketWorkflowService(PostgresTicketRepository(session_factory))
    return ProcessedDataService(repository=repository, ticket_workflow=ticket_workflow)

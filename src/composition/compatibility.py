"""Composition for the historical analytics and legacy API service graph."""

from __future__ import annotations

from src.api.services.analytics_snapshot import (
    ASSET_FILE,
    MAINTENANCE_LOG_FILE,
    TICKET_FILE,
)
from src.api.services.compatibility import ProcessedDataService
from src.composition.assets import build_asset_management_service
from src.config.settings import get_settings
from src.database.session import get_session_factory
from src.repositories.contracts import MaintenanceRepository
from src.repositories.csv import CsvMaintenanceRepository
from src.repositories.postgres import PostgresMaintenanceRepository


def build_processed_data_service() -> ProcessedDataService:
    """Select storage and construct the complete legacy compatibility graph."""

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
    return ProcessedDataService(
        repository=repository,
        asset_management=build_asset_management_service(repository, settings),
        ticket_workflow=ticket_workflow,
    )

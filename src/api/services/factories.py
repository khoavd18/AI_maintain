"""Outer construction for the configured API service graph."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.composition.assets import build_asset_management_service
from src.config.settings import get_settings
from src.database.session import get_session_factory
from src.repositories.csv import CsvMaintenanceRepository
from src.repositories.postgres import PostgresMaintenanceRepository

from .analytics_snapshot import (
    ASSET_FILE,
    MAINTENANCE_LOG_FILE,
    TICKET_FILE,
)

__all__ = ["build_asset_management_service", "build_processed_data_service"]

if TYPE_CHECKING:
    from src.repositories.contracts import MaintenanceRepository
    from src.api.services.compatibility import ProcessedDataService


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

"""Public API service boundary and compatibility exports."""

from __future__ import annotations

from functools import lru_cache

from src.analytics.errors import (
    AssetNotFoundError,
    ProcessedDataNotFoundError,
    TicketNotFoundError,
)
from src.repositories.csv import (
    ASSET_REQUIRED_COLUMNS,
    MAINTENANCE_LOG_REQUIRED_COLUMNS,
    TICKET_REQUIRED_COLUMNS,
)

from .analytics_snapshot import (
    ASSET_COLUMNS,
    ASSET_FILE,
    ANOMALY_FILE,
    FACILITY_TIMEZONE,
    FEATURE_FILE,
    MAINTENANCE_KPI_FILE,
    MAINTENANCE_LOG_COLUMNS,
    MAINTENANCE_LOG_FILE,
    PREVENTIVE_FILE,
    RECURRING_ISSUE_FILE,
    RISK_FILE,
    TICKET_COLUMNS,
    TICKET_FILE,
    AnalyticsSnapshotService,
)
from .analytics_projection import AnalyticsProjectionService
from .asset_context import AssetContextQueryService
from .compatibility import ProcessedDataService
from .legacy_maintenance_adapter import LegacyMaintenanceAdapter
from .legacy_ticket_adapter import LegacyTicketAdapter


@lru_cache(maxsize=1)
def get_processed_data_service() -> ProcessedDataService:
    """Return the configured service graph through the outer factory."""

    from .factories import build_processed_data_service

    return build_processed_data_service()


__all__ = [
    "ASSET_COLUMNS",
    "ASSET_FILE",
    "ASSET_REQUIRED_COLUMNS",
    "ANOMALY_FILE",
    "AnalyticsProjectionService",
    "AnalyticsSnapshotService",
    "AssetContextQueryService",
    "AssetNotFoundError",
    "FACILITY_TIMEZONE",
    "FEATURE_FILE",
    "LegacyMaintenanceAdapter",
    "LegacyTicketAdapter",
    "MAINTENANCE_KPI_FILE",
    "MAINTENANCE_LOG_COLUMNS",
    "MAINTENANCE_LOG_FILE",
    "MAINTENANCE_LOG_REQUIRED_COLUMNS",
    "PREVENTIVE_FILE",
    "ProcessedDataNotFoundError",
    "ProcessedDataService",
    "RECURRING_ISSUE_FILE",
    "RISK_FILE",
    "TICKET_COLUMNS",
    "TICKET_FILE",
    "TICKET_REQUIRED_COLUMNS",
    "TicketNotFoundError",
    "get_processed_data_service",
]

"""Compatibility facade for storage-neutral repository contracts.

Definitions live in bounded-context modules; this package keeps the historical
``src.repositories.contracts`` import path stable for the application, tests,
and external local integrations.
"""

from .assets import AssetRepository
from .inventory import InventoryRepository
from .maintenance import MaintenancePlanningRepository, MaintenanceRepository
from .operations import OperationsRepository
from src.security.audit import AuditContext
from .shared import (
    DuplicateIdentifierError,
    IntegrityViolationError,
    RecordNotFoundError,
    RepositoryError,
    StaleRecordError,
    StorageUnavailableError,
    StoredPage,
    StoredRecord,
    UnsupportedStorageOperationError,
)
from .tickets import TicketRepository

__all__ = [
    "AssetRepository",
    "AuditContext",
    "DuplicateIdentifierError",
    "IntegrityViolationError",
    "InventoryRepository",
    "MaintenancePlanningRepository",
    "MaintenanceRepository",
    "OperationsRepository",
    "RecordNotFoundError",
    "RepositoryError",
    "StaleRecordError",
    "StorageUnavailableError",
    "StoredPage",
    "StoredRecord",
    "TicketRepository",
    "UnsupportedStorageOperationError",
]

"""Transactional persistence boundaries for the maintenance product."""

from src.repositories.contracts import (
    DuplicateIdentifierError,
    IntegrityViolationError,
    MaintenanceRepository,
    RecordNotFoundError,
    RepositoryError,
    StaleRecordError,
    StorageUnavailableError,
    StoredRecord,
)

__all__ = [
    "DuplicateIdentifierError",
    "IntegrityViolationError",
    "MaintenanceRepository",
    "RecordNotFoundError",
    "RepositoryError",
    "StaleRecordError",
    "StorageUnavailableError",
    "StoredRecord",
]

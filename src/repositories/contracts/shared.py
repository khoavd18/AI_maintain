"""Storage-neutral records and repository errors shared by bounded contexts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

class RepositoryError(RuntimeError):
    """Base class for persistence failures safe to map at the API boundary."""


class StorageUnavailableError(RepositoryError):
    """Raised when configured primary storage cannot serve a request."""


class DuplicateIdentifierError(RepositoryError):
    """Raised when a primary or unique identifier already exists."""


class RecordNotFoundError(RepositoryError):
    """Raised when a requested transactional record does not exist."""


class IntegrityViolationError(RepositoryError):
    """Raised when a foreign key or database invariant is violated."""


class StaleRecordError(RepositoryError):
    """Raised when optimistic concurrency rejects a stale write."""


class UnsupportedStorageOperationError(RepositoryError):
    """Raised when a compatibility adapter cannot provide a product write."""


@dataclass(frozen=True)
class StoredRecord:
    """API-shaped values plus a storage-only optimistic version."""

    values: dict[str, Any]
    version: int | None = None


@dataclass(frozen=True)
class StoredPage:
    """Storage-neutral paginated records and their total count."""

    items: list[StoredRecord]
    page: int
    page_size: int
    total: int

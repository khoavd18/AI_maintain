"""Storage-neutral maintenance application errors."""

from __future__ import annotations


class MaintenanceDomainError(ValueError):
    """Base error for safe business-rule messages."""


class MaintenanceNotFoundError(MaintenanceDomainError):
    """Raised when a planning resource does not exist."""


class MaintenanceConflictError(MaintenanceDomainError):
    """Raised when a transition or relationship is inconsistent."""


class MaintenanceAuthorizationError(MaintenanceDomainError):
    """Raised when resource ownership denies an otherwise permitted action."""

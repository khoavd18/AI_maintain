"""Storage-neutral inventory application errors."""

from __future__ import annotations


class InventoryDomainError(ValueError):
    """Raised when an inventory request violates the public domain contract."""


class InventoryNotFoundError(InventoryDomainError):
    """Raised when an inventory resource does not exist."""


class InventoryConflictError(InventoryDomainError):
    """Raised when lifecycle, stock, or relationship state rejects an action."""


class InventoryAuthorizationError(InventoryDomainError):
    """Raised when resource-level access is not allowed."""

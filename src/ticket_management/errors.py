"""Storage-neutral ticket application errors."""

from __future__ import annotations


class TicketDomainError(ValueError):
    """Base class for safe ticket workflow errors."""


class TicketNotFoundError(TicketDomainError):
    """Raised when a ticket or related resource does not exist."""


class TicketConflictError(TicketDomainError):
    """Raised when a transition conflicts with current state."""


class TicketAuthorizationError(TicketDomainError):
    """Raised when resource ownership or service-level RBAC rejects an action."""

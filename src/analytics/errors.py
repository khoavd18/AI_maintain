"""Storage-neutral errors shared by analytics-facing adapters."""


class ProcessedDataNotFoundError(FileNotFoundError):
    """Raised when a required analytics snapshot is missing or stale."""


class AssetNotFoundError(ValueError):
    """Raised when an asset identifier cannot be resolved."""


class TicketNotFoundError(ValueError):
    """Raised when a ticket identifier cannot be resolved."""

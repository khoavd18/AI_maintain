"""RAG-side port and adapter for bounded asset context access.

The RAG application needs a small, read-only view of asset facts and recent
tickets.  Keeping that port here prevents the retrieval/orchestration layer
from depending on FastAPI or the analytics service implementation.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

AssetContext = dict[str, Any]


@runtime_checkable
class AssetContextProvider(Protocol):
    """Read-only asset context required by the Copilot application."""

    def get_asset_context(self, asset_id: str) -> AssetContext:
        """Return the bounded context for one asset or raise its domain error."""


class AssetContextSource(Protocol):
    """Structural port implemented by the existing application query service."""

    def get_asset_context(self, asset_id: str, limit: int = 10) -> AssetContext:
        """Return the legacy-compatible asset context payload."""

    def list_tickets(
        self,
        asset_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return recent ticket records for query enrichment."""


class ProcessedDataAssetContextAdapter:
    """Adapt the legacy processed-data query service to the RAG port.

    This adapter intentionally exposes only read operations used by RAG.  The
    source remains selected by the API composition root, so RAG does not know
    whether the application is backed by PostgreSQL or a compatibility fixture.
    """

    def __init__(self, source: AssetContextSource) -> None:
        self._source = source

    def get_asset_context(self, asset_id: str) -> AssetContext:
        return self._source.get_asset_context(asset_id)

    def list_tickets(
        self,
        asset_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._source.list_tickets(asset_id=asset_id, limit=limit)

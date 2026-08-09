"""Characterization tests for the RAG asset-context application port."""

from typing import Any

from src.analytics.errors import AssetNotFoundError
from src.api.services import AssetNotFoundError as ApiAssetNotFoundError
from src.rag.adapters.asset_context import (
    AssetContextProvider,
    ProcessedDataAssetContextAdapter,
)


class _Source:
    def get_asset_context(self, asset_id: str, limit: int = 10) -> dict[str, Any]:
        return {"asset_id": asset_id, "limit": limit}

    def list_tickets(
        self,
        asset_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return [{"asset_id": asset_id, "limit": limit}]


def test_context_adapter_exposes_only_the_rag_read_port() -> None:
    adapter = ProcessedDataAssetContextAdapter(_Source())

    assert isinstance(adapter, AssetContextProvider)
    assert adapter.get_asset_context("HVAC_001") == {"asset_id": "HVAC_001", "limit": 10}
    assert adapter.list_tickets(asset_id="HVAC_001", limit=3) == [
        {"asset_id": "HVAC_001", "limit": 3}
    ]


def test_api_compatibility_reexports_storage_neutral_errors() -> None:
    assert ApiAssetNotFoundError is AssetNotFoundError

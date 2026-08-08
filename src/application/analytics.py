"""Neutral application boundary for the legacy analytics query service."""

from __future__ import annotations

from src.rag.adapters.asset_context import AssetContextSource


def get_asset_context_source() -> AssetContextSource:
    """Expose the outer-selected analytics source through an application port."""

    from src.api.services import get_processed_data_service

    return get_processed_data_service()

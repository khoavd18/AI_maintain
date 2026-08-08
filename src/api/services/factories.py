"""Outer construction for the configured API service graph."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.composition.assets import build_asset_management_service

__all__ = ["build_asset_management_service", "build_processed_data_service"]

if TYPE_CHECKING:
    from src.api.services.compatibility import ProcessedDataService


def build_processed_data_service() -> "ProcessedDataService":
    """Historical builder delegated to the explicit composition root."""

    from src.composition.compatibility import build_processed_data_service as build

    return build()

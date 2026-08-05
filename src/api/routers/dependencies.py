"""Compatibility-aware dependencies shared by focused legacy routers."""

from __future__ import annotations

from src.api.services import ProcessedDataService, get_processed_data_service


def get_service() -> ProcessedDataService:
    """Resolve the configured query service through the existing factory."""

    return get_processed_data_service()

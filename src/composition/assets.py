"""Construction of the asset lifecycle service graph."""

from __future__ import annotations

from typing import Any

from src.asset_management.service import AssetManagementService
from src.asset_management.storage import LocalAttachmentStorage
from src.config.settings import Settings, get_settings
from src.repositories.postgres_assets import PostgresAssetRepository


def build_asset_management_service(
    repository: Any, settings: Settings | None = None
) -> AssetManagementService:
    """Construct asset application dependencies for the selected repository."""

    settings = settings or get_settings()
    session_factory = getattr(repository, "session_factory", None)
    asset_repository = (
        PostgresAssetRepository(session_factory) if session_factory is not None else None
    )
    return AssetManagementService(
        asset_repository,
        LocalAttachmentStorage(settings.attachment_storage_root),
        attachment_max_size_bytes=settings.attachment_max_size_bytes,
        frontend_base_url=settings.frontend_base_url,
    )

"""Construction of the inventory application service graph."""

from __future__ import annotations

from pathlib import Path

from src.asset_management.storage import LocalAttachmentStorage
from src.config.settings import get_settings
from src.database.session import get_session_factory
from src.inventory_management.service import InventoryManagementService
from src.repositories.contracts import InventoryRepository
from src.repositories.postgres_inventory import PostgresInventoryRepository


def build_inventory_management_service() -> InventoryManagementService:
    """Build inventory service dependencies from validated product settings."""

    settings = get_settings()
    repository: InventoryRepository | None = None
    if settings.storage_backend == "postgresql":
        repository = PostgresInventoryRepository(
            get_session_factory(settings.database_url)
        )
    return InventoryManagementService(
        repository,
        LocalAttachmentStorage(Path(settings.attachment_storage_root)),
        attachment_max_size_bytes=settings.attachment_max_size_bytes,
    )

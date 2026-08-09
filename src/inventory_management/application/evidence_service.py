"""Inventory evidence capability."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Callable
from uuid import UUID

from src.asset_management.storage import AttachmentStorage, AttachmentStorageError, validate_attachment
from src.inventory_management.domain import INVENTORY_ATTACHMENT_CATEGORIES
from src.repositories.contracts import InventoryRepository
from src.security.audit import AuditContext
from src.security.permissions import Permission
from src.security.principal import CurrentUser

from src.inventory_management.errors import InventoryDomainError, InventoryNotFoundError


@dataclass(frozen=True)
class InventoryEvidenceDownload:
    filename: str
    media_type: str
    content: bytes


class InventoryEvidenceService:
    """Own attachment validation and storage while the repository owns transactions."""

    def __init__(
        self,
        repository_provider: Callable[[], InventoryRepository],
        attachment_storage: AttachmentStorage,
        *,
        attachment_max_size_bytes: int,
        require_permission: Callable[[CurrentUser, Permission], None],
        get_movement: Callable[[UUID], dict[str, Any]],
        require_movement_access: Callable[[dict[str, Any], CurrentUser], None],
    ) -> None:
        self._repository_provider = repository_provider
        self._attachment_storage = attachment_storage
        self._attachment_max_size_bytes = attachment_max_size_bytes
        self._require_permission = require_permission
        self._get_movement = get_movement
        self._require_movement_access = require_movement_access

    def list_evidence(self, movement_id: UUID, *, actor: CurrentUser) -> list[dict[str, Any]]:
        self._require_permission(actor, Permission.INVENTORY_ATTACHMENTS_READ)
        movement = self._get_movement(movement_id)
        self._require_movement_access(movement, actor)
        return [
            dict(record.values)
            for record in self._repository_provider().list_inventory_attachments(movement_id)
        ]

    def upload_evidence(
        self,
        movement_id: UUID,
        *,
        category: str,
        filename: str,
        claimed_media_type: str | None,
        content: bytes,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_ATTACHMENTS_CREATE)
        movement = self._get_movement(movement_id)
        self._require_movement_access(movement, actor)
        if category not in INVENTORY_ATTACHMENT_CATEGORIES:
            raise InventoryDomainError("Inventory evidence category không hợp lệ.")
        validated = validate_attachment(
            filename=filename,
            claimed_media_type=claimed_media_type,
            content=content,
            max_size_bytes=self._attachment_max_size_bytes,
        )
        storage_key = self._attachment_storage.save(validated, namespace="inventory")
        try:
            record = self._repository_provider().create_inventory_attachment(
                {
                    "movement_id": movement_id,
                    "category": category,
                    "original_filename": validated.original_filename,
                    "storage_key": storage_key,
                    "media_type": validated.media_type,
                    "size_bytes": validated.size_bytes,
                    "checksum": validated.checksum,
                    "uploaded_by_user_id": actor.id,
                    "deleted_at": None,
                    "deleted_by_user_id": None,
                },
                audit_context=audit_context,
            )
        except Exception:
            self._attachment_storage.delete(storage_key)
            raise
        return _public_attachment(record.values)

    def download_evidence(
        self,
        movement_id: UUID,
        attachment_id: UUID,
        *,
        actor: CurrentUser,
    ) -> InventoryEvidenceDownload:
        self._require_permission(actor, Permission.INVENTORY_ATTACHMENTS_READ)
        movement = self._get_movement(movement_id)
        self._require_movement_access(movement, actor)
        record = self._repository_provider().get_inventory_attachment(
            movement_id, attachment_id
        )
        if record is None or record.values.get("deleted_at"):
            raise InventoryNotFoundError(f"Không tìm thấy inventory evidence: {attachment_id}")
        content = self._attachment_storage.read(str(record.values["storage_key"]))
        if hashlib.sha256(content).hexdigest() != record.values["checksum"]:
            raise AttachmentStorageError("Checksum inventory evidence không khớp.")
        return InventoryEvidenceDownload(
            filename=str(record.values["original_filename"]),
            media_type=str(record.values["media_type"]),
            content=content,
        )

    def delete_evidence(
        self,
        movement_id: UUID,
        attachment_id: UUID,
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_ATTACHMENTS_DELETE)
        movement = self._get_movement(movement_id)
        self._require_movement_access(movement, actor)
        record = self._repository_provider().delete_inventory_attachment(
            movement_id, attachment_id, audit_context=audit_context
        )
        self._attachment_storage.delete(str(record.values["storage_key"]))
        return _public_attachment(record.values)


def _public_attachment(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key != "storage_key"}

"""Work-order evidence capability."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Callable
from uuid import UUID

from src.asset_management.storage import AttachmentStorage, AttachmentStorageError, validate_attachment
from src.maintenance_management.domain import WORK_ORDER_ATTACHMENT_CATEGORIES
from src.repositories.contracts import MaintenancePlanningRepository, StoredRecord
from src.security.audit import AuditContext
from src.security.service import CurrentUser

from src.maintenance_management.errors import MaintenanceConflictError, MaintenanceDomainError, MaintenanceNotFoundError


@dataclass(frozen=True)
class EvidenceDownload:
    """Authorized attachment bytes and public-safe response metadata."""

    filename: str
    media_type: str
    content: bytes


class MaintenanceEvidenceService:
    """Own evidence policy and storage while the repository owns transactions."""

    def __init__(
        self,
        repository_provider: Callable[[], MaintenancePlanningRepository],
        attachment_storage: AttachmentStorage,
        *,
        attachment_max_size_bytes: int,
        get_work_order: Callable[[UUID], StoredRecord],
        require_work_order_access: Callable[[dict[str, Any], CurrentUser], None],
    ) -> None:
        self._repository_provider = repository_provider
        self._attachment_storage = attachment_storage
        self._attachment_max_size_bytes = attachment_max_size_bytes
        self._get_work_order = get_work_order
        self._require_work_order_access = require_work_order_access

    def list_evidence(self, work_order_id: UUID, *, actor: CurrentUser) -> list[dict[str, Any]]:
        current = dict(self._get_work_order(work_order_id).values)
        self._require_work_order_access(current, actor)
        return [
            dict(record.values)
            for record in self._repository_provider().list_work_order_attachments(work_order_id)
        ]

    def upload_evidence(
        self,
        work_order_id: UUID,
        *,
        category: str,
        filename: str,
        claimed_media_type: str | None,
        content: bytes,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        if category not in WORK_ORDER_ATTACHMENT_CATEGORIES:
            raise MaintenanceDomainError("Evidence category không được hỗ trợ.")
        current = dict(self._get_work_order(work_order_id).values)
        self._require_work_order_access(current, actor)
        if current["status"] in {"verified", "cancelled"}:
            raise MaintenanceConflictError(
                "Không thể thêm evidence cho work order đã verify hoặc cancel."
            )
        validated = validate_attachment(
            filename=filename,
            claimed_media_type=claimed_media_type,
            content=content,
            max_size_bytes=self._attachment_max_size_bytes,
        )
        storage_key = self._attachment_storage.save(validated, namespace="work-orders")
        try:
            record = self._repository_provider().create_work_order_attachment(
                {
                    "work_order_id": work_order_id,
                    "asset_id": current["asset_id"],
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
        work_order_id: UUID,
        attachment_id: UUID,
        *,
        actor: CurrentUser,
    ) -> EvidenceDownload:
        current = dict(self._get_work_order(work_order_id).values)
        self._require_work_order_access(current, actor)
        record = self._repository_provider().get_work_order_attachment(
            work_order_id, attachment_id
        )
        if record is None or record.values.get("deleted_at"):
            raise MaintenanceNotFoundError(
                f"Không tìm thấy evidence attachment: {attachment_id}"
            )
        content = self._attachment_storage.read(str(record.values["storage_key"]))
        if hashlib.sha256(content).hexdigest() != record.values["checksum"]:
            raise AttachmentStorageError("Checksum evidence không khớp metadata.")
        return EvidenceDownload(
            filename=str(record.values["original_filename"]),
            media_type=str(record.values["media_type"]),
            content=content,
        )

    def delete_evidence(
        self,
        work_order_id: UUID,
        attachment_id: UUID,
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = dict(self._get_work_order(work_order_id).values)
        self._require_work_order_access(current, actor)
        if current["status"] == "verified":
            raise MaintenanceConflictError(
                "Evidence của work order verified được giữ bất biến."
            )
        record = self._repository_provider().delete_work_order_attachment(
            work_order_id, attachment_id, audit_context=audit_context
        )
        self._attachment_storage.delete(str(record.values["storage_key"]))
        return _public_attachment(record.values)


def _public_attachment(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key != "storage_key"}

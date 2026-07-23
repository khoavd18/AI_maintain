"""Business rules for asset lifecycle, location hierarchy, attachments, and QR."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from src.asset_management.qr import asset_qr_token, qr_svg_base64
from src.asset_management.storage import (
    AttachmentStorage,
    AttachmentStorageError,
    AttachmentValidationError,
    validate_attachment,
)
from src.config.value_mappings import (
    ASSET_CATEGORY_CODE_TO_VI,
    ASSET_TYPE_CODE_TO_VI,
    ATTACHMENT_CATEGORY_CODE_TO_VI,
    CRITICALITY_CODE_TO_VI,
    LIFECYCLE_STATUS_CODE_TO_VI,
    LOCATION_TYPE_CODE_TO_VI,
    OPERATIONAL_STATUS_CODE_TO_VI,
    OWNERSHIP_TYPE_CODE_TO_VI,
)
from src.repositories.contracts import (
    AssetRepository,
    RecordNotFoundError,
    StoredPage,
    UnsupportedStorageOperationError,
)
from src.security.audit import AuditContext


class AssetDomainError(ValueError):
    """Base class for safe asset-domain errors."""


class AssetDomainNotFoundError(AssetDomainError):
    """Raised when an asset-domain resource is unknown."""


class AssetDomainConflictError(AssetDomainError):
    """Raised for lifecycle, hierarchy, or immutable-state conflicts."""


class ArchivedAssetLookupError(AssetDomainConflictError):
    """Raised when a QR resolves to an archived asset."""


LIFECYCLE_TRANSITIONS = {
    "planned": {"active", "inactive"},
    "active": {"inactive", "retired"},
    "inactive": {"active", "retired"},
    "retired": {"inactive"},
    "archived": set(),
}
OPERATIONAL_TRANSITIONS = {
    "running": {"warning", "fault", "under_maintenance", "out_of_service"},
    "warning": {"running", "fault", "under_maintenance", "out_of_service"},
    "fault": {"running", "under_maintenance", "out_of_service"},
    "under_maintenance": {"running", "warning", "fault", "out_of_service"},
    "out_of_service": {"running", "under_maintenance"},
}
PROFILE_UPDATE_FIELDS = {
    "asset_name",
    "asset_type",
    "asset_category",
    "manufacturer",
    "model",
    "serial_number",
    "production_year",
    "location_id",
    "criticality",
    "installed_at",
    "commissioned_at",
    "ownership_type",
    "description",
    "warranty_start_date",
    "warranty_end_date",
    "warranty_provider",
    "warranty_reference",
    "maintenance_interval_days",
    "last_maintenance_date",
    "next_maintenance_date",
}


class AssetManagementService:
    """Apply lifecycle invariants before delegating atomic writes to a repository."""

    def __init__(
        self,
        repository: AssetRepository | None,
        attachment_storage: AttachmentStorage,
        *,
        attachment_max_size_bytes: int,
        frontend_base_url: str,
    ) -> None:
        self.repository = repository
        self.attachment_storage = attachment_storage
        self.attachment_max_size_bytes = attachment_max_size_bytes
        self.frontend_base_url = frontend_base_url.rstrip("/")

    def options(self) -> dict[str, list[dict[str, str]]]:
        return {
            "asset_types": _options(ASSET_TYPE_CODE_TO_VI, allowed={"hvac", "pump", "generator"}),
            "asset_categories": _options(ASSET_CATEGORY_CODE_TO_VI),
            "criticalities": _options(CRITICALITY_CODE_TO_VI),
            "lifecycle_statuses": _options(LIFECYCLE_STATUS_CODE_TO_VI),
            "operational_statuses": _options(OPERATIONAL_STATUS_CODE_TO_VI),
            "ownership_types": _options(OWNERSHIP_TYPE_CODE_TO_VI),
            "location_types": _options(LOCATION_TYPE_CODE_TO_VI),
            "attachment_categories": _options(ATTACHMENT_CATEGORY_CODE_TO_VI),
        }

    def list_assets(
        self,
        *,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        normalized = dict(filters)
        location_id = normalized.get("location_id")
        if location_id:
            normalized["location_id"] = UUID(str(location_id))
        result = self._repository().list_asset_catalog(
            filters=normalized,
            page=page,
            page_size=page_size,
        )
        return _page_values(result)

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        record = self._repository().get_asset_profile(_normalize_asset_id(asset_id))
        if record is None:
            raise AssetDomainNotFoundError(f"Không tìm thấy asset_id: {asset_id}")
        return dict(record.values)

    def create_asset(
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        asset_id = _normalize_asset_id(str(values["asset_id"]))
        location = self._active_location(UUID(str(values["location_id"])))
        installed_at = _zoned_datetime(values["installed_at"], "installed_at")
        commissioned_at = _optional_zoned_datetime(
            values.get("commissioned_at"), "commissioned_at"
        )
        lifecycle_status = _enum_code(
            values.get("lifecycle_status", "active"),
            LIFECYCLE_STATUS_CODE_TO_VI,
            "lifecycle_status",
        )
        if lifecycle_status in {"retired", "archived"}:
            raise AssetDomainConflictError(
                "Asset mới không thể bắt đầu ở trạng thái retired hoặc archived."
            )
        operational_status = _enum_code(
            values.get("operational_status", "running"),
            OPERATIONAL_STATUS_CODE_TO_VI,
            "operational_status",
        )
        normalized = {
            "asset_id": asset_id,
            "asset_name": _required_text(values["asset_name"], "asset_name"),
            "asset_type": _enum_code(values["asset_type"], ASSET_TYPE_CODE_TO_VI, "asset_type"),
            "asset_category": _enum_code(
                values.get("asset_category", "other"),
                ASSET_CATEGORY_CODE_TO_VI,
                "asset_category",
            ),
            "manufacturer": _optional_text(values.get("manufacturer")),
            "model": _optional_text(values.get("model")),
            "serial_number": _serial_number(values.get("serial_number")),
            "production_year": values.get("production_year"),
            "location": str(location["name"]),
            "location_id": UUID(str(location["id"])),
            "criticality": _enum_code(
                values["criticality"], CRITICALITY_CODE_TO_VI, "criticality"
            ),
            "lifecycle_status": lifecycle_status,
            "operational_status": operational_status,
            "installation_date": installed_at.date(),
            "installed_at": installed_at,
            "commissioned_at": commissioned_at,
            "ownership_type": _enum_code(
                values.get("ownership_type", "owned"),
                OWNERSHIP_TYPE_CODE_TO_VI,
                "ownership_type",
            ),
            "description": _optional_text(values.get("description")),
            "warranty_start_date": values.get("warranty_start_date"),
            "warranty_end_date": values.get("warranty_end_date"),
            "warranty_provider": _optional_text(values.get("warranty_provider")),
            "warranty_reference": _optional_text(values.get("warranty_reference")),
            "last_maintenance_date": values["last_maintenance_date"],
            "maintenance_interval_days": int(values["maintenance_interval_days"]),
            "next_maintenance_date": values["next_maintenance_date"],
            "created_by_user_id": audit_context.actor_user_id,
            "updated_by_user_id": audit_context.actor_user_id,
            "qr_token": asset_qr_token(asset_id),
        }
        _validate_asset_chronology(normalized)
        return dict(
            self._repository().create_asset(
                normalized,
                audit_context=audit_context,
            ).values
        )

    def update_asset(
        self,
        asset_id: str,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        unknown = set(updates) - PROFILE_UPDATE_FIELDS
        if unknown:
            raise AssetDomainConflictError(
                f"Không hỗ trợ cập nhật profile fields: {', '.join(sorted(unknown))}."
            )
        if not updates:
            raise AssetDomainError("Cần cung cấp ít nhất một trường để cập nhật.")
        current = self.get_asset(asset_id)
        if current["lifecycle_status"] == "archived":
            raise AssetDomainConflictError("Cần restore asset trước khi cập nhật hồ sơ.")
        normalized = self._normalize_profile_updates(updates)
        if "location_id" in normalized:
            location = self._active_location(normalized["location_id"])
            normalized["location"] = location["name"]
        combined = _combined_asset_state(current, normalized)
        _validate_asset_chronology(combined)
        actions = ["asset.updated"]
        if "location_id" in normalized:
            actions.append("asset.location_changed")
        return dict(
            self._repository().update_asset(
                _normalize_asset_id(asset_id),
                normalized,
                expected_version=expected_version,
                audit_actions=actions,
                audit_context=audit_context,
            ).values
        )

    def change_operational_status(
        self,
        asset_id: str,
        *,
        operational_status: str,
        expected_version: int,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self.get_asset(asset_id)
        lifecycle = str(current["lifecycle_status"])
        if lifecycle in {"planned", "retired", "archived"}:
            raise AssetDomainConflictError(
                "Lifecycle hiện tại không cho phép thay đổi trạng thái vận hành."
            )
        target = _enum_code(
            operational_status,
            OPERATIONAL_STATUS_CODE_TO_VI,
            "operational_status",
        )
        source = str(current["operational_status"])
        if target == source or target not in OPERATIONAL_TRANSITIONS[source]:
            raise AssetDomainConflictError(
                f"Chuyển trạng thái vận hành không hợp lệ: {source} -> {target}."
            )
        if lifecycle == "inactive" and target != "out_of_service":
            raise AssetDomainConflictError(
                "Asset inactive chỉ có thể giữ trạng thái out_of_service."
            )
        return dict(
            self._repository().update_asset(
                _normalize_asset_id(asset_id),
                {"operational_status": target},
                expected_version=expected_version,
                audit_actions=["asset.operational_status_changed"],
                audit_context=audit_context,
            ).values
        )

    def transition_lifecycle(
        self,
        asset_id: str,
        *,
        lifecycle_status: str,
        expected_version: int,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self.get_asset(asset_id)
        source = str(current["lifecycle_status"])
        target = _enum_code(
            lifecycle_status,
            LIFECYCLE_STATUS_CODE_TO_VI,
            "lifecycle_status",
        )
        if target == "archived":
            raise AssetDomainConflictError("Dùng endpoint archive với lý do lưu trữ.")
        if target == source or target not in LIFECYCLE_TRANSITIONS[source]:
            raise AssetDomainConflictError(
                f"Chuyển lifecycle không hợp lệ: {source} -> {target}."
            )
        updates: dict[str, Any] = {"lifecycle_status": target}
        if target == "retired":
            updates.update(retired_at=_utc_now(), operational_status="out_of_service")
        elif source == "retired":
            updates["retired_at"] = None
        if target == "inactive":
            updates["operational_status"] = "out_of_service"
        return dict(
            self._repository().update_asset(
                _normalize_asset_id(asset_id),
                updates,
                expected_version=expected_version,
                audit_actions=["asset.lifecycle_transitioned"],
                audit_context=audit_context,
            ).values
        )

    def archive_asset(
        self,
        asset_id: str,
        *,
        archive_reason: str,
        expected_version: int,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self.get_asset(asset_id)
        if current["lifecycle_status"] == "archived":
            raise AssetDomainConflictError("Asset đã ở trạng thái archived.")
        reason = _required_text(archive_reason, "archive_reason")
        if len(reason) < 5:
            raise AssetDomainError("Lý do archive cần ít nhất 5 ký tự.")
        updates = {
            "lifecycle_status_before_archive": current["lifecycle_status"],
            "operational_status_before_archive": current["operational_status"],
            "lifecycle_status": "archived",
            "operational_status": "out_of_service",
            "archived_at": _utc_now(),
            "archive_reason": reason,
        }
        return dict(
            self._repository().update_asset(
                _normalize_asset_id(asset_id),
                updates,
                expected_version=expected_version,
                audit_actions=["asset.archived"],
                audit_context=audit_context,
            ).values
        )

    def restore_asset(
        self,
        asset_id: str,
        *,
        expected_version: int,
        lifecycle_status: str | None,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self.get_asset(asset_id)
        if current["lifecycle_status"] != "archived":
            raise AssetDomainConflictError("Chỉ asset archived mới có thể restore.")
        previous_lifecycle = current.get("lifecycle_status_before_archive")
        target = lifecycle_status or previous_lifecycle or "inactive"
        if target == "retired":
            target = "inactive"
        target = _enum_code(target, LIFECYCLE_STATUS_CODE_TO_VI, "lifecycle_status")
        if target not in {"planned", "active", "inactive"}:
            raise AssetDomainConflictError("Restore chỉ hỗ trợ planned, active hoặc inactive.")
        previous_operational = current.get("operational_status_before_archive") or "out_of_service"
        if target in {"planned", "inactive"}:
            previous_operational = "out_of_service"
        updates = {
            "lifecycle_status": target,
            "operational_status": previous_operational,
            "lifecycle_status_before_archive": None,
            "operational_status_before_archive": None,
            "archived_at": None,
            "archive_reason": None,
            "retired_at": None,
        }
        return dict(
            self._repository().update_asset(
                _normalize_asset_id(asset_id),
                updates,
                expected_version=expected_version,
                audit_actions=["asset.restored"],
                audit_context=audit_context,
            ).values
        )

    def ensure_ticket_allowed(self, asset_id: str) -> None:
        current = self.get_asset(asset_id)
        if current["lifecycle_status"] in {"retired", "archived"}:
            raise AssetDomainConflictError(
                "Asset retired hoặc archived không thể nhận ticket mới. Hãy restore trước."
            )

    def list_locations(self, *, include_archived: bool) -> list[dict[str, Any]]:
        return [
            dict(record.values)
            for record in self._repository().list_locations(include_archived=include_archived)
        ]

    def create_location(
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        parent_id = values.get("parent_id")
        if parent_id is not None:
            self._active_location(UUID(str(parent_id)))
        normalized = {
            "code": _location_code(values["code"]),
            "name": _required_text(values["name"], "name"),
            "location_type": _enum_code(
                values["location_type"], LOCATION_TYPE_CODE_TO_VI, "location_type"
            ),
            "parent_id": UUID(str(parent_id)) if parent_id else None,
            "description": _optional_text(values.get("description")),
        }
        return dict(
            self._repository().create_location(
                normalized,
                audit_context=audit_context,
            ).values
        )

    def update_location(
        self,
        location_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self._location(location_id)
        if not current["is_active"]:
            raise AssetDomainConflictError("Không thể sửa vị trí đã archive.")
        allowed = {"code", "name", "location_type", "parent_id", "description"}
        if not updates or set(updates) - allowed:
            raise AssetDomainError("Yêu cầu cập nhật vị trí không hợp lệ.")
        normalized = dict(updates)
        if "code" in normalized:
            normalized["code"] = _location_code(normalized["code"])
        if "name" in normalized:
            normalized["name"] = _required_text(normalized["name"], "name")
        if "description" in normalized:
            normalized["description"] = _optional_text(normalized["description"])
        if "location_type" in normalized:
            normalized["location_type"] = _enum_code(
                normalized["location_type"], LOCATION_TYPE_CODE_TO_VI, "location_type"
            )
        if "parent_id" in normalized:
            parent = normalized["parent_id"]
            normalized["parent_id"] = UUID(str(parent)) if parent else None
            self._validate_location_parent(location_id, normalized["parent_id"])
        return dict(
            self._repository().update_location(
                location_id,
                normalized,
                expected_version=expected_version,
                audit_action="location.updated",
                audit_context=audit_context,
            ).values
        )

    def archive_location(
        self,
        location_id: UUID,
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        current = self._location(location_id)
        if not current["is_active"]:
            raise AssetDomainConflictError("Vị trí đã được archive.")
        locations = self.list_locations(include_archived=True)
        if any(
            item["is_active"] and item.get("parent_id") == str(location_id)
            for item in locations
        ):
            raise AssetDomainConflictError(
                "Cần archive các vị trí con đang hoạt động trước vị trí cha."
            )
        return dict(
            self._repository().update_location(
                location_id,
                {"is_active": False},
                expected_version=expected_version,
                audit_action="location.archived",
                audit_context=audit_context,
            ).values
        )

    def list_attachments(self, asset_id: str) -> list[dict[str, Any]]:
        self.get_asset(asset_id)
        return [
            _public_attachment(record.values)
            for record in self._repository().list_attachments(
                _normalize_asset_id(asset_id)
            )
        ]

    def upload_attachment(
        self,
        asset_id: str,
        *,
        category: str,
        filename: str,
        media_type: str | None,
        content: bytes,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        asset = self.get_asset(asset_id)
        if asset["lifecycle_status"] == "archived":
            raise AssetDomainConflictError("Cần restore asset trước khi tải tệp mới.")
        category_code = _enum_code(
            category,
            ATTACHMENT_CATEGORY_CODE_TO_VI,
            "category",
        )
        validated = validate_attachment(
            filename=filename,
            claimed_media_type=media_type,
            content=content,
            max_size_bytes=self.attachment_max_size_bytes,
        )
        if category_code == "asset_photo" and not validated.media_type.startswith("image/"):
            raise AttachmentValidationError("Ảnh thiết bị phải là PNG, JPG hoặc JPEG.")
        storage_key = self.attachment_storage.save(validated)
        try:
            record = self._repository().create_attachment(
                {
                    "asset_id": _normalize_asset_id(asset_id),
                    "category": category_code,
                    "original_filename": validated.original_filename,
                    "storage_key": storage_key,
                    "media_type": validated.media_type,
                    "size_bytes": validated.size_bytes,
                    "checksum": validated.checksum,
                },
                audit_context=audit_context,
            )
        except Exception:
            try:
                self.attachment_storage.delete(storage_key)
            except AttachmentStorageError:
                pass
            raise
        return _public_attachment(record.values)

    def download_attachment(
        self,
        asset_id: str,
        attachment_id: UUID,
    ) -> tuple[dict[str, Any], bytes]:
        self.get_asset(asset_id)
        record = self._repository().get_attachment(
            _normalize_asset_id(asset_id), attachment_id
        )
        if record is None or record.values.get("deleted_at") is not None:
            raise AssetDomainNotFoundError("Không tìm thấy tệp đính kèm của asset.")
        storage_key = str(record.values["_storage_key"])
        content = self.attachment_storage.read(storage_key)
        import hashlib

        if hashlib.sha256(content).hexdigest() != record.values["checksum"]:
            raise AttachmentStorageError("Checksum tệp đính kèm không khớp metadata.")
        return _public_attachment(record.values), content

    def delete_attachment(
        self,
        asset_id: str,
        attachment_id: UUID,
        *,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self.get_asset(asset_id)
        try:
            record = self._repository().delete_attachment(
                _normalize_asset_id(asset_id),
                attachment_id,
                audit_context=audit_context,
            )
        except RecordNotFoundError as exc:
            raise AssetDomainNotFoundError(str(exc)) from exc
        storage_cleanup_pending = False
        try:
            self.attachment_storage.delete(str(record.values["_storage_key"]))
        except AttachmentStorageError:
            storage_cleanup_pending = True
        result = _public_attachment(record.values)
        result["storage_cleanup_pending"] = storage_cleanup_pending
        return result

    def qr_payload(self, asset_id: str) -> dict[str, Any]:
        asset = self.get_asset(asset_id)
        token = str(asset["qr_lookup_token"])
        lookup_url = f"{self.frontend_base_url}/scan/assets/{token}"
        return {
            "asset_id": asset["asset_id"],
            "lookup_token": token,
            "lookup_url": lookup_url,
            "svg_base64": qr_svg_base64(lookup_url),
            "label_text": f"{asset['asset_id']} - {asset['asset_name']}",
        }

    def lookup_qr(self, token: UUID) -> dict[str, Any]:
        record = self._repository().get_asset_by_qr_token(token)
        if record is None:
            raise AssetDomainNotFoundError("QR không khớp asset nào.")
        if record.values["lifecycle_status"] == "archived":
            raise ArchivedAssetLookupError(
                "Asset từ QR đã được archive. Liên hệ quản lý để xác minh."
            )
        return dict(record.values)

    def history(self, asset_id: str, *, page: int, page_size: int) -> dict[str, Any]:
        try:
            result = self._repository().list_asset_history(
                _normalize_asset_id(asset_id),
                page=page,
                page_size=page_size,
            )
        except RecordNotFoundError as exc:
            raise AssetDomainNotFoundError(str(exc)) from exc
        return _page_values(result)

    def _normalize_profile_updates(self, updates: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(updates)
        required_fields = {
            "asset_name",
            "asset_type",
            "asset_category",
            "location_id",
            "criticality",
            "installed_at",
            "ownership_type",
            "maintenance_interval_days",
            "last_maintenance_date",
            "next_maintenance_date",
        }
        empty_required = sorted(
            field for field in required_fields if field in normalized and normalized[field] is None
        )
        if empty_required:
            raise AssetDomainError(
                f"Không thể xóa các field bắt buộc: {', '.join(empty_required)}."
            )
        enum_fields = {
            "asset_type": ASSET_TYPE_CODE_TO_VI,
            "asset_category": ASSET_CATEGORY_CODE_TO_VI,
            "criticality": CRITICALITY_CODE_TO_VI,
            "ownership_type": OWNERSHIP_TYPE_CODE_TO_VI,
        }
        for field, mapping in enum_fields.items():
            if field in normalized:
                normalized[field] = _enum_code(normalized[field], mapping, field)
        for field in (
            "manufacturer",
            "model",
            "description",
            "warranty_provider",
            "warranty_reference",
        ):
            if field in normalized:
                normalized[field] = _optional_text(normalized[field])
        if "asset_name" in normalized:
            normalized["asset_name"] = _required_text(normalized["asset_name"], "asset_name")
        if "serial_number" in normalized:
            normalized["serial_number"] = _serial_number(normalized["serial_number"])
        if "location_id" in normalized:
            normalized["location_id"] = UUID(str(normalized["location_id"]))
        if "installed_at" in normalized:
            normalized["installed_at"] = _zoned_datetime(
                normalized["installed_at"], "installed_at"
            )
            normalized["installation_date"] = normalized["installed_at"].date()
        if "commissioned_at" in normalized:
            normalized["commissioned_at"] = _optional_zoned_datetime(
                normalized["commissioned_at"], "commissioned_at"
            )
        return normalized

    def _active_location(self, location_id: UUID) -> dict[str, Any]:
        location = self._location(location_id)
        if not location["is_active"]:
            raise AssetDomainConflictError("Không thể gán asset vào vị trí đã archive.")
        return location

    def _location(self, location_id: UUID) -> dict[str, Any]:
        record = self._repository().get_location(location_id)
        if record is None:
            raise AssetDomainNotFoundError(f"Không tìm thấy location_id: {location_id}")
        return dict(record.values)

    def _validate_location_parent(
        self,
        location_id: UUID,
        parent_id: UUID | None,
    ) -> None:
        if parent_id is None:
            return
        if parent_id == location_id:
            raise AssetDomainConflictError("Vị trí không thể là parent của chính nó.")
        parent = self._active_location(parent_id)
        locations = {
            UUID(str(item["id"])): item
            for item in self.list_locations(include_archived=True)
        }
        cursor: dict[str, Any] | None = parent
        visited: set[UUID] = set()
        while cursor is not None:
            cursor_id = UUID(str(cursor["id"]))
            if cursor_id == location_id:
                raise AssetDomainConflictError("Parent mới tạo vòng lặp trong cây vị trí.")
            if cursor_id in visited:
                raise AssetDomainConflictError("Cây vị trí hiện tại có vòng lặp không hợp lệ.")
            visited.add(cursor_id)
            next_id = cursor.get("parent_id")
            cursor = locations.get(UUID(str(next_id))) if next_id else None

    def _repository(self) -> AssetRepository:
        if self.repository is None:
            raise UnsupportedStorageOperationError(
                "Asset Management writes require PostgreSQL product mode; CSV is compatibility-only."
            )
        return self.repository


def _options(
    mapping: dict[str, str],
    *,
    allowed: set[str] | None = None,
) -> list[dict[str, str]]:
    return [
        {"code": code, "display_name": display_name}
        for code, display_name in mapping.items()
        if allowed is None or code in allowed
    ]


def _page_values(page: StoredPage) -> dict[str, Any]:
    return {
        "items": [dict(record.values) for record in page.items],
        "page": page.page,
        "page_size": page.page_size,
        "total": page.total,
        "total_pages": (page.total + page.page_size - 1) // page.page_size,
    }


def _normalize_asset_id(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized or len(normalized) > 50:
        raise AssetDomainError("asset_id không hợp lệ.")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if any(character not in allowed for character in normalized):
        raise AssetDomainError("asset_id chỉ hỗ trợ chữ cái, số, dấu gạch dưới hoặc gạch ngang.")
    return normalized


def _enum_code(value: Any, mapping: dict[str, str], field: str) -> str:
    code = str(value)
    if code not in mapping:
        raise AssetDomainError(f"Giá trị {field} không được hỗ trợ: {code}")
    return code


def _required_text(value: Any, field: str) -> str:
    normalized = str(value).strip() if value is not None else ""
    if not normalized:
        raise AssetDomainError(f"{field} không được để trống.")
    return normalized


def _optional_text(value: Any) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def _serial_number(value: Any) -> str | None:
    normalized = _optional_text(value)
    return normalized.upper() if normalized else None


def _location_code(value: Any) -> str:
    normalized = _required_text(value, "code").upper()
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if len(normalized) > 50 or any(character not in allowed for character in normalized):
        raise AssetDomainError("Location code chỉ hỗ trợ chữ cái, số, '_' hoặc '-'.")
    return normalized


def _zoned_datetime(value: Any, field: str) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AssetDomainError(f"{field} phải có timezone.")
    return parsed.astimezone(timezone.utc)


def _optional_zoned_datetime(value: Any, field: str) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    return _zoned_datetime(value, field)


def _validate_asset_chronology(values: dict[str, Any]) -> None:
    installed_at = values["installed_at"]
    commissioned_at = values.get("commissioned_at")
    if commissioned_at and commissioned_at < installed_at:
        raise AssetDomainError("commissioned_at không được sớm hơn installed_at.")
    warranty_start = values.get("warranty_start_date")
    warranty_end = values.get("warranty_end_date")
    if warranty_start and warranty_end and warranty_end < warranty_start:
        raise AssetDomainError("warranty_end_date không được sớm hơn warranty_start_date.")
    last_date = values["last_maintenance_date"]
    next_date = values["next_maintenance_date"]
    if next_date < last_date:
        raise AssetDomainError(
            "next_maintenance_date không được sớm hơn last_maintenance_date."
        )
    if int(values["maintenance_interval_days"]) <= 0:
        raise AssetDomainError("maintenance_interval_days phải lớn hơn 0.")


def _combined_asset_state(
    current: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    combined = dict(current)
    combined.update(updates)
    for field in ("last_maintenance_date", "next_maintenance_date"):
        value = combined[field]
        if isinstance(value, str):
            combined[field] = date.fromisoformat(value)
    if isinstance(combined["installed_at"], str):
        combined["installed_at"] = _zoned_datetime(combined["installed_at"], "installed_at")
    if isinstance(combined.get("commissioned_at"), str):
        combined["commissioned_at"] = _optional_zoned_datetime(
            combined["commissioned_at"], "commissioned_at"
        )
    for field in ("warranty_start_date", "warranty_end_date"):
        value = combined.get(field)
        if isinstance(value, str):
            combined[field] = date.fromisoformat(value)
    return combined


def _public_attachment(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key != "_storage_key"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

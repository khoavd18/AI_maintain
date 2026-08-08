"""Storage-neutral asset lifecycle repository contract."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from src.security.audit_context import AuditContext

from .shared import StoredPage, StoredRecord


class AssetRepository(Protocol):
    """Persistence operations for canonical asset lifecycle management."""

    backend_name: str

    def list_asset_catalog(
        self,
        *,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> StoredPage: ...

    def get_asset_profile(self, asset_id: str) -> StoredRecord | None: ...

    def get_asset_by_qr_token(self, token: UUID) -> StoredRecord | None: ...

    def create_asset(
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def update_asset(
        self,
        asset_id: str,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_actions: list[str],
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def list_locations(self, *, include_archived: bool) -> list[StoredRecord]: ...

    def get_location(self, location_id: UUID) -> StoredRecord | None: ...

    def create_location(
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def update_location(
        self,
        location_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_action: str,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def list_attachments(
        self,
        asset_id: str,
        *,
        include_deleted: bool = False,
    ) -> list[StoredRecord]: ...

    def get_attachment(self, asset_id: str, attachment_id: UUID) -> StoredRecord | None: ...

    def create_attachment(
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def delete_attachment(
        self,
        asset_id: str,
        attachment_id: UUID,
        *,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def list_asset_history(
        self,
        asset_id: str,
        *,
        page: int,
        page_size: int,
    ) -> StoredPage: ...

"""Storage-neutral repository contract for spare-parts inventory."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from src.security.audit_context import AuditContext

from .shared import StoredPage, StoredRecord


class InventoryRepository(Protocol):
    """Persistence operations for the spare-parts inventory bounded context."""

    backend_name: str

    def list_categories(self, *, include_inactive: bool) -> list[StoredRecord]: ...

    def create_category(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord: ...

    def list_units(self, *, include_inactive: bool) -> list[StoredRecord]: ...

    def create_unit(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord: ...

    def list_parts(
        self,
        *,
        filters: dict[str, Any],
        sort_by: str,
        sort_direction: str,
        page: int,
        page_size: int,
    ) -> StoredPage: ...

    def get_part(self, part_id: UUID) -> StoredRecord | None: ...

    def create_part(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord: ...

    def update_part(
        self,
        part_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_action: str,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def list_stock_locations(self, *, include_archived: bool) -> list[StoredRecord]: ...

    def get_stock_location(self, location_id: UUID) -> StoredRecord | None: ...

    def create_stock_location(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord: ...

    def update_stock_location(
        self,
        location_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_action: str,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def upsert_reorder_configuration(
        self,
        values: dict[str, Any],
        *,
        expected_version: int | None,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def list_balances(
        self,
        *,
        filters: dict[str, Any],
        sort_by: str,
        sort_direction: str,
        page: int,
        page_size: int,
    ) -> StoredPage: ...

    def list_movements(
        self, *, filters: dict[str, Any], page: int, page_size: int
    ) -> StoredPage: ...

    def get_movement(self, movement_id: UUID) -> StoredRecord | None: ...

    def create_opening_balance(
        self,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def receive_stock(
        self,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def transfer_stock(
        self,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> dict[str, StoredRecord | UUID]: ...

    def adjust_stock(
        self,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def create_requirement(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord: ...

    def get_requirement(self, requirement_id: UUID) -> StoredRecord | None: ...

    def reserve_stock(
        self,
        requirement_id: UUID,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        expected_requirement_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def get_reservation(self, reservation_id: UUID) -> StoredRecord | None: ...

    def list_reservations(
        self, *, filters: dict[str, Any], page: int, page_size: int
    ) -> StoredPage: ...

    def close_reservation(
        self,
        reservation_id: UUID,
        *,
        target_status: str,
        reason: str,
        expected_version: int,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def replace_reservation(
        self,
        reservation_id: UUID,
        values: dict[str, Any],
        *,
        expected_version: int,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def issue_stock(
        self,
        work_order_id: UUID,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def get_issue(self, issue_id: UUID) -> StoredRecord | None: ...

    def consume_issue(
        self,
        issue_id: UUID,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def return_issue(
        self,
        issue_id: UUID,
        values: dict[str, Any],
        *,
        idempotency_key: str,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def get_work_order_state(self, work_order_id: UUID) -> StoredRecord | None: ...

    def work_order_parts(self, work_order_id: UUID) -> StoredRecord: ...

    def inventory_metrics(self) -> StoredRecord: ...

    def list_inventory_attachments(
        self, movement_id: UUID, *, include_deleted: bool = False
    ) -> list[StoredRecord]: ...

    def get_inventory_attachment(
        self, movement_id: UUID, attachment_id: UUID
    ) -> StoredRecord | None: ...

    def create_inventory_attachment(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord: ...

    def delete_inventory_attachment(
        self, movement_id: UUID, attachment_id: UUID, *, audit_context: AuditContext
    ) -> StoredRecord: ...

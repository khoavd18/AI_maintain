"""Storage-neutral repository contracts for transactional maintenance data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol
from uuid import UUID

from src.security.audit import AuditContext


class RepositoryError(RuntimeError):
    """Base class for persistence failures safe to map at the API boundary."""


class StorageUnavailableError(RepositoryError):
    """Raised when configured primary storage cannot serve a request."""


class DuplicateIdentifierError(RepositoryError):
    """Raised when a primary or unique identifier already exists."""


class RecordNotFoundError(RepositoryError):
    """Raised when a requested transactional record does not exist."""


class IntegrityViolationError(RepositoryError):
    """Raised when a foreign key or database invariant is violated."""


class StaleRecordError(RepositoryError):
    """Raised when optimistic concurrency rejects a stale write."""


class UnsupportedStorageOperationError(RepositoryError):
    """Raised when a compatibility adapter cannot provide a product write."""


@dataclass(frozen=True)
class StoredRecord:
    """API-shaped values plus a storage-only optimistic version."""

    values: dict[str, Any]
    version: int | None = None


@dataclass(frozen=True)
class StoredPage:
    """Storage-neutral paginated records and their total count."""

    items: list[StoredRecord]
    page: int
    page_size: int
    total: int


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


class MaintenanceRepository(Protocol):
    """Persistence operations required by the existing FastAPI service."""

    backend_name: str

    def check_health(self) -> None:
        """Raise when the configured repository is unavailable or not initialized."""

    def list_assets(self) -> list[StoredRecord]: ...

    def get_asset(self, asset_id: str) -> StoredRecord | None: ...

    def list_tickets(self) -> list[StoredRecord]: ...

    def get_ticket(self, ticket_id: str) -> StoredRecord | None: ...

    def create_ticket(
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext | None = None,
    ) -> StoredRecord: ...

    def update_ticket(
        self,
        ticket_id: str,
        updates: dict[str, Any],
        *,
        expected_version: int | None,
        audit_context: AuditContext | None = None,
    ) -> StoredRecord: ...

    def list_maintenance_logs(self) -> list[StoredRecord]: ...

    def get_maintenance_log(self, log_id: str) -> StoredRecord | None: ...

    def snapshot(self) -> dict[str, list[StoredRecord]]: ...

    def create_maintenance_log(
        self,
        values: dict[str, Any],
        *,
        last_maintenance_date: date,
        next_maintenance_date: date,
        expected_asset_version: int | None,
        expected_ticket_version: int | None,
        audit_context: AuditContext | None = None,
    ) -> StoredRecord: ...


class MaintenancePlanningRepository(Protocol):
    """Storage-neutral operations for plans, templates, and work orders."""

    backend_name: str

    def get_asset_state(self, asset_id: str) -> StoredRecord | None: ...

    def get_ticket_state(self, ticket_id: str) -> StoredRecord | None: ...

    def get_user_state(self, user_id: UUID) -> StoredRecord | None: ...

    def list_technicians(self) -> list[StoredRecord]: ...

    def list_plans(
        self, *, filters: dict[str, Any], page: int, page_size: int
    ) -> StoredPage: ...

    def get_plan(self, plan_id: UUID) -> StoredRecord | None: ...

    def create_plan(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord: ...

    def update_plan(
        self,
        plan_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_actions: list[str],
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def list_templates(
        self, *, filters: dict[str, Any], page: int, page_size: int
    ) -> StoredPage: ...

    def get_template(self, template_id: UUID) -> StoredRecord | None: ...

    def create_template(
        self,
        values: dict[str, Any],
        items: list[dict[str, Any]],
        *,
        audit_action: str,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def archive_template(
        self,
        template_id: UUID,
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def list_work_orders(
        self, *, filters: dict[str, Any], page: int, page_size: int
    ) -> StoredPage: ...

    def get_work_order(self, work_order_id: UUID) -> StoredRecord | None: ...

    def create_work_order(
        self,
        values: dict[str, Any],
        checklist_items: list[dict[str, Any]],
        *,
        audit_action: str,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def update_work_order(
        self,
        work_order_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_action: str,
        audit_context: AuditContext,
        audit_metadata: dict[str, Any] | None = None,
    ) -> StoredRecord: ...

    def update_checklist(
        self,
        work_order_id: UUID,
        responses: list[dict[str, Any]],
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def complete_work_order(
        self,
        work_order_id: UUID,
        work_order_updates: dict[str, Any],
        log_values: dict[str, Any],
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def verify_work_order(
        self,
        work_order_id: UUID,
        *,
        expected_version: int,
        verified_by_user_id: UUID,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def generate_plan_occurrences(
        self,
        plan_id: UUID,
        *,
        schedule_signature: dict[str, Any],
        due_dates: list[date],
        next_due_date: date | None,
        audit_context: AuditContext,
    ) -> dict[str, Any]: ...

    def list_generated_due_dates(self, plan_id: UUID) -> set[date]: ...

    def list_work_order_attachments(
        self, work_order_id: UUID, *, include_deleted: bool = False
    ) -> list[StoredRecord]: ...

    def get_work_order_attachment(
        self, work_order_id: UUID, attachment_id: UUID
    ) -> StoredRecord | None: ...

    def create_work_order_attachment(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord: ...

    def delete_work_order_attachment(
        self,
        work_order_id: UUID,
        attachment_id: UUID,
        *,
        audit_context: AuditContext,
    ) -> StoredRecord: ...


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

    def list_stock_locations(
        self, *, include_archived: bool
    ) -> list[StoredRecord]: ...

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
        self,
        *,
        filters: dict[str, Any],
        page: int,
        page_size: int,
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
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext,
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
        self,
        movement_id: UUID,
        attachment_id: UUID,
        *,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

"""Storage-neutral maintenance and work-order repository contracts."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol
from uuid import UUID

from src.security.audit import AuditContext

from .shared import StoredPage, StoredRecord


class MaintenanceRepository(Protocol):
    """Persistence operations required by the legacy analytics service."""

    backend_name: str

    def check_health(self) -> None: ...

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

    def list_plans(self, *, filters: dict[str, Any], page: int, page_size: int) -> StoredPage: ...

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

    def list_templates(self, *, filters: dict[str, Any], page: int, page_size: int) -> StoredPage: ...

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
        self, template_id: UUID, *, expected_version: int, audit_context: AuditContext
    ) -> StoredRecord: ...

    def list_work_orders(self, *, filters: dict[str, Any], page: int, page_size: int) -> StoredPage: ...

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
        self, work_order_id: UUID, attachment_id: UUID, *, audit_context: AuditContext
    ) -> StoredRecord: ...

"""Storage-neutral ticket, SLA, and escalation repository contract."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from src.security.audit_context import AuditContext

from .shared import StoredRecord


class TicketReferenceKind(str, Enum):
    """Bounded ticket-intake reference types understood by storage adapters."""

    CATEGORY = "category"
    SUBCATEGORY = "subcategory"
    SUPPORT_GROUP = "support_group"
    INTAKE_SOURCE = "intake_source"


class TicketRepository(Protocol):
    """Persistence operations required by the rich ticket application service."""

    backend_name: str

    def get_asset(self, asset_id: str) -> StoredRecord | None: ...

    def get_user(self, user_id: UUID) -> StoredRecord | None: ...

    def find_user(
        self, *, username: str | None = None, role: str | None = None
    ) -> StoredRecord | None: ...

    def has_maintenance_log(self, ticket_id: str) -> bool: ...

    def get_ticket(
        self, ticket_id: str, *, include_timeline: bool = False
    ) -> StoredRecord | None: ...

    def list_tickets(self, *, filters: dict[str, Any]) -> list[StoredRecord]: ...

    def reference_options(self) -> dict[str, list[dict[str, Any]]]: ...

    def get_reference(
        self, kind: TicketReferenceKind, identifier: UUID
    ) -> StoredRecord | None: ...

    def find_sla_policy(
        self,
        *,
        category_id: UUID | None,
        priority: str,
        effective_date: date,
        policy_id: UUID | None = None,
    ) -> StoredRecord | None: ...

    def create_ticket(
        self,
        values: dict[str, Any],
        *,
        sla_values: dict[str, Any] | None,
        sla_events: list[dict[str, Any]],
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def mutate_ticket(
        self,
        ticket_id: str,
        *,
        expected_version: int,
        ticket_updates: dict[str, Any],
        sla_updates: dict[str, Any] | None,
        sla_events: list[dict[str, Any]],
        audit_action: str,
        audit_context: AuditContext,
        audit_metadata: dict[str, Any] | None = None,
    ) -> StoredRecord: ...

    def replace_sla_policy(
        self,
        ticket_id: str,
        *,
        expected_version: int,
        sla_values: dict[str, Any],
        sla_events: list[dict[str, Any]],
        audit_context: AuditContext,
        reason: str,
    ) -> StoredRecord: ...

    def create_comment(
        self,
        ticket_id: str,
        *,
        visibility: str,
        body: str,
        asset_attachment_ids: list[UUID],
        work_order_attachment_ids: list[UUID],
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def list_calendars(self) -> list[StoredRecord]: ...

    def create_calendar(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord: ...

    def update_calendar(
        self,
        calendar_id: UUID,
        values: dict[str, Any],
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def list_policies(self) -> list[StoredRecord]: ...

    def create_policy(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord: ...

    def update_policy(
        self,
        policy_id: UUID,
        values: dict[str, Any],
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord: ...

    def record_escalations(
        self, events: list[dict[str, Any]], *, audit_context: AuditContext
    ) -> list[StoredRecord]: ...

    def seed_defaults(
        self, *, actor_user_id: UUID, audit_context: AuditContext
    ) -> dict[str, int]: ...

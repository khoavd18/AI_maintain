"""Ticket SLA calendar and policy administration operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from src.repositories.contracts import TicketRepository
from src.security.audit import AuditContext
from src.security.permissions import Permission
from src.security.principal import CurrentUser


class TicketSlaAdministrationService:
    """Own SLA reference-data commands without owning repository transactions."""

    def __init__(
        self,
        repository: TicketRepository,
        require_permission: Callable[[CurrentUser, Permission], None],
        calendar_values: Callable[[dict[str, Any], CurrentUser], dict[str, Any]],
        policy_values: Callable[[dict[str, Any], CurrentUser], dict[str, Any]],
    ) -> None:
        self._repository = repository
        self._require_permission = require_permission
        self._calendar_values = calendar_values
        self._policy_values = policy_values

    def list_calendars(self, *, actor: CurrentUser) -> list[dict[str, Any]]:
        self._require_permission(actor, Permission.SLA_POLICIES_READ)
        return [dict(record.values) for record in self._repository.list_calendars()]

    def create_calendar(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.SLA_POLICIES_MANAGE)
        values = self._calendar_values(request, actor=actor)
        return dict(
            self._repository.create_calendar(values, audit_context=audit_context).values
        )

    def update_calendar(
        self,
        calendar_id: UUID,
        request: dict[str, Any],
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.SLA_POLICIES_MANAGE)
        values = self._calendar_values(request, actor=actor)
        values.pop("code", None)
        values.pop("created_by_user_id", None)
        return dict(
            self._repository.update_calendar(
                calendar_id,
                values,
                expected_version=expected_version,
                audit_context=audit_context,
            ).values
        )

    def list_policies(self, *, actor: CurrentUser) -> list[dict[str, Any]]:
        self._require_permission(actor, Permission.SLA_POLICIES_READ)
        return [dict(record.values) for record in self._repository.list_policies()]

    def create_policy(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.SLA_POLICIES_MANAGE)
        values = self._policy_values(request, actor=actor)
        return dict(
            self._repository.create_policy(values, audit_context=audit_context).values
        )

    def update_policy(
        self,
        policy_id: UUID,
        request: dict[str, Any],
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.SLA_POLICIES_MANAGE)
        values = self._policy_values(request, actor=actor)
        values.pop("code", None)
        values.pop("created_by_user_id", None)
        return dict(
            self._repository.update_policy(
                policy_id,
                values,
                expected_version=expected_version,
                audit_context=audit_context,
            ).values
        )

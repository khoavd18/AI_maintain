"""Ticket assignment and reassignment orchestration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from src.repositories.contracts import (
    StoredRecord,
    TicketReferenceKind,
    TicketRepository,
)
from src.security.audit_context import AuditContext
from src.security.permissions import Permission
from src.security.principal import CurrentUser
from src.ticket_management.domain import (
    ASSIGNABLE_STATUSES,
    TicketStatus,
)
from src.ticket_management.errors import TicketConflictError, TicketNotFoundError


class TicketAssignmentService:
    """Own assignment validation and atomic ticket mutation orchestration."""

    def __init__(
        self,
        repository: TicketRepository,
        *,
        require_permission: Callable[[CurrentUser, Permission], None],
        ticket_record: Callable[[str], StoredRecord],
        active_assignee: Callable[[UUID], StoredRecord],
        present: Callable[..., dict[str, Any]],
    ) -> None:
        self._repository = repository
        self._require_permission = require_permission
        self._ticket_record = ticket_record
        self._active_assignee = active_assignee
        self._present = present

    def assign(
        self,
        ticket_id: str,
        *,
        assigned_user_id: UUID | None,
        support_group_id: UUID | None,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_ASSIGN)
        record = self._ticket_record(ticket_id)
        status = TicketStatus(record.values["status"])
        if status not in ASSIGNABLE_STATUSES:
            raise TicketConflictError("Chỉ ticket đang hoạt động mới được phân công.")
        assignee = self._active_assignee(assigned_user_id) if assigned_user_id else None
        if support_group_id is not None:
            group = self._repository.get_reference(
                TicketReferenceKind.SUPPORT_GROUP,
                support_group_id,
            )
            if group is None or not group.values.get("is_active"):
                raise TicketNotFoundError("Không tìm thấy support group đang hoạt động.")
        target_status = (
            TicketStatus.ASSIGNED.value
            if status in {TicketStatus.OPEN, TicketStatus.REOPENED} and assignee
            else status.value
        )
        updates = {
            "assigned_user_id": assigned_user_id,
            "support_group_id": support_group_id,
            "technician_id": (
                str(assignee.values.get("technician_id") or "UNASSIGNED")
                if assignee
                else "UNASSIGNED"
            ),
            "status": target_status,
        }
        result = self._repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates=updates,
            sla_updates=None,
            sla_events=[],
            audit_action="ticket.assigned",
            audit_context=audit_context,
            audit_metadata={
                "assigned_user_id": str(assigned_user_id) if assigned_user_id else None,
                "support_group_id": str(support_group_id) if support_group_id else None,
            },
        )
        return self._present(result.values, actor=actor)

"""Independent rich-ticket mutations outside the lifecycle state machine."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.repositories.contracts import StoredRecord, TicketRepository
from src.security.audit_context import AuditContext
from src.security.permissions import Permission
from src.security.principal import CurrentUser
from src.ticket_management.domain import Impact, Urgency, calculate_priority


class TicketMutationService:
    """Apply named non-lifecycle ticket changes through one repository command."""

    def __init__(
        self,
        repository: TicketRepository,
        *,
        require_permission: Callable[[CurrentUser, Permission], None],
        ticket_record: Callable[[str], StoredRecord],
        normalize_text: Callable[..., str],
        present: Callable[..., dict[str, Any]],
    ) -> None:
        self._repository = repository
        self._require_permission = require_permission
        self._ticket_record = ticket_record
        self._normalize_text = normalize_text
        self._present = present

    def change_priority(
        self,
        ticket_id: str,
        *,
        impact: str,
        urgency: str,
        reason: str,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_UPDATE)
        self._ticket_record(ticket_id)
        selected_impact = Impact(impact)
        selected_urgency = Urgency(urgency)
        priority = calculate_priority(selected_impact, selected_urgency)
        result = self._repository.mutate_ticket(
            ticket_id,
            expected_version=expected_version,
            ticket_updates={
                "impact": selected_impact.value,
                "urgency": selected_urgency.value,
                "priority": priority.value,
            },
            sla_updates=None,
            sla_events=[],
            audit_action="ticket.priority_changed",
            audit_context=audit_context,
            audit_metadata={"reason": self._normalize_text(reason, "reason", 1000)},
        )
        return self._present(result.values, actor=actor)

"""Read-only ticket options and priority preview operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.config.value_mappings import FAILURE_TYPE_CODE_TO_VI
from src.repositories.contracts import TicketRepository
from src.security.permissions import Permission
from src.security.principal import CurrentUser
from src.ticket_management.domain import (
    COMMENT_VISIBILITY_LABELS,
    IMPACT_LABELS,
    PRIORITY_LABELS,
    SLA_STATUS_LABELS,
    TICKET_QUEUE_LABELS,
    TICKET_STATUS_LABELS,
    URGENCY_LABELS,
    Impact,
    Urgency,
    calculate_priority,
    priority_matrix_values,
)


class TicketCatalogueService:
    """Own read-only ticket reference data and server-side priority preview."""

    def __init__(
        self,
        repository: TicketRepository,
        require_permission: Callable[[CurrentUser, Permission], None],
    ) -> None:
        self._repository = repository
        self._require_permission = require_permission

    def options(self, *, actor: CurrentUser) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_READ)
        references = self._repository.reference_options()
        return {
            **references,
            "statuses": _options(TICKET_STATUS_LABELS),
            "impacts": _options(IMPACT_LABELS),
            "urgencies": _options(URGENCY_LABELS),
            "priorities": _options(PRIORITY_LABELS),
            "comment_visibilities": _options(COMMENT_VISIBILITY_LABELS),
            "sla_statuses": _options(SLA_STATUS_LABELS),
            "queues": _options(TICKET_QUEUE_LABELS),
            "failure_categories": [
                {"code": code, "display_name": label}
                for code, label in FAILURE_TYPE_CODE_TO_VI.items()
            ],
            "priority_matrix": priority_matrix_values(),
        }

    def priority_preview(self, *, impact: str, urgency: str) -> dict[str, str]:
        selected_impact = Impact(impact)
        selected_urgency = Urgency(urgency)
        priority = calculate_priority(selected_impact, selected_urgency)
        return {
            "impact": selected_impact.value,
            "impact_display": IMPACT_LABELS[selected_impact],
            "urgency": selected_urgency.value,
            "urgency_display": URGENCY_LABELS[selected_urgency],
            "priority": priority.value,
            "priority_display": PRIORITY_LABELS[priority],
        }


def _options(labels: dict[Any, str]) -> list[dict[str, str]]:
    return [
        {
            "code": item.value if hasattr(item, "value") else str(item),
            "display_name": label,
        }
        for item, label in labels.items()
    ]

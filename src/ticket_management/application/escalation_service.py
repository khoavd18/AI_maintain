"""Ticket escalation eligibility and storage-neutral evaluation orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from src.repositories.contracts import TicketRepository
from src.security.audit_context import AuditContext
from src.security.permissions import Permission
from src.security.principal import CurrentUser
from src.ticket_management.application.sla_runtime_service import TicketSlaRuntimeService
from src.ticket_management.domain import (
    ACTIVE_TICKET_STATUSES,
    ESCALATION_RULE_LABELS,
    EscalationRule,
    SlaClockStatus,
    TicketPriority,
    TicketStatus,
)


class TicketEscalationService:
    """Evaluate eligible ticket clocks; persistence remains repository-owned."""

    def __init__(
        self,
        repository: TicketRepository,
        *,
        require_permission: Callable[[CurrentUser, Permission], None],
        normalize_datetime: Callable[[datetime], datetime],
        utc_now: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._require_permission = require_permission
        self._normalize_datetime = normalize_datetime
        self._utc_now = utc_now

    def evaluate(
        self,
        *,
        dry_run: bool,
        actor: CurrentUser,
        audit_context: AuditContext,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        permission = (
            Permission.ESCALATIONS_EVALUATE
            if dry_run
            else Permission.ESCALATIONS_EXECUTE
        )
        self._require_permission(actor, permission)
        current = self._normalize_datetime(as_of or self._utc_now())
        candidates: list[dict[str, Any]] = []
        for record in self._repository.list_tickets(filters={}):
            item = dict(record.values)
            sla = item.get("sla")
            if TicketStatus(item["status"]) not in ACTIVE_TICKET_STATUSES:
                continue
            projected_sla = (
                TicketSlaRuntimeService.present(item, dict(sla), current) if sla else None
            )
            occurrence = int((sla or {}).get("occurrence_number", 1))
            for clock_name, due_rule, breach_rule in (
                (
                    "first_response",
                    EscalationRule.FIRST_RESPONSE_DUE_SOON,
                    EscalationRule.FIRST_RESPONSE_BREACHED,
                ),
                (
                    "resolution",
                    EscalationRule.RESOLUTION_DUE_SOON,
                    EscalationRule.RESOLUTION_BREACHED,
                ),
            ):
                clock = (projected_sla or {}).get(clock_name)
                if not clock:
                    continue
                status = SlaClockStatus(clock["status"])
                rule = (
                    due_rule
                    if status is SlaClockStatus.DUE_SOON
                    else breach_rule
                    if status is SlaClockStatus.BREACHED
                    else None
                )
                if rule:
                    candidates.append(
                        _candidate(item, rule, current, occurrence, clock_name, clock.get("due_at"))
                    )
            if item["priority"] == TicketPriority.CRITICAL.value:
                candidates.append(
                    _candidate(item, EscalationRule.CRITICAL_PRIORITY, current, occurrence, None, None)
                )
            if int(item["reopen_count"]) >= 2:
                candidates.append(
                    _candidate(
                        item,
                        EscalationRule.REPEATED_REOPEN,
                        current,
                        int(item["reopen_count"]),
                        None,
                        None,
                    )
                )
        created = (
            []
            if dry_run
            else self._repository.record_escalations(candidates, audit_context=audit_context)
        )
        return {
            "dry_run": dry_run,
            "as_of": current.isoformat(),
            "candidate_count": len(candidates),
            "created_count": len(created),
            "candidates": [
                {
                    "ticket_id": item["ticket_id"],
                    "rule_code": item["rule_code"],
                    "rule_display": ESCALATION_RULE_LABELS[EscalationRule(item["rule_code"])],
                    "clock_type": item["clock_type"],
                    "occurrence_number": item["occurrence_number"],
                    "due_at": item["due_at"].isoformat() if item["due_at"] else None,
                }
                for item in candidates
            ],
        }


def _candidate(
    ticket: dict[str, Any],
    rule: EscalationRule,
    current: datetime,
    occurrence: int,
    clock_type: str | None,
    due_at: object,
) -> dict[str, Any]:
    sla = ticket.get("sla")
    return {
        "ticket_id": ticket["ticket_id"],
        "ticket_sla_id": UUID(sla["id"]) if sla else None,
        "rule_code": rule.value,
        "clock_type": clock_type,
        "occurrence_number": occurrence,
        "detected_at": current,
        "due_at": _parse_datetime(due_at),
        "details": {"priority": ticket["priority"], "status": ticket["status"]},
    }


def _parse_datetime(value: object) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Escalation timestamp must include timezone.")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)

"""Ticket SLA runtime policy, clock, and override orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from src.repositories.contracts import StoredRecord, TicketRepository
from src.security.audit_context import AuditContext
from src.security.permissions import Permission
from src.security.principal import CurrentUser
from src.ticket_management.domain import SlaClockStatus, SlaClockType, TicketStatus
from src.ticket_management.domain import ACTIVE_TICKET_STATUSES
from src.ticket_management.errors import TicketConflictError, TicketNotFoundError
from src.ticket_management.sla import (
    BusinessCalendarDefinition,
    derive_clock_status,
    remaining_minutes,
)


@dataclass(frozen=True)
class SlaPolicyOverrideResult:
    """Committed record and the single timestamp used for an SLA override."""

    record: StoredRecord
    occurred_at: datetime


class TicketSlaRuntimeService:
    """Own SLA runtime intent while repositories retain persistence transactions."""

    def __init__(
        self,
        repository: TicketRepository,
        *,
        require_permission: Callable[[CurrentUser, Permission], None],
        ticket_record: Callable[[str], StoredRecord],
        parse_uuid: Callable[..., UUID | None],
        normalize_datetime: Callable[[datetime], datetime],
        normalize_text: Callable[..., str],
        utc_now: Callable[[], datetime],
        facility_timezone: ZoneInfo,
    ) -> None:
        self._repository = repository
        self._require_permission = require_permission
        self._ticket_record = ticket_record
        self._parse_uuid = parse_uuid
        self._normalize_datetime = normalize_datetime
        self._normalize_text = normalize_text
        self._utc_now = utc_now
        self._facility_timezone = facility_timezone

    def override_policy(
        self,
        ticket_id: str,
        *,
        policy_id: UUID,
        reason: str,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> SlaPolicyOverrideResult:
        """Apply one eligible policy through the repository's atomic replacement."""

        self._require_permission(actor, Permission.SLA_POLICIES_MANAGE)
        record = self._ticket_record(ticket_id)
        current = self._normalize_datetime(now or self._utc_now())
        policy = self._repository.find_sla_policy(
            category_id=self._parse_uuid(
                record.values.get("category_id"), "category_id", required=False
            ),
            priority=str(record.values["priority"]),
            effective_date=current.astimezone(self._facility_timezone).date(),
            policy_id=policy_id,
        )
        if policy is None:
            raise TicketNotFoundError("SLA policy không hoạt động hoặc thiếu target phù hợp.")
        occurrence = int((record.values.get("sla") or {}).get("occurrence_number", 0)) + 1
        values, events = self.snapshot(policy.values, started_at=current, occurrence_number=occurrence)
        events[0]["details"] = {"reason": self._normalize_text(reason, "reason", 1000)}
        result = self._repository.replace_sla_policy(
            ticket_id,
            expected_version=expected_version,
            sla_values=values,
            sla_events=events,
            audit_context=audit_context,
            reason=reason,
        )
        return SlaPolicyOverrideResult(record=result, occurred_at=current)

    def summary(
        self, *, actor: CurrentUser, as_of: datetime | None = None
    ) -> dict[str, Any]:
        """Aggregate active SLA clock states from persisted ticket snapshots."""

        self._require_permission(actor, Permission.SLA_POLICIES_READ)
        current = self._normalize_datetime(as_of or self._utc_now())
        items = []
        for record in self._repository.list_tickets(filters={}):
            ticket = dict(record.values)
            sla = ticket.get("sla")
            if sla:
                ticket["sla"] = self.present(ticket, dict(sla), current)
            items.append(ticket)
        active = [item for item in items if TicketStatus(item["status"]) in ACTIVE_TICKET_STATUSES]
        return {
            "as_of": current.isoformat(),
            "active_count": len(active),
            "waiting_count": sum(item["status"] == "waiting" for item in active),
            "critical_count": sum(item["priority"] == "critical" for item in active),
            "due_soon_count": sum(_has_status(item, SlaClockStatus.DUE_SOON) for item in active),
            "breached_count": sum(_has_status(item, SlaClockStatus.BREACHED) for item in active),
            "without_sla_count": sum(item.get("sla") is None for item in active),
        }

    @staticmethod
    def snapshot(
        policy: dict[str, Any],
        *,
        started_at: datetime,
        occurrence_number: int = 1,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Freeze policy/calendar values and start both SLA clocks."""

        calendar_data = policy.get("calendar")
        targets = policy.get("targets") or []
        if not calendar_data or len(targets) != 1:
            raise TicketConflictError("SLA policy thiếu calendar hoặc target.")
        if policy["timezone"] != calendar_data["timezone"]:
            raise TicketConflictError("Timezone của SLA policy và calendar không khớp.")
        calendar = BusinessCalendarDefinition.from_snapshot(
            {
                "timezone": calendar_data["timezone"],
                "periods": calendar_data["periods"],
                "holidays": [item["holiday_date"] for item in calendar_data["holidays"]],
            }
        )
        target = targets[0]
        response_minutes = int(target["first_response_minutes"])
        resolution_minutes = int(target["resolution_minutes"])
        values = {
            "policy_id": UUID(policy["id"]),
            "policy_code": policy["code"],
            "policy_name": policy["name"],
            "calendar_id": UUID(policy["calendar_id"]),
            "calendar_code": policy["calendar_code"],
            "timezone": policy["timezone"],
            "calendar_snapshot": calendar.to_snapshot(),
            "pause_on_waiting": bool(policy["pause_on_waiting"]),
            "due_soon_percent": int(policy["due_soon_percent"]),
            "first_response_target_minutes": response_minutes,
            "resolution_target_minutes": resolution_minutes,
            "started_at": started_at,
            "first_response_due_at": calendar.add_working_minutes(started_at, response_minutes),
            "resolution_due_at": calendar.add_working_minutes(started_at, resolution_minutes),
            "first_response_remaining_minutes": None,
            "resolution_remaining_minutes": None,
            "paused_at": None,
            "resolution_stopped_at": None,
            "occurrence_number": occurrence_number,
        }
        events = [
            _sla_event("policy_applied", started_at, occurrence_number, details={"policy_code": policy["code"]}),
            _sla_event(
                "clock_started",
                started_at,
                occurrence_number,
                clock_type=SlaClockType.FIRST_RESPONSE.value,
            ),
            _sla_event(
                "clock_started",
                started_at,
                occurrence_number,
                clock_type=SlaClockType.RESOLUTION.value,
            ),
        ]
        return values, events

    @staticmethod
    def events_for_first_response(
        sla: dict[str, Any] | None, current: datetime
    ) -> list[dict[str, Any]]:
        """Return immutable first-response SLA event intent, if an SLA exists."""

        if not sla:
            return []
        events = [
            _sla_event(
                "first_response_recorded",
                current,
                sla["occurrence_number"],
                clock_type=SlaClockType.FIRST_RESPONSE.value,
            )
        ]
        if current <= _parse_datetime(sla["first_response_due_at"]):
            events.append(
                _sla_event(
                    "target_met",
                    current,
                    sla["occurrence_number"],
                    clock_type=SlaClockType.FIRST_RESPONSE.value,
                )
            )
        return events

    @staticmethod
    def present(
        ticket: dict[str, Any], sla: dict[str, Any], as_of: datetime
    ) -> dict[str, Any]:
        """Derive read-time clock presentation from immutable SLA source data."""

        calendar = BusinessCalendarDefinition.from_snapshot(sla["calendar_snapshot"])
        paused = _parse_datetime(sla.get("paused_at"))
        stopped = ticket["status"] == TicketStatus.CANCELLED.value
        response_status = derive_clock_status(
            started_at=_parse_datetime(sla["started_at"]),
            due_at=_parse_datetime(sla["first_response_due_at"]),
            completed_at=_parse_datetime(ticket.get("first_response_at")),
            paused_at=paused,
            target_minutes=int(sla["first_response_target_minutes"]),
            as_of=as_of,
            calendar=calendar,
            due_soon_percent=int(sla["due_soon_percent"]),
            stopped=stopped,
        )
        resolution_status = derive_clock_status(
            started_at=_parse_datetime(sla["started_at"]),
            due_at=_parse_datetime(sla["resolution_due_at"]),
            completed_at=_parse_datetime(ticket.get("resolved_at")),
            paused_at=paused,
            target_minutes=int(sla["resolution_target_minutes"]),
            as_of=as_of,
            calendar=calendar,
            due_soon_percent=int(sla["due_soon_percent"]),
            stopped=stopped,
        )
        sla["first_response"] = _clock_values(
            response_status,
            due_at=sla["first_response_due_at"],
            completed_at=ticket.get("first_response_at"),
            remaining=(
                sla.get("first_response_remaining_minutes")
                if response_status is SlaClockStatus.PAUSED
                else remaining_minutes(_parse_datetime(sla["first_response_due_at"]), as_of, calendar=calendar)
            ),
        )
        sla["resolution"] = _clock_values(
            resolution_status,
            due_at=sla["resolution_due_at"],
            completed_at=ticket.get("resolved_at"),
            remaining=(
                sla.get("resolution_remaining_minutes")
                if resolution_status is SlaClockStatus.PAUSED
                else remaining_minutes(_parse_datetime(sla["resolution_due_at"]), as_of, calendar=calendar)
            ),
        )
        return sla


def _sla_event(
    event_type: str,
    occurred_at: datetime,
    occurrence_number: int,
    *,
    clock_type: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "clock_type": clock_type,
        "occurrence_number": int(occurrence_number),
        "occurred_at": occurred_at,
        "details": details,
    }


def _clock_values(
    status: SlaClockStatus,
    *,
    due_at: str,
    completed_at: str | None,
    remaining: int | None,
) -> dict[str, Any]:
    from src.ticket_management.domain import SLA_STATUS_LABELS

    return {
        "status": status.value,
        "status_display": SLA_STATUS_LABELS[status],
        "due_at": due_at,
        "completed_at": completed_at,
        "remaining_business_minutes": remaining,
    }


def _parse_datetime(value: object) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        from src.ticket_management.errors import TicketDomainError

        raise TicketDomainError("Timestamp phải có timezone.")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _has_status(ticket: dict[str, Any], status: SlaClockStatus) -> bool:
    sla = ticket.get("sla") or {}
    return any((sla.get(clock) or {}).get("status") == status.value for clock in ("first_response", "resolution"))

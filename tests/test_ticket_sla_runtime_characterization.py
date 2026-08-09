"""Focused characterization of SLA runtime policy and clock orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.repositories.contracts import StoredRecord
from src.security.audit import AuditContext
from src.security.permissions import ROLE_PERMISSIONS, Permission, Role
from src.security.principal import CurrentUser
from src.ticket_management.application.sla_runtime_service import TicketSlaRuntimeService
from src.ticket_management.errors import TicketAuthorizationError, TicketNotFoundError
from src.ticket_management.sla import BusinessCalendarDefinition, WorkingPeriod


@dataclass
class RecordingSlaRepository:
    ticket: StoredRecord
    policy: StoredRecord | None

    def __post_init__(self) -> None:
        self.find_calls: list[dict[str, Any]] = []
        self.replace_calls: list[dict[str, Any]] = []

    def get_ticket(self, ticket_id: str, *, include_timeline: bool = False) -> StoredRecord:
        del ticket_id, include_timeline
        return self.ticket

    def find_sla_policy(self, **kwargs: Any) -> StoredRecord | None:
        self.find_calls.append(kwargs)
        return self.policy

    def replace_sla_policy(self, ticket_id: str, **kwargs: Any) -> StoredRecord:
        self.replace_calls.append({"ticket_id": ticket_id, **kwargs})
        return self.ticket


def _actor(role: Role = Role.PROPERTY_MANAGER) -> CurrentUser:
    now = datetime(2026, 8, 8, tzinfo=UTC)
    return CurrentUser(
        id=uuid4(),
        username="sla.runtime",
        email=None,
        display_name="SLA runtime",
        role=role,
        permissions=ROLE_PERMISSIONS[role],
        technician_id=None,
        is_active=True,
        version=1,
        session_id=uuid4(),
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )


def _policy() -> StoredRecord:
    calendar_id = uuid4()
    return StoredRecord(
        {
            "id": str(uuid4()),
            "code": "CATEGORY_HIGH",
            "name": "Category high",
            "calendar_id": str(calendar_id),
            "calendar_code": "WEEKDAY",
            "timezone": "Asia/Ho_Chi_Minh",
            "pause_on_waiting": True,
            "due_soon_percent": 20,
            "calendar": {
                "timezone": "Asia/Ho_Chi_Minh",
                "periods": [
                    {"weekday": day, "start_time": "08:00", "end_time": "17:00"}
                    for day in range(5)
                ],
                "holidays": [],
            },
            "targets": [
                {"priority": "high", "first_response_minutes": 30, "resolution_minutes": 240}
            ],
        }
    )


def _ticket() -> StoredRecord:
    return StoredRecord(
        {
            "ticket_id": "TCK-000001",
            "category_id": str(uuid4()),
            "priority": "high",
            "sla": {"occurrence_number": 2},
        },
        version=4,
    )


def _runtime(repository: RecordingSlaRepository) -> TicketSlaRuntimeService:
    def require_permission(actor: CurrentUser, permission: Permission) -> None:
        if not actor.has(permission):
            raise TicketAuthorizationError("Báº¡n khÃ´ng cÃ³ quyá»n thá»±c hiá»‡n thao tÃ¡c ticket nÃ y.")

    def parse_uuid(value: object, _field: str, *, required: bool) -> UUID | None:
        if value is None and not required:
            return None
        return UUID(str(value))

    return TicketSlaRuntimeService(
        repository,  # type: ignore[arg-type]
        require_permission=require_permission,
        ticket_record=repository.get_ticket,
        parse_uuid=parse_uuid,
        normalize_datetime=lambda value: value.astimezone(UTC).replace(microsecond=0),
        normalize_text=lambda value, _field, _maximum: str(value).strip(),
        utc_now=lambda: datetime(2026, 8, 8, 1, tzinfo=UTC),
        facility_timezone=BusinessCalendarDefinition(
            timezone="Asia/Ho_Chi_Minh",
            periods=(WorkingPeriod(0, time(8), time(17)),),
            holidays=frozenset(),
        ).zone,
    )


def test_override_selects_active_policy_for_local_date_and_starts_next_occurrence() -> None:
    repository = RecordingSlaRepository(_ticket(), _policy())
    actor = _actor()
    current = datetime(2026, 8, 8, 18, 30, 45, tzinfo=UTC)

    outcome = _runtime(repository).override_policy(
        "TCK-000001",
        policy_id=UUID(repository.policy.values["id"]),  # type: ignore[union-attr]
        reason="  Policy corrected  ",
        expected_version=4,
        actor=actor,
        audit_context=AuditContext(actor.id, actor.display_name, "sla-runtime"),
        now=current,
    )

    assert outcome.record is repository.ticket
    assert outcome.occurred_at == datetime(2026, 8, 8, 18, 30, 45, tzinfo=UTC).replace(microsecond=0)
    assert repository.find_calls == [
        {
            "category_id": UUID(repository.ticket.values["category_id"]),
            "priority": "high",
            "effective_date": date(2026, 8, 9),
            "policy_id": UUID(repository.policy.values["id"]),  # type: ignore[union-attr]
        }
    ]
    replacement = repository.replace_calls[0]
    assert replacement["sla_values"]["occurrence_number"] == 3
    assert replacement["sla_events"][0]["details"] == {"reason": "Policy corrected"}
    assert [event["event_type"] for event in replacement["sla_events"]] == [
        "policy_applied",
        "clock_started",
        "clock_started",
    ]


def test_override_rejects_missing_or_ineligible_policy_without_a_persistent_mutation() -> None:
    repository = RecordingSlaRepository(_ticket(), None)
    actor = _actor()

    with pytest.raises(TicketNotFoundError, match="SLA policy"):
        _runtime(repository).override_policy(
            "TCK-000001",
            policy_id=uuid4(),
            reason="missing",
            expected_version=4,
            actor=actor,
            audit_context=AuditContext(actor.id, actor.display_name, "sla-runtime-missing"),
        )

    assert len(repository.find_calls) == 1
    assert repository.replace_calls == []


def test_snapshot_and_first_response_events_preserve_deadline_and_target_met_rules() -> None:
    policy = _policy().values
    started = datetime(2026, 8, 3, 1, tzinfo=UTC)

    values, events = TicketSlaRuntimeService.snapshot(policy, started_at=started)
    on_time = TicketSlaRuntimeService.events_for_first_response(values, values["first_response_due_at"])
    late = TicketSlaRuntimeService.events_for_first_response(
        values, values["first_response_due_at"].replace(minute=31)
    )

    assert values["first_response_due_at"] == datetime(2026, 8, 3, 1, 30, tzinfo=UTC)
    assert values["resolution_due_at"] == datetime(2026, 8, 3, 5, tzinfo=UTC)
    assert [event["event_type"] for event in events] == [
        "policy_applied",
        "clock_started",
        "clock_started",
    ]
    assert [event["event_type"] for event in on_time] == ["first_response_recorded", "target_met"]
    assert [event["event_type"] for event in late] == ["first_response_recorded"]

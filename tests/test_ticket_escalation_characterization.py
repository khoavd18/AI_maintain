"""Focused characterization of ticket escalation decisions and idempotent intent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any

import pytest

from src.repositories.contracts import StoredRecord
from src.security.audit_context import AuditContext
from src.security.permissions import Permission, Role
from src.ticket_management.application.escalation_service import TicketEscalationService
from src.ticket_management.errors import TicketAuthorizationError
from src.ticket_management.sla import BusinessCalendarDefinition, WorkingPeriod
from tests.auth_helpers import build_test_user


@dataclass
class RecordingEscalationRepository:
    records: list[StoredRecord]

    def __post_init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def list_tickets(self, *, filters: dict[str, Any]) -> list[StoredRecord]:
        assert filters == {}
        return self.records

    def record_escalations(
        self, events: list[dict[str, Any]], *, audit_context: AuditContext
    ) -> list[StoredRecord]:
        self.calls.append({"events": events, "audit_context": audit_context})
        return [StoredRecord(event) for event in events]


def _calendar_snapshot() -> dict[str, Any]:
    return BusinessCalendarDefinition(
        timezone="Asia/Ho_Chi_Minh",
        periods=tuple(WorkingPeriod(day, time(8), time(17)) for day in range(5)),
        holidays=frozenset(),
    ).to_snapshot()


def _record(
    ticket_id: str,
    *,
    status: str = "in_progress",
    priority: str = "high",
    reopen_count: int = 0,
    sla: dict[str, Any] | None = None,
) -> StoredRecord:
    return StoredRecord(
        {
            "ticket_id": ticket_id,
            "status": status,
            "priority": priority,
            "reopen_count": reopen_count,
            "first_response_at": None,
            "resolved_at": None,
            "sla": sla,
        }
    )


def _sla(*, paused_at: str | None = None) -> dict[str, Any]:
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "occurrence_number": 2,
        "started_at": "2026-08-07T01:00:00+00:00",
        "first_response_due_at": "2026-08-07T02:00:00+00:00",
        "resolution_due_at": "2026-08-10T02:00:00+00:00",
        "first_response_target_minutes": 60,
        "resolution_target_minutes": 240,
        "due_soon_percent": 20,
        "paused_at": paused_at,
        "calendar_snapshot": _calendar_snapshot(),
    }


def _service(repository: RecordingEscalationRepository) -> TicketEscalationService:
    def require_permission(user, permission: Permission) -> None:
        if not user.has(permission):
            raise TicketAuthorizationError("Không có quyền đánh giá escalation.")

    return TicketEscalationService(
        repository,  # type: ignore[arg-type]
        require_permission=require_permission,
        normalize_datetime=lambda value: value.astimezone(UTC).replace(microsecond=0),
        utc_now=lambda: datetime(2026, 8, 10, 3, tzinfo=UTC),
    )


def test_only_active_breached_clocks_and_priority_reopen_rules_become_candidates() -> None:
    repository = RecordingEscalationRepository(
        [
            _record("breached", sla=_sla()),
            _record("paused", status="waiting", sla=_sla(paused_at="2026-08-08T01:00:00+00:00")),
            _record("terminal", status="closed", sla=_sla()),
            _record("critical", priority="critical"),
            _record("reopened", status="reopened", reopen_count=2),
            _record("no-sla"),
        ]
    )
    actor = build_test_user(Role.PROPERTY_MANAGER)
    as_of = datetime(2026, 8, 10, 3, 30, 45, tzinfo=UTC)

    result = _service(repository).evaluate(
        dry_run=True,
        actor=actor,
        audit_context=AuditContext(actor.id, actor.display_name, "escalation-dry-run"),
        as_of=as_of,
    )

    assert result["candidate_count"] == 4
    assert {item["rule_code"] for item in result["candidates"]} == {
        "first_response_breached",
        "resolution_breached",
        "critical_priority",
        "repeated_reopen",
    }
    assert result["as_of"] == "2026-08-10T03:30:45+00:00"
    assert repository.calls == []


def test_execution_passes_one_timestamp_and_repository_owns_created_results() -> None:
    repository = RecordingEscalationRepository([_record("breached", sla=_sla())])
    actor = build_test_user(Role.PROPERTY_MANAGER)
    context = AuditContext(actor.id, actor.display_name, "escalation-execute")
    as_of = datetime(2026, 8, 10, 3, tzinfo=UTC)

    result = _service(repository).evaluate(
        dry_run=False, actor=actor, audit_context=context, as_of=as_of
    )

    assert result["created_count"] == 2
    assert repository.calls[0]["audit_context"] == context
    assert repository.calls[0]["events"][0]["detected_at"] == as_of


def test_permission_is_checked_before_ticket_reads() -> None:
    repository = RecordingEscalationRepository([])
    actor = build_test_user(Role.STOREKEEPER)

    with pytest.raises(TicketAuthorizationError):
        _service(repository).evaluate(
            dry_run=False,
            actor=actor,
            audit_context=AuditContext(actor.id, actor.display_name, "escalation-denied"),
        )

    assert repository.calls == []

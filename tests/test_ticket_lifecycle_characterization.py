"""Focused characterization of the named ticket lifecycle boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, time
from typing import Any
from uuid import uuid4

import pytest

from src.repositories.contracts import StoredRecord
from src.security.audit import AuditContext
from src.security.permissions import ROLE_PERMISSIONS, Role
from src.security.principal import CurrentUser
from src.ticket_management.application.lifecycle_service import TicketLifecycleService
from src.ticket_management.domain import TicketStatus
from src.ticket_management.errors import (
    TicketAuthorizationError,
    TicketConflictError,
    TicketDomainError,
)
from src.ticket_management.sla import BusinessCalendarDefinition, WorkingPeriod
from src.ticket_management.service import (
    TicketWorkflowService,
    _aware_utc,
    _parse_datetime,
    _plain_text,
    _sla_event,
    _utc_now,
)


@dataclass
class RecordingTicketRepository:
    record: StoredRecord
    maintenance_log: bool = True

    def __post_init__(self) -> None:
        self.read_count = 0
        self.calls: list[dict[str, Any]] = []

    def get_ticket(self, ticket_id: str, *, include_timeline: bool = False) -> StoredRecord:
        del ticket_id, include_timeline
        self.read_count += 1
        return self.record

    def has_maintenance_log(self, ticket_id: str) -> bool:
        del ticket_id
        return self.maintenance_log

    def mutate_ticket(self, ticket_id: str, **kwargs: Any) -> StoredRecord:
        self.calls.append({"ticket_id": ticket_id, **kwargs})
        values = dict(self.record.values)
        values.update(kwargs["ticket_updates"])
        if kwargs["sla_updates"] is not None and values.get("sla") is not None:
            values["sla"] = {**values["sla"], **kwargs["sla_updates"]}
        self.record = StoredRecord(values, version=(self.record.version or 0) + 1)
        return self.record


def _actor(role: Role, *, technician_id: str | None = None) -> CurrentUser:
    now = datetime(2026, 8, 8, tzinfo=UTC)
    return CurrentUser(
        id=uuid4(),
        username=f"{role.value}.lifecycle",
        email=None,
        display_name=f"{role.value} lifecycle",
        role=role,
        permissions=ROLE_PERMISSIONS[role],
        technician_id=technician_id,
        is_active=True,
        version=1,
        session_id=uuid4(),
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )


def _audit(actor: CurrentUser) -> AuditContext:
    return AuditContext(actor.id, actor.display_name, "lifecycle-characterization")


def _calendar_snapshot() -> dict[str, Any]:
    return BusinessCalendarDefinition(
        timezone="Asia/Ho_Chi_Minh",
        periods=tuple(WorkingPeriod(day, time(8), time(17)) for day in range(5)),
        holidays=frozenset(),
    ).to_snapshot()


def _record(status: TicketStatus, *, actor: CurrentUser, sla: dict[str, Any] | None = None) -> StoredRecord:
    return StoredRecord(
        {
            "ticket_id": "TCK-000001",
            "status": status.value,
            "assigned_user_id": str(actor.id),
            "technician_id": actor.technician_id or "UNASSIGNED",
            "first_response_at": None,
            "created_at": "2026-08-07T01:00:00+00:00",
            "waiting_previous_status": (
                TicketStatus.IN_PROGRESS.value if status is TicketStatus.WAITING else None
            ),
            "waiting_reason": "đang chờ" if status is TicketStatus.WAITING else None,
            "reopen_count": 1,
            "resolved_at": (
                "2026-08-07T02:00:00+00:00"
                if status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}
                else None
            ),
            "closed_at": "2026-08-07T03:00:00+00:00" if status is TicketStatus.CLOSED else None,
            "sla": sla,
        },
        version=3,
    )


def _service(repository: RecordingTicketRepository) -> TicketLifecycleService:
    def ticket_for_action(ticket_id: str, actor: CurrentUser) -> StoredRecord:
        record = repository.get_ticket(ticket_id)
        if actor.role is Role.TECHNICIAN and not TicketWorkflowService._is_owned(
            actor, record.values
        ):
            raise TicketAuthorizationError(
                "Ticket không được phân công cho kỹ thuật viên đang đăng nhập."
            )
        return record

    return TicketLifecycleService(
        repository,  # type: ignore[arg-type]
        require_permission=TicketWorkflowService._require_permission,
        ticket_record=repository.get_ticket,
        ticket_for_action=ticket_for_action,
        sla_events_for_first_response=lambda sla, current: (
            [{"event_type": "first_response_recorded", "occurred_at": current}]
            if sla
            else []
        ),
        sla_event=_sla_event,
        present=lambda values, **_: dict(values),
        normalize_datetime=_aware_utc,
        parse_datetime=_parse_datetime,
        normalize_text=_plain_text,
        utc_now=_utc_now,
    )


def test_permission_is_checked_before_ticket_lookup() -> None:
    actor = _actor(Role.STOREKEEPER)
    repository = RecordingTicketRepository(_record(TicketStatus.OPEN, actor=actor))

    with pytest.raises(TicketAuthorizationError):
        _service(repository).acknowledge(
            "TCK-000001",
            expected_version=3,
            actor=actor,
            audit_context=_audit(actor),
        )

    assert repository.read_count == 0
    assert repository.calls == []


def test_direct_inactive_principal_is_not_revalidated_by_lifecycle_service() -> None:
    actor = replace(_actor(Role.HELPDESK), is_active=False)
    repository = RecordingTicketRepository(_record(TicketStatus.OPEN, actor=actor))

    result = _service(repository).acknowledge(
        "TCK-000001",
        expected_version=3,
        actor=actor,
        audit_context=_audit(actor),
        now=datetime(2026, 8, 8, 1, tzinfo=UTC),
    )

    assert result["first_response_at"] is not None
    assert repository.calls[0]["audit_action"] == "ticket.first_response_recorded"


def test_invalid_state_wins_before_timestamp_or_mutation() -> None:
    actor = _actor(Role.PROPERTY_MANAGER)
    repository = RecordingTicketRepository(_record(TicketStatus.CLOSED, actor=actor))

    with pytest.raises(
        TicketConflictError,
        match="Không thể bắt đầu ticket từ trạng thái closed",
    ):
        _service(repository).start(
            "TCK-000001",
            expected_version=3,
            actor=actor,
            audit_context=_audit(actor),
            now=datetime(2026, 8, 8, 1, tzinfo=UTC),
        )

    assert repository.calls == []


def test_technician_ownership_is_checked_for_execution_actions() -> None:
    owner = _actor(Role.TECHNICIAN, technician_id="TECH-OWNER")
    other = _actor(Role.TECHNICIAN, technician_id="TECH-OTHER")
    repository = RecordingTicketRepository(_record(TicketStatus.ASSIGNED, actor=owner))

    with pytest.raises(TicketAuthorizationError, match="không được phân công"):
        _service(repository).start(
            "TCK-000001",
            expected_version=3,
            actor=other,
            audit_context=_audit(other),
        )

    assert repository.read_count == 1
    assert repository.calls == []


def test_hold_and_resume_preserve_pause_payload_and_event_order() -> None:
    actor = _actor(Role.TECHNICIAN, technician_id="TECH-OWNER")
    started = datetime(2026, 8, 7, 1, tzinfo=UTC)
    sla = {
        "pause_on_waiting": True,
        "calendar_snapshot": _calendar_snapshot(),
        "first_response_due_at": "2026-08-07T04:00:00+00:00",
        "resolution_due_at": "2026-08-08T04:00:00+00:00",
        "occurrence_number": 1,
        "first_response_remaining_minutes": None,
        "resolution_remaining_minutes": None,
        "paused_at": None,
        "resolution_target_minutes": 240,
    }
    repository = RecordingTicketRepository(
        _record(TicketStatus.IN_PROGRESS, actor=actor, sla=sla)
    )
    service = _service(repository)

    held = service.hold(
        "TCK-000001",
        reason="Chờ kiểm tra an toàn",
        expected_version=3,
        actor=actor,
        audit_context=_audit(actor),
        now=started,
    )
    resumed = service.resume(
        "TCK-000001",
        expected_version=4,
        actor=actor,
        audit_context=_audit(actor),
        now=datetime(2026, 8, 8, 1, tzinfo=UTC),
    )

    assert held["status"] == TicketStatus.WAITING.value
    assert repository.calls[0]["audit_action"] == "ticket.placed_on_hold"
    assert repository.calls[0]["sla_updates"]["paused_at"] == started
    assert repository.calls[0]["sla_events"][0]["event_type"] == "paused"
    assert resumed["status"] == TicketStatus.IN_PROGRESS.value
    assert repository.calls[1]["audit_action"] == "ticket.resumed"
    assert repository.calls[1]["sla_updates"]["paused_at"] is None
    assert repository.calls[1]["sla_events"][0]["event_type"] == "resumed"


def test_resolve_requires_log_then_chronological_timestamp() -> None:
    actor = _actor(Role.TECHNICIAN, technician_id="TECH-OWNER")
    repository = RecordingTicketRepository(
        _record(TicketStatus.IN_PROGRESS, actor=actor),
        maintenance_log=False,
    )
    service = _service(repository)

    with pytest.raises(TicketConflictError, match="maintenance log"):
        service.resolve(
            "TCK-000001",
            expected_version=3,
            actor=actor,
            audit_context=_audit(actor),
            resolved_at=datetime(2026, 8, 7, 2, tzinfo=UTC),
        )
    repository.maintenance_log = True
    with pytest.raises(TicketDomainError, match="resolved_at không được sớm"):
        service.resolve(
            "TCK-000001",
            expected_version=3,
            actor=actor,
            audit_context=_audit(actor),
            resolved_at=datetime(2026, 8, 6, 2, tzinfo=UTC),
        )

    assert repository.calls == []


def test_reopen_and_cancel_keep_reason_and_audit_contract() -> None:
    actor = _actor(Role.PROPERTY_MANAGER)
    repository = RecordingTicketRepository(_record(TicketStatus.CLOSED, actor=actor))
    service = _service(repository)

    service.reopen(
        "TCK-000001",
        reason="Tái xuất hiện",
        expected_version=3,
        actor=actor,
        audit_context=_audit(actor),
        now=datetime(2026, 8, 8, 1, tzinfo=UTC),
    )
    reopen_call = repository.calls[0]
    assert reopen_call["audit_action"] == "ticket.reopened"
    assert reopen_call["audit_metadata"] == {"reason": "Tái xuất hiện"}
    assert reopen_call["ticket_updates"]["status"] == TicketStatus.REOPENED.value

    repository.record = _record(TicketStatus.OPEN, actor=actor)
    service.cancel(
        "TCK-000001",
        reason="Yêu cầu đã hủy",
        expected_version=3,
        actor=actor,
        audit_context=_audit(actor),
        now=datetime(2026, 8, 8, 1, tzinfo=UTC),
    )
    cancel_call = repository.calls[1]
    assert cancel_call["audit_action"] == "ticket.cancelled"
    assert cancel_call["audit_metadata"] == {"reason": "Yêu cầu đã hủy"}
    assert cancel_call["ticket_updates"]["cancellation_reason"] == "Yêu cầu đã hủy"


def test_close_allows_authorized_manager_across_assignee_ownership() -> None:
    manager = _actor(Role.PROPERTY_MANAGER)
    other_manager = _actor(Role.PROPERTY_MANAGER)
    repository = RecordingTicketRepository(_record(TicketStatus.RESOLVED, actor=manager))
    repository.record = StoredRecord(
        {**repository.record.values, "assigned_user_id": str(manager.id)},
        version=3,
    )
    service = _service(repository)

    service.close(
        "TCK-000001",
        expected_version=3,
        actor=other_manager,
        audit_context=_audit(other_manager),
        now=datetime(2026, 8, 8, 1, tzinfo=UTC),
    )

    assert repository.calls[0]["audit_action"] == "ticket.closed"

"""PostgreSQL persistence for ticket intake, SLA, comments, and escalation."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.database.models import (
    AssetAttachment,
    BusinessCalendar,
    BusinessCalendarHoliday,
    BusinessWorkingPeriod,
    SlaPolicy,
    SlaPolicyTarget,
    SupportGroup,
    Ticket,
    TicketCategory,
    TicketComment,
    TicketCommentAttachment,
    TicketEscalationEvent,
    TicketIntakeSource,
    TicketSlaEvent,
    TicketSlaState,
    TicketSubcategory,
    User,
    WorkOrder,
    WorkOrderAttachment,
)
from src.repositories.contracts import (
    DuplicateIdentifierError,
    IntegrityViolationError,
    RecordNotFoundError,
    RepositoryError,
    StaleRecordError,
    StorageUnavailableError,
    StoredRecord,
    TicketReferenceKind,
)
from src.repositories.postgres.tickets.queries import TicketQueryRepository
from src.operations.outbox import enqueue_outbox_event
from src.security.audit import AuditContext, safe_state
from src.security.service import append_audit_event

TICKET_SEQUENCE = "maintenance_ticket_id_seq"

TICKET_OPERATION_AUDIT_FIELDS = {
    "ticket_id",
    "asset_id",
    "category_id",
    "subcategory_id",
    "impact",
    "urgency",
    "priority",
    "status",
    "failure_category",
    "intake_source_id",
    "support_group_id",
    "assigned_user_id",
    "first_response_at",
    "waiting_reason",
    "resolved_at",
    "closed_at",
    "reopened_at",
    "cancelled_at",
    "reopen_count",
    "version",
}


class PostgresTicketRepository:
    """Keep ticket writes atomic and expose storage-neutral records to services."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self.queries = TicketQueryRepository(
            session_factory,
            user_record=_user_record,
            ticket_record=_ticket_record,
            reference_record=_reference_record,
            calendar_values=_calendar_values,
            policy_values=_policy_values,
        )

    def get_asset(self, asset_id: str) -> StoredRecord | None:
        return self.queries.get_asset(asset_id)

    def get_user(self, user_id: UUID) -> StoredRecord | None:
        return self.queries.get_user(user_id)

    def find_user(
        self, *, username: str | None = None, role: str | None = None
    ) -> StoredRecord | None:
        return self.queries.find_user(username=username, role=role)

    def has_maintenance_log(self, ticket_id: str) -> bool:
        return self.queries.has_maintenance_log(ticket_id)

    def get_ticket(self, ticket_id: str, *, include_timeline: bool = False) -> StoredRecord | None:
        return self.queries.get_ticket(ticket_id, include_timeline=include_timeline)

    def list_tickets(self, *, filters: dict[str, Any]) -> list[StoredRecord]:
        return self.queries.list_tickets(filters=filters)

    def reference_options(self) -> dict[str, list[dict[str, Any]]]:
        return self.queries.reference_options()

    def get_reference(
        self, kind: TicketReferenceKind, identifier: UUID
    ) -> StoredRecord | None:
        return self.queries.get_reference(kind, identifier)

    def find_sla_policy(
        self,
        *,
        category_id: UUID | None,
        priority: str,
        effective_date: date,
        policy_id: UUID | None = None,
    ) -> StoredRecord | None:
        return self.queries.find_sla_policy(
            category_id=category_id,
            priority=priority,
            effective_date=effective_date,
            policy_id=policy_id,
        )

    def create_ticket(
        self,
        values: dict[str, Any],
        *,
        sla_values: dict[str, Any] | None,
        sla_events: list[dict[str, Any]],
        audit_context: AuditContext,
    ) -> StoredRecord:
        ticket_id = ""
        try:
            with self.session_factory() as session, session.begin():
                ticket_id = _next_ticket_id(session)
                entity = Ticket(ticket_id=ticket_id, **values)
                session.add(entity)
                session.flush()
                sla_state: TicketSlaState | None = None
                if sla_values is not None:
                    sla_state = TicketSlaState(id=uuid4(), ticket_id=ticket_id, **sla_values)
                    session.add(sla_state)
                    session.flush()
                    _append_sla_events(
                        session,
                        ticket_id=ticket_id,
                        sla_state=sla_state,
                        events=sla_events,
                        actor_id=audit_context.actor_user_id,
                    )
                result = _ticket_record(session, entity)
                _audit(
                    session,
                    audit_context,
                    action="ticket.created",
                    ticket_id=ticket_id,
                    after=result.values,
                )
                _audit(
                    session,
                    audit_context,
                    action="ticket.priority_calculated",
                    ticket_id=ticket_id,
                    metadata={
                        "impact": entity.impact,
                        "urgency": entity.urgency,
                        "priority": entity.priority,
                    },
                )
                if sla_state is not None:
                    _audit(
                        session,
                        audit_context,
                        action="ticket.sla_policy_applied",
                        ticket_id=ticket_id,
                        metadata={
                            "policy_code": sla_state.policy_code,
                            "occurrence_number": sla_state.occurrence_number,
                        },
                    )
                if entity.priority == "critical":
                    enqueue_outbox_event(
                        session,
                        event_type="ticket.critical_created",
                        aggregate_type="ticket",
                        aggregate_id=ticket_id,
                        payload={
                            "ticket_id": ticket_id,
                            "asset_id": entity.asset_id,
                            "priority": entity.priority,
                        },
                        idempotency_key=f"ticket:{ticket_id}:critical-created",
                    )
                if entity.assigned_user_id is not None:
                    enqueue_outbox_event(
                        session,
                        event_type="ticket.assigned",
                        aggregate_type="ticket",
                        aggregate_id=ticket_id,
                        payload={
                            "ticket_id": ticket_id,
                            "asset_id": entity.asset_id,
                            "assigned_user_id": str(entity.assigned_user_id),
                        },
                        idempotency_key=f"ticket:{ticket_id}:initial-assignment",
                    )
            return result
        except RepositoryError:
            raise
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate=f"Ticket đã tồn tại: {ticket_id}")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo ticket trong PostgreSQL.") from exc

    # Atomic lifecycle mutation: ticket/SLA locks, events, audit, and outbox.
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
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = session.get(Ticket, ticket_id, with_for_update=True)
                if entity is None:
                    raise RecordNotFoundError(f"Không tìm thấy ticket: {ticket_id}")
                _require_version(entity.version, expected_version, ticket_id)
                before = _ticket_record(session, entity)
                for field, value in ticket_updates.items():
                    setattr(entity, field, value)
                sla_state = session.scalar(
                    select(TicketSlaState)
                    .where(TicketSlaState.ticket_id == ticket_id)
                    .with_for_update()
                )
                if sla_updates is not None:
                    if sla_state is None:
                        raise IntegrityViolationError("Ticket chưa có SLA state để cập nhật.")
                    for field, value in sla_updates.items():
                        setattr(sla_state, field, value)
                if sla_events:
                    if sla_state is None:
                        raise IntegrityViolationError("Ticket chưa có SLA state để ghi event.")
                    _append_sla_events(
                        session,
                        ticket_id=ticket_id,
                        sla_state=sla_state,
                        events=sla_events,
                        actor_id=audit_context.actor_user_id,
                    )
                session.flush()
                result = _ticket_record(session, entity)
                _audit(
                    session,
                    audit_context,
                    action=audit_action,
                    ticket_id=ticket_id,
                    before=before.values,
                    after=result.values,
                    metadata=audit_metadata,
                )
                outbox_event_type = {
                    "ticket.assigned": "ticket.assigned",
                    "ticket.placed_on_hold": "ticket.held",
                    "ticket.resumed": "ticket.resumed",
                }.get(audit_action)
                if outbox_event_type:
                    payload = {
                        "ticket_id": entity.ticket_id,
                        "asset_id": entity.asset_id,
                        "assigned_user_id": (
                            str(entity.assigned_user_id)
                            if entity.assigned_user_id
                            else None
                        ),
                    }
                    if (
                        outbox_event_type != "ticket.assigned"
                        or entity.assigned_user_id is not None
                    ):
                        enqueue_outbox_event(
                            session,
                            event_type=outbox_event_type,
                            aggregate_type="ticket",
                            aggregate_id=ticket_id,
                            payload=payload,
                            idempotency_key=(
                                f"ticket:{ticket_id}:{outbox_event_type}:"
                                f"version:{entity.version}"
                            ),
                        )
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError(
                f"Ticket {ticket_id} đã thay đổi. Hãy tải lại trước khi cập nhật."
            ) from exc
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate="Ticket hoặc SLA event bị trùng.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể cập nhật ticket.") from exc

    def replace_sla_policy(
        self,
        ticket_id: str,
        *,
        expected_version: int,
        sla_values: dict[str, Any],
        sla_events: list[dict[str, Any]],
        audit_context: AuditContext,
        reason: str,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                ticket = session.get(Ticket, ticket_id, with_for_update=True)
                if ticket is None:
                    raise RecordNotFoundError(f"Không tìm thấy ticket: {ticket_id}")
                _require_version(ticket.version, expected_version, ticket_id)
                state = session.scalar(
                    select(TicketSlaState)
                    .where(TicketSlaState.ticket_id == ticket_id)
                    .with_for_update()
                )
                if state is None:
                    state = TicketSlaState(id=uuid4(), ticket_id=ticket_id, **sla_values)
                    session.add(state)
                else:
                    for field, value in sla_values.items():
                        setattr(state, field, value)
                ticket.updated_at = _utc_now()
                session.flush()
                _append_sla_events(
                    session,
                    ticket_id=ticket_id,
                    sla_state=state,
                    events=sla_events,
                    actor_id=audit_context.actor_user_id,
                )
                session.flush()
                result = _ticket_record(session, ticket)
                _audit(
                    session,
                    audit_context,
                    action="ticket.sla_policy_overridden",
                    ticket_id=ticket_id,
                    after=result.values,
                    metadata={"reason": reason, "policy_code": state.policy_code},
                )
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError("Ticket đã thay đổi trong khi override SLA.") from exc
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate="SLA state bị trùng.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể override SLA policy.") from exc

    def create_comment(
        self,
        ticket_id: str,
        *,
        visibility: str,
        body: str,
        asset_attachment_ids: list[UUID],
        work_order_attachment_ids: list[UUID],
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                ticket = session.get(Ticket, ticket_id)
                if ticket is None:
                    raise RecordNotFoundError(f"Không tìm thấy ticket: {ticket_id}")
                comment = TicketComment(
                    id=uuid4(),
                    ticket_id=ticket_id,
                    author_user_id=audit_context.actor_user_id,
                    visibility=visibility,
                    body=body,
                    created_at=_utc_now(),
                )
                session.add(comment)
                session.flush()
                for attachment_id in asset_attachment_ids:
                    attachment = session.get(AssetAttachment, attachment_id)
                    if (
                        attachment is None
                        or attachment.asset_id != ticket.asset_id
                        or attachment.deleted_at is not None
                    ):
                        raise IntegrityViolationError(
                            "Asset attachment không thuộc asset của ticket hoặc đã bị xóa."
                        )
                    session.add(
                        TicketCommentAttachment(
                            id=uuid4(),
                            comment_id=comment.id,
                            asset_attachment_id=attachment_id,
                            work_order_attachment_id=None,
                        )
                    )
                for attachment_id in work_order_attachment_ids:
                    attachment = session.get(WorkOrderAttachment, attachment_id)
                    work_order = (
                        session.get(WorkOrder, attachment.work_order_id) if attachment else None
                    )
                    if (
                        attachment is None
                        or attachment.deleted_at is not None
                        or work_order is None
                        or work_order.source_ticket_id != ticket_id
                    ):
                        raise IntegrityViolationError(
                            "Work-order attachment không thuộc ticket hoặc đã bị xóa."
                        )
                    session.add(
                        TicketCommentAttachment(
                            id=uuid4(),
                            comment_id=comment.id,
                            asset_attachment_id=None,
                            work_order_attachment_id=attachment_id,
                        )
                    )
                session.flush()
                result = _comment_record(session, comment)
                _audit(
                    session,
                    audit_context,
                    action="ticket.comment_created",
                    ticket_id=ticket_id,
                    metadata={
                        "comment_id": str(comment.id),
                        "visibility": visibility,
                        "attachment_count": len(asset_attachment_ids)
                        + len(work_order_attachment_ids),
                    },
                )
            return result
        except RepositoryError:
            raise
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate="Comment attachment đã được liên kết.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể ghi comment ticket.") from exc

    def list_calendars(self) -> list[StoredRecord]:
        return self.queries.list_calendars()

    def create_calendar(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                periods = values.pop("periods")
                holidays = values.pop("holidays")
                entity = BusinessCalendar(id=uuid4(), **values)
                session.add(entity)
                session.flush()
                _replace_calendar_children(session, entity.id, periods, holidays)
                session.flush()
                result = StoredRecord(_calendar_values(session, entity), entity.version)
                _audit_resource(
                    session,
                    audit_context,
                    action="sla_calendar.created",
                    resource_type="business_calendar",
                    resource_id=str(entity.id),
                    after={"code": entity.code, "timezone": entity.timezone},
                )
            return result
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate="Business calendar code đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo business calendar.") from exc

    def update_calendar(
        self,
        calendar_id: UUID,
        values: dict[str, Any],
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = session.get(BusinessCalendar, calendar_id, with_for_update=True)
                if entity is None:
                    raise RecordNotFoundError(f"Không tìm thấy calendar: {calendar_id}")
                _require_version(entity.version, expected_version, str(calendar_id))
                periods = values.pop("periods", None)
                holidays = values.pop("holidays", None)
                for field, value in values.items():
                    setattr(entity, field, value)
                if periods is not None and holidays is not None:
                    _replace_calendar_children(session, entity.id, periods, holidays)
                entity.updated_at = _utc_now()
                session.flush()
                result = StoredRecord(_calendar_values(session, entity), entity.version)
                _audit_resource(
                    session,
                    audit_context,
                    action="sla_calendar.updated",
                    resource_type="business_calendar",
                    resource_id=str(entity.id),
                    after={"code": entity.code, "is_active": entity.is_active},
                )
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError("Business calendar đã thay đổi.") from exc
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate="Business calendar code bị trùng.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể cập nhật business calendar.") from exc

    def list_policies(self) -> list[StoredRecord]:
        return self.queries.list_policies()

    def create_policy(self, values: dict[str, Any], *, audit_context: AuditContext) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                targets = values.pop("targets")
                entity = SlaPolicy(id=uuid4(), **values)
                session.add(entity)
                session.flush()
                _replace_policy_targets(session, entity.id, targets)
                session.flush()
                result = StoredRecord(_policy_values(session, entity), entity.version)
                _audit_resource(
                    session,
                    audit_context,
                    action="sla_policy.created",
                    resource_type="sla_policy",
                    resource_id=str(entity.id),
                    after={"code": entity.code, "is_active": entity.is_active},
                )
            return result
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate="SLA policy code đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo SLA policy.") from exc

    def update_policy(
        self,
        policy_id: UUID,
        values: dict[str, Any],
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = session.get(SlaPolicy, policy_id, with_for_update=True)
                if entity is None:
                    raise RecordNotFoundError(f"Không tìm thấy SLA policy: {policy_id}")
                _require_version(entity.version, expected_version, str(policy_id))
                targets = values.pop("targets", None)
                for field, value in values.items():
                    setattr(entity, field, value)
                if targets is not None:
                    _replace_policy_targets(session, entity.id, targets)
                entity.updated_at = _utc_now()
                session.flush()
                result = StoredRecord(_policy_values(session, entity), entity.version)
                _audit_resource(
                    session,
                    audit_context,
                    action="sla_policy.updated",
                    resource_type="sla_policy",
                    resource_id=str(entity.id),
                    after={"code": entity.code, "is_active": entity.is_active},
                )
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError("SLA policy đã thay đổi.") from exc
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate="SLA policy hoặc target bị trùng.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể cập nhật SLA policy.") from exc

    # Atomic escalation recording: uniqueness, SLA events, audit, and outbox.
    def record_escalations(
        self,
        events: list[dict[str, Any]],
        *,
        audit_context: AuditContext,
    ) -> list[StoredRecord]:
        if not events:
            return []
        try:
            inserted: list[StoredRecord] = []
            with self.session_factory() as session, session.begin():
                for values in events:
                    event_id = uuid4()
                    statement = (
                        insert(TicketEscalationEvent)
                        .values(
                            id=event_id, created_by_user_id=audit_context.actor_user_id, **values
                        )
                        .on_conflict_do_nothing(constraint="uq_ticket_escalation_rule_occurrence")
                        .returning(TicketEscalationEvent.id)
                    )
                    created_id = session.scalar(statement)
                    if created_id is None:
                        continue
                    entity = session.get(TicketEscalationEvent, created_id)
                    if entity is None:  # pragma: no cover - RETURNING guarantees the row
                        continue
                    if entity.rule_code.endswith("breached") and entity.ticket_sla_id:
                        session.add(
                            TicketSlaEvent(
                                id=uuid4(),
                                ticket_sla_id=entity.ticket_sla_id,
                                ticket_id=entity.ticket_id,
                                event_type="breach_detected",
                                clock_type=entity.clock_type,
                                occurrence_number=entity.occurrence_number,
                                occurred_at=entity.detected_at,
                                details={"rule_code": entity.rule_code},
                                created_by_user_id=audit_context.actor_user_id,
                            )
                        )
                    record = StoredRecord(_escalation_values(entity))
                    inserted.append(record)
                    _audit(
                        session,
                        audit_context,
                        action="ticket.escalated",
                        ticket_id=entity.ticket_id,
                        metadata={
                            "rule_code": entity.rule_code,
                            "occurrence_number": entity.occurrence_number,
                        },
                    )
                    ticket = session.get(Ticket, entity.ticket_id)
                    if ticket is None:  # pragma: no cover - protected by FK
                        continue
                    event_type = (
                        "ticket.sla_breach"
                        if entity.rule_code.endswith("breached")
                        else "ticket.sla_warning"
                        if entity.rule_code.endswith("due_soon")
                        else "ticket.escalated"
                    )
                    enqueue_outbox_event(
                        session,
                        event_type=event_type,
                        aggregate_type="ticket",
                        aggregate_id=entity.ticket_id,
                        payload={
                            "ticket_id": entity.ticket_id,
                            "asset_id": ticket.asset_id,
                            "rule_code": entity.rule_code,
                            "clock_type": entity.clock_type,
                            "occurrence_number": entity.occurrence_number,
                            "assigned_user_id": (
                                str(ticket.assigned_user_id)
                                if ticket.assigned_user_id
                                else None
                            ),
                        },
                        idempotency_key=f"ticket-escalation:{entity.id}",
                    )
            return inserted
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate="Escalation event bị trùng.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể ghi escalation events.") from exc

    def seed_defaults(
        self,
        *,
        actor_user_id: UUID,
        audit_context: AuditContext,
    ) -> dict[str, int]:
        """Idempotently seed bounded local ticket/SLA reference data."""

        counts = {
            "categories": 0,
            "subcategories": 0,
            "sources": 0,
            "groups": 0,
            "calendars": 0,
            "policies": 0,
        }
        try:
            with self.session_factory() as session, session.begin():
                category_specs = (
                    ("electrical", "Hệ thống điện"),
                    ("mechanical", "Hệ thống cơ khí"),
                    ("hvac", "Điều hòa không khí"),
                    ("safety", "An toàn và PCCC"),
                    ("general", "Yêu cầu chung"),
                )
                categories: dict[str, TicketCategory] = {}
                for code, name in category_specs:
                    entity, created = _get_or_create(
                        session, TicketCategory, code=code, defaults={"name": name}
                    )
                    categories[code] = entity
                    counts["categories"] += int(created)
                subcategory_specs = (
                    ("electrical", "power", "Nguồn điện"),
                    ("mechanical", "vibration", "Rung động"),
                    ("hvac", "cooling", "Làm lạnh"),
                    ("safety", "alarm", "Cảnh báo an toàn"),
                    ("general", "inspection", "Kiểm tra hiện trường"),
                )
                for category_code, code, name in subcategory_specs:
                    _, created = _get_or_create(
                        session,
                        TicketSubcategory,
                        category_id=categories[category_code].id,
                        code=code,
                        defaults={"name": name},
                    )
                    counts["subcategories"] += int(created)
                for code, name in (
                    ("web", "Cổng nội bộ"),
                    ("phone", "Điện thoại"),
                    ("email", "Email"),
                    ("analytics", "Phân tích batch"),
                ):
                    _, created = _get_or_create(
                        session, TicketIntakeSource, code=code, defaults={"name": name}
                    )
                    counts["sources"] += int(created)
                for code, name in (
                    ("HELPDESK", "Bộ phận tiếp nhận"),
                    ("ENGINEERING", "Đội kỹ thuật"),
                ):
                    _, created = _get_or_create(
                        session, SupportGroup, code=code, defaults={"name": name}
                    )
                    counts["groups"] += int(created)
                calendar = session.scalar(
                    select(BusinessCalendar).where(BusinessCalendar.code == "VN_BUSINESS")
                )
                if calendar is None:
                    calendar = BusinessCalendar(
                        id=uuid4(),
                        code="VN_BUSINESS",
                        name="Giờ làm việc Việt Nam",
                        timezone="Asia/Ho_Chi_Minh",
                        is_active=True,
                        created_by_user_id=actor_user_id,
                        updated_by_user_id=actor_user_id,
                    )
                    session.add(calendar)
                    session.flush()
                    for weekday in range(5):
                        session.add(
                            BusinessWorkingPeriod(
                                id=uuid4(),
                                calendar_id=calendar.id,
                                weekday=weekday,
                                start_time=datetime.strptime("08:00", "%H:%M").time(),
                                end_time=datetime.strptime("17:00", "%H:%M").time(),
                            )
                        )
                    counts["calendars"] = 1
                policy = session.scalar(
                    select(SlaPolicy).where(SlaPolicy.code == "DEFAULT_FACILITY")
                )
                if policy is None:
                    policy = SlaPolicy(
                        id=uuid4(),
                        code="DEFAULT_FACILITY",
                        name="SLA vận hành cơ sở mặc định",
                        calendar_id=calendar.id,
                        category_id=None,
                        timezone=calendar.timezone,
                        pause_on_waiting=True,
                        due_soon_percent=20,
                        effective_from=date(2020, 1, 1),
                        effective_to=None,
                        is_active=True,
                        created_by_user_id=actor_user_id,
                        updated_by_user_id=actor_user_id,
                    )
                    session.add(policy)
                    session.flush()
                    for priority, response, resolution in (
                        ("low", 240, 1440),
                        ("medium", 120, 720),
                        ("high", 60, 240),
                        ("critical", 15, 120),
                    ):
                        session.add(
                            SlaPolicyTarget(
                                id=uuid4(),
                                policy_id=policy.id,
                                priority=priority,
                                first_response_minutes=response,
                                resolution_minutes=resolution,
                            )
                        )
                    counts["policies"] = 1
                _audit_resource(
                    session,
                    audit_context,
                    action="ticketing.defaults_seeded",
                    resource_type="ticketing_configuration",
                    resource_id="default",
                    after=counts,
                )
            return counts
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate="Reference data ticketing bị trùng.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể seed cấu hình ticketing.") from exc


def _ticket_record(
    session: Session, entity: Ticket, *, include_timeline: bool = False
) -> StoredRecord:
    category = session.get(TicketCategory, entity.category_id) if entity.category_id else None
    subcategory = (
        session.get(TicketSubcategory, entity.subcategory_id) if entity.subcategory_id else None
    )
    source = (
        session.get(TicketIntakeSource, entity.intake_source_id)
        if entity.intake_source_id
        else None
    )
    group = session.get(SupportGroup, entity.support_group_id) if entity.support_group_id else None
    assignee = session.get(User, entity.assigned_user_id) if entity.assigned_user_id else None
    sla = session.scalar(select(TicketSlaState).where(TicketSlaState.ticket_id == entity.ticket_id))
    values: dict[str, Any] = {
        "ticket_id": entity.ticket_id,
        "asset_id": entity.asset_id,
        "issue_description": entity.issue_description,
        "failure_category": entity.failure_category,
        "reporter_name": entity.reporter_name,
        "reporter_email": entity.reporter_email,
        "reporter_phone": entity.reporter_phone,
        "category_id": _uuid_text(entity.category_id),
        "category_name": category.name if category else None,
        "subcategory_id": _uuid_text(entity.subcategory_id),
        "subcategory_name": subcategory.name if subcategory else None,
        "impact": entity.impact,
        "urgency": entity.urgency,
        "priority": entity.priority,
        "status": entity.status,
        "intake_source_id": _uuid_text(entity.intake_source_id),
        "intake_source_name": source.name if source else None,
        "support_group_id": _uuid_text(entity.support_group_id),
        "support_group_name": group.name if group else None,
        "assigned_user_id": _uuid_text(entity.assigned_user_id),
        "assigned_user_name": assignee.display_name if assignee else None,
        "technician_id": entity.technician_id,
        "created_at": _iso_datetime(entity.created_at),
        "first_response_at": _iso_datetime(entity.first_response_at),
        "waiting_reason": entity.waiting_reason,
        "waiting_previous_status": entity.waiting_previous_status,
        "resolved_at": _iso_datetime(entity.resolved_at),
        "closed_at": _iso_datetime(entity.closed_at),
        "reopened_at": _iso_datetime(entity.reopened_at),
        "cancelled_at": _iso_datetime(entity.cancelled_at),
        "cancellation_reason": entity.cancellation_reason,
        "reopen_count": entity.reopen_count,
        "manager_note": entity.manager_note,
        "note": entity.note,
        "updated_at": _iso_datetime(entity.updated_at),
        "version": entity.version,
        "sla": _sla_state_values(sla) if sla else None,
    }
    if include_timeline:
        comments = session.scalars(
            select(TicketComment)
            .where(TicketComment.ticket_id == entity.ticket_id)
            .order_by(TicketComment.created_at)
        ).all()
        sla_events = session.scalars(
            select(TicketSlaEvent)
            .where(TicketSlaEvent.ticket_id == entity.ticket_id)
            .order_by(TicketSlaEvent.occurred_at)
        ).all()
        escalations = session.scalars(
            select(TicketEscalationEvent)
            .where(TicketEscalationEvent.ticket_id == entity.ticket_id)
            .order_by(TicketEscalationEvent.detected_at)
        ).all()
        work_orders = session.scalars(
            select(WorkOrder)
            .where(WorkOrder.source_ticket_id == entity.ticket_id)
            .order_by(WorkOrder.created_at.desc())
        ).all()
        values["comments"] = [dict(_comment_record(session, item).values) for item in comments]
        values["sla_events"] = [_sla_event_values(item) for item in sla_events]
        values["escalations"] = [_escalation_values(item) for item in escalations]
        values["linked_work_orders"] = [
            {
                "id": str(item.id),
                "work_order_number": item.work_order_number,
                "title": item.title,
                "status": item.status,
                "priority": item.priority,
                "due_date": item.due_date.isoformat(),
            }
            for item in work_orders
        ]
    return StoredRecord(values, version=entity.version)


def _comment_record(session: Session, entity: TicketComment) -> StoredRecord:
    author = session.get(User, entity.author_user_id)
    links = session.scalars(
        select(TicketCommentAttachment).where(TicketCommentAttachment.comment_id == entity.id)
    ).all()
    return StoredRecord(
        {
            "id": str(entity.id),
            "ticket_id": entity.ticket_id,
            "author_user_id": str(entity.author_user_id),
            "author_name": author.display_name if author else "Người dùng nội bộ",
            "visibility": entity.visibility,
            "body": entity.body,
            "created_at": _iso_datetime(entity.created_at),
            "attachments": [
                {
                    "asset_attachment_id": _uuid_text(item.asset_attachment_id),
                    "work_order_attachment_id": _uuid_text(item.work_order_attachment_id),
                }
                for item in links
            ],
        }
    )


def _sla_state_values(entity: TicketSlaState) -> dict[str, Any]:
    return {
        "id": str(entity.id),
        "policy_id": str(entity.policy_id),
        "policy_code": entity.policy_code,
        "policy_name": entity.policy_name,
        "calendar_id": str(entity.calendar_id),
        "calendar_code": entity.calendar_code,
        "timezone": entity.timezone,
        "calendar_snapshot": entity.calendar_snapshot,
        "pause_on_waiting": entity.pause_on_waiting,
        "due_soon_percent": entity.due_soon_percent,
        "first_response_target_minutes": entity.first_response_target_minutes,
        "resolution_target_minutes": entity.resolution_target_minutes,
        "started_at": _iso_datetime(entity.started_at),
        "first_response_due_at": _iso_datetime(entity.first_response_due_at),
        "resolution_due_at": _iso_datetime(entity.resolution_due_at),
        "first_response_remaining_minutes": entity.first_response_remaining_minutes,
        "resolution_remaining_minutes": entity.resolution_remaining_minutes,
        "paused_at": _iso_datetime(entity.paused_at),
        "resolution_stopped_at": _iso_datetime(entity.resolution_stopped_at),
        "occurrence_number": entity.occurrence_number,
        "version": entity.version,
    }


def _sla_event_values(entity: TicketSlaEvent) -> dict[str, Any]:
    return {
        "id": str(entity.id),
        "event_type": entity.event_type,
        "clock_type": entity.clock_type,
        "occurrence_number": entity.occurrence_number,
        "occurred_at": _iso_datetime(entity.occurred_at),
        "details": entity.details,
    }


def _escalation_values(entity: TicketEscalationEvent) -> dict[str, Any]:
    return {
        "id": str(entity.id),
        "ticket_id": entity.ticket_id,
        "rule_code": entity.rule_code,
        "clock_type": entity.clock_type,
        "occurrence_number": entity.occurrence_number,
        "detected_at": _iso_datetime(entity.detected_at),
        "due_at": _iso_datetime(entity.due_at),
        "details": entity.details,
    }


def _calendar_values(session: Session, entity: BusinessCalendar) -> dict[str, Any]:
    periods = session.scalars(
        select(BusinessWorkingPeriod)
        .where(BusinessWorkingPeriod.calendar_id == entity.id)
        .order_by(BusinessWorkingPeriod.weekday, BusinessWorkingPeriod.start_time)
    ).all()
    holidays = session.scalars(
        select(BusinessCalendarHoliday)
        .where(BusinessCalendarHoliday.calendar_id == entity.id)
        .order_by(BusinessCalendarHoliday.holiday_date)
    ).all()
    return {
        "id": str(entity.id),
        "code": entity.code,
        "name": entity.name,
        "timezone": entity.timezone,
        "is_active": entity.is_active,
        "periods": [
            {
                "weekday": item.weekday,
                "start_time": item.start_time.isoformat(timespec="minutes"),
                "end_time": item.end_time.isoformat(timespec="minutes"),
            }
            for item in periods
        ],
        "holidays": [
            {"holiday_date": item.holiday_date.isoformat(), "name": item.name} for item in holidays
        ],
        "version": entity.version,
    }


def _policy_values(
    session: Session, entity: SlaPolicy, *, target: SlaPolicyTarget | None = None
) -> dict[str, Any]:
    calendar = session.get(BusinessCalendar, entity.calendar_id)
    category = session.get(TicketCategory, entity.category_id) if entity.category_id else None
    targets = (
        [target]
        if target is not None
        else session.scalars(
            select(SlaPolicyTarget)
            .where(SlaPolicyTarget.policy_id == entity.id)
            .order_by(SlaPolicyTarget.priority)
        ).all()
    )
    return {
        "id": str(entity.id),
        "code": entity.code,
        "name": entity.name,
        "calendar_id": str(entity.calendar_id),
        "calendar_code": calendar.code if calendar else None,
        "calendar": _calendar_values(session, calendar) if calendar else None,
        "category_id": _uuid_text(entity.category_id),
        "category_name": category.name if category else None,
        "timezone": entity.timezone,
        "pause_on_waiting": entity.pause_on_waiting,
        "due_soon_percent": entity.due_soon_percent,
        "effective_from": entity.effective_from.isoformat(),
        "effective_to": entity.effective_to.isoformat() if entity.effective_to else None,
        "is_active": entity.is_active,
        "targets": [
            {
                "priority": item.priority,
                "first_response_minutes": item.first_response_minutes,
                "resolution_minutes": item.resolution_minutes,
            }
            for item in targets
        ],
        "version": entity.version,
    }


def _replace_calendar_children(
    session: Session,
    calendar_id: UUID,
    periods: list[dict[str, Any]],
    holidays: list[dict[str, Any]],
) -> None:
    session.query(BusinessWorkingPeriod).filter(
        BusinessWorkingPeriod.calendar_id == calendar_id
    ).delete(synchronize_session=False)
    session.query(BusinessCalendarHoliday).filter(
        BusinessCalendarHoliday.calendar_id == calendar_id
    ).delete(synchronize_session=False)
    for values in periods:
        session.add(BusinessWorkingPeriod(id=uuid4(), calendar_id=calendar_id, **values))
    for values in holidays:
        session.add(BusinessCalendarHoliday(id=uuid4(), calendar_id=calendar_id, **values))


def _replace_policy_targets(
    session: Session, policy_id: UUID, targets: list[dict[str, Any]]
) -> None:
    session.query(SlaPolicyTarget).filter(SlaPolicyTarget.policy_id == policy_id).delete(
        synchronize_session=False
    )
    for values in targets:
        session.add(SlaPolicyTarget(id=uuid4(), policy_id=policy_id, **values))


def _append_sla_events(
    session: Session,
    *,
    ticket_id: str,
    sla_state: TicketSlaState,
    events: list[dict[str, Any]],
    actor_id: UUID,
) -> None:
    for values in events:
        session.add(
            TicketSlaEvent(
                id=uuid4(),
                ticket_sla_id=sla_state.id,
                ticket_id=ticket_id,
                created_by_user_id=actor_id,
                **values,
            )
        )


def _get_or_create(
    session: Session, model: type[Any], *, defaults: dict[str, Any], **lookup: Any
) -> tuple[Any, bool]:
    entity = session.scalar(select(model).filter_by(**lookup))
    if entity is not None:
        return entity, False
    entity = model(id=uuid4(), **lookup, **defaults)
    session.add(entity)
    session.flush()
    return entity, True


def _next_ticket_id(session: Session) -> str:
    number = session.scalar(text(f"SELECT nextval('{TICKET_SEQUENCE}')"))
    if number is None:  # pragma: no cover
        raise StorageUnavailableError("Sequence ticket không trả về giá trị.")
    return f"TCK-{int(number):06d}"


def _user_record(entity: User) -> StoredRecord:
    return StoredRecord(
        {
            "id": str(entity.id),
            "display_name": entity.display_name,
            "role": entity.role,
            "technician_id": entity.technician_id,
            "is_active": entity.is_active,
        },
        version=entity.version,
    )


def _reference_record(entity: Any) -> dict[str, Any]:
    return {
        "id": str(entity.id),
        "code": entity.code,
        "name": entity.name,
        "is_active": entity.is_active,
    }


def _audit(
    session: Session,
    context: AuditContext,
    *,
    action: str,
    ticket_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    _audit_resource(
        session,
        context,
        action=action,
        resource_type="ticket",
        resource_id=ticket_id,
        before=safe_state(before or {}, TICKET_OPERATION_AUDIT_FIELDS) or None,
        after=safe_state(after or {}, TICKET_OPERATION_AUDIT_FIELDS) or None,
        metadata=metadata,
    )


def _audit_resource(
    session: Session,
    context: AuditContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    append_audit_event(
        session,
        actor_user_id=context.actor_user_id,
        actor_display_name=context.actor_display_name,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=context.request_id,
        before_state=before,
        after_state=after,
        metadata=metadata,
    )


def _require_version(current: int, expected: int, identifier: str) -> None:
    if current != expected:
        raise StaleRecordError(f"Dữ liệu {identifier} đã thay đổi. Hãy tải lại trước khi cập nhật.")


def _raise_integrity(exc: IntegrityError, *, duplicate: str) -> None:
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if sqlstate == "23505":
        raise DuplicateIdentifierError(duplicate) from exc
    raise IntegrityViolationError(
        "Dữ liệu ticket vi phạm foreign key hoặc ràng buộc PostgreSQL."
    ) from exc


def _uuid_text(value: UUID | None) -> str | None:
    return str(value) if value else None


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

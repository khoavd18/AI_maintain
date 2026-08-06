"""Read-only ticket intake, SLA, and timeline queries."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import (
    Asset,
    BusinessCalendar,
    MaintenanceLog,
    SlaPolicy,
    SlaPolicyTarget,
    SupportGroup,
    Ticket,
    TicketCategory,
    TicketIntakeSource,
    TicketSubcategory,
    User,
)
from src.repositories.contracts import StorageUnavailableError, StoredRecord


class TicketQueryRepository:
    """Own ticket, intake-reference, and SLA policy reads."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        user_record: Callable[..., StoredRecord],
        ticket_record: Callable[..., StoredRecord],
        reference_record: Callable[..., dict[str, Any]],
        calendar_values: Callable[..., dict[str, Any]],
        policy_values: Callable[..., dict[str, Any]],
    ) -> None:
        self.session_factory = session_factory
        self._user_record = user_record
        self._ticket_record = ticket_record
        self._reference_record = reference_record
        self._calendar_values = calendar_values
        self._policy_values = policy_values

    def get_asset(self, asset_id: str) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(Asset, asset_id)
                if entity is None:
                    return None
                return StoredRecord(
                    {
                        "asset_id": entity.asset_id,
                        "asset_name": entity.asset_name,
                        "asset_type": entity.asset_type,
                        "location": entity.location,
                        "lifecycle_status": entity.lifecycle_status,
                        "operational_status": entity.operational_status,
                    },
                    version=entity.version,
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc asset cho ticket.") from exc

    def get_user(self, user_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(User, user_id)
                return self._user_record(entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc người dùng ticket.") from exc

    def find_user(
        self, *, username: str | None = None, role: str | None = None
    ) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                statement = select(User).where(User.is_active.is_(True))
                if username is not None:
                    statement = statement.where(User.username == username)
                if role is not None:
                    statement = statement.where(User.role == role)
                entity = session.scalar(statement.order_by(User.username).limit(1))
                return self._user_record(entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể tìm người dùng ticketing."
            ) from exc

    def has_maintenance_log(self, ticket_id: str) -> bool:
        try:
            with self.session_factory() as session:
                count = session.scalar(
                    select(func.count())
                    .select_from(MaintenanceLog)
                    .where(MaintenanceLog.ticket_id == ticket_id)
                )
                return bool(count)
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể kiểm tra maintenance log.") from exc

    def get_ticket(
        self, ticket_id: str, *, include_timeline: bool = False
    ) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(Ticket, ticket_id)
                if entity is None:
                    return None
                return self._ticket_record(
                    session, entity, include_timeline=include_timeline
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc ticket.") from exc

    def list_tickets(self, *, filters: dict[str, Any]) -> list[StoredRecord]:
        try:
            with self.session_factory() as session:
                statement = select(Ticket)
                field_map = {
                    "asset_id": Ticket.asset_id,
                    "status": Ticket.status,
                    "priority": Ticket.priority,
                    "category_id": Ticket.category_id,
                    "support_group_id": Ticket.support_group_id,
                    "assigned_user_id": Ticket.assigned_user_id,
                }
                for name, column in field_map.items():
                    value = filters.get(name)
                    if value is not None:
                        statement = statement.where(column == value)
                if filters.get("search"):
                    pattern = f"%{str(filters['search']).strip()}%"
                    statement = statement.where(
                        or_(
                            Ticket.ticket_id.ilike(pattern),
                            Ticket.issue_description.ilike(pattern),
                            Ticket.asset_id.ilike(pattern),
                        )
                    )
                entities = session.scalars(
                    statement.order_by(Ticket.created_at.desc(), Ticket.ticket_id)
                ).all()
                return [self._ticket_record(session, entity) for entity in entities]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc ticket queues.") from exc

    def reference_options(self) -> dict[str, list[dict[str, Any]]]:
        try:
            with self.session_factory() as session:
                categories = session.scalars(
                    select(TicketCategory)
                    .where(TicketCategory.is_active.is_(True))
                    .order_by(TicketCategory.name)
                ).all()
                subcategories = session.scalars(
                    select(TicketSubcategory)
                    .where(TicketSubcategory.is_active.is_(True))
                    .order_by(TicketSubcategory.name)
                ).all()
                sources = session.scalars(
                    select(TicketIntakeSource)
                    .where(TicketIntakeSource.is_active.is_(True))
                    .order_by(TicketIntakeSource.name)
                ).all()
                groups = session.scalars(
                    select(SupportGroup)
                    .where(SupportGroup.is_active.is_(True))
                    .order_by(SupportGroup.name)
                ).all()
                users = session.scalars(
                    select(User)
                    .where(
                        User.is_active.is_(True),
                        User.role.in_(("chief_engineer", "technician", "helpdesk")),
                    )
                    .order_by(User.display_name)
                ).all()
                return {
                    "categories": [self._reference_record(item) for item in categories],
                    "subcategories": [
                        {
                            **self._reference_record(item),
                            "category_id": str(item.category_id),
                        }
                        for item in subcategories
                    ],
                    "intake_sources": [
                        self._reference_record(item) for item in sources
                    ],
                    "support_groups": [
                        self._reference_record(item) for item in groups
                    ],
                    "assignees": [dict(self._user_record(item).values) for item in users],
                }
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể đọc cấu hình ticket intake."
            ) from exc

    def get_reference(self, model: type[Any], identifier: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(model, identifier)
                if entity is None:
                    return None
                values = self._reference_record(entity)
                if isinstance(entity, TicketSubcategory):
                    values["category_id"] = str(entity.category_id)
                if isinstance(entity, User):
                    return self._user_record(entity)
                return StoredRecord(values, version=getattr(entity, "version", None))
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc tham chiếu ticket.") from exc

    def find_sla_policy(
        self,
        *,
        category_id: UUID | None,
        priority: str,
        effective_date: date,
        policy_id: UUID | None = None,
    ) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                statement = (
                    select(SlaPolicy)
                    .where(
                        SlaPolicy.is_active.is_(True),
                        SlaPolicy.effective_from <= effective_date,
                        or_(
                            SlaPolicy.effective_to.is_(None),
                            SlaPolicy.effective_to >= effective_date,
                        ),
                    )
                    .order_by(
                        SlaPolicy.category_id.desc().nullslast(), SlaPolicy.code
                    )
                )
                if policy_id is not None:
                    statement = statement.where(SlaPolicy.id == policy_id)
                elif category_id is not None:
                    statement = statement.where(
                        or_(
                            SlaPolicy.category_id == category_id,
                            SlaPolicy.category_id.is_(None),
                        )
                    )
                else:
                    statement = statement.where(SlaPolicy.category_id.is_(None))
                policies = session.scalars(statement).all()
                for policy in policies:
                    target = session.scalar(
                        select(SlaPolicyTarget).where(
                            SlaPolicyTarget.policy_id == policy.id,
                            SlaPolicyTarget.priority == priority,
                        )
                    )
                    if target is not None:
                        return StoredRecord(
                            self._policy_values(session, policy, target=target)
                        )
                return None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể chọn SLA policy.") from exc

    def list_calendars(self) -> list[StoredRecord]:
        try:
            with self.session_factory() as session:
                entities = session.scalars(
                    select(BusinessCalendar).order_by(BusinessCalendar.code)
                ).all()
                return [
                    StoredRecord(self._calendar_values(session, item), item.version)
                    for item in entities
                ]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc business calendars.") from exc

    def list_policies(self) -> list[StoredRecord]:
        try:
            with self.session_factory() as session:
                entities = session.scalars(
                    select(SlaPolicy).order_by(SlaPolicy.code)
                ).all()
                return [
                    StoredRecord(self._policy_values(session, item), item.version)
                    for item in entities
                ]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc SLA policies.") from exc

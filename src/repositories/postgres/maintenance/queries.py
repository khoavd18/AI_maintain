"""Read-only preventive-maintenance and work-order queries."""

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
    ChecklistTemplate,
    PreventiveMaintenancePlan,
    Ticket,
    User,
    WorkOrder,
    WorkOrderAttachment,
)
from src.repositories.contracts import StorageUnavailableError, StoredPage, StoredRecord


class MaintenanceQueryRepository:
    """Own read-only maintenance plan, work-order, and evidence queries."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        plan_record: Callable[..., StoredRecord],
        template_record: Callable[..., StoredRecord],
        work_order_record: Callable[..., StoredRecord],
        evidence_record: Callable[..., StoredRecord],
        user_record: Callable[..., StoredRecord],
        iso_datetime: Callable[..., str | None],
    ) -> None:
        self.session_factory = session_factory
        self._plan_record = plan_record
        self._template_record = template_record
        self._work_order_record = work_order_record
        self._evidence_record = evidence_record
        self._user_record = user_record
        self._iso_datetime = iso_datetime

    def get_asset_state(self, asset_id: str) -> StoredRecord | None:
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
                        "last_maintenance_date": entity.last_maintenance_date.isoformat(),
                        "next_maintenance_date": entity.next_maintenance_date.isoformat(),
                        "maintenance_interval_days": entity.maintenance_interval_days,
                    },
                    version=entity.version,
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể đọc asset cho maintenance workflow."
            ) from exc

    def get_ticket_state(self, ticket_id: str) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(Ticket, ticket_id)
                if entity is None:
                    return None
                return StoredRecord(
                    {
                        "ticket_id": entity.ticket_id,
                        "asset_id": entity.asset_id,
                        "issue_description": entity.issue_description,
                        "priority": entity.priority,
                        "status": entity.status,
                        "technician_id": entity.technician_id,
                        "created_at": self._iso_datetime(entity.created_at),
                        "resolved_at": self._iso_datetime(entity.resolved_at),
                    },
                    version=entity.version,
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể đọc ticket cho work order."
            ) from exc

    def get_user_state(self, user_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(User, user_id)
                return self._user_record(entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc assignee user.") from exc

    def list_technicians(self) -> list[StoredRecord]:
        try:
            with self.session_factory() as session:
                entities = session.scalars(
                    select(User)
                    .where(User.role == "technician", User.is_active.is_(True))
                    .order_by(User.display_name)
                ).all()
                return [self._user_record(entity) for entity in entities]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể đọc danh sách technician."
            ) from exc

    def list_plans(
        self, *, filters: dict[str, Any], page: int, page_size: int
    ) -> StoredPage:
        try:
            with self.session_factory() as session:
                statement = select(PreventiveMaintenancePlan)
                if filters.get("asset_id"):
                    statement = statement.where(
                        PreventiveMaintenancePlan.asset_id == filters["asset_id"]
                    )
                if filters.get("status"):
                    statement = statement.where(
                        PreventiveMaintenancePlan.status == filters["status"]
                    )
                if filters.get("search"):
                    pattern = f"%{str(filters['search']).strip()}%"
                    statement = statement.where(
                        or_(
                            PreventiveMaintenancePlan.plan_code.ilike(pattern),
                            PreventiveMaintenancePlan.name.ilike(pattern),
                        )
                    )
                if filters.get("due_from"):
                    statement = statement.where(
                        PreventiveMaintenancePlan.next_due_date >= filters["due_from"]
                    )
                if filters.get("due_to"):
                    statement = statement.where(
                        PreventiveMaintenancePlan.next_due_date <= filters["due_to"]
                    )
                total = session.scalar(
                    select(func.count()).select_from(statement.subquery())
                ) or 0
                entities = session.scalars(
                    statement.order_by(
                        PreventiveMaintenancePlan.next_due_date.asc().nullslast(),
                        PreventiveMaintenancePlan.plan_code,
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
                return StoredPage(
                    items=[self._plan_record(session, entity) for entity in entities],
                    page=page,
                    page_size=page_size,
                    total=int(total),
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc maintenance plans.") from exc

    def get_plan(self, plan_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(PreventiveMaintenancePlan, plan_id)
                return self._plan_record(session, entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc maintenance plan.") from exc

    def list_templates(
        self, *, filters: dict[str, Any], page: int, page_size: int
    ) -> StoredPage:
        try:
            with self.session_factory() as session:
                statement = select(ChecklistTemplate)
                if filters.get("status"):
                    statement = statement.where(
                        ChecklistTemplate.status == filters["status"]
                    )
                if filters.get("asset_type"):
                    statement = statement.where(
                        ChecklistTemplate.asset_type == filters["asset_type"]
                    )
                if filters.get("search"):
                    pattern = f"%{str(filters['search']).strip()}%"
                    statement = statement.where(
                        or_(
                            ChecklistTemplate.code.ilike(pattern),
                            ChecklistTemplate.name.ilike(pattern),
                        )
                    )
                total = session.scalar(
                    select(func.count()).select_from(statement.subquery())
                ) or 0
                entities = session.scalars(
                    statement.order_by(
                        ChecklistTemplate.code,
                        ChecklistTemplate.version_number.desc(),
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
                return StoredPage(
                    items=[self._template_record(session, entity) for entity in entities],
                    page=page,
                    page_size=page_size,
                    total=int(total),
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc checklist templates.") from exc

    def get_template(self, template_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(ChecklistTemplate, template_id)
                return self._template_record(session, entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc checklist template.") from exc

    def list_work_orders(
        self, *, filters: dict[str, Any], page: int, page_size: int
    ) -> StoredPage:
        try:
            with self.session_factory() as session:
                statement = select(WorkOrder)
                field_map = {
                    "status": WorkOrder.status,
                    "work_order_type": WorkOrder.work_order_type,
                    "asset_id": WorkOrder.asset_id,
                    "assigned_to_user_id": WorkOrder.assigned_to_user_id,
                    "source_ticket_id": WorkOrder.source_ticket_id,
                    "preventive_plan_id": WorkOrder.preventive_plan_id,
                }
                for name, column in field_map.items():
                    if filters.get(name) is not None:
                        statement = statement.where(column == filters[name])
                if filters.get("due_from"):
                    statement = statement.where(WorkOrder.due_date >= filters["due_from"])
                if filters.get("due_to"):
                    statement = statement.where(WorkOrder.due_date <= filters["due_to"])
                if filters.get("search"):
                    pattern = f"%{str(filters['search']).strip()}%"
                    statement = statement.where(
                        or_(
                            WorkOrder.work_order_number.ilike(pattern),
                            WorkOrder.title.ilike(pattern),
                        )
                    )
                if filters.get("overdue") is not None:
                    entities = session.scalars(
                        statement.order_by(WorkOrder.due_date, WorkOrder.work_order_number)
                    ).all()
                    records = [
                        self._work_order_record(session, entity) for entity in entities
                    ]
                    records = [
                        record
                        for record in records
                        if bool(record.values["is_overdue"]) is bool(filters["overdue"])
                    ]
                    return StoredPage(
                        items=records[(page - 1) * page_size : page * page_size],
                        page=page,
                        page_size=page_size,
                        total=len(records),
                    )
                total = session.scalar(
                    select(func.count()).select_from(statement.subquery())
                ) or 0
                entities = session.scalars(
                    statement.order_by(WorkOrder.due_date, WorkOrder.work_order_number)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
                return StoredPage(
                    items=[
                        self._work_order_record(session, entity) for entity in entities
                    ],
                    page=page,
                    page_size=page_size,
                    total=int(total),
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc work orders.") from exc

    def get_work_order(self, work_order_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(WorkOrder, work_order_id)
                return (
                    self._work_order_record(session, entity, include_history=True)
                    if entity
                    else None
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc work order.") from exc

    def list_generated_due_dates(self, plan_id: UUID) -> set[date]:
        try:
            with self.session_factory() as session:
                return set(
                    session.scalars(
                        select(WorkOrder.due_date).where(
                            WorkOrder.preventive_plan_id == plan_id
                        )
                    ).all()
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc generated occurrences.") from exc

    def list_work_order_attachments(
        self, work_order_id: UUID, *, include_deleted: bool = False
    ) -> list[StoredRecord]:
        try:
            with self.session_factory() as session:
                statement = select(WorkOrderAttachment).where(
                    WorkOrderAttachment.work_order_id == work_order_id
                )
                if not include_deleted:
                    statement = statement.where(WorkOrderAttachment.deleted_at.is_(None))
                entities = session.scalars(
                    statement.order_by(WorkOrderAttachment.created_at.desc())
                ).all()
                return [self._evidence_record(entity) for entity in entities]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc work-order evidence.") from exc

    def get_work_order_attachment(
        self, work_order_id: UUID, attachment_id: UUID
    ) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.scalar(
                    select(WorkOrderAttachment).where(
                        WorkOrderAttachment.id == attachment_id,
                        WorkOrderAttachment.work_order_id == work_order_id,
                    )
                )
                return (
                    self._evidence_record(entity, include_storage_key=True)
                    if entity
                    else None
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc work-order evidence.") from exc

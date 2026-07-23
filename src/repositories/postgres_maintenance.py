"""PostgreSQL repository for preventive plans and standalone work orders."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.config.value_mappings import PRIORITY_CODE_TO_VI
from src.database.models import (
    Asset,
    AuditLog,
    ChecklistTemplate,
    ChecklistTemplateItem,
    MaintenanceLog,
    PreventiveMaintenancePlan,
    Ticket,
    User,
    WorkOrder,
    WorkOrderAttachment,
    WorkOrderChecklistItem,
)
from src.maintenance_management.domain import (
    CHECKLIST_RESPONSE_TYPE_LABELS,
    CHECKLIST_RESULT_LABELS,
    PLAN_STATUS_LABELS,
    TERMINAL_WORK_ORDER_STATUSES,
    WORK_ORDER_ATTACHMENT_CATEGORIES,
    WORK_ORDER_STATUS_LABELS,
    WORK_ORDER_TYPE_LABELS,
    ChecklistResponseType,
    ChecklistResultStatus,
    PlanStatus,
    WorkOrderStatus,
    WorkOrderType,
    recurrence_summary,
)
from src.repositories.contracts import (
    DuplicateIdentifierError,
    IntegrityViolationError,
    RecordNotFoundError,
    RepositoryError,
    StaleRecordError,
    StorageUnavailableError,
    StoredPage,
    StoredRecord,
)
from src.security.audit import AuditContext, safe_state
from src.security.service import append_audit_event

WORK_ORDER_SEQUENCE = "work_order_number_seq"

PLAN_AUDIT_FIELDS = {
    "id",
    "plan_code",
    "asset_id",
    "interval_value",
    "interval_unit",
    "start_date",
    "end_date",
    "local_timezone",
    "next_due_date",
    "last_generated_due_date",
    "status",
    "is_active",
    "default_assignee_user_id",
    "checklist_template_id",
    "version",
}
TEMPLATE_AUDIT_FIELDS = {
    "id",
    "code",
    "asset_type",
    "version_number",
    "status",
    "item_count",
    "version",
}
WORK_ORDER_AUDIT_FIELDS = {
    "id",
    "work_order_number",
    "work_order_type",
    "asset_id",
    "preventive_plan_id",
    "source_ticket_id",
    "assigned_to_user_id",
    "priority",
    "due_date",
    "status",
    "started_at",
    "completed_at",
    "verified_at",
    "cancelled_at",
    "maintenance_log_id",
    "version",
}
EVIDENCE_AUDIT_FIELDS = {
    "id",
    "work_order_id",
    "asset_id",
    "category",
    "original_filename",
    "media_type",
    "size_bytes",
    "checksum",
    "uploaded_by_user_id",
    "created_at",
    "deleted_at",
    "deleted_by_user_id",
}


class PostgresMaintenancePlanningRepository:
    """Persist planning workflows with explicit transaction boundaries."""

    backend_name = "postgresql"

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

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
            raise StorageUnavailableError("Không thể đọc asset cho maintenance workflow.") from exc

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
                        "created_at": _iso_datetime(entity.created_at),
                        "resolved_at": _iso_datetime(entity.resolved_at),
                    },
                    version=entity.version,
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc ticket cho work order.") from exc

    def get_user_state(self, user_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                entity = session.get(User, user_id)
                return _user_record(entity) if entity else None
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
                return [_user_record(entity) for entity in entities]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc danh sách technician.") from exc

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
                    items=[_plan_record(session, entity) for entity in entities],
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
                return _plan_record(session, entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc maintenance plan.") from exc

    def create_plan(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = PreventiveMaintenancePlan(id=uuid4(), **values)
                session.add(entity)
                session.flush()
                result = _plan_record(session, entity)
                _audit(
                    session,
                    audit_context,
                    action="maintenance_plan.created",
                    resource_type="maintenance_plan",
                    resource_id=str(entity.id),
                    after=result.values,
                    fields=PLAN_AUDIT_FIELDS,
                )
            return result
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="plan_code đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo maintenance plan.") from exc

    def update_plan(
        self,
        plan_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_actions: list[str],
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = session.get(
                    PreventiveMaintenancePlan, plan_id, with_for_update=True
                )
                if entity is None:
                    raise RecordNotFoundError(f"Không tìm thấy maintenance plan: {plan_id}")
                _require_version(entity.version, expected_version, str(plan_id))
                before = _plan_record(session, entity)
                for field, value in updates.items():
                    setattr(entity, field, value)
                session.flush()
                result = _plan_record(session, entity)
                for action in audit_actions:
                    _audit(
                        session,
                        audit_context,
                        action=action,
                        resource_type="maintenance_plan",
                        resource_id=str(plan_id),
                        before=before.values,
                        after=result.values,
                        fields=PLAN_AUDIT_FIELDS,
                    )
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError(
                "Maintenance plan đã thay đổi. Hãy tải lại dữ liệu."
            ) from exc
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="plan_code đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể cập nhật maintenance plan.") from exc

    def list_templates(
        self, *, filters: dict[str, Any], page: int, page_size: int
    ) -> StoredPage:
        try:
            with self.session_factory() as session:
                statement = select(ChecklistTemplate)
                if filters.get("status"):
                    statement = statement.where(ChecklistTemplate.status == filters["status"])
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
                        ChecklistTemplate.code, ChecklistTemplate.version_number.desc()
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
                return StoredPage(
                    items=[_template_record(session, entity) for entity in entities],
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
                return _template_record(session, entity) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc checklist template.") from exc

    def create_template(
        self,
        values: dict[str, Any],
        items: list[dict[str, Any]],
        *,
        audit_action: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = ChecklistTemplate(id=uuid4(), **values)
                session.add(entity)
                session.flush()
                for values_item in items:
                    session.add(
                        ChecklistTemplateItem(
                            id=uuid4(), template_id=entity.id, **values_item
                        )
                    )
                session.flush()
                result = _template_record(session, entity)
                _audit(
                    session,
                    audit_context,
                    action=audit_action,
                    resource_type="checklist_template",
                    resource_id=str(entity.id),
                    after=result.values,
                    fields=TEMPLATE_AUDIT_FIELDS,
                    metadata={"item_count": len(items)},
                )
            return result
        except IntegrityError as exc:
            _raise_integrity(
                exc, duplicate_message="Phiên bản checklist template đã tồn tại."
            )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo checklist template.") from exc

    def archive_template(
        self,
        template_id: UUID,
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = session.get(ChecklistTemplate, template_id, with_for_update=True)
                if entity is None:
                    raise RecordNotFoundError(
                        f"Không tìm thấy checklist template: {template_id}"
                    )
                _require_version(entity.version, expected_version, str(template_id))
                before = _template_record(session, entity)
                entity.status = "archived"
                entity.archived_at = _utc_now()
                session.flush()
                result = _template_record(session, entity)
                _audit(
                    session,
                    audit_context,
                    action="checklist_template.archived",
                    resource_type="checklist_template",
                    resource_id=str(template_id),
                    before=before.values,
                    after=result.values,
                    fields=TEMPLATE_AUDIT_FIELDS,
                )
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError(
                "Checklist template đã thay đổi. Hãy tải lại dữ liệu."
            ) from exc
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể archive checklist template.") from exc

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
                    records = [_work_order_record(session, entity) for entity in entities]
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
                    items=[_work_order_record(session, entity) for entity in entities],
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
                    _work_order_record(session, entity, include_history=True)
                    if entity
                    else None
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc work order.") from exc

    def create_work_order(
        self,
        values: dict[str, Any],
        checklist_items: list[dict[str, Any]],
        *,
        audit_action: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = _new_work_order(session, values)
                session.add(entity)
                session.flush()
                _snapshot_checklist(session, entity.id, checklist_items)
                session.flush()
                result = _work_order_record(session, entity)
                _audit(
                    session,
                    audit_context,
                    action=audit_action,
                    resource_type="work_order",
                    resource_id=str(entity.id),
                    after=result.values,
                    fields=WORK_ORDER_AUDIT_FIELDS,
                )
                if entity.source_ticket_id:
                    _audit(
                        session,
                        audit_context,
                        action="work_order.linked_to_ticket",
                        resource_type="ticket",
                        resource_id=entity.source_ticket_id,
                        metadata={"work_order_id": str(entity.id)},
                    )
            return result
        except IntegrityError as exc:
            _raise_integrity(
                exc,
                duplicate_message=(
                    "Work order trùng occurrence hoặc ticket đã có corrective work order đang mở."
                ),
            )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo work order.") from exc

    def update_work_order(
        self,
        work_order_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_action: str,
        audit_context: AuditContext,
        audit_metadata: dict[str, Any] | None = None,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = session.get(WorkOrder, work_order_id, with_for_update=True)
                if entity is None:
                    raise RecordNotFoundError(f"Không tìm thấy work order: {work_order_id}")
                _require_version(entity.version, expected_version, str(work_order_id))
                before = _work_order_record(session, entity)
                for field, value in updates.items():
                    setattr(entity, field, value)
                session.flush()
                result = _work_order_record(session, entity)
                _audit(
                    session,
                    audit_context,
                    action=audit_action,
                    resource_type="work_order",
                    resource_id=str(work_order_id),
                    before=before.values,
                    after=result.values,
                    fields=WORK_ORDER_AUDIT_FIELDS,
                    metadata=audit_metadata,
                )
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError("Work order đã thay đổi. Hãy tải lại dữ liệu.") from exc
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="Work order vi phạm ràng buộc duy nhất.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể cập nhật work order.") from exc

    def update_checklist(
        self,
        work_order_id: UUID,
        responses: list[dict[str, Any]],
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                work_order = session.get(WorkOrder, work_order_id, with_for_update=True)
                if work_order is None:
                    raise RecordNotFoundError(f"Không tìm thấy work order: {work_order_id}")
                _require_version(work_order.version, expected_version, str(work_order_id))
                items = {
                    item.id: item
                    for item in session.scalars(
                        select(WorkOrderChecklistItem)
                        .where(WorkOrderChecklistItem.work_order_id == work_order_id)
                        .with_for_update()
                    ).all()
                }
                for response in responses:
                    item_id = response["item_id"]
                    item = items.get(item_id)
                    if item is None:
                        raise IntegrityViolationError(
                            f"Checklist item không thuộc work order: {item_id}"
                        )
                    for field, value in response.items():
                        if field != "item_id":
                            setattr(item, field, value)
                work_order.updated_at = _utc_now()
                session.flush()
                result = _work_order_record(session, work_order)
                _audit(
                    session,
                    audit_context,
                    action="work_order.checklist_updated",
                    resource_type="work_order",
                    resource_id=str(work_order_id),
                    after=result.values,
                    fields=WORK_ORDER_AUDIT_FIELDS,
                    metadata={"updated_item_count": len(responses)},
                )
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError("Work order đã thay đổi. Hãy tải lại dữ liệu.") from exc
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="Checklist response bị trùng.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể cập nhật checklist.") from exc

    def complete_work_order(
        self,
        work_order_id: UUID,
        work_order_updates: dict[str, Any],
        log_values: dict[str, Any],
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                work_order = session.get(WorkOrder, work_order_id, with_for_update=True)
                if work_order is None:
                    raise RecordNotFoundError(f"Không tìm thấy work order: {work_order_id}")
                existing_log = session.scalar(
                    select(MaintenanceLog).where(
                        MaintenanceLog.work_order_id == work_order_id
                    )
                )
                if work_order.status in {"completed", "verified"} and existing_log:
                    return _work_order_record(session, work_order)
                _require_version(work_order.version, expected_version, str(work_order_id))
                if work_order.status != "in_progress":
                    raise IntegrityViolationError(
                        "Work order phải ở trạng thái in_progress trước khi hoàn thành."
                    )
                _require_completable_checklist(session, work_order_id)
                before = _work_order_record(session, work_order)
                if existing_log is None:
                    log_id = _next_identifier(session, "maintenance_log_id_seq", "LOG")
                    maintenance_log = MaintenanceLog(
                        log_id=log_id,
                        work_order_id=work_order_id,
                        **log_values,
                    )
                    session.add(maintenance_log)
                else:
                    log_id = existing_log.log_id
                for field, value in work_order_updates.items():
                    setattr(work_order, field, value)
                session.flush()
                result = _work_order_record(session, work_order)
                _audit(
                    session,
                    audit_context,
                    action="work_order.completed",
                    resource_type="work_order",
                    resource_id=str(work_order_id),
                    before=before.values,
                    after=result.values,
                    fields=WORK_ORDER_AUDIT_FIELDS,
                )
                if existing_log is None:
                    _audit(
                        session,
                        audit_context,
                        action="maintenance_log.created_from_work_order",
                        resource_type="maintenance_log",
                        resource_id=log_id,
                        metadata={
                            "work_order_id": str(work_order_id),
                            "asset_id": work_order.asset_id,
                            "ticket_id": work_order.source_ticket_id,
                        },
                    )
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError("Work order đã thay đổi. Hãy tải lại dữ liệu.") from exc
        except IntegrityError as exc:
            _raise_integrity(
                exc, duplicate_message="Work order đã có maintenance log liên kết."
            )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể hoàn thành work order.") from exc

    def verify_work_order(
        self,
        work_order_id: UUID,
        *,
        expected_version: int,
        verified_by_user_id: UUID,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                work_order = session.get(WorkOrder, work_order_id, with_for_update=True)
                if work_order is None:
                    raise RecordNotFoundError(f"Không tìm thấy work order: {work_order_id}")
                if work_order.status == "verified":
                    return _work_order_record(session, work_order)
                _require_version(work_order.version, expected_version, str(work_order_id))
                if work_order.status != "completed":
                    raise IntegrityViolationError(
                        "Chỉ work order completed mới có thể được verify."
                    )
                if work_order.assigned_to_user_id == verified_by_user_id:
                    raise IntegrityViolationError(
                        "Người thực hiện không được tự verify work order của mình."
                    )
                maintenance_log = session.scalar(
                    select(MaintenanceLog)
                    .where(MaintenanceLog.work_order_id == work_order_id)
                    .with_for_update()
                )
                if maintenance_log is None:
                    raise IntegrityViolationError(
                        "Work order completed phải có maintenance log trước khi verify."
                    )
                asset = session.get(Asset, work_order.asset_id, with_for_update=True)
                if asset is None:  # pragma: no cover - protected by FK
                    raise RecordNotFoundError(
                        f"Không tìm thấy asset: {work_order.asset_id}"
                    )
                before = _work_order_record(session, work_order)
                work_order.status = "verified"
                work_order.verified_by_user_id = verified_by_user_id
                work_order.verified_at = _utc_now()
                old_last = asset.last_maintenance_date
                old_next = asset.next_maintenance_date
                if maintenance_log.maintenance_date > asset.last_maintenance_date:
                    asset.last_maintenance_date = maintenance_log.maintenance_date
                earliest_plan_due = session.scalar(
                    select(func.min(PreventiveMaintenancePlan.next_due_date)).where(
                        PreventiveMaintenancePlan.asset_id == asset.asset_id,
                        PreventiveMaintenancePlan.status == "active",
                        PreventiveMaintenancePlan.next_due_date.is_not(None),
                    )
                )
                asset.next_maintenance_date = (
                    earliest_plan_due or maintenance_log.next_maintenance_date
                )
                asset.updated_by_user_id = verified_by_user_id
                session.flush()
                result = _work_order_record(session, work_order)
                _audit(
                    session,
                    audit_context,
                    action="work_order.verified",
                    resource_type="work_order",
                    resource_id=str(work_order_id),
                    before=before.values,
                    after=result.values,
                    fields=WORK_ORDER_AUDIT_FIELDS,
                )
                _audit(
                    session,
                    audit_context,
                    action="asset.maintenance_dates_updated",
                    resource_type="asset",
                    resource_id=asset.asset_id,
                    before={
                        "last_maintenance_date": old_last.isoformat(),
                        "next_maintenance_date": old_next.isoformat(),
                    },
                    after={
                        "last_maintenance_date": asset.last_maintenance_date.isoformat(),
                        "next_maintenance_date": asset.next_maintenance_date.isoformat(),
                    },
                    metadata={"work_order_id": str(work_order_id)},
                )
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError("Work order đã thay đổi. Hãy tải lại dữ liệu.") from exc
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="Work order đã được verify.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể verify work order.") from exc

    def generate_plan_occurrences(
        self,
        plan_id: UUID,
        *,
        schedule_signature: dict[str, Any],
        due_dates: list[date],
        next_due_date: date | None,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        try:
            with self.session_factory() as session, session.begin():
                plan = session.get(
                    PreventiveMaintenancePlan, plan_id, with_for_update=True
                )
                if plan is None:
                    raise RecordNotFoundError(f"Không tìm thấy maintenance plan: {plan_id}")
                for field, expected in schedule_signature.items():
                    if getattr(plan, field) != expected:
                        raise StaleRecordError(
                            f"Schedule của plan {plan.plan_code} đã thay đổi. Hãy chạy lại."
                        )
                asset = session.get(Asset, plan.asset_id, with_for_update=True)
                if asset is None:  # pragma: no cover - FK protection
                    raise RecordNotFoundError(f"Không tìm thấy asset: {plan.asset_id}")
                if plan.status != "active" or asset.lifecycle_status in {
                    "retired",
                    "archived",
                }:
                    return {
                        "plan_id": str(plan.id),
                        "plan_code": plan.plan_code,
                        "generated": [],
                        "skipped_due_dates": [value.isoformat() for value in due_dates],
                        "reason": "Plan hoặc asset không còn đủ điều kiện generation.",
                    }
                existing = set(
                    session.scalars(
                        select(WorkOrder.due_date).where(
                            WorkOrder.preventive_plan_id == plan_id,
                            WorkOrder.due_date.in_(due_dates) if due_dates else text("false"),
                        )
                    ).all()
                )
                template_items = _template_snapshot_items(
                    session, plan.checklist_template_id
                )
                generated: list[str] = []
                for due_date in due_dates:
                    if due_date in existing:
                        continue
                    entity = _new_work_order(
                        session,
                        {
                            "title": f"{plan.name} - {due_date.isoformat()}",
                            "description": plan.instructions or plan.description,
                            "work_order_type": "preventive",
                            "asset_id": plan.asset_id,
                            "preventive_plan_id": plan.id,
                            "source_ticket_id": None,
                            "assigned_to_user_id": plan.default_assignee_user_id,
                            "created_by_user_id": audit_context.actor_user_id,
                            "priority": plan.default_priority,
                            "scheduled_start_at": None,
                            "scheduled_end_at": None,
                            "due_date": due_date,
                            "local_timezone": plan.local_timezone,
                            "grace_period_days": plan.grace_period_days,
                            "estimated_duration_minutes": plan.estimated_duration_minutes,
                            "status": (
                                "assigned"
                                if plan.default_assignee_user_id is not None
                                else "planned"
                            ),
                        },
                    )
                    session.add(entity)
                    session.flush()
                    _snapshot_checklist(session, entity.id, template_items)
                    generated.append(entity.work_order_number)
                    _audit(
                        session,
                        audit_context,
                        action="work_order.generated",
                        resource_type="work_order",
                        resource_id=str(entity.id),
                        after=_work_order_record(session, entity).values,
                        fields=WORK_ORDER_AUDIT_FIELDS,
                        metadata={
                            "plan_id": str(plan.id),
                            "occurrence_due_date": due_date.isoformat(),
                        },
                    )
                if due_dates:
                    plan.last_generated_due_date = max(
                        value
                        for value in [plan.last_generated_due_date, *due_dates]
                        if value is not None
                    )
                    plan.next_due_date = next_due_date
                    plan.updated_by_user_id = audit_context.actor_user_id
                    session.flush()
                skipped = sorted(value for value in due_dates if value in existing)
                _audit(
                    session,
                    audit_context,
                    action="maintenance_plan.generation_processed",
                    resource_type="maintenance_plan",
                    resource_id=str(plan.id),
                    after=_plan_record(session, plan).values,
                    fields=PLAN_AUDIT_FIELDS,
                    metadata={
                        "generated_count": len(generated),
                        "skipped_count": len(skipped),
                    },
                )
                return {
                    "plan_id": str(plan.id),
                    "plan_code": plan.plan_code,
                    "generated": generated,
                    "skipped_due_dates": [value.isoformat() for value in skipped],
                    "reason": None,
                }
        except RepositoryError:
            raise
        except IntegrityError as exc:
            _raise_integrity(
                exc, duplicate_message="Occurrence đã được generator khác tạo trước."
            )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể generate preventive work order.") from exc

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
                return [_evidence_record(entity) for entity in entities]
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
                return _evidence_record(entity, include_storage_key=True) if entity else None
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc work-order evidence.") from exc

    def create_work_order_attachment(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = WorkOrderAttachment(id=uuid4(), **values)
                session.add(entity)
                session.flush()
                result = _evidence_record(entity, include_storage_key=True)
                _audit(
                    session,
                    audit_context,
                    action="work_order.attachment_uploaded",
                    resource_type="work_order",
                    resource_id=str(entity.work_order_id),
                    after=result.values,
                    fields=EVIDENCE_AUDIT_FIELDS,
                    metadata={"attachment_id": str(entity.id)},
                )
            return result
        except IntegrityError as exc:
            _raise_integrity(exc, duplicate_message="Storage key evidence đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể lưu metadata evidence.") from exc

    def delete_work_order_attachment(
        self,
        work_order_id: UUID,
        attachment_id: UUID,
        *,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = session.scalar(
                    select(WorkOrderAttachment)
                    .where(
                        WorkOrderAttachment.id == attachment_id,
                        WorkOrderAttachment.work_order_id == work_order_id,
                    )
                    .with_for_update()
                )
                if entity is None:
                    raise RecordNotFoundError(
                        f"Không tìm thấy evidence attachment: {attachment_id}"
                    )
                if entity.deleted_at is None:
                    before = _evidence_record(entity)
                    entity.deleted_at = _utc_now()
                    entity.deleted_by_user_id = audit_context.actor_user_id
                    session.flush()
                    result = _evidence_record(entity, include_storage_key=True)
                    _audit(
                        session,
                        audit_context,
                        action="work_order.attachment_deleted",
                        resource_type="work_order",
                        resource_id=str(work_order_id),
                        before=before.values,
                        after=result.values,
                        fields=EVIDENCE_AUDIT_FIELDS,
                        metadata={"attachment_id": str(entity.id)},
                    )
                else:
                    result = _evidence_record(entity, include_storage_key=True)
            return result
        except RepositoryError:
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể xóa evidence attachment.") from exc


def _new_work_order(session: Session, values: dict[str, Any]) -> WorkOrder:
    number = _next_identifier(session, WORK_ORDER_SEQUENCE, "WO")
    return WorkOrder(id=uuid4(), work_order_number=number, **values)


def _next_identifier(session: Session, sequence: str, prefix: str) -> str:
    number = session.scalar(text(f"SELECT nextval('{sequence}')"))
    if number is None:  # pragma: no cover
        raise StorageUnavailableError(f"Sequence {sequence} không trả về giá trị.")
    return f"{prefix}-{int(number):06d}"


def _snapshot_checklist(
    session: Session, work_order_id: UUID, items: list[dict[str, Any]]
) -> None:
    for values in items:
        session.add(
            WorkOrderChecklistItem(id=uuid4(), work_order_id=work_order_id, **values)
        )


def _template_snapshot_items(
    session: Session, template_id: UUID | None
) -> list[dict[str, Any]]:
    if template_id is None:
        return []
    entities = session.scalars(
        select(ChecklistTemplateItem)
        .where(ChecklistTemplateItem.template_id == template_id)
        .order_by(ChecklistTemplateItem.sequence)
    ).all()
    return [
        {
            "source_template_item_id": entity.id,
            "sequence": entity.sequence,
            "instruction": entity.instruction,
            "response_type": entity.response_type,
            "is_required": entity.is_required,
            "safety_critical": entity.safety_critical,
            "allow_not_applicable": entity.allow_not_applicable,
            "expected_unit": entity.expected_unit,
            "minimum_value": entity.minimum_value,
            "maximum_value": entity.maximum_value,
            "guidance": entity.guidance,
            "result_status": "pending",
            "boolean_value": None,
            "numeric_value": None,
            "text_value": None,
            "note": None,
            "completed_by_user_id": None,
            "completed_at": None,
        }
        for entity in entities
    ]


def _require_completable_checklist(session: Session, work_order_id: UUID) -> None:
    items = session.scalars(
        select(WorkOrderChecklistItem).where(
            WorkOrderChecklistItem.work_order_id == work_order_id
        )
    ).all()
    for item in items:
        if item.is_required and item.result_status == "pending":
            raise IntegrityViolationError(
                f"Checklist bắt buộc #{item.sequence} chưa được hoàn thành."
            )
        failed = item.result_status == "fail" or (
            item.response_type == "checkbox" and item.boolean_value is False
        )
        if item.safety_critical and failed:
            raise IntegrityViolationError(
                f"Checklist an toàn #{item.sequence} không đạt; không thể hoàn thành."
            )


def _plan_record(session: Session, entity: PreventiveMaintenancePlan) -> StoredRecord:
    asset = session.get(Asset, entity.asset_id)
    assignee = (
        session.get(User, entity.default_assignee_user_id)
        if entity.default_assignee_user_id
        else None
    )
    template = (
        session.get(ChecklistTemplate, entity.checklist_template_id)
        if entity.checklist_template_id
        else None
    )
    values = {
        "id": str(entity.id),
        "plan_code": entity.plan_code,
        "name": entity.name,
        "description": entity.description,
        "asset_id": entity.asset_id,
        "asset_name": asset.asset_name if asset else entity.asset_id,
        "schedule_type": entity.schedule_type,
        "interval_value": entity.interval_value,
        "interval_unit": entity.interval_unit,
        "recurrence_summary": recurrence_summary(
            entity.interval_value, entity.interval_unit
        ),
        "recurrence_rule": entity.recurrence_rule,
        "start_date": entity.start_date.isoformat(),
        "end_date": _iso_date(entity.end_date),
        "local_timezone": entity.local_timezone,
        "lead_time_days": entity.lead_time_days,
        "grace_period_days": entity.grace_period_days,
        "next_due_date": _iso_date(entity.next_due_date),
        "last_generated_due_date": _iso_date(entity.last_generated_due_date),
        "estimated_duration_minutes": entity.estimated_duration_minutes,
        "default_priority": entity.default_priority,
        "default_priority_display": PRIORITY_CODE_TO_VI[entity.default_priority],
        "default_assignee_user_id": _uuid_text(entity.default_assignee_user_id),
        "default_assignee_name": assignee.display_name if assignee else None,
        "checklist_template_id": _uuid_text(entity.checklist_template_id),
        "checklist_template_name": template.name if template else None,
        "instructions": entity.instructions,
        "status": entity.status,
        "status_display": PLAN_STATUS_LABELS[PlanStatus(entity.status)],
        "is_active": entity.is_active,
        "paused_at": _iso_datetime(entity.paused_at),
        "archived_at": _iso_datetime(entity.archived_at),
        "archive_reason": entity.archive_reason,
        "created_by_user_id": str(entity.created_by_user_id),
        "updated_by_user_id": str(entity.updated_by_user_id),
        "created_at": _iso_datetime(entity.created_at),
        "updated_at": _iso_datetime(entity.updated_at),
        "version": entity.version,
    }
    return StoredRecord(values, version=entity.version)


def _template_record(session: Session, entity: ChecklistTemplate) -> StoredRecord:
    items = session.scalars(
        select(ChecklistTemplateItem)
        .where(ChecklistTemplateItem.template_id == entity.id)
        .order_by(ChecklistTemplateItem.sequence)
    ).all()
    values = {
        "id": str(entity.id),
        "code": entity.code,
        "name": entity.name,
        "asset_type": entity.asset_type,
        "description": entity.description,
        "version_number": entity.version_number,
        "status": entity.status,
        "status_display": (
            "Đang hoạt động" if entity.status == "active" else "Đã lưu trữ"
        ),
        "created_by_user_id": str(entity.created_by_user_id),
        "created_at": _iso_datetime(entity.created_at),
        "updated_at": _iso_datetime(entity.updated_at),
        "archived_at": _iso_datetime(entity.archived_at),
        "version": entity.version,
        "item_count": len(items),
        "items": [_template_item_values(item) for item in items],
    }
    return StoredRecord(values, version=entity.version)


def _template_item_values(entity: ChecklistTemplateItem) -> dict[str, Any]:
    return {
        "id": str(entity.id),
        "sequence": entity.sequence,
        "instruction": entity.instruction,
        "response_type": entity.response_type,
        "response_type_display": CHECKLIST_RESPONSE_TYPE_LABELS[
            ChecklistResponseType(entity.response_type)
        ],
        "is_required": entity.is_required,
        "safety_critical": entity.safety_critical,
        "allow_not_applicable": entity.allow_not_applicable,
        "expected_unit": entity.expected_unit,
        "minimum_value": entity.minimum_value,
        "maximum_value": entity.maximum_value,
        "guidance": entity.guidance,
    }


def _work_order_record(
    session: Session,
    entity: WorkOrder,
    *,
    include_history: bool = False,
) -> StoredRecord:
    asset = session.get(Asset, entity.asset_id)
    assignee = (
        session.get(User, entity.assigned_to_user_id)
        if entity.assigned_to_user_id
        else None
    )
    verifier = (
        session.get(User, entity.verified_by_user_id)
        if entity.verified_by_user_id
        else None
    )
    plan = (
        session.get(PreventiveMaintenancePlan, entity.preventive_plan_id)
        if entity.preventive_plan_id
        else None
    )
    log = session.scalar(
        select(MaintenanceLog).where(MaintenanceLog.work_order_id == entity.id)
    )
    checklist = session.scalars(
        select(WorkOrderChecklistItem)
        .where(WorkOrderChecklistItem.work_order_id == entity.id)
        .order_by(WorkOrderChecklistItem.sequence)
    ).all()
    today = datetime.now(ZoneInfo(entity.local_timezone)).date()
    is_overdue = (
        WorkOrderStatus(entity.status) not in TERMINAL_WORK_ORDER_STATUSES
        and today > entity.due_date + timedelta(days=entity.grace_period_days)
    )
    values: dict[str, Any] = {
        "id": str(entity.id),
        "work_order_number": entity.work_order_number,
        "title": entity.title,
        "description": entity.description,
        "work_order_type": entity.work_order_type,
        "work_order_type_display": WORK_ORDER_TYPE_LABELS[
            WorkOrderType(entity.work_order_type)
        ],
        "asset_id": entity.asset_id,
        "asset_name": asset.asset_name if asset else entity.asset_id,
        "location": asset.location if asset else None,
        "preventive_plan_id": _uuid_text(entity.preventive_plan_id),
        "preventive_plan_code": plan.plan_code if plan else None,
        "source_ticket_id": entity.source_ticket_id,
        "assigned_to_user_id": _uuid_text(entity.assigned_to_user_id),
        "assigned_to_name": assignee.display_name if assignee else None,
        "created_by_user_id": str(entity.created_by_user_id),
        "verified_by_user_id": _uuid_text(entity.verified_by_user_id),
        "verified_by_name": verifier.display_name if verifier else None,
        "maintenance_log_id": log.log_id if log else None,
        "priority": entity.priority,
        "priority_display": PRIORITY_CODE_TO_VI[entity.priority],
        "scheduled_start_at": _iso_datetime(entity.scheduled_start_at),
        "scheduled_end_at": _iso_datetime(entity.scheduled_end_at),
        "due_date": entity.due_date.isoformat(),
        "local_timezone": entity.local_timezone,
        "grace_period_days": entity.grace_period_days,
        "is_overdue": is_overdue,
        "estimated_duration_minutes": entity.estimated_duration_minutes,
        "started_at": _iso_datetime(entity.started_at),
        "completed_at": _iso_datetime(entity.completed_at),
        "verified_at": _iso_datetime(entity.verified_at),
        "cancelled_at": _iso_datetime(entity.cancelled_at),
        "cancellation_reason": entity.cancellation_reason,
        "completion_summary": entity.completion_summary,
        "safety_notes": entity.safety_notes,
        "labor_minutes": entity.labor_minutes,
        "status": entity.status,
        "status_display": WORK_ORDER_STATUS_LABELS[WorkOrderStatus(entity.status)],
        "hold_reason": entity.hold_reason,
        "created_at": _iso_datetime(entity.created_at),
        "updated_at": _iso_datetime(entity.updated_at),
        "version": entity.version,
        "checklist": [_work_order_checklist_values(item) for item in checklist],
    }
    if include_history:
        history = session.scalars(
            select(AuditLog)
            .where(
                or_(
                    (AuditLog.resource_type == "work_order")
                    & (AuditLog.resource_id == str(entity.id)),
                    (AuditLog.resource_type == "maintenance_log")
                    & (AuditLog.resource_id == (log.log_id if log else "")),
                )
            )
            .order_by(AuditLog.occurred_at.desc())
            .limit(100)
        ).all()
        values["history"] = [
            {
                "id": str(event.id),
                "occurred_at": _iso_datetime(event.occurred_at),
                "actor_display_name": event.actor_display_name,
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
            }
            for event in history
        ]
    else:
        values["history"] = []
    return StoredRecord(values, version=entity.version)


def _work_order_checklist_values(entity: WorkOrderChecklistItem) -> dict[str, Any]:
    return {
        "id": str(entity.id),
        "source_template_item_id": _uuid_text(entity.source_template_item_id),
        "sequence": entity.sequence,
        "instruction": entity.instruction,
        "response_type": entity.response_type,
        "response_type_display": CHECKLIST_RESPONSE_TYPE_LABELS[
            ChecklistResponseType(entity.response_type)
        ],
        "is_required": entity.is_required,
        "safety_critical": entity.safety_critical,
        "allow_not_applicable": entity.allow_not_applicable,
        "expected_unit": entity.expected_unit,
        "minimum_value": entity.minimum_value,
        "maximum_value": entity.maximum_value,
        "guidance": entity.guidance,
        "result_status": entity.result_status,
        "result_status_display": CHECKLIST_RESULT_LABELS[
            ChecklistResultStatus(entity.result_status)
        ],
        "boolean_value": entity.boolean_value,
        "numeric_value": entity.numeric_value,
        "text_value": entity.text_value,
        "note": entity.note,
        "completed_by_user_id": _uuid_text(entity.completed_by_user_id),
        "completed_at": _iso_datetime(entity.completed_at),
    }


def _evidence_record(
    entity: WorkOrderAttachment, *, include_storage_key: bool = False
) -> StoredRecord:
    values = {
        "id": str(entity.id),
        "work_order_id": str(entity.work_order_id),
        "asset_id": entity.asset_id,
        "category": entity.category,
        "category_display": WORK_ORDER_ATTACHMENT_CATEGORIES[entity.category],
        "original_filename": entity.original_filename,
        "media_type": entity.media_type,
        "size_bytes": entity.size_bytes,
        "checksum": entity.checksum,
        "uploaded_by_user_id": str(entity.uploaded_by_user_id),
        "created_at": _iso_datetime(entity.created_at),
        "deleted_at": _iso_datetime(entity.deleted_at),
        "deleted_by_user_id": _uuid_text(entity.deleted_by_user_id),
    }
    if include_storage_key:
        values["storage_key"] = entity.storage_key
    return StoredRecord(values)


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


def _audit(
    session: Session,
    context: AuditContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    fields: set[str] | None = None,
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
        before_state=safe_state(before or {}, fields or set()) or None,
        after_state=safe_state(after or {}, fields or set()) or None,
        metadata=metadata,
    )


def _require_version(current: int, expected: int, identifier: str) -> None:
    if current != expected:
        raise StaleRecordError(
            f"Dữ liệu {identifier} đã thay đổi. Hãy tải lại trước khi cập nhật."
        )


def _raise_integrity(exc: IntegrityError, *, duplicate_message: str) -> None:
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if sqlstate == "23505":
        raise DuplicateIdentifierError(duplicate_message) from exc
    raise IntegrityViolationError(
        "Dữ liệu vi phạm foreign key hoặc ràng buộc toàn vẹn PostgreSQL."
    ) from exc


def _iso_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _uuid_text(value: UUID | None) -> str | None:
    return str(value) if value else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

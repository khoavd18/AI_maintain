"""PostgreSQL implementation of the transactional maintenance repository."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.config.value_mappings import (
    FAILURE_TYPE_CODE_TO_VI,
    FAILURE_TYPE_VI_TO_CODE,
    MAINTENANCE_RESULT_CODE_TO_VI,
    MAINTENANCE_RESULT_VI_TO_CODE,
    MAINTENANCE_TYPE_CODE_TO_VI,
    MAINTENANCE_TYPE_VI_TO_CODE,
    PRIORITY_CODE_TO_VI,
    PRIORITY_VI_TO_CODE,
    STATUS_VI_TO_CODE,
)
from src.database.models import Asset, MaintenanceLog, Ticket
from src.repositories.contracts import (
    DuplicateIdentifierError,
    IntegrityViolationError,
    RecordNotFoundError,
    RepositoryError,
    StaleRecordError,
    StorageUnavailableError,
    StoredRecord,
)
from src.repositories.postgres_assets import analytics_asset_values, asset_values
from src.security.audit import (
    AuditContext,
    LOG_AUDIT_FIELDS,
    TICKET_AUDIT_FIELDS,
    safe_state,
)
from src.security.service import append_audit_event
from src.ticket_management.domain import (
    LEGACY_STATUS_LABELS,
    TicketStatus,
    legacy_priority_dimensions,
)

REQUIRED_TABLES = {
    "assets",
    "maintenance_tickets",
    "maintenance_logs",
    "users",
    "refresh_sessions",
    "audit_logs",
    "locations",
    "asset_attachments",
    "preventive_maintenance_plans",
    "checklist_templates",
    "checklist_template_items",
    "work_orders",
    "work_order_checklist_items",
    "work_order_attachments",
    "ticket_categories",
    "ticket_subcategories",
    "ticket_intake_sources",
    "support_groups",
    "business_calendars",
    "business_working_periods",
    "business_calendar_holidays",
    "sla_policies",
    "sla_policy_targets",
    "ticket_sla_states",
    "ticket_sla_events",
    "ticket_comments",
    "ticket_comment_attachments",
    "ticket_escalation_events",
    "part_categories",
    "units_of_measure",
    "spare_parts",
    "stock_locations",
    "inventory_positions",
    "part_reorder_configurations",
    "inventory_operations",
    "inventory_movements",
    "work_order_part_requirements",
    "stock_reservations",
    "stock_reservation_events",
    "work_order_part_issues",
    "work_order_part_consumptions",
    "work_order_part_returns",
    "inventory_attachments",
    "alembic_version",
}
CANONICAL_SCHEMA_REVISION = "20260723_0006"
TICKET_SEQUENCE = "maintenance_ticket_id_seq"
LOG_SEQUENCE = "maintenance_log_id_seq"


class PostgresMaintenanceRepository:
    """Persist the focused maintenance workflow with database transactions."""

    backend_name = "postgresql"

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def check_health(self) -> None:
        try:
            with self.session_factory() as session:
                session.execute(text("SELECT 1"))
                table_names = set(inspect(session.get_bind()).get_table_names())
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "PostgreSQL primary storage is unavailable. Check DATABASE_URL and service health."
            ) from exc
        missing = REQUIRED_TABLES - table_names
        if missing:
            raise StorageUnavailableError(
                "PostgreSQL schema is not initialized. Run Alembic upgrade head before the API."
            )
        try:
            with self.session_factory() as session:
                revision = session.scalar(text("SELECT version_num FROM alembic_version"))
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể kiểm tra Alembic revision của PostgreSQL."
            ) from exc
        if revision != CANONICAL_SCHEMA_REVISION:
            raise StorageUnavailableError(
                "PostgreSQL schema is not at the current Alembic head. "
                "Run `alembic upgrade head` before the API."
            )

    def list_assets(self) -> list[StoredRecord]:
        entities = self._all(select(Asset).order_by(Asset.asset_id))
        return [_asset_record(entity) for entity in entities]

    def get_asset(self, asset_id: str) -> StoredRecord | None:
        entity = self._one(Asset, asset_id)
        return _asset_record(entity) if entity else None

    def list_tickets(self) -> list[StoredRecord]:
        entities = self._all(select(Ticket).order_by(Ticket.created_at.desc(), Ticket.ticket_id))
        return [_ticket_record(entity) for entity in entities]

    def get_ticket(self, ticket_id: str) -> StoredRecord | None:
        entity = self._one(Ticket, ticket_id)
        return _ticket_record(entity) if entity else None

    def create_ticket(
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext | None = None,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                ticket_id = _next_identifier(session, TICKET_SEQUENCE, "TCK")
                entity = Ticket(ticket_id=ticket_id, **_ticket_storage_values(values))
                session.add(entity)
                session.flush()
                result = _ticket_record(entity)
                if audit_context:
                    _append_workflow_audit(
                        session,
                        audit_context,
                        action="ticket.created",
                        resource_type="ticket",
                        resource_id=ticket_id,
                        after_state=safe_state(result.values, TICKET_AUDIT_FIELDS),
                    )
            return result
        except RepositoryError:
            raise
        except IntegrityError as exc:
            _raise_integrity_error(exc, identifier=ticket_id if "ticket_id" in locals() else None)
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể ghi ticket vào PostgreSQL primary storage."
            ) from exc

    def update_ticket(
        self,
        ticket_id: str,
        updates: dict[str, Any],
        *,
        expected_version: int | None,
        audit_context: AuditContext | None = None,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = session.get(Ticket, ticket_id)
                if entity is None:
                    raise RecordNotFoundError(f"Không tìm thấy ticket_id: {ticket_id}")
                _require_version(entity.version, expected_version, ticket_id)
                before = _ticket_record(entity)
                _apply_ticket_updates(entity, updates)
                session.flush()
                result = _ticket_record(entity)
                if audit_context:
                    _append_ticket_update_audits(
                        session,
                        audit_context,
                        ticket_id=ticket_id,
                        before=before.values,
                        after=result.values,
                    )
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError(
                f"Ticket {ticket_id} đã được cập nhật bởi yêu cầu khác. Hãy tải lại dữ liệu."
            ) from exc
        except IntegrityError as exc:
            _raise_integrity_error(exc, identifier=ticket_id)
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể cập nhật ticket trong PostgreSQL primary storage."
            ) from exc

    def list_maintenance_logs(self) -> list[StoredRecord]:
        entities = self._all(
            select(MaintenanceLog).order_by(
                MaintenanceLog.maintenance_date.desc(),
                MaintenanceLog.log_id.desc(),
            )
        )
        return [_maintenance_log_record(entity) for entity in entities]

    def get_maintenance_log(self, log_id: str) -> StoredRecord | None:
        entity = self._one(MaintenanceLog, log_id)
        return _maintenance_log_record(entity) if entity else None

    def snapshot(self) -> dict[str, list[StoredRecord]]:
        """Read all transactional tables from one repeatable-read snapshot."""

        try:
            with self.session_factory() as session, session.begin():
                session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                assets = session.scalars(select(Asset).order_by(Asset.asset_id)).all()
                tickets = session.scalars(select(Ticket).order_by(Ticket.ticket_id)).all()
                logs = session.scalars(select(MaintenanceLog).order_by(MaintenanceLog.log_id)).all()
                return {
                    "assets": [
                        StoredRecord(
                            analytics_asset_values(entity),
                            version=entity.version,
                        )
                        for entity in assets
                    ],
                    "maintenance_tickets": [_ticket_record(entity) for entity in tickets],
                    "maintenance_logs": [_maintenance_log_record(entity) for entity in logs],
                }
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể tạo transactional snapshot từ PostgreSQL."
            ) from exc

    def create_maintenance_log(
        self,
        values: dict[str, Any],
        *,
        last_maintenance_date: date,
        next_maintenance_date: date,
        expected_asset_version: int | None,
        expected_ticket_version: int | None,
        audit_context: AuditContext | None = None,
    ) -> StoredRecord:
        ticket_id = str(values["ticket_id"])
        asset_id = str(values["asset_id"])
        try:
            with self.session_factory() as session, session.begin():
                asset = session.get(Asset, asset_id, with_for_update=True)
                ticket = session.get(Ticket, ticket_id, with_for_update=True)
                if asset is None:
                    raise RecordNotFoundError(f"Không tìm thấy asset_id: {asset_id}")
                if ticket is None:
                    raise RecordNotFoundError(f"Không tìm thấy ticket_id: {ticket_id}")
                _require_version(asset.version, expected_asset_version, asset_id)
                _require_version(ticket.version, expected_ticket_version, ticket_id)
                if ticket.asset_id != asset_id:
                    raise IntegrityViolationError("asset_id không khớp với ticket đã chọn.")

                log_id = _next_identifier(session, LOG_SEQUENCE, "LOG")
                entity = MaintenanceLog(
                    log_id=log_id,
                    **_maintenance_log_storage_values(values),
                )
                session.add(entity)
                asset.last_maintenance_date = last_maintenance_date
                asset.next_maintenance_date = next_maintenance_date
                ticket.updated_at = datetime.now(timezone.utc)
                session.flush()
                result = _maintenance_log_record(entity)
                if audit_context:
                    _append_workflow_audit(
                        session,
                        audit_context,
                        action="maintenance_log.created",
                        resource_type="maintenance_log",
                        resource_id=log_id,
                        after_state=safe_state(result.values, LOG_AUDIT_FIELDS),
                        metadata={"ticket_id": ticket_id, "asset_id": asset_id},
                    )
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError(
                "Asset hoặc ticket đã thay đổi trong khi ghi maintenance log. Hãy tải lại dữ liệu."
            ) from exc
        except IntegrityError as exc:
            _raise_integrity_error(exc, identifier=log_id if "log_id" in locals() else None)
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể ghi maintenance log vào PostgreSQL primary storage."
            ) from exc

    def _all(self, statement) -> list[Any]:
        try:
            with self.session_factory() as session:
                return list(session.scalars(statement).all())
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc PostgreSQL primary storage.") from exc

    def _one(self, model, identifier: str) -> Any | None:
        try:
            with self.session_factory() as session:
                return session.get(model, identifier)
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc PostgreSQL primary storage.") from exc


def _append_ticket_update_audits(
    session: Session,
    context: AuditContext,
    *,
    ticket_id: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    before_state = safe_state(before, TICKET_AUDIT_FIELDS)
    after_state = safe_state(after, TICKET_AUDIT_FIELDS)
    changed = sorted(
        field for field in TICKET_AUDIT_FIELDS if before.get(field) != after.get(field)
    )
    actions: list[str] = []
    if before.get("technician_id") != after.get("technician_id"):
        actions.append("ticket.assigned")
    if before.get("priority") != after.get("priority"):
        actions.append("ticket.priority_changed")
    if before.get("status") != after.get("status"):
        actions.append("ticket.status_changed")
        if after.get("resolved_at"):
            actions.append("ticket.resolved")
    if not actions:
        actions.append("ticket.updated")
    for action in actions:
        _append_workflow_audit(
            session,
            context,
            action=action,
            resource_type="ticket",
            resource_id=ticket_id,
            before_state=before_state,
            after_state=after_state,
            metadata={"changed_fields": ",".join(changed)},
        )


def _append_workflow_audit(
    session: Session,
    context: AuditContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    before_state: dict[str, object] | None = None,
    after_state: dict[str, object] | None = None,
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
        before_state=before_state,
        after_state=after_state,
        metadata=metadata,
    )


def _next_identifier(session: Session, sequence: str, prefix: str) -> str:
    number = session.scalar(text(f"SELECT nextval('{sequence}')"))
    if number is None:  # pragma: no cover - PostgreSQL nextval always returns a value
        raise StorageUnavailableError(f"Sequence {sequence} không trả về giá trị.")
    return f"{prefix}-{int(number):06d}"


def _require_version(current: int, expected: int | None, identifier: str) -> None:
    if expected is not None and current != expected:
        raise StaleRecordError(f"Dữ liệu {identifier} đã thay đổi. Hãy tải lại trước khi cập nhật.")


def _ticket_storage_values(values: dict[str, Any]) -> dict[str, Any]:
    priority = _to_code(str(values["priority"]), PRIORITY_VI_TO_CODE, "priority")
    impact, urgency = legacy_priority_dimensions(priority)
    return {
        "asset_id": str(values["asset_id"]),
        "issue_description": str(values["issue_description"]),
        "priority": priority,
        "impact": impact.value,
        "urgency": urgency.value,
        "status": _to_code(str(values["status"]), STATUS_VI_TO_CODE, "status"),
        "failure_category": _to_code(
            str(values["failure_category"]),
            FAILURE_TYPE_VI_TO_CODE,
            "failure_category",
        ),
        "created_at": _as_datetime(values["created_at"]),
        "resolved_at": _as_optional_datetime(values.get("resolved_at")),
        "technician_id": str(values["technician_id"]),
        "manager_note": _optional_text(values.get("manager_note")),
        "note": _optional_text(values.get("note")),
    }


def _apply_ticket_updates(entity: Ticket, updates: dict[str, Any]) -> None:
    for field, value in updates.items():
        if field == "status":
            entity.status = _to_code(str(value), STATUS_VI_TO_CODE, field)
        elif field == "priority":
            entity.priority = _to_code(str(value), PRIORITY_VI_TO_CODE, field)
            impact, urgency = legacy_priority_dimensions(entity.priority)
            entity.impact = impact.value
            entity.urgency = urgency.value
        elif field == "resolved_at":
            entity.resolved_at = _as_optional_datetime(value)
        elif field in {"technician_id", "note"}:
            setattr(entity, field, _optional_text(value) if field == "note" else str(value))
        else:
            raise IntegrityViolationError(f"Không hỗ trợ cập nhật trường: {field}")


def _maintenance_log_storage_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticket_id": _optional_text(values.get("ticket_id")),
        "asset_id": str(values["asset_id"]),
        "maintenance_date": _as_date(values["maintenance_date"]),
        "maintenance_type": _to_code(
            str(values["maintenance_type"]),
            MAINTENANCE_TYPE_VI_TO_CODE,
            "maintenance_type",
        ),
        "technician_id": str(values["technician_id"]),
        "inspection_result": str(values["inspection_result"]),
        "actions_taken": str(values["actions_taken"]),
        "parts_replaced": _optional_text(values.get("parts_replaced")),
        "technician_note": str(values["technician_note"]),
        "maintenance_result": _to_code(
            str(values["maintenance_result"]),
            MAINTENANCE_RESULT_VI_TO_CODE,
            "maintenance_result",
        ),
        "follow_up_required": bool(values["follow_up_required"]),
        "next_maintenance_date": _as_date(values["next_maintenance_date"]),
    }


def _asset_record(entity: Asset) -> StoredRecord:
    return StoredRecord(asset_values(entity), version=entity.version)


def _ticket_record(entity: Ticket) -> StoredRecord:
    return StoredRecord(
        {
            "ticket_id": entity.ticket_id,
            "asset_id": entity.asset_id,
            "issue_description": entity.issue_description,
            "priority": _to_display(entity.priority, PRIORITY_CODE_TO_VI, "priority"),
            "status": LEGACY_STATUS_LABELS[TicketStatus(entity.status)],
            "failure_category": _to_display(
                entity.failure_category,
                FAILURE_TYPE_CODE_TO_VI,
                "failure_category",
            ),
            "created_at": _iso_datetime(entity.created_at),
            "resolved_at": _iso_datetime(entity.resolved_at) if entity.resolved_at else None,
            "technician_id": entity.technician_id,
            "manager_note": entity.manager_note,
            "note": entity.note,
        },
        version=entity.version,
    )


def _maintenance_log_record(entity: MaintenanceLog) -> StoredRecord:
    return StoredRecord(
        {
            "log_id": entity.log_id,
            "ticket_id": entity.ticket_id,
            "asset_id": entity.asset_id,
            "maintenance_date": entity.maintenance_date.isoformat(),
            "maintenance_type": _to_display(
                entity.maintenance_type,
                MAINTENANCE_TYPE_CODE_TO_VI,
                "maintenance_type",
            ),
            "technician_id": entity.technician_id,
            "inspection_result": entity.inspection_result,
            "actions_taken": entity.actions_taken,
            "parts_replaced": entity.parts_replaced,
            "technician_note": entity.technician_note,
            "maintenance_result": _to_display(
                entity.maintenance_result,
                MAINTENANCE_RESULT_CODE_TO_VI,
                "maintenance_result",
            ),
            "follow_up_required": entity.follow_up_required,
            "next_maintenance_date": entity.next_maintenance_date.isoformat(),
        }
    )


def _to_code(value: str, mapping: dict[str, str], field: str) -> str:
    try:
        return mapping[value]
    except KeyError as exc:
        raise IntegrityViolationError(f"Giá trị {field} không được hỗ trợ: {value}") from exc


def _to_display(value: str, mapping: dict[str, str], field: str) -> str:
    try:
        return mapping[value]
    except KeyError as exc:
        raise IntegrityViolationError(f"PostgreSQL chứa mã {field} không được hỗ trợ.") from exc


def _as_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IntegrityViolationError("Timestamp phải có timezone.")
    return parsed


def _as_optional_datetime(value: object) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    return _as_datetime(value)


def _iso_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _optional_text(value: object) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def _raise_integrity_error(exc: IntegrityError, *, identifier: str | None) -> None:
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if sqlstate == "23505":
        suffix = f": {identifier}" if identifier else ""
        raise DuplicateIdentifierError(f"Định danh đã tồn tại{suffix}") from exc
    raise IntegrityViolationError(
        "Dữ liệu vi phạm foreign key hoặc ràng buộc toàn vẹn PostgreSQL."
    ) from exc

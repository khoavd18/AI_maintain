"""PostgreSQL repository for asset lifecycle and location management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.config.value_mappings import (
    ASSET_CATEGORY_CODE_TO_VI,
    ASSET_TYPE_CODE_TO_VI,
    ATTACHMENT_CATEGORY_CODE_TO_VI,
    CRITICALITY_CODE_TO_VI,
    LIFECYCLE_STATUS_CODE_TO_VI,
    LOCATION_TYPE_CODE_TO_VI,
    OPERATIONAL_STATUS_CODE_TO_VI,
    OPERATIONAL_TO_LEGACY_STATUS_CODE,
    OWNERSHIP_TYPE_CODE_TO_VI,
    STATUS_CODE_TO_VI,
)
from src.database.models import Asset, AssetAttachment, AuditLog, Location, MaintenanceLog, Ticket
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
from src.security.audit import (
    ASSET_AUDIT_FIELDS,
    ATTACHMENT_AUDIT_FIELDS,
    LOCATION_AUDIT_FIELDS,
    AuditContext,
    safe_state,
)
from src.security.service import append_audit_event


class PostgresAssetRepository:
    """Persist asset-domain operations with transaction-coupled audit events."""

    backend_name = "postgresql"

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def list_asset_catalog(
        self,
        *,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> StoredPage:
        try:
            with self.session_factory() as session:
                statement = select(Asset)
                conditions = _asset_conditions(filters)
                if conditions:
                    statement = statement.where(*conditions)
                total = int(
                    session.scalar(
                        select(func.count()).select_from(statement.subquery())
                    )
                    or 0
                )
                assets = session.scalars(
                    statement.order_by(Asset.asset_id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
                paths = _location_paths(session)
                return StoredPage(
                    items=[
                        StoredRecord(
                            asset_values(asset, paths.get(asset.location_id)),
                            version=asset.version,
                        )
                        for asset in assets
                    ],
                    page=page,
                    page_size=page_size,
                    total=total,
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc danh mục asset từ PostgreSQL.") from exc

    def get_asset_profile(self, asset_id: str) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                asset = session.get(Asset, asset_id)
                if asset is None:
                    return None
                paths = _location_paths(session)
                return StoredRecord(
                    asset_values(asset, paths.get(asset.location_id)),
                    version=asset.version,
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc hồ sơ asset từ PostgreSQL.") from exc

    def get_asset_by_qr_token(self, token: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                asset = session.scalar(select(Asset).where(Asset.qr_token == token))
                if asset is None:
                    return None
                paths = _location_paths(session)
                return StoredRecord(
                    asset_values(asset, paths.get(asset.location_id)),
                    version=asset.version,
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tra cứu asset bằng QR.") from exc

    def create_asset(
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                asset = Asset(**values)
                session.add(asset)
                session.flush()
                paths = _location_paths(session)
                result = StoredRecord(
                    asset_values(asset, paths.get(asset.location_id)),
                    version=asset.version,
                )
                _append_audit(
                    session,
                    audit_context,
                    action="asset.created",
                    resource_type="asset",
                    resource_id=asset.asset_id,
                    after_state=safe_state(result.values, ASSET_AUDIT_FIELDS),
                )
                session.flush()
            return result
        except RepositoryError:
            raise
        except IntegrityError as exc:
            _raise_integrity_error(exc, duplicate_message="Asset ID hoặc serial number đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo asset trong PostgreSQL.") from exc

    def update_asset(
        self,
        asset_id: str,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_actions: list[str],
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                asset = session.get(Asset, asset_id, with_for_update=True)
                if asset is None:
                    raise RecordNotFoundError(f"Không tìm thấy asset_id: {asset_id}")
                _require_version(asset.version, expected_version, asset_id)
                paths = _location_paths(session)
                before = asset_values(asset, paths.get(asset.location_id))
                for field, value in updates.items():
                    setattr(asset, field, value)
                asset.updated_by_user_id = audit_context.actor_user_id
                asset.updated_at = _utc_now()
                session.flush()
                paths = _location_paths(session)
                after = asset_values(asset, paths.get(asset.location_id))
                changed_fields = sorted(
                    field for field in ASSET_AUDIT_FIELDS if before.get(field) != after.get(field)
                )
                for action in dict.fromkeys(audit_actions or ["asset.updated"]):
                    _append_audit(
                        session,
                        audit_context,
                        action=action,
                        resource_type="asset",
                        resource_id=asset_id,
                        before_state=safe_state(before, ASSET_AUDIT_FIELDS),
                        after_state=safe_state(after, ASSET_AUDIT_FIELDS),
                        metadata={"changed_fields": ",".join(changed_fields)},
                    )
                session.flush()
                result = StoredRecord(after, version=asset.version)
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError(
                f"Asset {asset_id} đã thay đổi. Hãy tải lại hồ sơ trước khi lưu."
            ) from exc
        except IntegrityError as exc:
            _raise_integrity_error(exc, duplicate_message="Serial number đã được sử dụng.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể cập nhật asset trong PostgreSQL.") from exc

    def list_locations(self, *, include_archived: bool) -> list[StoredRecord]:
        try:
            with self.session_factory() as session:
                statement = select(Location)
                if not include_archived:
                    statement = statement.where(Location.is_active.is_(True))
                locations = session.scalars(statement.order_by(Location.code)).all()
                paths = _location_paths(session)
                counts = dict(
                    session.execute(
                        select(Asset.location_id, func.count(Asset.asset_id))
                        .where(Asset.location_id.is_not(None))
                        .group_by(Asset.location_id)
                    ).all()
                )
                return [
                    StoredRecord(
                        location_values(
                            location,
                            paths.get(location.id),
                            asset_count=int(counts.get(location.id, 0)),
                        ),
                        version=location.version,
                    )
                    for location in locations
                ]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc cây vị trí từ PostgreSQL.") from exc

    def get_location(self, location_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                location = session.get(Location, location_id)
                if location is None:
                    return None
                paths = _location_paths(session)
                count = int(
                    session.scalar(
                        select(func.count(Asset.asset_id)).where(
                            Asset.location_id == location_id
                        )
                    )
                    or 0
                )
                return StoredRecord(
                    location_values(location, paths.get(location.id), asset_count=count),
                    version=location.version,
                )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc vị trí từ PostgreSQL.") from exc

    def create_location(
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                location = Location(
                    **values,
                    created_by_user_id=audit_context.actor_user_id,
                    updated_by_user_id=audit_context.actor_user_id,
                )
                session.add(location)
                session.flush()
                paths = _location_paths(session)
                result = StoredRecord(
                    location_values(location, paths.get(location.id), asset_count=0),
                    version=location.version,
                )
                _append_audit(
                    session,
                    audit_context,
                    action="location.created",
                    resource_type="location",
                    resource_id=str(location.id),
                    after_state=safe_state(result.values, LOCATION_AUDIT_FIELDS),
                )
                session.flush()
            return result
        except RepositoryError:
            raise
        except IntegrityError as exc:
            _raise_integrity_error(exc, duplicate_message="Mã vị trí đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể tạo vị trí trong PostgreSQL.") from exc

    def update_location(
        self,
        location_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        audit_action: str,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                location = session.get(Location, location_id, with_for_update=True)
                if location is None:
                    raise RecordNotFoundError(f"Không tìm thấy location_id: {location_id}")
                _require_version(location.version, expected_version, str(location_id))
                paths = _location_paths(session)
                before = location_values(location, paths.get(location.id), asset_count=0)
                for field, value in updates.items():
                    setattr(location, field, value)
                location.updated_by_user_id = audit_context.actor_user_id
                location.updated_at = _utc_now()
                session.flush()
                paths = _location_paths(session)
                count = int(
                    session.scalar(
                        select(func.count(Asset.asset_id)).where(
                            Asset.location_id == location_id
                        )
                    )
                    or 0
                )
                after = location_values(location, paths.get(location.id), asset_count=count)
                _append_audit(
                    session,
                    audit_context,
                    action=audit_action,
                    resource_type="location",
                    resource_id=str(location_id),
                    before_state=safe_state(before, LOCATION_AUDIT_FIELDS),
                    after_state=safe_state(after, LOCATION_AUDIT_FIELDS),
                )
                session.flush()
                result = StoredRecord(after, version=location.version)
            return result
        except RepositoryError:
            raise
        except StaleDataError as exc:
            raise StaleRecordError("Vị trí đã thay đổi. Hãy tải lại trước khi lưu.") from exc
        except IntegrityError as exc:
            _raise_integrity_error(exc, duplicate_message="Mã vị trí đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể cập nhật vị trí trong PostgreSQL.") from exc

    def list_attachments(
        self,
        asset_id: str,
        *,
        include_deleted: bool = False,
    ) -> list[StoredRecord]:
        try:
            with self.session_factory() as session:
                statement = select(AssetAttachment).where(
                    AssetAttachment.asset_id == asset_id
                )
                if not include_deleted:
                    statement = statement.where(AssetAttachment.deleted_at.is_(None))
                attachments = session.scalars(
                    statement.order_by(AssetAttachment.created_at.desc())
                ).all()
                return [StoredRecord(attachment_values(item, include_storage_key=True)) for item in attachments]
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc tệp đính kèm từ PostgreSQL.") from exc

    def get_attachment(self, asset_id: str, attachment_id: UUID) -> StoredRecord | None:
        try:
            with self.session_factory() as session:
                attachment = session.get(AssetAttachment, attachment_id)
                if attachment is None or attachment.asset_id != asset_id:
                    return None
                return StoredRecord(attachment_values(attachment, include_storage_key=True))
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc metadata tệp đính kèm.") from exc

    def create_attachment(
        self,
        values: dict[str, Any],
        *,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                attachment = AssetAttachment(
                    **values,
                    uploaded_by_user_id=audit_context.actor_user_id,
                )
                session.add(attachment)
                session.flush()
                result = StoredRecord(
                    attachment_values(attachment, include_storage_key=True)
                )
                _append_audit(
                    session,
                    audit_context,
                    action="attachment.uploaded",
                    resource_type="asset_attachment",
                    resource_id=str(attachment.id),
                    after_state=safe_state(result.values, ATTACHMENT_AUDIT_FIELDS),
                    metadata={"asset_id": attachment.asset_id},
                )
                session.flush()
            return result
        except RepositoryError:
            raise
        except IntegrityError as exc:
            _raise_integrity_error(exc, duplicate_message="Storage key của tệp đã tồn tại.")
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể ghi metadata tệp đính kèm.") from exc

    def delete_attachment(
        self,
        asset_id: str,
        attachment_id: UUID,
        *,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                attachment = session.get(AssetAttachment, attachment_id, with_for_update=True)
                if attachment is None or attachment.asset_id != asset_id:
                    raise RecordNotFoundError("Không tìm thấy tệp đính kèm của asset.")
                if attachment.deleted_at is not None:
                    raise RecordNotFoundError("Tệp đính kèm đã được xóa trước đó.")
                before = attachment_values(attachment, include_storage_key=True)
                attachment.deleted_at = _utc_now()
                attachment.deleted_by_user_id = audit_context.actor_user_id
                session.flush()
                after = attachment_values(attachment, include_storage_key=True)
                _append_audit(
                    session,
                    audit_context,
                    action="attachment.deleted",
                    resource_type="asset_attachment",
                    resource_id=str(attachment.id),
                    before_state=safe_state(before, ATTACHMENT_AUDIT_FIELDS),
                    after_state=safe_state(after, ATTACHMENT_AUDIT_FIELDS),
                    metadata={"asset_id": asset_id},
                )
                session.flush()
                result = StoredRecord(after)
            return result
        except RepositoryError:
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể xóa metadata tệp đính kèm.") from exc

    def list_asset_history(
        self,
        asset_id: str,
        *,
        page: int,
        page_size: int,
    ) -> StoredPage:
        try:
            with self.session_factory() as session:
                asset = session.get(Asset, asset_id)
                if asset is None:
                    raise RecordNotFoundError(f"Không tìm thấy asset_id: {asset_id}")
                events = _asset_history_events(session, asset)
                total = len(events)
                start = (page - 1) * page_size
                items = events[start : start + page_size]
                return StoredPage(
                    items=[StoredRecord(item) for item in items],
                    page=page,
                    page_size=page_size,
                    total=total,
                )
        except RepositoryError:
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError("Không thể đọc lịch sử asset.") from exc


def asset_values(asset: Asset, location_breadcrumb: str | None = None) -> dict[str, Any]:
    """Return a rich asset record plus the unchanged legacy analytics fields."""

    legacy_status_code = OPERATIONAL_TO_LEGACY_STATUS_CODE[asset.operational_status]
    return {
        "asset_id": asset.asset_id,
        "asset_name": asset.asset_name,
        "asset_type": ASSET_TYPE_CODE_TO_VI[asset.asset_type],
        "asset_type_code": asset.asset_type,
        "asset_category": asset.asset_category,
        "asset_category_display": ASSET_CATEGORY_CODE_TO_VI[asset.asset_category],
        "manufacturer": asset.manufacturer,
        "model": asset.model,
        "serial_number": asset.serial_number,
        "production_year": asset.production_year,
        "location": asset.location,
        "location_id": str(asset.location_id) if asset.location_id else None,
        "location_breadcrumb": location_breadcrumb or asset.location,
        "criticality": CRITICALITY_CODE_TO_VI[asset.criticality],
        "criticality_code": asset.criticality,
        "status": STATUS_CODE_TO_VI[legacy_status_code],
        "lifecycle_status": asset.lifecycle_status,
        "lifecycle_status_display": LIFECYCLE_STATUS_CODE_TO_VI[asset.lifecycle_status],
        "lifecycle_status_before_archive": asset.lifecycle_status_before_archive,
        "operational_status": asset.operational_status,
        "operational_status_display": OPERATIONAL_STATUS_CODE_TO_VI[
            asset.operational_status
        ],
        "operational_status_before_archive": asset.operational_status_before_archive,
        "installation_date": asset.installation_date.isoformat(),
        "installed_at": _iso_datetime(asset.installed_at),
        "commissioned_at": _optional_datetime(asset.commissioned_at),
        "retired_at": _optional_datetime(asset.retired_at),
        "archived_at": _optional_datetime(asset.archived_at),
        "archive_reason": asset.archive_reason,
        "ownership_type": asset.ownership_type,
        "ownership_type_display": OWNERSHIP_TYPE_CODE_TO_VI[asset.ownership_type],
        "description": asset.description,
        "warranty_start_date": _optional_date(asset.warranty_start_date),
        "warranty_end_date": _optional_date(asset.warranty_end_date),
        "warranty_provider": asset.warranty_provider,
        "warranty_reference": asset.warranty_reference,
        "last_maintenance_date": asset.last_maintenance_date.isoformat(),
        "maintenance_interval_days": asset.maintenance_interval_days,
        "next_maintenance_date": asset.next_maintenance_date.isoformat(),
        "created_at": _iso_datetime(asset.created_at),
        "updated_at": _iso_datetime(asset.updated_at),
        "created_by_user_id": str(asset.created_by_user_id)
        if asset.created_by_user_id
        else None,
        "updated_by_user_id": str(asset.updated_by_user_id)
        if asset.updated_by_user_id
        else None,
        "version": asset.version,
        "qr_lookup_token": str(asset.qr_token),
    }


def analytics_asset_values(asset: Asset) -> dict[str, Any]:
    """Return exactly the legacy ten-column batch analytics contract."""

    values = asset_values(asset)
    return {
        "asset_id": values["asset_id"],
        "asset_name": values["asset_name"],
        "asset_type": values["asset_type"],
        "location": values["location"],
        "criticality": values["criticality"],
        "status": values["status"],
        "installation_date": values["installation_date"],
        "last_maintenance_date": values["last_maintenance_date"],
        "maintenance_interval_days": values["maintenance_interval_days"],
        "next_maintenance_date": values["next_maintenance_date"],
    }


def location_values(
    location: Location,
    breadcrumb: str | None,
    *,
    asset_count: int,
) -> dict[str, Any]:
    return {
        "id": str(location.id),
        "code": location.code,
        "name": location.name,
        "location_type": location.location_type,
        "location_type_display": LOCATION_TYPE_CODE_TO_VI[location.location_type],
        "parent_id": str(location.parent_id) if location.parent_id else None,
        "breadcrumb": breadcrumb or location.name,
        "description": location.description,
        "is_active": location.is_active,
        "asset_count": asset_count,
        "created_at": _iso_datetime(location.created_at),
        "updated_at": _iso_datetime(location.updated_at),
        "version": location.version,
    }


def attachment_values(
    attachment: AssetAttachment,
    *,
    include_storage_key: bool,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": str(attachment.id),
        "asset_id": attachment.asset_id,
        "category": attachment.category,
        "category_display": ATTACHMENT_CATEGORY_CODE_TO_VI[attachment.category],
        "original_filename": attachment.original_filename,
        "media_type": attachment.media_type,
        "size_bytes": attachment.size_bytes,
        "checksum": attachment.checksum,
        "uploaded_by_user_id": str(attachment.uploaded_by_user_id),
        "created_at": _iso_datetime(attachment.created_at),
        "deleted_at": _optional_datetime(attachment.deleted_at),
        "deleted_by_user_id": str(attachment.deleted_by_user_id)
        if attachment.deleted_by_user_id
        else None,
    }
    if include_storage_key:
        values["_storage_key"] = attachment.storage_key
    return values


def _asset_conditions(filters: dict[str, Any]) -> list[Any]:
    conditions: list[Any] = []
    if not filters.get("include_archived"):
        conditions.append(Asset.lifecycle_status != "archived")
    for field in (
        "asset_type",
        "criticality",
        "lifecycle_status",
        "operational_status",
        "location_id",
    ):
        value = filters.get(field)
        if value is not None:
            conditions.append(getattr(Asset, field) == value)
    search = str(filters.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                Asset.asset_id.ilike(pattern),
                Asset.asset_name.ilike(pattern),
                Asset.manufacturer.ilike(pattern),
                Asset.model.ilike(pattern),
                Asset.serial_number.ilike(pattern),
            )
        )
    return conditions


def _location_paths(session: Session) -> dict[UUID, str]:
    locations = list(session.scalars(select(Location)).all())
    by_id = {location.id: location for location in locations}
    cache: dict[UUID, str] = {}

    def path(location_id: UUID, visiting: set[UUID]) -> str:
        if location_id in cache:
            return cache[location_id]
        location = by_id[location_id]
        if location_id in visiting:
            return location.name
        if location.parent_id is None or location.parent_id not in by_id:
            result = location.name
        else:
            result = f"{path(location.parent_id, visiting | {location_id})} / {location.name}"
        cache[location_id] = result
        return result

    for identifier in by_id:
        path(identifier, set())
    return cache


def _asset_history_events(session: Session, asset: Asset) -> list[dict[str, Any]]:
    audit_events = list(
        session.scalars(
            select(AuditLog)
            .where(
                AuditLog.resource_type.in_(
                    ["asset", "ticket", "maintenance_log", "asset_attachment"]
                )
            )
            .order_by(AuditLog.occurred_at.desc())
        ).all()
    )
    matching_audits = [event for event in audit_events if _audit_matches_asset(event, asset.asset_id)]
    events = [_history_from_audit(event) for event in matching_audits]

    created_audits = {
        (event.resource_type, event.resource_id)
        for event in matching_audits
        if event.action in {"asset.created", "ticket.created", "maintenance_log.created"}
    }
    if ("asset", asset.asset_id) not in created_audits:
        events.append(
            _synthetic_history(
                identifier=f"asset-import:{asset.asset_id}",
                occurred_at=asset.created_at,
                action="asset.imported",
                event_type="asset",
                summary="Asset được nhập từ dữ liệu canonical.",
                resource_type="asset",
                resource_id=asset.asset_id,
            )
        )
    tickets = session.scalars(
        select(Ticket).where(Ticket.asset_id == asset.asset_id)
    ).all()
    for ticket in tickets:
        if ("ticket", ticket.ticket_id) not in created_audits:
            events.append(
                _synthetic_history(
                    identifier=f"ticket:{ticket.ticket_id}",
                    occurred_at=ticket.created_at,
                    action="ticket.recorded",
                    event_type="ticket",
                    summary=f"Ticket {ticket.ticket_id} được ghi nhận cho asset.",
                    resource_type="ticket",
                    resource_id=ticket.ticket_id,
                )
            )
    logs = session.scalars(
        select(MaintenanceLog).where(MaintenanceLog.asset_id == asset.asset_id)
    ).all()
    for log in logs:
        if ("maintenance_log", log.log_id) not in created_audits:
            events.append(
                _synthetic_history(
                    identifier=f"maintenance-log:{log.log_id}",
                    occurred_at=log.created_at,
                    action="maintenance_log.recorded",
                    event_type="maintenance",
                    summary=f"Kết quả bảo trì {log.log_id} được ghi nhận.",
                    resource_type="maintenance_log",
                    resource_id=log.log_id,
                )
            )
    return sorted(events, key=lambda item: str(item["occurred_at"]), reverse=True)


def _audit_matches_asset(event: AuditLog, asset_id: str) -> bool:
    if event.resource_type == "asset" and event.resource_id == asset_id:
        return True
    candidates = [event.before_state, event.after_state, event.event_metadata]
    return any(
        isinstance(candidate, dict) and candidate.get("asset_id") == asset_id
        for candidate in candidates
    )


def _history_from_audit(event: AuditLog) -> dict[str, Any]:
    before = event.before_state or {}
    after = event.after_state or {}
    changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
    return {
        "id": f"audit:{event.id}",
        "occurred_at": _iso_datetime(event.occurred_at),
        "action": event.action,
        "event_type": _event_type(event.action),
        "summary": _history_summary(event.action, event.resource_id),
        "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
        "actor_display_name": event.actor_display_name,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "changed_fields": changed,
    }


def _synthetic_history(
    *,
    identifier: str,
    occurred_at: datetime,
    action: str,
    event_type: str,
    summary: str,
    resource_type: str,
    resource_id: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "occurred_at": _iso_datetime(occurred_at),
        "action": action,
        "event_type": event_type,
        "summary": summary,
        "actor_user_id": None,
        "actor_display_name": None,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "changed_fields": [],
    }


def _event_type(action: str) -> str:
    if action.startswith("ticket."):
        return "ticket"
    if action.startswith("maintenance_log."):
        return "maintenance"
    if action.startswith("attachment."):
        return "attachment"
    if "location" in action:
        return "location"
    if "status" in action or "lifecycle" in action or action.endswith("archived"):
        return "status"
    return "asset"


def _history_summary(action: str, resource_id: str | None) -> str:
    summaries = {
        "asset.created": "Asset được đăng ký.",
        "asset.updated": "Hồ sơ kỹ thuật của asset được cập nhật.",
        "asset.location_changed": "Vị trí asset được thay đổi.",
        "asset.operational_status_changed": "Trạng thái vận hành được thay đổi.",
        "asset.lifecycle_transitioned": "Trạng thái vòng đời được chuyển đổi.",
        "asset.archived": "Asset được lưu trữ và ngừng nhận ticket mới.",
        "asset.restored": "Asset được khôi phục khỏi trạng thái lưu trữ.",
        "attachment.uploaded": "Tệp đính kèm được tải lên.",
        "attachment.deleted": "Tệp đính kèm được xóa mềm.",
        "ticket.created": f"Ticket {resource_id or ''} được tạo cho asset.",
        "ticket.assigned": f"Ticket {resource_id or ''} được phân công.",
        "ticket.status_changed": f"Trạng thái ticket {resource_id or ''} được cập nhật.",
        "ticket.resolved": f"Ticket {resource_id or ''} được đánh dấu đã xử lý.",
        "maintenance_log.created": f"Kết quả bảo trì {resource_id or ''} được ghi nhận.",
    }
    return summaries.get(action, f"Sự kiện {action} được ghi nhận.")


def _append_audit(
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


def _require_version(current: int, expected: int, identifier: str) -> None:
    if current != expected:
        raise StaleRecordError(
            f"Dữ liệu {identifier} đã thay đổi. Hãy tải lại trước khi cập nhật."
        )


def _raise_integrity_error(exc: IntegrityError, *, duplicate_message: str) -> None:
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if sqlstate == "23505":
        raise DuplicateIdentifierError(duplicate_message) from exc
    raise IntegrityViolationError(
        "Dữ liệu vi phạm foreign key hoặc ràng buộc toàn vẹn PostgreSQL."
    ) from exc


def _iso_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _optional_datetime(value: datetime | None) -> str | None:
    return _iso_datetime(value) if value else None


def _optional_date(value) -> str | None:
    return value.isoformat() if value else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

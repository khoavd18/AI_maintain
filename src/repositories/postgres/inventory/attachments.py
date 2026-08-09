"""Inventory evidence metadata persistence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import InventoryAttachment, InventoryMovement
from src.repositories.contracts import (
    RecordNotFoundError,
    StorageUnavailableError,
    StoredRecord,
)
from src.security.audit import AuditContext


class InventoryAttachmentRepository:
    """Own append-only/soft-delete inventory evidence metadata changes."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        attachment_record: Callable[..., StoredRecord],
        audit: Callable[..., None],
        raise_integrity: Callable[..., None],
        utc_now: Callable[..., Any],
        audit_fields: set[str],
    ) -> None:
        self.session_factory = session_factory
        self._attachment_record = attachment_record
        self._audit = audit
        self._raise_integrity = raise_integrity
        self._utc_now = utc_now
        self._audit_fields = audit_fields

    def create(
        self, values: dict[str, Any], *, audit_context: AuditContext
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                if session.get(InventoryMovement, values["movement_id"]) is None:
                    raise RecordNotFoundError(
                        f"Không tìm thấy stock movement: {values['movement_id']}"
                    )
                entity = InventoryAttachment(id=uuid4(), **values)
                session.add(entity)
                session.flush()
                result = self._attachment_record(entity, include_storage_key=True)
                self._audit(
                    session,
                    audit_context,
                    action="inventory.attachment_uploaded",
                    resource_type="inventory_movement",
                    resource_id=str(entity.movement_id),
                    after=result.values,
                    fields=self._audit_fields,
                    metadata={"attachment_id": str(entity.id)},
                )
            return result
        except RecordNotFoundError:
            raise
        except IntegrityError as exc:
            self._raise_integrity(
                exc, duplicate_message="Storage key evidence đã tồn tại."
            )
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể lưu inventory evidence metadata."
            ) from exc

    def delete(
        self,
        movement_id: UUID,
        attachment_id: UUID,
        *,
        audit_context: AuditContext,
    ) -> StoredRecord:
        try:
            with self.session_factory() as session, session.begin():
                entity = session.scalar(
                    select(InventoryAttachment)
                    .where(
                        InventoryAttachment.id == attachment_id,
                        InventoryAttachment.movement_id == movement_id,
                    )
                    .with_for_update()
                )
                if entity is None:
                    raise RecordNotFoundError(
                        f"Không tìm thấy inventory evidence: {attachment_id}"
                    )
                if entity.deleted_at is None:
                    before = self._attachment_record(entity)
                    entity.deleted_at = self._utc_now()
                    entity.deleted_by_user_id = audit_context.actor_user_id
                    session.flush()
                    result = self._attachment_record(entity, include_storage_key=True)
                    self._audit(
                        session,
                        audit_context,
                        action="inventory.attachment_deleted",
                        resource_type="inventory_movement",
                        resource_id=str(movement_id),
                        before=before.values,
                        after=result.values,
                        fields=self._audit_fields,
                        metadata={"attachment_id": str(entity.id)},
                    )
                else:
                    result = self._attachment_record(entity, include_storage_key=True)
            return result
        except RecordNotFoundError:
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise StorageUnavailableError(
                "Không thể soft-delete inventory evidence."
            ) from exc

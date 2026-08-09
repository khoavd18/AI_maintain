"""Business service for spare-parts inventory and work-order stock control."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import re
from typing import Any
from uuid import UUID

from src.asset_management.storage import (
    AttachmentStorage,
)
from src.config.value_mappings import ASSET_TYPE_CODE_TO_VI
from src.inventory_management.domain import (
    ISSUABLE_WORK_ORDER_STATUSES,
    REQUIREMENT_EDITABLE_WORK_ORDER_STATUSES,
    InventoryMovementType,
    InventoryOperationType,
    PartLifecycleStatus,
    RequirementStatus,
    ReservationStatus,
)
from src.inventory_management.application.catalogue_service import (
    InventoryCatalogueService,
)
from src.inventory_management.application.catalogue_mutation_service import (
    InventoryCatalogueMutationService,
)
from src.inventory_management.application.evidence_service import (
    InventoryEvidenceDownload,
    InventoryEvidenceService,
)
from src.inventory_management.application.stock_query_service import (
    InventoryStockQueryService,
)
from src.inventory_management.errors import (
    InventoryAuthorizationError,
    InventoryConflictError,
    InventoryDomainError,
    InventoryNotFoundError,
)
from src.repositories.contracts import (
    InventoryRepository,
    StoredPage,
    StoredRecord,
    UnsupportedStorageOperationError,
)
from src.security.audit import AuditContext
from src.security.permissions import Permission, Role
from src.security.principal import CurrentUser

_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")
_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,99}$")


class InventoryManagementService:
    """Canonical named inventory operations with human-controlled workflows."""

    def __init__(
        self,
        repository: InventoryRepository | None,
        attachment_storage: AttachmentStorage,
        *,
        attachment_max_size_bytes: int,
    ) -> None:
        self.repository = repository
        self.attachment_storage = attachment_storage
        self.attachment_max_size_bytes = attachment_max_size_bytes
        self.catalogue = InventoryCatalogueService(
            self._repository,
            self._require_permission,
            self._require_any_read,
        )
        self.catalogue_mutations = InventoryCatalogueMutationService(
            self._repository,
            self._require_permission,
            self._part_record,
            self._stock_location_record,
            _normalized_code,
            _plain_text,
            _optional_text,
            _uuid,
            _asset_types,
            _thresholds,
            _cost_values,
            _utc_now,
        )
        self.evidence = InventoryEvidenceService(
            self._repository,
            attachment_storage,
            attachment_max_size_bytes=attachment_max_size_bytes,
            require_permission=self._require_permission,
            get_movement=self._movement,
            require_movement_access=self._require_movement_access,
        )
        self.stock_queries = InventoryStockQueryService(
            self._repository,
            require_permission=self._require_permission,
            get_work_order=self._work_order,
            require_work_order_access=self._require_work_order_access,
        )

    def options(self, *, actor: CurrentUser) -> dict[str, Any]:
        return self.catalogue.options(actor=actor)

    def list_categories(
        self, *, actor: CurrentUser, include_inactive: bool
    ) -> list[dict[str, Any]]:
        return self.catalogue.list_categories(
            actor=actor,
            include_inactive=include_inactive,
        )

    def create_category(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.catalogue_mutations.create_category(
            request, actor=actor, audit_context=audit_context
        )

    def list_units(
        self, *, actor: CurrentUser, include_inactive: bool
    ) -> list[dict[str, Any]]:
        return self.catalogue.list_units(
            actor=actor,
            include_inactive=include_inactive,
        )

    def create_unit(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.catalogue_mutations.create_unit(
            request, actor=actor, audit_context=audit_context
        )

    def list_parts(
        self,
        *,
        actor: CurrentUser,
        filters: dict[str, Any],
        sort_by: str,
        sort_direction: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        if sort_by not in {
            "part_number",
            "name_vi",
            "available_quantity",
            "stock_state",
        }:
            raise InventoryDomainError("Trường sắp xếp spare part không hợp lệ.")
        if sort_direction not in {"asc", "desc"}:
            raise InventoryDomainError("sort_direction chỉ hỗ trợ asc hoặc desc.")
        result = _page_values(
            self._repository().list_parts(
                filters=filters,
                sort_by=sort_by,
                sort_direction=sort_direction,
                page=page,
                page_size=page_size,
            )
        )
        result["items"] = [
            self._scope_part(item, actor) for item in result["items"]
        ]
        return result

    def get_part(self, part_id: UUID, *, actor: CurrentUser) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        return self._scope_part(dict(self._part_record(part_id).values), actor)

    def create_part(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.catalogue_mutations.create_part(
            request, actor=actor, audit_context=audit_context
        )

    def update_part(
        self,
        part_id: UUID,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.catalogue_mutations.update_part(
            part_id, request, actor=actor, audit_context=audit_context
        )

    def change_part_lifecycle(
        self,
        part_id: UUID,
        *,
        action: str,
        expected_version: int,
        reason: str | None,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.catalogue_mutations.change_part_lifecycle(
            part_id,
            action=action,
            expected_version=expected_version,
            reason=reason,
            actor=actor,
            audit_context=audit_context,
        )

    def list_stock_locations(
        self, *, actor: CurrentUser, include_archived: bool
    ) -> list[dict[str, Any]]:
        return self.catalogue_mutations.list_stock_locations(
            actor=actor, include_archived=include_archived
        )

    def create_stock_location(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.catalogue_mutations.create_stock_location(
            request, actor=actor, audit_context=audit_context
        )

    def update_stock_location(
        self,
        location_id: UUID,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.catalogue_mutations.update_stock_location(
            location_id, request, actor=actor, audit_context=audit_context
        )

    def change_stock_location_lifecycle(
        self,
        location_id: UUID,
        *,
        action: str,
        expected_version: int,
        reason: str | None,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.catalogue_mutations.change_stock_location_lifecycle(
            location_id,
            action=action,
            expected_version=expected_version,
            reason=reason,
            actor=actor,
            audit_context=audit_context,
        )

    def upsert_reorder_configuration(
        self,
        part_id: UUID,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.catalogue_mutations.upsert_reorder_configuration(
            part_id, request, actor=actor, audit_context=audit_context
        )

    def list_balances(
        self,
        *,
        actor: CurrentUser,
        filters: dict[str, Any],
        sort_by: str,
        sort_direction: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self.stock_queries.list_balances(
            actor=actor,
            filters=filters,
            sort_by=sort_by,
            sort_direction=sort_direction,
            page=page,
            page_size=page_size,
        )

    def list_movements(
        self,
        *,
        actor: CurrentUser,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self.stock_queries.list_movements(
            actor=actor,
            filters=filters,
            page=page,
            page_size=page_size,
        )

    def create_opening_balance(
        self,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_RECEIVE)
        values = self._stock_operation_values(request)
        return dict(
            self._repository()
            .create_opening_balance(
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def receive_stock(
        self,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_RECEIVE)
        values = self._stock_operation_values(request)
        return dict(
            self._repository()
            .receive_stock(
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def transfer_stock(
        self,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_TRANSFER)
        part = dict(self._part_record(_uuid(request["part_id"], "part_id")).values)
        source = _uuid(
            request["source_stock_location_id"], "source_stock_location_id"
        )
        destination = _uuid(
            request["destination_stock_location_id"],
            "destination_stock_location_id",
        )
        if source == destination:
            raise InventoryDomainError("Kho nguồn và kho đích phải khác nhau.")
        values = {
            "part_id": UUID(str(part["id"])),
            "source_stock_location_id": source,
            "destination_stock_location_id": destination,
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "business_reference": _plain_text(
                request["business_reference"],
                "business_reference",
                maximum=160,
            ),
            "occurred_at": _safe_timestamp(
                request.get("occurred_at"), "occurred_at"
            ),
            "reason": _plain_text(
                request["reason"], "reason", minimum=3, maximum=1000
            ),
            "unit_cost_snapshot": part.get("unit_cost"),
        }
        result = self._repository().transfer_stock(
            values,
            idempotency_key=_idempotency_key(idempotency_key),
            audit_context=audit_context,
        )
        return {
            "transfer_group_id": str(result["transfer_group_id"]),
            "transfer_out": dict(result["transfer_out"].values),
            "transfer_in": dict(result["transfer_in"].values),
        }

    def adjust_stock(
        self,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_ADJUST)
        values = self._stock_operation_values(request)
        adjustment_type = request["adjustment_type"]
        mapping = {
            "increase": (
                InventoryOperationType.ADJUSTMENT_INCREASE,
                InventoryMovementType.ADJUSTMENT_INCREASE,
            ),
            "decrease": (
                InventoryOperationType.ADJUSTMENT_DECREASE,
                InventoryMovementType.ADJUSTMENT_DECREASE,
            ),
            "damaged_scrapped": (
                InventoryOperationType.DAMAGED_SCRAPPED,
                InventoryMovementType.DAMAGED_SCRAPPED,
            ),
        }
        try:
            operation_type, movement_type = mapping[adjustment_type]
        except KeyError as exc:
            raise InventoryDomainError("adjustment_type không hợp lệ.") from exc
        values.update(
            {
                "operation_type": operation_type,
                "movement_type": movement_type,
                "supporting_note": _plain_text(
                    request["supporting_note"],
                    "supporting_note",
                    minimum=3,
                    maximum=2000,
                ),
            }
        )
        return dict(
            self._repository()
            .adjust_stock(
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def create_requirement(
        self,
        work_order_id: UUID,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_REQUIREMENTS_MANAGE)
        work_order = self._work_order(work_order_id)
        self._require_work_order_status(
            work_order, REQUIREMENT_EDITABLE_WORK_ORDER_STATUSES, "thêm requirement"
        )
        part = dict(self._part_record(_uuid(request["part_id"], "part_id")).values)
        if part["lifecycle_status"] != PartLifecycleStatus.ACTIVE:
            raise InventoryConflictError(
                "Chỉ spare part active mới được thêm vào requirement."
            )
        values = {
            "work_order_id": work_order_id,
            "part_id": UUID(str(part["id"])),
            "planned_quantity": _quantity(
                request["planned_quantity"], int(part["quantity_precision"])
            ),
            "required_by_date": _optional_date(request.get("required_by_date")),
            "source_stock_location_id": _uuid(
                request["source_stock_location_id"],
                "source_stock_location_id",
            ),
            "status": RequirementStatus.PLANNED,
            "notes": _optional_text(request.get("notes"), maximum=1000),
            "created_by_user_id": actor.id,
            "updated_by_user_id": actor.id,
        }
        return dict(
            self._repository()
            .create_requirement(values, audit_context=audit_context)
            .values
        )

    def reserve_stock(
        self,
        requirement_id: UUID,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_RESERVE)
        requirement = self._requirement(requirement_id)
        work_order = self._work_order(UUID(str(requirement["work_order_id"])))
        self._require_work_order_status(
            work_order, REQUIREMENT_EDITABLE_WORK_ORDER_STATUSES, "reserve stock"
        )
        part = dict(self._part_record(UUID(str(requirement["part_id"]))).values)
        expires_at = _optional_future_timestamp(
            request.get("expires_at"), "expires_at"
        )
        values = {
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "expires_at": expires_at,
            "reason": _plain_text(
                request["reason"], "reason", minimum=3, maximum=1000
            ),
            "occurred_at": _utc_now(),
        }
        return dict(
            self._repository()
            .reserve_stock(
                requirement_id,
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                expected_requirement_version=int(
                    request["expected_requirement_version"]
                ),
                audit_context=audit_context,
            )
            .values
        )

    def close_reservation(
        self,
        reservation_id: UUID,
        request: dict[str, Any],
        *,
        target_status: ReservationStatus,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_RESERVE)
        self._reservation(reservation_id)
        return dict(
            self._repository()
            .close_reservation(
                reservation_id,
                target_status=target_status.value,
                reason=_plain_text(
                    request["reason"], "reason", minimum=3, maximum=1000
                ),
                expected_version=int(request["expected_version"]),
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def list_reservations(
        self,
        *,
        actor: CurrentUser,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_READ)
        return _page_values(
            self._repository().list_reservations(
                filters=filters, page=page, page_size=page_size
            )
        )

    def replace_reservation(
        self,
        reservation_id: UUID,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_RESERVE)
        reservation = self._reservation(reservation_id)
        part = dict(self._part_record(UUID(str(reservation["part_id"]))).values)
        values = {
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "stock_location_id": _uuid(
                request["stock_location_id"], "stock_location_id"
            ),
            "expires_at": _optional_future_timestamp(
                request.get("expires_at"), "expires_at"
            ),
            "reason": _plain_text(
                request["reason"], "reason", minimum=3, maximum=1000
            ),
            "occurred_at": _utc_now(),
        }
        return dict(
            self._repository()
            .replace_reservation(
                reservation_id,
                values,
                expected_version=int(request["expected_version"]),
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def issue_stock(
        self,
        work_order_id: UUID,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_ISSUE)
        work_order = self._work_order(work_order_id)
        self._require_work_order_status(
            work_order, ISSUABLE_WORK_ORDER_STATUSES, "issue stock"
        )
        part = dict(self._part_record(_uuid(request["part_id"], "part_id")).values)
        values = {
            "part_id": UUID(str(part["id"])),
            "stock_location_id": _uuid(
                request["stock_location_id"], "stock_location_id"
            ),
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "requirement_id": _optional_uuid(
                request.get("requirement_id"), "requirement_id"
            ),
            "reservation_id": _optional_uuid(
                request.get("reservation_id"), "reservation_id"
            ),
            "issued_to_user_id": _optional_uuid(
                request.get("issued_to_user_id")
                or work_order.get("assigned_to_user_id"),
                "issued_to_user_id",
            ),
            "issued_at": _safe_timestamp(
                request.get("issued_at"), "issued_at"
            ),
            "reason": _plain_text(
                request["reason"], "reason", minimum=3, maximum=1000
            ),
            "business_reference": f"ISSUE-{work_order['work_order_number']}",
        }
        return dict(
            self._repository()
            .issue_stock(
                work_order_id,
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def consume_issue(
        self,
        issue_id: UUID,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_CONSUME)
        issue = self._issue(issue_id)
        work_order = self._work_order(UUID(str(issue["work_order_id"])))
        self._require_work_order_access(work_order, actor)
        if work_order["status"] in {"verified", "cancelled"}:
            raise InventoryConflictError(
                "Không thể ghi consumption cho work order verified hoặc cancelled."
            )
        part = dict(self._part_record(UUID(str(issue["part_id"]))).values)
        values = {
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "consumed_at": _safe_timestamp(
                request.get("consumed_at"), "consumed_at"
            ),
            "note": _optional_text(request.get("note"), maximum=1000),
        }
        return dict(
            self._repository()
            .consume_issue(
                issue_id,
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def return_issue(
        self,
        issue_id: UUID,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.INVENTORY_RETURN)
        issue = self._issue(issue_id)
        part = dict(self._part_record(UUID(str(issue["part_id"]))).values)
        values = {
            "stock_location_id": _uuid(
                request["stock_location_id"], "stock_location_id"
            ),
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "returned_at": _safe_timestamp(
                request.get("returned_at"), "returned_at"
            ),
            "reason": _plain_text(
                request["reason"], "reason", minimum=3, maximum=1000
            ),
            "business_reference": f"RETURN-{issue['issue_number']}",
        }
        return dict(
            self._repository()
            .return_issue(
                issue_id,
                values,
                idempotency_key=_idempotency_key(idempotency_key),
                audit_context=audit_context,
            )
            .values
        )

    def work_order_parts(
        self, work_order_id: UUID, *, actor: CurrentUser
    ) -> dict[str, Any]:
        return self.stock_queries.work_order_parts(work_order_id, actor=actor)

    def metrics(self, *, actor: CurrentUser) -> dict[str, Any]:
        return self.stock_queries.metrics(actor=actor)

    def list_evidence(
        self, movement_id: UUID, *, actor: CurrentUser
    ) -> list[dict[str, Any]]:
        return self.evidence.list_evidence(movement_id, actor=actor)

    def upload_evidence(
        self,
        movement_id: UUID,
        *,
        category: str,
        filename: str,
        claimed_media_type: str | None,
        content: bytes,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.evidence.upload_evidence(
            movement_id,
            category=category,
            filename=filename,
            claimed_media_type=claimed_media_type,
            content=content,
            actor=actor,
            audit_context=audit_context,
        )

    def download_evidence(
        self,
        movement_id: UUID,
        attachment_id: UUID,
        *,
        actor: CurrentUser,
    ) -> InventoryEvidenceDownload:
        return self.evidence.download_evidence(
            movement_id, attachment_id, actor=actor
        )

    def delete_evidence(
        self,
        movement_id: UUID,
        attachment_id: UUID,
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.evidence.delete_evidence(
            movement_id,
            attachment_id,
            actor=actor,
            audit_context=audit_context,
        )

    def _stock_operation_values(self, request: dict[str, Any]) -> dict[str, Any]:
        part = dict(self._part_record(_uuid(request["part_id"], "part_id")).values)
        return {
            "part_id": UUID(str(part["id"])),
            "stock_location_id": _uuid(
                request["stock_location_id"], "stock_location_id"
            ),
            "quantity": _quantity(
                request["quantity"], int(part["quantity_precision"])
            ),
            "business_reference": _plain_text(
                request["business_reference"],
                "business_reference",
                maximum=160,
            ),
            "occurred_at": _safe_timestamp(
                request.get("occurred_at"), "occurred_at"
            ),
            "reason": _plain_text(
                request["reason"], "reason", minimum=3, maximum=1000
            ),
            "unit_cost_snapshot": (
                _optional_decimal(request.get("unit_cost_snapshot"))
                if request.get("unit_cost_snapshot") is not None
                else part.get("unit_cost")
            ),
        }

    def _part_record(self, part_id: UUID) -> StoredRecord:
        record = self._repository().get_part(part_id)
        if record is None:
            raise InventoryNotFoundError(f"Không tìm thấy spare part: {part_id}")
        return record

    def _stock_location_record(self, location_id: UUID) -> StoredRecord:
        record = self._repository().get_stock_location(location_id)
        if record is None:
            raise InventoryNotFoundError(
                f"Không tìm thấy stock location: {location_id}"
            )
        return record

    def _requirement(self, requirement_id: UUID) -> dict[str, Any]:
        record = self._repository().get_requirement(requirement_id)
        if record is None:
            raise InventoryNotFoundError(
                f"Không tìm thấy part requirement: {requirement_id}"
            )
        return dict(record.values)

    def _reservation(self, reservation_id: UUID) -> dict[str, Any]:
        record = self._repository().get_reservation(reservation_id)
        if record is None:
            raise InventoryNotFoundError(
                f"Không tìm thấy stock reservation: {reservation_id}"
            )
        return dict(record.values)

    def _issue(self, issue_id: UUID) -> dict[str, Any]:
        record = self._repository().get_issue(issue_id)
        if record is None:
            raise InventoryNotFoundError(f"Không tìm thấy part issue: {issue_id}")
        return dict(record.values)

    def _work_order(self, work_order_id: UUID) -> dict[str, Any]:
        record = self._repository().get_work_order_state(work_order_id)
        if record is None:
            raise InventoryNotFoundError(f"Không tìm thấy work order: {work_order_id}")
        return dict(record.values)

    def _movement(self, movement_id: UUID) -> dict[str, Any]:
        record = self._repository().get_movement(movement_id)
        if record is None:
            raise InventoryNotFoundError(
                f"Không tìm thấy stock movement: {movement_id}"
            )
        return dict(record.values)

    def _require_work_order_access(
        self, work_order: dict[str, Any], actor: CurrentUser
    ) -> None:
        if actor.role is Role.TECHNICIAN and str(
            work_order.get("assigned_to_user_id") or ""
        ) != str(actor.id):
            raise InventoryAuthorizationError(
                "Kỹ thuật viên chỉ được xem hoặc ghi vật tư cho work order được gán."
            )

    def _require_movement_access(
        self, movement: dict[str, Any], actor: CurrentUser
    ) -> None:
        if actor.role is not Role.TECHNICIAN:
            return
        work_order_id = movement.get("work_order_id")
        if not work_order_id:
            raise InventoryAuthorizationError(
                "Kỹ thuật viên chỉ được xem bằng chứng của vật tư thuộc work order được gán."
            )
        self._require_work_order_access(
            self._work_order(UUID(str(work_order_id))), actor
        )

    @staticmethod
    def _require_work_order_status(
        work_order: dict[str, Any], allowed: frozenset[str], action: str
    ) -> None:
        if work_order["status"] not in allowed:
            raise InventoryConflictError(
                f"Work order ở trạng thái {work_order['status']} không thể {action}."
            )

    @staticmethod
    def _scope_part(values: dict[str, Any], actor: CurrentUser) -> dict[str, Any]:
        result = dict(values)
        if actor.role is Role.HELPDESK:
            result["unit_cost"] = None
            result["currency_code"] = None
        return result

    @staticmethod
    def _require_permission(actor: CurrentUser, permission: Permission) -> None:
        if not actor.has(permission):
            raise InventoryAuthorizationError(
                "Bạn không có quyền thực hiện inventory action này."
            )

    def _require_any_read(self, actor: CurrentUser) -> None:
        if not (
            actor.has(Permission.INVENTORY_READ)
            or actor.has(Permission.WORK_ORDER_PARTS_READ)
        ):
            raise InventoryAuthorizationError(
                "Bạn không có quyền đọc inventory options."
            )

    def _repository(self) -> InventoryRepository:
        if self.repository is None:
            raise UnsupportedStorageOperationError(
                "Inventory management yêu cầu PostgreSQL product mode."
            )
        return self.repository


def build_inventory_management_service() -> InventoryManagementService:
    """Compatibility builder delegated to the explicit composition root."""

    from src.inventory_management.compatibility import build_inventory_management_service as build

    return build()


def _page_values(page: StoredPage) -> dict[str, Any]:
    return {
        "items": [dict(record.values) for record in page.items],
        "page": page.page,
        "page_size": page.page_size,
        "total": page.total,
        "total_pages": (page.total + page.page_size - 1) // page.page_size,
    }


def _normalized_code(value: object, field: str, *, maximum: int) -> str:
    normalized = _plain_text(value, field, maximum=maximum).upper()
    if not _CODE_PATTERN.fullmatch(normalized):
        raise InventoryDomainError(
            f"{field} chỉ hỗ trợ chữ in hoa, số, dấu chấm, gạch dưới hoặc gạch ngang."
        )
    return normalized


def _plain_text(
    value: object,
    field: str,
    *,
    maximum: int,
    minimum: int = 1,
) -> str:
    normalized = str(value or "").strip()
    if (
        len(normalized) < minimum
        or len(normalized) > maximum
        or any(ord(character) < 32 and character not in "\n\t" for character in normalized)
    ):
        raise InventoryDomainError(f"{field} không hợp lệ.")
    return normalized


def _optional_text(value: object, *, maximum: int) -> str | None:
    if value is None or not str(value).strip():
        return None
    return _plain_text(value, "text", maximum=maximum)


def _uuid(value: object, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise InventoryDomainError(f"{field} không phải UUID hợp lệ.") from exc


def _optional_uuid(value: object, field: str) -> UUID | None:
    return None if value is None or not str(value).strip() else _uuid(value, field)


def _asset_types(values: object) -> list[str]:
    allowed = set(ASSET_TYPE_CODE_TO_VI)
    result = sorted({str(item) for item in list(values or [])})
    if any(item not in allowed for item in result):
        raise InventoryDomainError("compatible_asset_types có code không hợp lệ.")
    return result


def _thresholds(
    request: dict[str, Any],
) -> tuple[Decimal, Decimal, Decimal | None]:
    minimum = _non_negative_decimal(request.get("minimum_stock", 0), "minimum_stock")
    reorder = _non_negative_decimal(request.get("reorder_point", 0), "reorder_point")
    maximum = (
        _non_negative_decimal(request["maximum_stock"], "maximum_stock")
        if request.get("maximum_stock") is not None
        else None
    )
    if reorder < minimum:
        raise InventoryDomainError(
            "reorder_point phải lớn hơn hoặc bằng minimum_stock."
        )
    if maximum is not None and maximum < reorder:
        raise InventoryDomainError(
            "maximum_stock phải lớn hơn hoặc bằng reorder_point."
        )
    return minimum, reorder, maximum


def _cost_values(request: dict[str, Any]) -> tuple[Decimal | None, str | None]:
    raw_cost = request.get("unit_cost")
    raw_currency = request.get("currency_code")
    if raw_cost is None and raw_currency is None:
        return None, None
    if raw_cost is None or raw_currency is None:
        raise InventoryDomainError(
            "unit_cost và currency_code phải được cung cấp cùng nhau."
        )
    currency = str(raw_currency).strip().upper()
    if len(currency) != 3 or not currency.isalpha() or not currency.isascii():
        raise InventoryDomainError("currency_code phải là mã ba chữ cái.")
    return _non_negative_decimal(raw_cost, "unit_cost"), currency


def _quantity(value: object, precision: int) -> Decimal:
    quantity = _positive_decimal(value, "quantity")
    quantum = Decimal(1).scaleb(-precision)
    if quantity != quantity.quantize(quantum):
        raise InventoryDomainError(
            f"Quantity chỉ hỗ trợ tối đa {precision} chữ số thập phân cho UOM này."
        )
    return quantity


def _positive_decimal(value: object, field: str) -> Decimal:
    result = _decimal(value, field)
    if result <= 0:
        raise InventoryDomainError(f"{field} phải lớn hơn 0.")
    return result


def _non_negative_decimal(value: object, field: str) -> Decimal:
    result = _decimal(value, field)
    if result < 0:
        raise InventoryDomainError(f"{field} không được âm.")
    return result


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else _non_negative_decimal(value, "decimal")


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise InventoryDomainError(f"{field} không phải số hợp lệ.") from exc
    if not result.is_finite() or result.as_tuple().exponent < -3:
        raise InventoryDomainError(f"{field} hỗ trợ tối đa 3 chữ số thập phân.")
    return result


def _idempotency_key(value: str) -> str:
    normalized = str(value or "").strip()
    if not _IDEMPOTENCY_PATTERN.fullmatch(normalized):
        raise InventoryDomainError(
            "Idempotency-Key phải dài 8-100 ký tự và chỉ chứa ký tự an toàn."
        )
    return normalized


def _safe_timestamp(value: object, field: str) -> datetime:
    if value is None:
        return _utc_now()
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InventoryDomainError(f"{field} phải có timezone.")
    normalized = parsed.astimezone(timezone.utc).replace(microsecond=0)
    if normalized > _utc_now() + timedelta(minutes=5):
        raise InventoryDomainError(f"{field} không được nằm trong tương lai.")
    return normalized


def _optional_future_timestamp(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InventoryDomainError(f"{field} phải có timezone.")
    normalized = parsed.astimezone(timezone.utc).replace(microsecond=0)
    if normalized <= _utc_now():
        raise InventoryDomainError(f"{field} phải nằm trong tương lai.")
    return normalized


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

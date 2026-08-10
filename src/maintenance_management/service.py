"""Business rules for preventive plans and standalone work orders."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from src.asset_management.storage import (
    AttachmentStorage,
)
from src.config.value_mappings import (
    MAINTENANCE_RESULT_CODE_TO_VI,
    MAINTENANCE_RESULT_VI_TO_CODE,
    PRIORITY_CODE_TO_VI,
)
from src.maintenance_management.domain import (
    WORK_ORDER_TRANSITIONS as _WORK_ORDER_TRANSITIONS,
    ChecklistResponseType,
    ChecklistResultStatus,
    IntervalUnit,
    WorkOrderStatus as _WorkOrderStatus,
    WorkOrderType as _WorkOrderType,
)
from src.maintenance_management.recurrence import (
    MAX_OCCURRENCES as _MAX_OCCURRENCES,
    RecurrenceSpec,
    advance_occurrence,
    first_occurrence_on_or_after as _first_occurrence_on_or_after,
    occurrences_between as _occurrences_between,
)
from src.repositories.contracts import (
    MaintenancePlanningRepository,
    StoredPage,
    StoredRecord,
    UnsupportedStorageOperationError,
)
from src.security.audit import AuditContext
from src.security.permissions import Role
from src.security.principal import CurrentUser
from src.maintenance_management.application.catalogue_service import MaintenanceCatalogueService
from src.maintenance_management.application.evidence_service import (
    EvidenceDownload,
    MaintenanceEvidenceService,
)
from src.maintenance_management.application.preventive_plan_service import (
    PreventivePlanService,
)
from src.maintenance_management.application.query_service import MaintenanceQueryService
from src.maintenance_management.application.template_service import MaintenanceTemplateService
from src.maintenance_management.application.work_order_planning_service import (
    WorkOrderPlanningService,
)
from src.maintenance_management.application.work_order_lifecycle_service import (
    WorkOrderLifecycleService,
)
from src.maintenance_management.application.work_order_completion_service import (
    WorkOrderCompletionService,
)
from src.maintenance_management.application.preventive_generation_service import (
    MAX_CATCH_UP_DAYS as _MAX_CATCH_UP_DAYS,
    PreventiveGenerationService,
)
from src.maintenance_management.application.work_order_reporting_service import (
    WorkOrderReportingService,
)
from src.maintenance_management.errors import (
    MaintenanceAuthorizationError,
    MaintenanceConflictError,
    MaintenanceDomainError,
    MaintenanceNotFoundError,
)

PLAN_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,49}$")
TEMPLATE_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,49}$")

# Preserve names that historically leaked through this compatibility facade.
MAX_CATCH_UP_DAYS = _MAX_CATCH_UP_DAYS
MAX_OCCURRENCES = _MAX_OCCURRENCES
WORK_ORDER_TRANSITIONS = _WORK_ORDER_TRANSITIONS
WorkOrderStatus = _WorkOrderStatus
WorkOrderType = _WorkOrderType
first_occurrence_on_or_after = _first_occurrence_on_or_after
occurrences_between = _occurrences_between


class MaintenancePlanningService:
    """Canonical service boundary for plans, checklists, and work orders."""

    def __init__(
        self,
        repository: MaintenancePlanningRepository | None,
        attachment_storage: AttachmentStorage,
        *,
        attachment_max_size_bytes: int,
    ) -> None:
        self.repository = repository
        self.attachment_storage = attachment_storage
        self.attachment_max_size_bytes = attachment_max_size_bytes
        self.catalogue = MaintenanceCatalogueService(self._repository, self.get_plan)
        self.evidence = MaintenanceEvidenceService(
            self._repository,
            attachment_storage,
            attachment_max_size_bytes=attachment_max_size_bytes,
            get_work_order=self._work_order_record,
            require_work_order_access=self._require_work_order_access,
        )
        self.queries = MaintenanceQueryService(
            self._repository,
            get_plan=lambda plan_id: dict(self._plan_record(plan_id).values),
            get_ticket=self._ticket,
            get_work_order_record=self._work_order_record,
            require_work_order_access=self._require_work_order_access,
            scope_work_order=self._scope_work_order,
        )
        self.templates = MaintenanceTemplateService(
            self._repository,
            lambda value, field: _normalized_code(value, TEMPLATE_CODE_PATTERN, field),
            _plain_text,
            _optional_plain_text,
            _validate_template_items,
            _page_values,
        )
        self.plans = PreventivePlanService(
            self._repository,
            get_plan=self.get_plan,
            get_asset=self._asset,
            require_asset_eligible=self._require_asset_eligible,
            require_eligible_technician=self._require_eligible_technician,
            require_template_usable=self._require_template_usable,
            recurrence_spec=_recurrence_spec,
            normalize_code=lambda value, field: _normalized_code(value, PLAN_CODE_PATTERN, field),
            normalize_text=_plain_text,
            normalize_optional_text=_optional_plain_text,
            require_priority_code=_require_priority_code,
            as_optional_date=_as_optional_date,
            utc_now=_utc_now,
        )
        self.work_order_planning = WorkOrderPlanningService(
            self._repository,
            get_asset=self._asset,
            get_ticket=self._ticket,
            get_plan=self.get_plan,
            get_work_order=self.get_work_order,
            get_work_order_record=self._work_order_record,
            require_asset_eligible=self._require_asset_eligible,
            require_eligible_technician=self._require_eligible_technician,
            require_template_usable=self._require_template_usable,
            template_snapshot=_template_snapshot,
            normalize_text=_plain_text,
            normalize_optional_text=_optional_plain_text,
            require_priority_code=_require_priority_code,
            recurrence_spec=_recurrence_spec,
            validate_utc_range=_validate_utc_range,
            as_optional_datetime=_as_optional_datetime,
        )
        self.work_order_lifecycle = WorkOrderLifecycleService(
            self._repository,
            get_work_order_record=self._work_order_record,
            get_work_order=self.get_work_order,
            require_work_order_access=self._require_work_order_access,
            normalize_checklist_response=_normalize_checklist_response,
            required_text=_required_text,
            utc_now=_utc_now,
        )
        self.work_order_completion = WorkOrderCompletionService(
            self._repository,
            get_work_order=self.get_work_order,
            get_work_order_record=self._work_order_record,
            get_asset=self._asset,
            validate_checklist_completion=_validate_checklist_completion,
            maintenance_result_code=_maintenance_result_code,
            required_text=_required_text,
            optional_text=_optional_plain_text,
            utc_now=_utc_now,
            local_today=lambda local_timezone: datetime.now(ZoneInfo(local_timezone)).date(),
            next_maintenance_date=self._next_maintenance_date,
        )
        self.generation = PreventiveGenerationService(
            self._repository,
            get_plan=self.get_plan,
            list_plans=self.list_plans,
            get_asset=self._asset,
            recurrence_spec=_recurrence_spec,
            as_optional_date=_as_optional_date,
            today=lambda: datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date(),
        )
        self.reporting = WorkOrderReportingService(
            self._repository,
            list_work_orders=self.list_work_orders,
            list_plans=self.list_plans,
            preview_occurrences=self.preview_occurrences,
        )

    def options(self) -> dict[str, Any]:
        return self.catalogue.options()

    def list_plans(
        self,
        *,
        asset_id: str | None,
        status: str | None,
        search: str | None,
        due_from: date | None,
        due_to: date | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self.queries.list_plans(
            asset_id=asset_id,
            status=status,
            search=search,
            due_from=due_from,
            due_to=due_to,
            page=page,
            page_size=page_size,
        )

    def get_plan(self, plan_id: UUID) -> dict[str, Any]:
        return self.queries.get_plan(plan_id)

    def create_plan(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.plans.create_plan(
            request,
            actor=actor,
            audit_context=audit_context,
        )

    def update_plan(
        self,
        plan_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.plans.update_plan(
            plan_id,
            updates,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
        )

    def pause_plan(
        self,
        plan_id: UUID,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.plans.pause_plan(
            plan_id,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
        )

    def resume_plan(
        self,
        plan_id: UUID,
        *,
        expected_version: int,
        resume_date: date,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.plans.resume_plan(
            plan_id,
            expected_version=expected_version,
            resume_date=resume_date,
            actor=actor,
            audit_context=audit_context,
        )

    def archive_plan(
        self,
        plan_id: UUID,
        *,
        expected_version: int,
        archive_reason: str,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.plans.archive_plan(
            plan_id,
            expected_version=expected_version,
            archive_reason=archive_reason,
            actor=actor,
            audit_context=audit_context,
        )

    def preview_occurrences(
        self,
        plan_id: UUID,
        *,
        date_from: date,
        date_to: date,
        limit: int,
    ) -> dict[str, Any]:
        return self.catalogue.preview_occurrences(
            plan_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )

    def list_templates(
        self,
        *,
        status: str | None,
        asset_type: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self.templates.list_templates(
            status=status,
            asset_type=asset_type,
            search=search,
            page=page,
            page_size=page_size,
        )

    def get_template(self, template_id: UUID) -> dict[str, Any]:
        return self.templates.get_template(template_id)

    def create_template(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.templates.create_template(request, actor=actor, audit_context=audit_context)

    def version_template(
        self,
        template_id: UUID,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.templates.version_template(
            template_id,
            request,
            actor=actor,
            audit_context=audit_context,
        )

    def archive_template(
        self,
        template_id: UUID,
        *,
        expected_version: int,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.templates.archive_template(
            template_id,
            expected_version=expected_version,
            audit_context=audit_context,
        )

    def list_work_orders(
        self,
        *,
        actor: CurrentUser,
        filters: dict[str, Any],
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self.queries.list_work_orders(
            actor=actor,
            filters=filters,
            page=page,
            page_size=page_size,
        )

    def get_work_order(self, work_order_id: UUID, *, actor: CurrentUser) -> dict[str, Any]:
        return self.queries.get_work_order(work_order_id, actor=actor)

    def create_work_order(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
        audit_action: str = "work_order.created",
    ) -> dict[str, Any]:
        return self.work_order_planning.create_work_order(
            request,
            actor=actor,
            audit_context=audit_context,
            audit_action=audit_action,
        )

    def create_corrective_from_ticket(
        self,
        ticket_id: str,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.work_order_planning.create_corrective_from_ticket(
            ticket_id,
            request,
            actor=actor,
            audit_context=audit_context,
        )

    def update_work_order(
        self,
        work_order_id: UUID,
        updates: dict[str, Any],
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.work_order_planning.update_work_order(
            work_order_id,
            updates,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
        )

    def assign_work_order(
        self,
        work_order_id: UUID,
        *,
        assigned_to_user_id: UUID,
        expected_version: int,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.work_order_planning.assign_work_order(
            work_order_id,
            assigned_to_user_id=assigned_to_user_id,
            expected_version=expected_version,
            audit_context=audit_context,
        )

    def transition_work_order(
        self,
        work_order_id: UUID,
        *,
        target_status: str,
        hold_reason: str | None,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.work_order_lifecycle.transition_work_order(
            work_order_id,
            target_status=target_status,
            hold_reason=hold_reason,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
        )

    def update_checklist(
        self,
        work_order_id: UUID,
        responses: list[dict[str, Any]],
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.work_order_lifecycle.update_checklist(
            work_order_id,
            responses,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
        )

    def complete_work_order(
        self,
        work_order_id: UUID,
        request: dict[str, Any],
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.work_order_completion.complete_work_order(
            work_order_id,
            request,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
        )

    def verify_work_order(
        self,
        work_order_id: UUID,
        *,
        expected_version: int,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.work_order_completion.verify_work_order(
            work_order_id,
            expected_version=expected_version,
            actor=actor,
            audit_context=audit_context,
        )

    def cancel_work_order(
        self,
        work_order_id: UUID,
        *,
        expected_version: int,
        cancellation_reason: str,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.work_order_lifecycle.cancel_work_order(
            work_order_id,
            expected_version=expected_version,
            cancellation_reason=cancellation_reason,
            audit_context=audit_context,
        )

    def reopen_work_order(
        self,
        work_order_id: UUID,
        *,
        expected_version: int,
        reason: str,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.work_order_lifecycle.reopen_work_order(
            work_order_id,
            expected_version=expected_version,
            reason=reason,
            audit_context=audit_context,
        )

    def generate(
        self,
        *,
        as_of_date: date,
        plan_id: UUID | None,
        dry_run: bool,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.generation.generate(
            as_of_date=as_of_date,
            plan_id=plan_id,
            dry_run=dry_run,
            actor=actor,
            audit_context=audit_context,
        )

    def schedule_view(
        self,
        *,
        actor: CurrentUser,
        date_from: date,
        date_to: date,
        asset_id: str | None,
        assigned_to_user_id: UUID | None,
    ) -> dict[str, Any]:
        return self.reporting.schedule_view(
            actor=actor,
            date_from=date_from,
            date_to=date_to,
            asset_id=asset_id,
            assigned_to_user_id=assigned_to_user_id,
        )

    def metrics(self, *, as_of_date: date) -> dict[str, Any]:
        return self.reporting.metrics(as_of_date=as_of_date)

    def list_evidence(self, work_order_id: UUID, *, actor: CurrentUser) -> list[dict[str, Any]]:
        return self.evidence.list_evidence(work_order_id, actor=actor)

    def upload_evidence(
        self,
        work_order_id: UUID,
        *,
        category: str,
        filename: str,
        claimed_media_type: str | None,
        content: bytes,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.evidence.upload_evidence(
            work_order_id,
            category=category,
            filename=filename,
            claimed_media_type=claimed_media_type,
            content=content,
            actor=actor,
            audit_context=audit_context,
        )

    def download_evidence(
        self,
        work_order_id: UUID,
        attachment_id: UUID,
        *,
        actor: CurrentUser,
    ) -> EvidenceDownload:
        return self.evidence.download_evidence(work_order_id, attachment_id, actor=actor)

    def delete_evidence(
        self,
        work_order_id: UUID,
        attachment_id: UUID,
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        return self.evidence.delete_evidence(
            work_order_id,
            attachment_id,
            actor=actor,
            audit_context=audit_context,
        )

    def linked_work_orders(self, ticket_id: str, *, actor: CurrentUser) -> list[dict[str, Any]]:
        return self.queries.linked_work_orders(ticket_id, actor=actor)

    def _next_maintenance_date(
        self,
        work_order: dict[str, Any],
        asset: dict[str, Any],
        maintenance_date: date,
    ) -> date:
        if work_order["preventive_plan_id"]:
            plan = self.get_plan(UUID(work_order["preventive_plan_id"]))
            candidate = _as_optional_date(plan["next_due_date"])
            if candidate and candidate > maintenance_date:
                return candidate
            spec = _recurrence_spec(plan)
            candidate = advance_occurrence(date.fromisoformat(work_order["due_date"]), spec)
            if candidate > maintenance_date:
                return candidate
        return maintenance_date + timedelta(days=int(asset["maintenance_interval_days"]))

    def _asset(self, asset_id: str) -> dict[str, Any]:
        record = self._repository().get_asset_state(asset_id)
        if record is None:
            raise MaintenanceNotFoundError(f"Không tìm thấy asset: {asset_id}")
        return dict(record.values)

    def _ticket(self, ticket_id: str) -> dict[str, Any]:
        record = self._repository().get_ticket_state(ticket_id)
        if record is None:
            raise MaintenanceNotFoundError(f"Không tìm thấy ticket: {ticket_id}")
        return dict(record.values)

    def _plan_record(self, plan_id: UUID) -> StoredRecord:
        record = self._repository().get_plan(plan_id)
        if record is None:
            raise MaintenanceNotFoundError(f"Không tìm thấy maintenance plan: {plan_id}")
        return record

    def _work_order_record(self, work_order_id: UUID) -> StoredRecord:
        record = self._repository().get_work_order(work_order_id)
        if record is None:
            raise MaintenanceNotFoundError(f"Không tìm thấy work order: {work_order_id}")
        return record

    def _require_asset_eligible(self, asset: dict[str, Any], action: str) -> None:
        if asset["lifecycle_status"] in {"retired", "archived"}:
            raise MaintenanceConflictError(f"Asset retired hoặc archived không thể {action}.")

    def _require_eligible_technician(self, user_id: UUID) -> dict[str, Any]:
        record = self._repository().get_user_state(user_id)
        if record is None:
            raise MaintenanceNotFoundError(f"Không tìm thấy technician user: {user_id}")
        user = dict(record.values)
        if user["role"] != "technician" or not user["is_active"] or not user["technician_id"]:
            raise MaintenanceConflictError("Assignee phải là technician active có technician_id.")
        return user

    def _require_template_usable(self, template_id: UUID, *, asset_type: str) -> dict[str, Any]:
        template = self.get_template(template_id)
        if template["status"] != "active":
            raise MaintenanceConflictError("Checklist template archived không thể dùng mới.")
        if template["asset_type"] and template["asset_type"] != asset_type:
            raise MaintenanceConflictError(
                "Checklist template không áp dụng cho asset type đã chọn."
            )
        return template

    def _require_work_order_access(self, work_order: dict[str, Any], actor: CurrentUser) -> None:
        if actor.role is Role.TECHNICIAN and work_order["assigned_to_user_id"] != str(actor.id):
            raise MaintenanceAuthorizationError(
                "Work order này không được phân công cho technician đang đăng nhập."
            )

    def _scope_work_order(self, work_order: dict[str, Any], actor: CurrentUser) -> dict[str, Any]:
        result = dict(work_order)
        if actor.role in {Role.HELPDESK, Role.STOREKEEPER}:
            result["checklist"] = []
            result["history"] = []
            result["safety_notes"] = None
            result["completion_summary"] = None
        return result

    def _repository(self) -> MaintenancePlanningRepository:
        if self.repository is None:
            raise UnsupportedStorageOperationError(
                "Maintenance planning yêu cầu PostgreSQL product mode."
            )
        return self.repository


def build_maintenance_planning_service() -> MaintenancePlanningService:
    """Compatibility builder delegated to the explicit composition root."""

    from src.maintenance_management.compatibility import build_maintenance_planning_service as build

    return build()


def _recurrence_spec(values: dict[str, Any]) -> RecurrenceSpec:
    return RecurrenceSpec(
        interval_value=int(values["interval_value"]),
        interval_unit=IntervalUnit(values["interval_unit"]),
        start_date=_as_date(values["start_date"]),
        end_date=_as_optional_date(values.get("end_date")),
        local_timezone=str(values["local_timezone"]),
    )


def _validate_template_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        raise MaintenanceDomainError("Checklist template cần ít nhất một item.")
    if len(items) > 100:
        raise MaintenanceDomainError("Checklist template không được vượt quá 100 items.")
    ordered = sorted(items, key=lambda item: int(item["sequence"]))
    if [int(item["sequence"]) for item in ordered] != list(range(1, len(items) + 1)):
        raise MaintenanceDomainError("Checklist sequence phải liên tục từ 1.")
    normalized: list[dict[str, Any]] = []
    for item in ordered:
        response_type = ChecklistResponseType(item["response_type"])
        minimum = item.get("minimum_value")
        maximum = item.get("maximum_value")
        unit = _optional_plain_text(item.get("expected_unit"), "expected_unit", max_length=40)
        if response_type is not ChecklistResponseType.NUMERIC and any(
            value is not None for value in (minimum, maximum, unit)
        ):
            raise MaintenanceDomainError(
                "minimum/maximum/unit chỉ dùng cho numeric checklist item."
            )
        if minimum is not None and maximum is not None and minimum > maximum:
            raise MaintenanceDomainError("minimum_value không được lớn hơn maximum_value.")
        normalized.append(
            {
                "sequence": int(item["sequence"]),
                "instruction": _plain_text(item["instruction"], "instruction", max_length=2000),
                "response_type": response_type.value,
                "is_required": bool(item.get("is_required", True)),
                "safety_critical": bool(item.get("safety_critical", False)),
                "allow_not_applicable": bool(item.get("allow_not_applicable", False)),
                "expected_unit": unit,
                "minimum_value": minimum,
                "maximum_value": maximum,
                "guidance": _optional_plain_text(item.get("guidance"), "guidance", max_length=2000),
            }
        )
    return normalized


def _template_snapshot(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_template_item_id": UUID(item["id"]),
            "sequence": item["sequence"],
            "instruction": item["instruction"],
            "response_type": item["response_type"],
            "is_required": item["is_required"],
            "safety_critical": item["safety_critical"],
            "allow_not_applicable": item["allow_not_applicable"],
            "expected_unit": item["expected_unit"],
            "minimum_value": item["minimum_value"],
            "maximum_value": item["maximum_value"],
            "guidance": item["guidance"],
            "result_status": "pending",
            "boolean_value": None,
            "numeric_value": None,
            "text_value": None,
            "note": None,
            "completed_by_user_id": None,
            "completed_at": None,
        }
        for item in items
    ]


def _normalize_checklist_response(
    response: dict[str, Any],
    items: dict[UUID, dict[str, Any]],
    actor_user_id: UUID,
) -> dict[str, Any]:
    item_id = response["item_id"]
    item = items.get(item_id)
    if item is None:
        raise MaintenanceConflictError(f"Checklist item không thuộc work order: {item_id}")
    result = ChecklistResultStatus(response["result_status"])
    if result is ChecklistResultStatus.PENDING:
        raise MaintenanceDomainError("Không thể submit result_status=pending.")
    if result is ChecklistResultStatus.NOT_APPLICABLE:
        if not item["allow_not_applicable"]:
            raise MaintenanceDomainError("Checklist item này không cho phép not_applicable.")
        return {
            "item_id": item_id,
            "result_status": result.value,
            "boolean_value": None,
            "numeric_value": None,
            "text_value": None,
            "note": _optional_plain_text(response.get("note"), "note", max_length=1000),
            "completed_by_user_id": actor_user_id,
            "completed_at": _utc_now(),
        }
    response_type = ChecklistResponseType(item["response_type"])
    boolean_value = response.get("boolean_value")
    numeric_value = response.get("numeric_value")
    text_value = _optional_plain_text(response.get("text_value"), "text_value", max_length=2000)
    if response_type is ChecklistResponseType.CHECKBOX:
        if boolean_value is None or result is not ChecklistResultStatus.COMPLETED:
            raise MaintenanceDomainError("Checkbox cần boolean_value và result_status=completed.")
    elif response_type is ChecklistResponseType.PASS_FAIL:
        if result not in {ChecklistResultStatus.PASS, ChecklistResultStatus.FAIL}:
            raise MaintenanceDomainError("Pass/fail item cần result_status pass hoặc fail.")
    elif response_type is ChecklistResponseType.NUMERIC:
        if numeric_value is None:
            raise MaintenanceDomainError("Numeric item cần numeric_value.")
        failed = (item["minimum_value"] is not None and numeric_value < item["minimum_value"]) or (
            item["maximum_value"] is not None and numeric_value > item["maximum_value"]
        )
        result = ChecklistResultStatus.FAIL if failed else ChecklistResultStatus.COMPLETED
    elif not text_value:
        raise MaintenanceDomainError("Text item cần nội dung trả lời.")
    return {
        "item_id": item_id,
        "result_status": result.value,
        "boolean_value": boolean_value if response_type is ChecklistResponseType.CHECKBOX else None,
        "numeric_value": numeric_value if response_type is ChecklistResponseType.NUMERIC else None,
        "text_value": text_value if response_type is ChecklistResponseType.TEXT else None,
        "note": _optional_plain_text(response.get("note"), "note", max_length=1000),
        "completed_by_user_id": actor_user_id,
        "completed_at": _utc_now(),
    }


def _validate_checklist_completion(items: list[dict[str, Any]]) -> None:
    for item in items:
        if item["is_required"] and item["result_status"] == "pending":
            raise MaintenanceConflictError(
                f"Checklist bắt buộc #{item['sequence']} chưa hoàn thành."
            )
        failed = item["result_status"] == "fail" or (
            item["response_type"] == "checkbox" and item["boolean_value"] is False
        )
        if item["safety_critical"] and failed:
            raise MaintenanceConflictError(
                f"Checklist an toàn #{item['sequence']} không đạt; completion bị chặn."
            )


def _maintenance_result_code(value: str) -> str:
    if value in MAINTENANCE_RESULT_CODE_TO_VI:
        return value
    try:
        return MAINTENANCE_RESULT_VI_TO_CODE[value]
    except KeyError as exc:
        raise MaintenanceDomainError("maintenance_result không được hỗ trợ.") from exc


def _require_priority_code(value: object) -> str:
    normalized = str(value)
    if normalized not in PRIORITY_CODE_TO_VI:
        raise MaintenanceDomainError("priority không được hỗ trợ.")
    return normalized


def _normalized_code(value: str, pattern: re.Pattern[str], field: str) -> str:
    normalized = str(value).strip().upper()
    if not pattern.fullmatch(normalized):
        raise MaintenanceDomainError(
            f"{field} chỉ nhận 3–50 ký tự A-Z, 0-9, dấu gạch ngang hoặc gạch dưới."
        )
    return normalized


def _plain_text(value: object, field: str, *, max_length: int) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise MaintenanceDomainError(f"{field} không được để trống.")
    if len(normalized) > max_length:
        raise MaintenanceDomainError(f"{field} không được vượt quá {max_length} ký tự.")
    if "<" in normalized or ">" in normalized or "javascript:" in normalized.casefold():
        raise MaintenanceDomainError(f"{field} chỉ chấp nhận plain text an toàn.")
    return normalized


def _required_text(value: object, field: str, *, max_length: int) -> str:
    return _plain_text(value, field, max_length=max_length)


def _optional_plain_text(value: object | None, field: str, *, max_length: int) -> str | None:
    if value is None or not str(value).strip():
        return None
    return _plain_text(value, field, max_length=max_length)


def _validate_utc_range(start: datetime | None, end: datetime | None) -> None:
    for field, value in (("scheduled_start_at", start), ("scheduled_end_at", end)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise MaintenanceDomainError(f"{field} phải có timezone.")
    if start is not None and end is not None and end < start:
        raise MaintenanceDomainError("scheduled_end_at không được sớm hơn scheduled_start_at.")


def _as_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _as_optional_date(value: object | None) -> date | None:
    if value is None or not str(value).strip():
        return None
    return _as_date(value)


def _as_optional_datetime(value: object | None) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _options(mapping: dict[Any, str]) -> list[dict[str, str]]:
    return [
        {"code": str(code.value if hasattr(code, "value") else code), "display_name": label}
        for code, label in mapping.items()
    ]


def _page_values(page: StoredPage) -> dict[str, Any]:
    total_pages = (page.total + page.page_size - 1) // page.page_size if page.total else 0
    return {
        "items": [dict(record.values) for record in page.items],
        "page": page.page,
        "page_size": page.page_size,
        "total": page.total,
        "total_pages": total_pages,
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

"""Ticket intake application orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import re
from typing import Any
from uuid import UUID

from src.repositories.contracts import StoredRecord, TicketRepository
from src.security.audit_context import AuditContext
from src.security.permissions import Permission
from src.security.principal import CurrentUser
from src.ticket_management.domain import Impact, TicketStatus, Urgency, calculate_priority
from src.ticket_management.errors import TicketConflictError, TicketDomainError, TicketNotFoundError


class TicketIntakeService:
    """Validate intake commands and delegate one atomic create operation."""

    def __init__(
        self,
        repository: TicketRepository,
        *,
        require_permission: Callable[[CurrentUser, Permission], None],
        validate_references: Callable[..., None],
        active_assignee: Callable[[UUID], StoredRecord],
        sla_snapshot: Callable[..., tuple[dict[str, Any], list[dict[str, Any]]]],
        present: Callable[..., dict[str, Any]],
        normalize_text: Callable[..., str],
        optional_text: Callable[[object, int], str | None],
        parse_uuid: Callable[..., UUID | None],
        normalize_datetime: Callable[[datetime], datetime],
        utc_now: Callable[[], datetime],
        facility_timezone: Any,
        failure_categories: frozenset[str],
        email_pattern: re.Pattern[str],
    ) -> None:
        self._repository = repository
        self._require_permission = require_permission
        self._validate_references = validate_references
        self._active_assignee = active_assignee
        self._sla_snapshot = sla_snapshot
        self._present = present
        self._normalize_text = normalize_text
        self._optional_text = optional_text
        self._parse_uuid = parse_uuid
        self._normalize_datetime = normalize_datetime
        self._utc_now = utc_now
        self._facility_timezone = facility_timezone
        self._failure_categories = failure_categories
        self._email_pattern = email_pattern

    def intake(
        self,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_permission(actor, Permission.TICKETS_CREATE)
        current = self._normalize_datetime(now or self._utc_now())
        asset_id = self._normalize_text(request["asset_id"], "asset_id", 50)
        asset = self._repository.get_asset(asset_id)
        if asset is None:
            raise TicketNotFoundError(f"Không tìm thấy asset: {asset_id}")
        if asset.values.get("lifecycle_status") in {"retired", "archived"}:
            raise TicketConflictError(
                "Không thể tạo ticket cho asset đã ngừng hoặc lưu trữ."
            )

        category_id = self._parse_uuid(
            request.get("category_id"), "category_id", required=False
        )
        subcategory_id = self._parse_uuid(
            request.get("subcategory_id"), "subcategory_id", required=False
        )
        source_id = self._parse_uuid(
            request.get("intake_source_id"), "intake_source_id", required=False
        )
        group_id = self._parse_uuid(
            request.get("support_group_id"), "support_group_id", required=False
        )
        assigned_user_id = self._parse_uuid(
            request.get("assigned_user_id"), "assigned_user_id", required=False
        )
        self._validate_references(
            category_id=category_id,
            subcategory_id=subcategory_id,
            source_id=source_id,
            group_id=group_id,
        )
        assignee = None
        if assigned_user_id is not None:
            self._require_permission(actor, Permission.TICKETS_ASSIGN)
            assignee = self._active_assignee(assigned_user_id)

        impact = Impact(request["impact"])
        urgency = Urgency(request["urgency"])
        priority = calculate_priority(impact, urgency)
        failure_category = str(request.get("failure_category") or "no_failure")
        if failure_category not in self._failure_categories:
            raise TicketDomainError("failure_category không được hỗ trợ.")
        reporter_email = self._optional_text(request.get("reporter_email"), 254)
        if reporter_email and not self._email_pattern.fullmatch(reporter_email):
            raise TicketDomainError("reporter_email không hợp lệ.")
        status = TicketStatus.ASSIGNED if assignee else TicketStatus.OPEN
        policy = self._repository.find_sla_policy(
            category_id=category_id,
            priority=priority.value,
            effective_date=current.astimezone(self._facility_timezone).date(),
        )
        if policy is None:
            raise TicketConflictError(
                "Không có SLA policy đang hiệu lực cho ticket. Hãy seed hoặc cấu hình policy."
            )
        sla_values, sla_events = self._sla_snapshot(policy.values, started_at=current)
        values = {
            "asset_id": asset_id,
            "issue_description": self._normalize_text(
                request["issue_description"],
                "issue_description",
                4000,
                minimum=5,
            ),
            "priority": priority.value,
            "status": status.value,
            "failure_category": failure_category,
            "reporter_name": self._optional_text(request.get("reporter_name"), 200),
            "reporter_email": reporter_email.casefold() if reporter_email else None,
            "reporter_phone": self._optional_text(request.get("reporter_phone"), 40),
            "category_id": category_id,
            "subcategory_id": subcategory_id,
            "impact": impact.value,
            "urgency": urgency.value,
            "intake_source_id": source_id,
            "support_group_id": group_id,
            "assigned_user_id": assigned_user_id,
            "created_at": current,
            "resolved_at": None,
            "first_response_at": None,
            "waiting_reason": None,
            "waiting_previous_status": None,
            "closed_at": None,
            "reopened_at": None,
            "cancelled_at": None,
            "cancellation_reason": None,
            "reopen_count": 0,
            "technician_id": (
                str(assignee.values.get("technician_id") or "UNASSIGNED")
                if assignee
                else "UNASSIGNED"
            ),
            "manager_note": self._optional_text(request.get("manager_note"), 1000),
            "note": None,
        }
        record = self._repository.create_ticket(
            values,
            sla_values=sla_values,
            sla_events=sla_events,
            audit_context=audit_context,
        )
        return self._present(record.values, actor=actor, as_of=current)

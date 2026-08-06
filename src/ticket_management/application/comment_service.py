"""Ticket comment capability."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from src.repositories.contracts import StoredRecord
from src.repositories.postgres_tickets import PostgresTicketRepository
from src.security.audit import AuditContext
from src.security.permissions import Permission
from src.security.service import CurrentUser
from src.ticket_management.domain import CommentVisibility, TicketStatus
from src.ticket_management.errors import TicketConflictError


class TicketCommentService:
    """Own comment visibility policy and append-only repository orchestration."""

    def __init__(
        self,
        repository: PostgresTicketRepository,
        *,
        require_permission: Callable[[CurrentUser, Permission], None],
        ticket_for_action: Callable[[str, CurrentUser], StoredRecord],
        normalize_text: Callable[..., str],
    ) -> None:
        self._repository = repository
        self._require_permission = require_permission
        self._ticket_for_action = ticket_for_action
        self._normalize_text = normalize_text

    def add_comment(
        self,
        ticket_id: str,
        request: dict[str, Any],
        *,
        actor: CurrentUser,
        audit_context: AuditContext,
    ) -> dict[str, Any]:
        visibility = CommentVisibility(request["visibility"])
        permission = (
            Permission.TICKET_COMMENTS_INTERNAL
            if visibility is CommentVisibility.INTERNAL
            else Permission.TICKET_COMMENTS_REQUESTER
        )
        self._require_permission(actor, permission)
        record = self._ticket_for_action(ticket_id, actor)
        if TicketStatus(record.values["status"]) in {
            TicketStatus.CLOSED,
            TicketStatus.CANCELLED,
        }:
            raise TicketConflictError("Ticket closed/cancelled không nhận comment mới.")
        result = self._repository.create_comment(
            ticket_id,
            visibility=visibility.value,
            body=self._normalize_text(request["body"], "body", 4000),
            asset_attachment_ids=[
                UUID(str(value)) for value in request.get("asset_attachment_ids", [])
            ],
            work_order_attachment_ids=[
                UUID(str(value)) for value in request.get("work_order_attachment_ids", [])
            ],
            audit_context=audit_context,
        )
        return dict(result.values)

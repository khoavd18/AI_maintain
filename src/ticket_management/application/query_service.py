"""Ticket queue and detail query capability."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from src.repositories.contracts import StoredRecord
from src.repositories.postgres_tickets import PostgresTicketRepository
from src.security.permissions import Role
from src.security.service import CurrentUser
from src.ticket_management.domain import TICKET_QUEUE_LABELS, TicketQueue


class TicketQueryService:
    """Own queue filtering, technician ownership, pagination, and read shaping."""

    def __init__(
        self,
        repository: PostgresTicketRepository,
        *,
        require_permission: Callable[..., None],
        ticket_record: Callable[..., StoredRecord],
        require_ticket_access: Callable[[CurrentUser, dict[str, Any]], None],
        present: Callable[..., dict[str, Any]],
        is_owned: Callable[[CurrentUser, dict[str, Any]], bool],
        in_queue: Callable[..., bool],
        queue_sort_key: Callable[[dict[str, Any]], tuple[Any, ...]],
        normalize_time: Callable[[datetime], datetime],
        now: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._require_permission = require_permission
        self._ticket_record = ticket_record
        self._require_ticket_access = require_ticket_access
        self._present = present
        self._is_owned = is_owned
        self._in_queue = in_queue
        self._queue_sort_key = queue_sort_key
        self._normalize_time = normalize_time
        self._now = now

    def list_queue(
        self,
        queue_name: str,
        *,
        actor: CurrentUser,
        filters: dict[str, Any],
        page: int,
        page_size: int,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        from src.security.permissions import Permission

        self._require_permission(actor, Permission.TICKETS_READ)
        queue = TicketQueue(queue_name)
        current = self._normalize_time(as_of or self._now())
        repository_filters = {
            key: value
            for key, value in filters.items()
            if key
            in {
                "asset_id",
                "status",
                "priority",
                "category_id",
                "support_group_id",
                "assigned_user_id",
                "search",
            }
            and value is not None
        }
        records = self._repository.list_tickets(filters=repository_filters)
        items = [self._present(record.values, actor=actor, as_of=current) for record in records]
        if actor.role is Role.TECHNICIAN:
            items = [item for item in items if self._is_owned(actor, item)]
        items = [item for item in items if self._in_queue(queue, item, actor, current)]
        items.sort(key=self._queue_sort_key)
        total = len(items)
        start = (page - 1) * page_size
        return {
            "items": items[start : start + page_size],
            "page": page,
            "page_size": page_size,
            "total": total,
            "queue": queue.value,
            "queue_display": TICKET_QUEUE_LABELS[queue],
            "as_of": current.isoformat(),
        }

    def get_ticket(
        self,
        ticket_id: str,
        *,
        actor: CurrentUser,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        from src.security.permissions import Permission

        self._require_permission(actor, Permission.TICKETS_READ)
        record = self._ticket_record(ticket_id, include_timeline=True)
        self._require_ticket_access(actor, record.values)
        return self._present(
            record.values,
            actor=actor,
            as_of=self._normalize_time(as_of or self._now()),
        )

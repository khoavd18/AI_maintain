"""Transactional outbox writer shared by existing PostgreSQL repositories."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.database.models import OutboxEvent
from src.operations.domain import EVENT_CATALOG, FORBIDDEN_PAYLOAD_KEYS
from src.repositories.contracts import IntegrityViolationError

MAX_OUTBOX_PAYLOAD_BYTES = 16_384


def enqueue_outbox_event(
    session: Session,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
    idempotency_key: str,
    scope_id: str | None = None,
    available_after: datetime | None = None,
) -> tuple[UUID, bool]:
    """Insert one validated event inside the caller's active transaction."""

    spec = EVENT_CATALOG.get(event_type)
    if spec is None:
        raise IntegrityViolationError(f"Unsupported outbox event type: {event_type}")
    if aggregate_type != spec.aggregate_type:
        raise IntegrityViolationError(
            f"Outbox aggregate type must be {spec.aggregate_type} for {event_type}."
        )
    normalized_aggregate_id = _bounded_text(aggregate_id, "aggregate_id", 120)
    normalized_key = _bounded_text(idempotency_key, "idempotency_key", 200)
    normalized_scope = (
        _bounded_text(scope_id, "scope_id", 100) if scope_id is not None else None
    )
    normalized_payload = _normalize_payload(payload)
    payload_keys = frozenset(normalized_payload)
    missing = spec.required_fields - payload_keys
    unexpected = payload_keys - spec.allowed_fields
    if missing:
        raise IntegrityViolationError(
            f"Outbox payload for {event_type} is missing fields: {sorted(missing)}"
        )
    if unexpected:
        raise IntegrityViolationError(
            f"Outbox payload for {event_type} has unsupported fields: {sorted(unexpected)}"
        )
    encoded = json.dumps(
        normalized_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > MAX_OUTBOX_PAYLOAD_BYTES:
        raise IntegrityViolationError("Outbox payload exceeds the 16 KiB safety bound.")
    payload_hash = hashlib.sha256(encoded).hexdigest()
    event_id = uuid4()
    now = datetime.now(timezone.utc)
    created_id = session.scalar(
        insert(OutboxEvent)
        .values(
            id=event_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=normalized_aggregate_id,
            scope_id=normalized_scope,
            payload=normalized_payload,
            payload_hash=payload_hash,
            created_at=now,
            available_after=available_after or now,
            status="pending",
            attempt_count=0,
            idempotency_key=normalized_key,
            updated_at=now,
            version=1,
        )
        .on_conflict_do_nothing(constraint="uq_outbox_events_idempotency")
        .returning(OutboxEvent.id)
    )
    if created_id is not None:
        return created_id, True
    existing = session.scalar(
        select(OutboxEvent).where(OutboxEvent.idempotency_key == normalized_key)
    )
    if existing is None:  # pragma: no cover - protected by the unique constraint
        raise IntegrityViolationError("Outbox idempotency state is inconsistent.")
    if (
        existing.event_type != event_type
        or existing.aggregate_type != aggregate_type
        or existing.aggregate_id != normalized_aggregate_id
        or existing.payload_hash != payload_hash
    ):
        raise IntegrityViolationError(
            "Outbox idempotency key was already used with a different event."
        )
    return existing.id, False


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise IntegrityViolationError("Outbox payload must be a JSON object.")
    return {
        _safe_key(key): _normalize_value(value, path=str(key))
        for key, value in payload.items()
    }


def _normalize_value(value: Any, *, path: str) -> Any:
    if path.casefold() in FORBIDDEN_PAYLOAD_KEYS:
        raise IntegrityViolationError(f"Sensitive outbox payload field is forbidden: {path}")
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str) and len(value) > 500:
            raise IntegrityViolationError(f"Outbox payload value is too long: {path}")
        return value
    if isinstance(value, (UUID, date, datetime, Decimal)):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    if isinstance(value, (list, tuple)):
        if len(value) > 100:
            raise IntegrityViolationError(f"Outbox payload list is too large: {path}")
        return [
            _normalize_value(item, path=path)
            for item in value
        ]
    if isinstance(value, dict):
        if len(value) > 50:
            raise IntegrityViolationError(f"Outbox payload object is too large: {path}")
        return {
            _safe_key(key): _normalize_value(item, path=f"{path}.{key}")
            for key, item in value.items()
        }
    raise IntegrityViolationError(
        f"Outbox payload contains unsupported value at {path}: {type(value).__name__}"
    )


def _safe_key(value: object) -> str:
    key = str(value).strip()
    if not key or len(key) > 100:
        raise IntegrityViolationError("Outbox payload keys must contain 1–100 characters.")
    if key.casefold() in FORBIDDEN_PAYLOAD_KEYS:
        raise IntegrityViolationError(f"Sensitive outbox payload field is forbidden: {key}")
    return key


def _bounded_text(value: object, label: str, maximum: int) -> str:
    normalized = str(value).strip()
    if not normalized or len(normalized) > maximum:
        raise IntegrityViolationError(
            f"{label} must contain between 1 and {maximum} characters."
        )
    return normalized

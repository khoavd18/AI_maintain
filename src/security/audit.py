"""Safe audit context and state projection helpers."""

from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from src.database.models import AuditLog, User
from src.security.audit_context import AuditContext
from src.security.principal import CurrentUser

__all__ = [
    "ASSET_AUDIT_FIELDS",
    "ATTACHMENT_AUDIT_FIELDS",
    "AuditContext",
    "LOCATION_AUDIT_FIELDS",
    "LOG_AUDIT_FIELDS",
    "TICKET_AUDIT_FIELDS",
    "append_security_audit",
    "safe_metadata",
    "safe_state",
]


TICKET_AUDIT_FIELDS = {
    "ticket_id",
    "asset_id",
    "priority",
    "status",
    "failure_category",
    "technician_id",
    "created_at",
    "resolved_at",
}
LOG_AUDIT_FIELDS = {
    "log_id",
    "ticket_id",
    "asset_id",
    "maintenance_date",
    "maintenance_type",
    "technician_id",
    "maintenance_result",
    "follow_up_required",
    "next_maintenance_date",
}
ASSET_AUDIT_FIELDS = {
    "asset_id",
    "asset_name",
    "asset_type_code",
    "asset_category",
    "manufacturer",
    "model",
    "serial_number",
    "production_year",
    "location_id",
    "location",
    "criticality_code",
    "lifecycle_status",
    "lifecycle_status_before_archive",
    "operational_status",
    "operational_status_before_archive",
    "ownership_type",
    "installed_at",
    "commissioned_at",
    "retired_at",
    "archived_at",
    "archive_reason",
    "maintenance_interval_days",
    "last_maintenance_date",
    "next_maintenance_date",
    "version",
}
LOCATION_AUDIT_FIELDS = {
    "id",
    "code",
    "name",
    "location_type",
    "parent_id",
    "is_active",
    "version",
}
ATTACHMENT_AUDIT_FIELDS = {
    "id",
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


def safe_state(values: dict[str, Any], allowed_fields: set[str]) -> dict[str, object]:
    """Project only bounded operational identifiers and state values."""

    return {
        key: _json_value(values[key])
        for key in sorted(allowed_fields & values.keys())
        if values[key] is not None
    }


def safe_metadata(values: dict[str, Any] | None = None) -> dict[str, object] | None:
    """Keep small allow-listed scalar metadata out of secret-bearing fields."""

    if not values:
        return None
    forbidden = {"password", "password_hash", "token", "authorization", "cookie"}
    result: dict[str, object] = {}
    for key, value in values.items():
        normalized_key = str(key).lower()
        if any(fragment in normalized_key for fragment in forbidden):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[str(key)[:80]] = str(value)[:300] if isinstance(value, str) else value
    return result or None


def append_security_audit(
    session: Session,
    *,
    actor: User | CurrentUser | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    request_id: str,
    before_state: dict[str, object] | None = None,
    after_state: dict[str, object] | None = None,
    metadata: dict[str, Any] | None = None,
    outcome: str,
) -> None:
    """Add one security audit row to the caller-owned transaction."""

    session.add(
        AuditLog(
            id=uuid4(),
            actor_user_id=actor.id if actor else None,
            actor_display_name=actor.display_name if actor else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id[:100],
            before_state=before_state,
            after_state=after_state,
            event_metadata=safe_metadata(metadata),
            outcome=outcome,
        )
    )


def _json_value(value: Any) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)[:300]

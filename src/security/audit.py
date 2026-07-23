"""Safe audit context and state projection helpers."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class AuditContext:
    actor_user_id: UUID
    actor_display_name: str
    request_id: str


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


def _json_value(value: Any) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)[:300]

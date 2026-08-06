"""Shared pure validation helpers for the internal-pilot contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .constants import (
    _COMMIT_RE,
    _EMAIL_RE,
    _PHONE_RE,
    _PLACEHOLDER_MARKERS,
    _SENSITIVE_VALUE_KEYS,
    _WINDOWS_ABSOLUTE_RE,
    REQUIRED_LIMITATIONS,
    REQUIRED_OWNERS,
    Severity,
)
from .schemas import Finding

def _validate_safe_document(
    document: dict[str, Any],
    scope: str,
    findings: list[Finding],
) -> None:
    def visit(value: Any, location: str, key: str | None = None) -> None:
        normalized_key = (key or "").casefold()
        if normalized_key in _SENSITIVE_VALUE_KEYS and value not in (None, False, True, ""):
            _add(
                findings,
                "secret_or_personal_value_committed",
                location,
                "Contract không được chứa secret, credential hoặc personal contact value.",
            )
            return
        if isinstance(value, Mapping):
            for child_key, child_value in value.items():
                visit(child_value, f"{location}.{child_key}", str(child_key))
        elif isinstance(value, list):
            for index, child_value in enumerate(value):
                visit(child_value, f"{location}[{index}]")
        elif isinstance(value, str):
            if _url_contains_credentials(value):
                _add(
                    findings,
                    "credential_url_committed",
                    location,
                    "Contract không được chứa URL có credential.",
                )
            if _looks_like_local_absolute_path(value) and normalized_key != "container_path":
                _add(
                    findings,
                    "absolute_local_path_committed",
                    location,
                    "Contract không được chứa absolute local path.",
                )
            if _EMAIL_RE.search(value) or _PHONE_RE.search(value):
                _add(
                    findings,
                    "personal_contact_committed",
                    location,
                    "Contract không được chứa email hoặc số điện thoại cá nhân.",
                )

    visit(document, scope)


def _ownership_ready(document: dict[str, Any]) -> bool:
    if (
        document.get("record_kind") != "internal_pilot_operational_ownership"
        or document.get("record_status") != "approved"
    ):
        return False
    assignments = _mapping(document.get("assignments"))
    for key in REQUIRED_OWNERS:
        assignment = _mapping(assignments.get(key))
        if (
            assignment.get("status") != "assigned"
            or not _non_placeholder_text(assignment.get("assigned_role"))
            or not _non_placeholder_text(assignment.get("approved_internal_channel"))
            or not _valid_evidence_links(assignment.get("approval_evidence_links"))
        ):
            return False
    incident = _mapping(document.get("incident_communication"))
    if (
        incident.get("status") != "configured"
        or not _non_placeholder_text(incident.get("primary_internal_channel"))
        or not _non_placeholder_text(incident.get("fallback_internal_channel"))
        or not _valid_evidence_links(incident.get("approval_evidence_links"))
    ):
        return False
    coverage = _mapping(document.get("support_coverage"))
    if (
        coverage.get("status") != "confirmed"
        or not _non_placeholder_text(coverage.get("support_hours"))
        or not _non_placeholder_text(coverage.get("after_hours_assumption"))
        or not _valid_iana_timezone(coverage.get("timezone"))
        or not _valid_evidence_links(coverage.get("approval_evidence_links"))
    ):
        return False
    escalation = _mapping(document.get("escalation_path"))
    raw_steps = escalation.get("steps")
    if not isinstance(raw_steps, list) or any(not isinstance(step, Mapping) for step in raw_steps):
        return False
    steps = [dict(step) for step in raw_steps]
    orders = [step.get("order") for step in steps]
    owner_refs = [step.get("owner_ref") for step in steps]
    return (
        escalation.get("status") == "configured"
        and _valid_evidence_links(escalation.get("approval_evidence_links"))
        and len(steps) >= 2
        and all(type(order) is int and order >= 1 for order in orders)
        and len(set(orders)) == len(orders)
        and all(isinstance(owner_ref, str) for owner_ref in owner_refs)
        and len(set(owner_refs)) == len(owner_refs)
        and all(
            step.get("owner_ref") in REQUIRED_OWNERS
            and _non_placeholder_text(step.get("channel_ref"))
            for step in steps
        )
    )


def _critical_limitations_accepted(document: dict[str, Any]) -> bool:
    if (
        document.get("record_kind") != "internal_pilot_known_limitations_acceptance"
        or document.get("record_status") != "accepted"
    ):
        return False
    raw_rows = document.get("limitations")
    if not isinstance(raw_rows, list) or any(not isinstance(row, Mapping) for row in raw_rows):
        return False
    rows = [dict(row) for row in raw_rows]
    row_ids = [row.get("id") for row in rows]
    if any(not _non_placeholder_text(row_id) for row_id in row_ids):
        return False
    ids = set(row_ids)
    if len(ids) != len(rows):
        return False
    if not REQUIRED_LIMITATIONS.issubset(ids):
        return False
    for row in rows:
        limitation_id = row.get("id")
        is_required = limitation_id in REQUIRED_LIMITATIONS
        if is_required and row.get("critical") is not True:
            return False
        status = row.get("acceptance_status")
        if not isinstance(status, str) or status not in {
            "accepted",
            "pending",
            "rejected",
        }:
            return False
        if row.get("critical") is False and not is_required:
            continue
        if row.get("critical") is not True:
            return False
        if (
            row.get("acceptance_status") != "accepted"
            or not _non_placeholder_text(row.get("owner_role"))
            or not _non_placeholder_text(row.get("accepted_by_role"))
            or not _valid_utc_timestamp(row.get("accepted_at_utc"))
            or not _valid_evidence_links(row.get("acceptance_evidence_links"))
            or not _non_placeholder_text(row.get("review_trigger"))
        ):
            return False
    return True


def _condition_is_bounded(condition: Mapping[str, Any]) -> bool:
    return all(
        (
            _non_placeholder_text(condition.get("description")),
            _non_placeholder_text(condition.get("owner_role")),
            _non_placeholder_text(condition.get("mitigation")),
            _non_placeholder_text(condition.get("review_trigger")),
            _non_placeholder_text(condition.get("pilot_scope_limit")),
            _valid_evidence_links(condition.get("evidence_links")),
        )
    )


def _valid_evidence_links(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for link in value:
        if not isinstance(link, str) or not link.strip() or _is_placeholder(link):
            return False
        if _looks_like_local_absolute_path(link) or _url_contains_credentials(link):
            return False
    return True


def _valid_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def _safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return False
    normalized = value.replace("\\", "/")
    if (
        normalized.startswith("/")
        or normalized.startswith("//")
        or _WINDOWS_ABSOLUTE_RE.match(value)
        or "://" in normalized
    ):
        return False
    parts = PurePosixPath(normalized).parts
    return ".." not in parts and all(part not in {"", "."} for part in parts)


def _safe_container_path(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or "\x00" in value
    ):
        return False
    parts = PurePosixPath(value).parts
    return ".." not in parts and all(part != "." for part in parts)


def _safe_service_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


def _url_contains_credentials(value: str) -> bool:
    if "://" not in value:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return True
    return parsed.username is not None or parsed.password is not None


def _looks_like_local_absolute_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return bool(
        _WINDOWS_ABSOLUTE_RE.match(value)
        or value.startswith("\\\\")
        or normalized.startswith(
            (
                "/Users/",
                "/home/",
                "/tmp/",
                "/var/",
                "/etc/",
                "/opt/",
                "/srv/",
                "/mnt/",
                "/app/",
                "/root/",
            )
        )
    )


def _git_identity_matches(expected: str, actual: str) -> bool:
    expected_normalized = expected.strip().casefold()
    actual_normalized = actual.strip().casefold()
    return bool(
        _COMMIT_RE.fullmatch(expected_normalized)
        and _COMMIT_RE.fullmatch(actual_normalized)
        and expected_normalized == actual_normalized
    )


def _validate_integer_environment_match(
    environment: Mapping[str, str],
    name: str,
    expected: Any,
    findings: list[Finding],
) -> None:
    value = environment.get(name)
    if not value:
        return
    try:
        actual = int(value)
    except ValueError:
        actual = None
    if actual != expected:
        _add(
            findings,
            "runtime_environment_mismatch",
            f"environment.{name}",
            f"{name} phải là số nguyên khớp deployment manifest.",
        )


def _validate_integer_environment_range(
    environment: Mapping[str, str],
    name: str,
    minimum: int,
    maximum: int,
    findings: list[Finding],
) -> None:
    value = environment.get(name)
    if not value:
        return
    try:
        actual = int(value)
    except ValueError:
        actual = None
    if actual is None or not minimum <= actual <= maximum:
        _add(
            findings,
            "runtime_environment_out_of_range",
            f"environment.{name}",
            f"{name} phải là số nguyên nằm trong giới hạn pilot.",
        )


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().casefold() in {"1", "true", "yes", "on"})


def _is_placeholder(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return True
    normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
    return any(marker in normalized for marker in _PLACEHOLDER_MARKERS)


def _non_placeholder_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _is_placeholder(value)


def _valid_iana_timezone(value: Any) -> bool:
    if not _non_placeholder_text(value):
        return False
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def _versioned(document: Mapping[str, Any]) -> bool:
    value = document.get("schema_version")
    return (
        isinstance(value, (str, int)) and not isinstance(value, bool) and bool(str(value).strip())
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_of_mappings(
    value: Any,
    *,
    findings: list[Finding] | None = None,
    scope: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            rows.append(dict(item))
        elif findings is not None and scope is not None:
            _add(
                findings,
                "list_entry_not_object",
                f"{scope}.{index}",
                "Mỗi phần tử trong danh sách contract phải là JSON object.",
            )
    return rows


def _require_keys(
    value: Mapping[str, Any],
    required: set[str],
    scope: str,
    findings: list[Finding],
) -> None:
    for key in sorted(required - set(value)):
        _add(
            findings,
            "required_key_missing",
            f"{scope}.{key}",
            f"Thiếu required key: {key}.",
        )


def _check_unique_names(
    rows: list[dict[str, Any]],
    key: str,
    entity: str,
    findings: list[Finding],
) -> set[str]:
    names: set[str] = set()
    for row in rows:
        name = row.get(key)
        if not isinstance(name, str) or not name:
            _add(
                findings,
                f"{entity}_name_missing",
                f"manifest.{entity}s",
                f"Mỗi {entity} phải có {key}.",
            )
            continue
        if name in names:
            _add(
                findings,
                f"duplicate_{entity}",
                f"manifest.{entity}s.{name}",
                f"{entity} bị khai báo trùng.",
            )
        names.add(name)
    return names


def _add(
    findings: list[Finding],
    code: str,
    scope: str,
    message: str,
    severity: Severity = "blocker",
) -> None:
    findings.append(Finding(code=code, scope=scope, message=message, severity=severity))


def _has_blocker(findings: Sequence[Finding]) -> bool:
    return any(finding.severity == "blocker" for finding in findings)


def _ordered_findings(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    unique = {
        (finding.code, finding.scope, finding.message, finding.severity): finding
        for finding in findings
    }
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (item.severity, item.code, item.scope, item.message),
        )
    )




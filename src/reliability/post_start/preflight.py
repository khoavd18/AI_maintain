"""No-network preflight contract for authenticated post-start validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlsplit


_EXECUTION_FLAG = "PM9_ALLOW_POST_START_VALIDATION"
_HTTP_TEST_FLAG = "PM9_ALLOW_HTTP_TEST_SMOKE"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_MANIFEST = _REPOSITORY_ROOT / "deployment" / "pilot_manifest.json"
_COOKIE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_EXPECTED_JOB_TYPES = frozenset(
    {
        "preventive_generation",
        "sla_escalation",
        "analytics_refresh",
        "inventory_reorder_detection",
    }
)


class PostStartValidationError(RuntimeError):
    """Safe validation failure that never contains response bodies or secrets."""


@dataclass(frozen=True, slots=True)
class _PostStartPreflight:
    transport_scope: Literal["https", "loopback_http_test"]
    expected_jobs: Mapping[str, bool]
    expected_release: Mapping[str, str]


def validate_post_start_preconditions(
    *,
    base_url: str,
    operator_username: str,
    operator_password: str,
    restricted_username: str,
    restricted_password: str,
    expected_release_identifier: str,
    expected_release_commit: str,
    expected_release_tag: str,
    expected_alembic_revision: str,
    manifest_path: Path = _DEFAULT_MANIFEST,
    refresh_cookie_name: str = "maintenance_refresh",
    csrf_cookie_name: str = "maintenance_csrf",
    host_approved: bool = False,
    intended_host: bool = False,
    allow_loopback_http: bool = False,
    timeout_seconds: float = 10.0,
) -> None:
    """Validate every no-network guard used by the authenticated smoke."""

    _prepare_post_start_validation(
        base_url=base_url,
        operator_username=operator_username,
        operator_password=operator_password,
        restricted_username=restricted_username,
        restricted_password=restricted_password,
        expected_release_identifier=expected_release_identifier,
        expected_release_commit=expected_release_commit,
        expected_release_tag=expected_release_tag,
        expected_alembic_revision=expected_alembic_revision,
        manifest_path=manifest_path,
        refresh_cookie_name=refresh_cookie_name,
        csrf_cookie_name=csrf_cookie_name,
        host_approved=host_approved,
        intended_host=intended_host,
        allow_loopback_http=allow_loopback_http,
        timeout_seconds=timeout_seconds,
    )


def _prepare_post_start_validation(
    *,
    base_url: str,
    operator_username: str,
    operator_password: str,
    restricted_username: str,
    restricted_password: str,
    expected_release_identifier: str,
    expected_release_commit: str,
    expected_release_tag: str,
    expected_alembic_revision: str,
    manifest_path: Path,
    refresh_cookie_name: str,
    csrf_cookie_name: str,
    host_approved: bool,
    intended_host: bool,
    allow_loopback_http: bool,
    timeout_seconds: float,
) -> _PostStartPreflight:
    if os.getenv(_EXECUTION_FLAG) != "true":
        raise PostStartValidationError(f"Execution requires {_EXECUTION_FLAG}=true.")
    transport_scope = _validated_origin(
        base_url,
        allow_loopback_http=allow_loopback_http,
    )
    if intended_host and not host_approved:
        raise PostStartValidationError(
            "An intended-host claim requires explicit pilot-host approval."
        )
    _validate_credentials(
        operator_username=operator_username,
        operator_password=operator_password,
        restricted_username=restricted_username,
        restricted_password=restricted_password,
    )
    expected_jobs, application_version = _load_manifest_expectations(manifest_path)
    expected_release = {
        "identifier": _required_text(
            expected_release_identifier,
            "release identifier",
        ),
        "application_version": application_version,
        "git_commit": _required_text(expected_release_commit, "release commit"),
        "git_tag": _required_text(expected_release_tag, "release tag"),
        "alembic_revision": _required_text(
            expected_alembic_revision,
            "Alembic revision",
        ),
    }
    if (
        not _COOKIE_NAME_PATTERN.fullmatch(refresh_cookie_name)
        or not _COOKIE_NAME_PATTERN.fullmatch(csrf_cookie_name)
        or refresh_cookie_name == csrf_cookie_name
    ):
        raise PostStartValidationError("Refresh and CSRF cookie names must be distinct and valid.")
    if not 1 <= timeout_seconds <= 60:
        raise PostStartValidationError(
            "Post-start request timeout must be between 1 and 60 seconds."
        )
    return _PostStartPreflight(
        transport_scope=transport_scope,
        expected_jobs=expected_jobs,
        expected_release=expected_release,
    )


def _load_manifest_expectations(path: Path) -> tuple[dict[str, bool], str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise PostStartValidationError("Deployment manifest is unavailable or invalid.") from None
    if not isinstance(document, Mapping):
        raise PostStartValidationError("Deployment manifest root is invalid.")
    rows = document.get("scheduled_jobs")
    versions = document.get("versions")
    if not isinstance(rows, list) or not isinstance(versions, Mapping):
        raise PostStartValidationError("Deployment manifest lacks jobs or versions.")
    jobs: dict[str, bool] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise PostStartValidationError("Manifest scheduled-job row is invalid.")
        name = row.get("job_type")
        enabled = row.get("enabled")
        if not isinstance(name, str) or type(enabled) is not bool or name in jobs:
            raise PostStartValidationError("Manifest scheduled-job catalog is invalid.")
        jobs[name] = enabled
    if set(jobs) != _EXPECTED_JOB_TYPES:
        raise PostStartValidationError("Manifest scheduled-job catalog is unsupported.")
    application_version = versions.get("application")
    if not isinstance(application_version, str) or not application_version:
        raise PostStartValidationError("Manifest application version is unavailable.")
    return jobs, application_version


def _validate_credentials(
    *,
    operator_username: str,
    operator_password: str,
    restricted_username: str,
    restricted_password: str,
) -> None:
    values = (
        operator_username,
        operator_password,
        restricted_username,
        restricted_password,
    )
    if any(not value or len(value) > 256 for value in values):
        raise PostStartValidationError("Both bounded smoke-account credentials are required.")
    if operator_username.casefold() == restricted_username.casefold():
        raise PostStartValidationError("Operator and restricted smoke accounts must be different.")


def _validated_origin(
    value: str,
    *,
    allow_loopback_http: bool,
) -> Literal["https", "loopback_http_test"]:
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise PostStartValidationError("Post-start base URL is invalid.") from None
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise PostStartValidationError("Post-start base URL must be a credential-free origin.")
    if parsed.scheme == "https":
        return "https"
    loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    if (
        parsed.scheme == "http"
        and loopback
        and allow_loopback_http
        and os.getenv(_HTTP_TEST_FLAG) == "true"
    ):
        return "loopback_http_test"
    raise PostStartValidationError(
        "Post-start validation requires HTTPS; loopback HTTP needs both test opt-ins."
    )


def _required_text(value: str, label: str) -> str:
    text = value.strip()
    if not text or len(text) > 200:
        raise PostStartValidationError(f"Expected {label} is invalid.")
    return text

"""Bounded authenticated post-start validation for an internal-pilot stack.

The validator exercises existing FastAPI boundaries only. It creates and
revokes normal authentication sessions, performs no business mutation, accepts
no arbitrary request targets, and writes only aggregate, credential-free
evidence outside the repository.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from src.reliability.deployment_rehearsal import load_environment_file

_EXECUTION_FLAG = "PM9_ALLOW_POST_START_VALIDATION"
_HTTP_TEST_FLAG = "PM9_ALLOW_HTTP_TEST_SMOKE"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MANIFEST = _REPOSITORY_ROOT / "deployment" / "pilot_manifest.json"
_MAX_RESPONSE_BYTES = 1024 * 1024
_COOKIE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_EXPECTED_JOB_TYPES = frozenset(
    {
        "preventive_generation",
        "sla_escalation",
        "analytics_refresh",
        "inventory_reorder_detection",
    }
)
_OPERATOR_PERMISSIONS = frozenset(
    {
        "assets:read",
        "tickets:read",
        "work_orders:read",
        "inventory:read",
        "analytics:read",
        "notifications:read",
        "job_operations:read",
    }
)
_RESTRICTED_REQUIRED_PERMISSIONS = frozenset(
    {
        "assets:read",
        "notifications:read",
    }
)
_RESTRICTED_FORBIDDEN_PERMISSIONS = frozenset(
    {
        "analytics:read",
        "job_operations:read",
        "job_operations:manage",
    }
)
_CHECK_ORDER = (
    "unauthenticated_boundary",
    "release_and_readiness",
    "operator_authentication",
    "operator_session_refresh",
    "restricted_authentication",
    "rbac_boundary",
    "scheduled_jobs",
    "approved_data_reads",
    "analytics_availability",
    "notification_owner_isolation",
    "session_cleanup",
)

CheckStatus = Literal["passed", "failed", "not_executed"]
OverallStatus = Literal["passed", "failed"]


class PostStartValidationError(RuntimeError):
    """Safe validation failure that never contains response bodies or secrets."""


@dataclass(frozen=True, slots=True)
class PostStartCheck:
    name: str
    status: CheckStatus
    evidence_code: str


@dataclass(frozen=True, slots=True)
class PostStartReport:
    schema_version: int
    generated_at: str
    scope: str
    executed: bool
    host_approved: bool
    intended_host_claim: bool
    production_readiness_claim: bool
    transport_scope: Literal["https", "loopback_http_test"]
    release_identifier: str
    release_commit: str
    release_tag: str
    alembic_revision: str
    overall_status: OverallStatus
    checks: tuple[PostStartCheck, ...]
    observations: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["checks"] = [asdict(check) for check in self.checks]
        value["observations"] = dict(self.observations)
        return value


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


def run_post_start_validation(
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
    evidence_dir: Path | None = None,
    host_approved: bool = False,
    intended_host: bool = False,
    allow_loopback_http: bool = False,
    timeout_seconds: float = 10.0,
    transport: httpx.BaseTransport | None = None,
) -> tuple[PostStartReport, Path | None]:
    """Execute the closed read-only smoke profile and return redacted evidence."""

    preflight = _prepare_post_start_validation(
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
    transport_scope = preflight.transport_scope
    expected_jobs = dict(preflight.expected_jobs)
    expected_release = dict(preflight.expected_release)
    output_root = _validated_evidence_dir(evidence_dir) if evidence_dir is not None else None

    checks: list[PostStartCheck] = []
    observations: dict[str, Any] = {
        "authentication_session_writes": True,
        "business_mutations_performed": False,
        "business_record_counts": {},
        "dead_letter_counts": {},
        "enabled_job_types": [],
        "notification_counts": {},
        "operator_role": None,
        "restricted_role": None,
        "refresh_rotation_old_session_rejected": False,
        "logout_session_revocations_verified": 0,
    }
    operator_access: str | None = None
    restricted_access: str | None = None
    operator_login_attempted = False
    restricted_login_attempted = False
    stopped = False

    client_arguments: dict[str, Any] = {
        "base_url": base_url.rstrip("/") + "/",
        "timeout": httpx.Timeout(timeout_seconds),
        "follow_redirects": False,
        "trust_env": False,
        "headers": {
            "Accept": "application/json",
            "User-Agent": "ai-maintenance-copilot-pm9-post-start/1",
        },
    }
    if transport is not None:
        client_arguments["transport"] = transport

    operator_client = httpx.Client(**client_arguments)
    restricted_client = httpx.Client(**client_arguments)
    revocation_client = httpx.Client(**client_arguments)

    def check(name: str, evidence_code: str, function):
        nonlocal stopped
        try:
            result = function()
        except (PostStartValidationError, httpx.HTTPError, ValueError):
            checks.append(PostStartCheck(name, "failed", "safe_validation_failure"))
            stopped = True
            raise _StopValidation from None
        checks.append(PostStartCheck(name, "passed", evidence_code))
        return result

    try:
        check(
            "unauthenticated_boundary",
            "protected_identity_rejected_without_token",
            lambda: _expect_status(
                operator_client,
                "GET",
                "/auth/me",
                expected_status=401,
            ),
        )

        def validate_release_and_readiness() -> None:
            liveness = _request_json(
                operator_client,
                "GET",
                "/health/live",
                expected_status=200,
                expected_type=dict,
            )
            _require_release_identity(liveness, expected_release)
            if liveness.get("status") != "alive":
                raise PostStartValidationError("API liveness status is not alive.")
            readiness = _request_json(
                operator_client,
                "GET",
                "/health/ready",
                expected_status=200,
                expected_type=dict,
            )
            _require_release_identity(readiness, expected_release)
            if (
                readiness.get("status") != "ready"
                or readiness.get("database_ready") is not True
                or readiness.get("worker_ready") is not True
            ):
                raise PostStartValidationError("API readiness is degraded.")
            worker = _request_json(
                operator_client,
                "GET",
                "/health/worker",
                expected_status=200,
                expected_type=dict,
            )
            if worker.get("status") != "ready" or worker.get("ready") is not True:
                raise PostStartValidationError("Worker heartbeat is not ready.")

        check(
            "release_and_readiness",
            "release_database_and_worker_ready",
            validate_release_and_readiness,
        )

        def authenticate_operator() -> None:
            nonlocal operator_access, operator_login_attempted
            operator_login_attempted = True
            payload = _login(
                operator_client,
                username=operator_username,
                password=operator_password,
            )
            operator_access = _access_token(payload)
            identity = _authenticated_identity(operator_client, operator_access)
            permissions = _permission_set(identity)
            if not _OPERATOR_PERMISSIONS.issubset(permissions):
                raise PostStartValidationError("Operator account lacks required smoke permissions.")
            observations["operator_role"] = _role(identity)

        check(
            "operator_authentication",
            "operator_login_and_current_user_validated",
            authenticate_operator,
        )

        def refresh_operator_session() -> None:
            nonlocal operator_access
            assert operator_access is not None
            previous_access = operator_access
            previous_refresh = _cookie_value(
                operator_client,
                refresh_cookie_name,
            )
            previous_csrf = _cookie_value(operator_client, csrf_cookie_name)
            refreshed = _request_json(
                operator_client,
                "POST",
                "/auth/refresh",
                expected_status=200,
                expected_type=dict,
                headers={"X-CSRF-Token": previous_csrf},
            )
            operator_access = _access_token(refreshed)
            current_refresh = _cookie_value(operator_client, refresh_cookie_name)
            current_csrf = _cookie_value(operator_client, csrf_cookie_name)
            if (
                operator_access == previous_access
                or current_refresh == previous_refresh
                or current_csrf == previous_csrf
            ):
                raise PostStartValidationError(
                    "Authentication refresh did not rotate every session credential."
                )
            _authenticated_identity(operator_client, operator_access)
            _expect_status(
                operator_client,
                "GET",
                "/auth/me",
                expected_status=401,
                headers=_bearer(previous_access),
            )
            _expect_refresh_rejected(
                revocation_client,
                refresh_cookie_name=refresh_cookie_name,
                csrf_cookie_name=csrf_cookie_name,
                refresh_token=previous_refresh,
                csrf_token=previous_csrf,
            )
            observations["refresh_rotation_old_session_rejected"] = True

        check(
            "operator_session_refresh",
            "refresh_rotation_old_session_rejected_and_new_access_validated",
            refresh_operator_session,
        )

        def authenticate_restricted() -> None:
            nonlocal restricted_access, restricted_login_attempted
            restricted_login_attempted = True
            payload = _login(
                restricted_client,
                username=restricted_username,
                password=restricted_password,
            )
            restricted_access = _access_token(payload)
            identity = _authenticated_identity(restricted_client, restricted_access)
            permissions = _permission_set(identity)
            if not _RESTRICTED_REQUIRED_PERMISSIONS.issubset(permissions):
                raise PostStartValidationError(
                    "Restricted account lacks required positive read permissions."
                )
            if permissions.intersection(_RESTRICTED_FORBIDDEN_PERMISSIONS):
                raise PostStartValidationError(
                    "Restricted account has a forbidden operator permission."
                )
            observations["restricted_role"] = _role(identity)

        check(
            "restricted_authentication",
            "restricted_login_and_permissions_validated",
            authenticate_restricted,
        )

        def validate_rbac() -> None:
            assert restricted_access is not None
            headers = _bearer(restricted_access)
            _expect_status(
                restricted_client,
                "GET",
                "/operations/jobs",
                expected_status=403,
                headers=headers,
            )
            _expect_status(
                restricted_client,
                "GET",
                "/summary",
                expected_status=403,
                headers=headers,
            )
            _request_json(
                restricted_client,
                "GET",
                "/assets/catalog?page=1&page_size=1",
                expected_status=200,
                expected_type=dict,
                headers=headers,
            )

        check(
            "rbac_boundary",
            "restricted_positive_read_and_forbidden_operator_paths_validated",
            validate_rbac,
        )

        def validate_jobs() -> None:
            assert operator_access is not None
            headers = _bearer(operator_access)
            jobs = _request_json(
                operator_client,
                "GET",
                "/operations/jobs",
                expected_status=200,
                expected_type=list,
                headers=headers,
            )
            observed: dict[str, bool] = {}
            for row in jobs:
                if not isinstance(row, Mapping):
                    raise PostStartValidationError("Scheduled-job response is invalid.")
                job_type = row.get("job_type")
                enabled = row.get("enabled")
                if (
                    not isinstance(job_type, str)
                    or type(enabled) is not bool
                    or job_type in observed
                ):
                    raise PostStartValidationError(
                        "Scheduled-job catalog contains an invalid or duplicate row."
                    )
                observed[job_type] = enabled
            if set(observed) != _EXPECTED_JOB_TYPES or observed != expected_jobs:
                raise PostStartValidationError(
                    "Scheduled-job catalog or enable state does not match the manifest."
                )
            metrics = _request_json(
                operator_client,
                "GET",
                "/operations/metrics",
                expected_status=200,
                expected_type=dict,
                headers=headers,
            )
            dead_job = _nonnegative_int(metrics.get("dead_letter_job_count"))
            dead_outbox = _nonnegative_int(metrics.get("dead_letter_outbox_count"))
            observations["dead_letter_counts"] = {
                "jobs": dead_job,
                "outbox": dead_outbox,
            }
            observations["enabled_job_types"] = sorted(
                name for name, enabled in observed.items() if enabled
            )
            if dead_job or dead_outbox:
                raise PostStartValidationError(
                    "Unresolved dead-letter records block the post-start gate."
                )

        check(
            "scheduled_jobs",
            "exact_job_catalog_enable_state_and_dead_letters_validated",
            validate_jobs,
        )

        def validate_approved_data() -> None:
            assert operator_access is not None
            headers = _bearer(operator_access)
            paths = {
                "assets": "/assets/catalog?page=1&page_size=1",
                "tickets": "/ticket-queues/all?page=1&page_size=1",
                "work_orders": "/work-orders?page=1&page_size=1",
                "inventory_balances": "/inventory/balances?page=1&page_size=1",
            }
            counts: dict[str, int] = {}
            for name, path in paths.items():
                payload = _request_json(
                    operator_client,
                    "GET",
                    path,
                    expected_status=200,
                    expected_type=dict,
                    headers=headers,
                )
                counts[name] = _nonnegative_int(payload.get("total"))
            observations["business_record_counts"] = counts
            if any(count == 0 for count in counts.values()):
                raise PostStartValidationError(
                    "Representative approved-data reads include an empty domain."
                )

        check(
            "approved_data_reads",
            "representative_asset_ticket_work_order_inventory_reads_validated",
            validate_approved_data,
        )

        def validate_analytics() -> None:
            assert operator_access is not None
            health = _request_json(
                operator_client,
                "GET",
                "/health",
                expected_status=200,
                expected_type=dict,
            )
            if (
                health.get("status") != "ok"
                or health.get("raw_data_available") is not True
                or health.get("analytics_available") is not True
            ):
                raise PostStartValidationError("Batch analytics inputs or outputs are unavailable.")
            summary = _request_json(
                operator_client,
                "GET",
                "/summary",
                expected_status=200,
                expected_type=dict,
                headers=_bearer(operator_access),
            )
            total_assets = _nonnegative_int(summary.get("total_assets"))
            total_records = _nonnegative_int(summary.get("total_records"))
            if total_assets == 0 or total_records == 0:
                raise PostStartValidationError(
                    "Analytics summary does not contain representative data."
                )
            observations["analytics_counts"] = {
                "total_assets": total_assets,
                "total_records": total_records,
            }

        check(
            "analytics_availability",
            "latest_batch_analytics_and_summary_validated",
            validate_analytics,
        )

        def validate_notifications() -> None:
            assert operator_access is not None
            assert restricted_access is not None
            # Read append-only unread counts first. Worker-created notifications
            # between these calls and the page reads can only increase the later
            # owner-visible totals, avoiding a false inconsistency failure.
            operator_unread = _unread_count(operator_client, operator_access)
            restricted_unread = _unread_count(restricted_client, restricted_access)
            operator_page = _request_json(
                operator_client,
                "GET",
                "/notifications?page=1&page_size=100",
                expected_status=200,
                expected_type=dict,
                headers=_bearer(operator_access),
            )
            restricted_page = _request_json(
                restricted_client,
                "GET",
                "/notifications?page=1&page_size=100",
                expected_status=200,
                expected_type=dict,
                headers=_bearer(restricted_access),
            )
            operator_ids = _notification_ids(operator_page)
            restricted_ids = _notification_ids(restricted_page)
            if operator_ids.intersection(restricted_ids):
                raise PostStartValidationError(
                    "Notification owner isolation check observed a shared record."
                )
            operator_total = _nonnegative_int(operator_page.get("total"))
            restricted_total = _nonnegative_int(restricted_page.get("total"))
            if operator_total + restricted_total == 0:
                raise PostStartValidationError(
                    "Notification evidence is empty for both smoke accounts."
                )
            if operator_unread > operator_total or restricted_unread > restricted_total:
                raise PostStartValidationError(
                    "Notification unread count exceeds the owner-visible total."
                )
            observations["notification_counts"] = {
                "operator_total": operator_total,
                "operator_unread": operator_unread,
                "restricted_total": restricted_total,
                "restricted_unread": restricted_unread,
            }

        check(
            "notification_owner_isolation",
            "nonempty_owner_isolated_inbox_and_unread_counts_validated",
            validate_notifications,
        )
    except _StopValidation:
        pass
    finally:
        cleanup_failed = False
        verified_revocations = 0
        if operator_login_attempted:
            operator_cleaned = _logout_if_session_exists(
                operator_client,
                revocation_client=revocation_client,
                refresh_cookie_name=refresh_cookie_name,
                csrf_cookie_name=csrf_cookie_name,
                access_token=operator_access,
            )
            cleanup_failed |= not operator_cleaned
            verified_revocations += int(operator_cleaned and operator_access is not None)
        if restricted_login_attempted:
            restricted_cleaned = _logout_if_session_exists(
                restricted_client,
                revocation_client=revocation_client,
                refresh_cookie_name=refresh_cookie_name,
                csrf_cookie_name=csrf_cookie_name,
                access_token=restricted_access,
            )
            cleanup_failed |= not restricted_cleaned
            verified_revocations += int(restricted_cleaned and restricted_access is not None)
        observations["logout_session_revocations_verified"] = verified_revocations
        operator_client.close()
        restricted_client.close()
        revocation_client.close()
        existing_cleanup = next(
            (item for item in checks if item.name == "session_cleanup"),
            None,
        )
        if existing_cleanup is None:
            checks.append(
                PostStartCheck(
                    "session_cleanup",
                    "failed" if cleanup_failed else "passed",
                    (
                        "logout_or_session_revocation_failed"
                        if cleanup_failed
                        else "authenticated_sessions_revoked_and_logged_out"
                    ),
                )
            )
        if cleanup_failed:
            stopped = True

    completed = {check.name for check in checks}
    for name in _CHECK_ORDER:
        if name not in completed:
            checks.append(PostStartCheck(name, "not_executed", "prior_check_failed"))
    checks.sort(key=lambda item: _CHECK_ORDER.index(item.name))
    overall: OverallStatus = (
        "passed" if not stopped and all(item.status == "passed" for item in checks) else "failed"
    )
    report = PostStartReport(
        schema_version=1,
        generated_at=_utc_now(),
        scope="authenticated-post-start-validation-no-business-mutations",
        executed=True,
        host_approved=host_approved,
        intended_host_claim=intended_host,
        production_readiness_claim=False,
        transport_scope=transport_scope,
        release_identifier=expected_release["identifier"],
        release_commit=expected_release["git_commit"],
        release_tag=expected_release["git_tag"],
        alembic_revision=expected_release["alembic_revision"],
        overall_status=overall,
        checks=tuple(checks),
        observations=observations,
    )
    report_path = _write_report(output_root, report) if output_root is not None else None
    return report, report_path


class _StopValidation(Exception):
    """Internal control flow after recording one safe failed check."""


def _login(
    client: httpx.Client,
    *,
    username: str,
    password: str,
) -> Mapping[str, Any]:
    return _request_json(
        client,
        "POST",
        "/auth/login",
        expected_status=200,
        expected_type=dict,
        json_body={"identifier": username, "password": password},
    )


def _logout_if_session_exists(
    client: httpx.Client,
    *,
    revocation_client: httpx.Client,
    refresh_cookie_name: str,
    csrf_cookie_name: str,
    access_token: str | None,
) -> bool:
    try:
        refresh = _optional_cookie_value(client, refresh_cookie_name)
        csrf = _optional_cookie_value(client, csrf_cookie_name)
        if refresh is None and csrf is None:
            return True
        if refresh is None or csrf is None:
            raise PostStartValidationError("Authentication session cookies are incomplete.")
        _expect_status(
            client,
            "POST",
            "/auth/logout",
            expected_status=204,
            headers={"X-CSRF-Token": csrf},
        )
        if access_token is not None:
            _expect_status(
                client,
                "GET",
                "/auth/me",
                expected_status=401,
                headers=_bearer(access_token),
            )
        _expect_refresh_rejected(
            revocation_client,
            refresh_cookie_name=refresh_cookie_name,
            csrf_cookie_name=csrf_cookie_name,
            refresh_token=refresh,
            csrf_token=csrf,
        )
    except (PostStartValidationError, httpx.HTTPError, ValueError):
        return False
    return True


def _expect_refresh_rejected(
    client: httpx.Client,
    *,
    refresh_cookie_name: str,
    csrf_cookie_name: str,
    refresh_token: str,
    csrf_token: str,
) -> None:
    _expect_status(
        client,
        "POST",
        "/auth/refresh",
        expected_status=401,
        headers={
            "X-CSRF-Token": csrf_token,
            "Cookie": (f"{refresh_cookie_name}={refresh_token}; {csrf_cookie_name}={csrf_token}"),
        },
    )


def _authenticated_identity(
    client: httpx.Client,
    access_token: str,
) -> Mapping[str, Any]:
    return _request_json(
        client,
        "GET",
        "/auth/me",
        expected_status=200,
        expected_type=dict,
        headers=_bearer(access_token),
    )


def _unread_count(client: httpx.Client, access_token: str) -> int:
    payload = _request_json(
        client,
        "GET",
        "/notifications/unread-count",
        expected_status=200,
        expected_type=dict,
        headers=_bearer(access_token),
    )
    return _nonnegative_int(payload.get("unread_count"))


def _request_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    expected_status: int,
    expected_type: type[dict] | type[list],
    headers: Mapping[str, str] | None = None,
    json_body: Mapping[str, Any] | None = None,
) -> Any:
    response = client.request(
        method,
        path,
        headers=dict(headers or {}),
        json=dict(json_body) if json_body is not None else None,
    )
    _validate_response(response, expected_status=expected_status)
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        raise PostStartValidationError("API returned invalid JSON.") from None
    if not isinstance(payload, expected_type):
        raise PostStartValidationError("API returned an unexpected JSON shape.")
    return payload


def _expect_status(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    expected_status: int,
    headers: Mapping[str, str] | None = None,
) -> None:
    response = client.request(method, path, headers=dict(headers or {}))
    _validate_response(response, expected_status=expected_status)


def _validate_response(response: httpx.Response, *, expected_status: int) -> None:
    if response.status_code != expected_status:
        raise PostStartValidationError("API returned an unexpected status.")
    if len(response.content) > _MAX_RESPONSE_BYTES:
        raise PostStartValidationError("API response exceeds the bounded smoke limit.")


def _require_release_identity(
    payload: Mapping[str, Any],
    expected: Mapping[str, str],
) -> None:
    release = payload.get("release")
    if not isinstance(release, Mapping):
        raise PostStartValidationError("Health response omits release identity.")
    if any(release.get(name) != value for name, value in expected.items()):
        raise PostStartValidationError(
            "Runtime release identity does not match the intended release."
        )


def _access_token(payload: Mapping[str, Any]) -> str:
    token = payload.get("access_token")
    if not isinstance(token, str) or not token or len(token) > 8192:
        raise PostStartValidationError("Authentication response has no bounded token.")
    return token


def _permission_set(identity: Mapping[str, Any]) -> frozenset[str]:
    permissions = identity.get("permissions")
    if not isinstance(permissions, list) or any(
        not isinstance(value, str) for value in permissions
    ):
        raise PostStartValidationError("Authenticated permission set is invalid.")
    return frozenset(permissions)


def _role(identity: Mapping[str, Any]) -> str:
    role = identity.get("role")
    if not isinstance(role, str) or not role or len(role) > 100:
        raise PostStartValidationError("Authenticated role is invalid.")
    return role


def _notification_ids(page: Mapping[str, Any]) -> frozenset[str]:
    items = page.get("items")
    if not isinstance(items, list):
        raise PostStartValidationError("Notification page has no item list.")
    ids: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
            raise PostStartValidationError("Notification page contains an invalid row.")
        identifier = item["id"]
        if identifier in ids:
            raise PostStartValidationError("Notification page contains a duplicate record.")
        ids.add(identifier)
    return frozenset(ids)


def _cookie_value(client: httpx.Client, name: str) -> str:
    value = _optional_cookie_value(client, name)
    if value is None:
        raise PostStartValidationError("Authentication session cookie is unavailable.")
    return value


def _optional_cookie_value(client: httpx.Client, name: str) -> str | None:
    values = [cookie.value for cookie in client.cookies.jar if cookie.name == name]
    if not values:
        return None
    if len(values) != 1 or not values[0] or len(values[0]) > 8192:
        raise PostStartValidationError("Authentication session cookie is unavailable.")
    return values[0]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PostStartValidationError("API aggregate count is invalid.")
    return value


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


def _validated_evidence_dir(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == _REPOSITORY_ROOT or resolved.is_relative_to(_REPOSITORY_ROOT):
        raise PostStartValidationError(
            "Raw post-start evidence must be written outside the repository."
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _write_report(root: Path, report: PostStartReport) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = root / f"pm9-post-start-validation-{stamp}.json"
    partial = destination.with_suffix(".partial")
    partial.write_text(
        json.dumps(
            report.as_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    os.replace(partial, destination)
    return destination


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _environment_value(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise PostStartValidationError(
            "A required smoke credential environment variable is unavailable."
        )
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment-file", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument(
        "--operator-username-env",
        default="PM9_SMOKE_OPERATOR_USERNAME",
    )
    parser.add_argument(
        "--operator-password-env",
        default="PM9_SMOKE_OPERATOR_PASSWORD",
    )
    parser.add_argument(
        "--restricted-username-env",
        default="PM9_SMOKE_RESTRICTED_USERNAME",
    )
    parser.add_argument(
        "--restricted-password-env",
        default="PM9_SMOKE_RESTRICTED_PASSWORD",
    )
    parser.add_argument("--intended-host", action="store_true")
    parser.add_argument("--allow-loopback-http", action="store_true")
    args = parser.parse_args(argv)
    configured = load_environment_file(args.environment_file)
    report, report_path = run_post_start_validation(
        base_url=configured.get("NEXT_PUBLIC_API_BASE_URL", ""),
        operator_username=_environment_value(args.operator_username_env),
        operator_password=_environment_value(args.operator_password_env),
        restricted_username=_environment_value(args.restricted_username_env),
        restricted_password=_environment_value(args.restricted_password_env),
        expected_release_identifier=configured.get("RELEASE_IDENTIFIER", ""),
        expected_release_commit=configured.get("RELEASE_GIT_COMMIT", ""),
        expected_release_tag=configured.get("RELEASE_GIT_TAG", ""),
        expected_alembic_revision=configured.get(
            "RELEASE_ALEMBIC_REVISION",
            "",
        ),
        manifest_path=args.manifest,
        refresh_cookie_name=configured.get(
            "REFRESH_COOKIE_NAME",
            "maintenance_refresh",
        ),
        csrf_cookie_name=configured.get("CSRF_COOKIE_NAME", "maintenance_csrf"),
        evidence_dir=args.evidence_dir,
        host_approved=configured.get("PILOT_HOST_APPROVED", "").lower() == "true",
        intended_host=args.intended_host,
        allow_loopback_http=args.allow_loopback_http,
    )
    print(
        json.dumps(
            {
                "executed": report.executed,
                "status": report.overall_status,
                "evidence_written": report_path is not None,
                "intended_host_claim": report.intended_host_claim,
                "production_readiness_claim": False,
            },
            sort_keys=True,
        )
    )
    return 0 if report.overall_status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

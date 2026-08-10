"""Ordered authenticated post-start workflow and unconditional session cleanup."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

from .contracts import (
    OverallStatus,
    PostStartCheck,
    PostStartReport,
    _CHECK_ORDER,
    _OPERATOR_PERMISSIONS,
    _RESTRICTED_FORBIDDEN_PERMISSIONS,
    _RESTRICTED_REQUIRED_PERMISSIONS,
)
from .evidence_storage import _utc_now, _validated_evidence_dir, _write_report
from .http_session import (
    _authenticated_identity,
    _expect_refresh_rejected,
    _expect_status,
    _login,
    _logout_if_session_exists,
    _request_json,
    _unread_count,
)
from .preflight import (
    PostStartValidationError,
    _DEFAULT_MANIFEST,
    _EXPECTED_JOB_TYPES,
    _prepare_post_start_validation,
)
from .response_contracts import (
    _access_token,
    _bearer,
    _cookie_value,
    _nonnegative_int,
    _notification_ids,
    _permission_set,
    _require_release_identity,
    _role,
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

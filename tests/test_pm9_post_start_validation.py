"""Infrastructure-free tests for the PM9 authenticated post-start validator."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.reliability.post_start_validation import (
    PostStartValidationError,
    run_post_start_validation,
)

_COMMIT = "b" * 40
_RELEASE = {
    "identifier": "product-milestone-9",
    "application_version": "0.1.0",
    "git_commit": _COMMIT,
    "git_tag": "product-milestone-9",
    "alembic_revision": "20260726_0008",
}
_OPERATOR_PERMISSIONS = [
    "assets:read",
    "tickets:read",
    "work_orders:read",
    "inventory:read",
    "analytics:read",
    "notifications:read",
    "job_operations:read",
]
_RESTRICTED_PERMISSIONS = [
    "assets:read",
    "tickets:read",
    "work_orders:read",
    "inventory:read",
    "notifications:read",
]
_JOBS = [
    {
        "job_type": name,
        "enabled": False,
    }
    for name in (
        "preventive_generation",
        "sla_escalation",
        "analytics_refresh",
        "inventory_reorder_detection",
    )
]


def _json_response(
    status_code: int,
    payload,
    *,
    headers: list[tuple[str, str]] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        headers=headers,
    )


def _transport(
    *,
    release_identifier: str = "product-milestone-9",
    shared_notification: bool = False,
    empty_notifications: bool = False,
    rotate_refresh_credentials: bool = True,
    revoke_on_logout: bool = True,
) -> httpx.MockTransport:
    rotated_operator = False
    revoked_access_tokens: set[str] = set()
    revoked_refresh_tokens: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal rotated_operator
        path = request.url.path
        method = request.method
        authorization = request.headers.get("Authorization", "")
        if path == "/auth/login" and method == "POST":
            payload = json.loads(request.content)
            identifier = payload["identifier"]
            if identifier == "pilot-operator":
                token = "operator-access"
                session = "operator-refresh"
                csrf = "operator-csrf"
            elif identifier == "pilot-restricted":
                token = "restricted-access"
                session = "restricted-refresh"
                csrf = "restricted-csrf"
            else:
                return _json_response(401, {"detail": "invalid"})
            return _json_response(
                200,
                {"access_token": token},
                headers=[
                    (
                        "Set-Cookie",
                        f"maintenance_refresh={session}; Path=/auth; Secure; HttpOnly",
                    ),
                    (
                        "Set-Cookie",
                        f"maintenance_csrf={csrf}; Path=/; Secure",
                    ),
                ],
            )
        if path == "/auth/refresh" and method == "POST":
            cookie = request.headers.get("Cookie", "")
            csrf = request.headers.get("X-CSRF-Token")
            if "maintenance_refresh=operator-refresh" in cookie:
                if csrf != "operator-csrf" or rotated_operator:
                    return _json_response(401, {"detail": "revoked"})
                rotated_operator = True
                revoked_access_tokens.add("Bearer operator-access")
                revoked_refresh_tokens.add("operator-refresh")
                if not rotate_refresh_credentials:
                    return _json_response(
                        200,
                        {"access_token": "operator-access-refreshed"},
                    )
                return _json_response(
                    200,
                    {"access_token": "operator-access-refreshed"},
                    headers=[
                        (
                            "Set-Cookie",
                            (
                                "maintenance_refresh=operator-refresh-rotated; "
                                "Path=/auth; Secure; HttpOnly"
                            ),
                        ),
                        (
                            "Set-Cookie",
                            "maintenance_csrf=operator-csrf-rotated; Path=/; Secure",
                        ),
                    ],
                )
            if "maintenance_refresh=operator-refresh-rotated" in cookie:
                if (
                    csrf != "operator-csrf-rotated"
                    or "operator-refresh-rotated" in revoked_refresh_tokens
                ):
                    return _json_response(401, {"detail": "revoked"})
            elif "maintenance_refresh=restricted-refresh" in cookie:
                if csrf != "restricted-csrf" or "restricted-refresh" in revoked_refresh_tokens:
                    return _json_response(401, {"detail": "revoked"})
            else:
                return _json_response(403, {"detail": "csrf"})
            return _json_response(409, {"detail": "unexpected active replay"})
        if path == "/auth/logout" and method == "POST":
            if not request.headers.get("X-CSRF-Token"):
                return _json_response(403, {"detail": "csrf"})
            cookie = request.headers.get("Cookie", "")
            if revoke_on_logout and "maintenance_refresh=operator-refresh-rotated" in cookie:
                revoked_refresh_tokens.add("operator-refresh-rotated")
                revoked_access_tokens.add("Bearer operator-access-refreshed")
            elif revoke_on_logout and "maintenance_refresh=restricted-refresh" in cookie:
                revoked_refresh_tokens.add("restricted-refresh")
                revoked_access_tokens.add("Bearer restricted-access")
            return httpx.Response(204)
        if path == "/auth/me":
            if not authorization:
                return _json_response(401, {"detail": "unauthorized"})
            if authorization in revoked_access_tokens:
                return _json_response(401, {"detail": "revoked"})
            if authorization in {
                "Bearer operator-access",
                "Bearer operator-access-refreshed",
            }:
                return _json_response(
                    200,
                    {
                        "role": "administrator",
                        "permissions": _OPERATOR_PERMISSIONS,
                    },
                )
            if authorization == "Bearer restricted-access":
                return _json_response(
                    200,
                    {
                        "role": "helpdesk",
                        "permissions": _RESTRICTED_PERMISSIONS,
                    },
                )
            return _json_response(401, {"detail": "unauthorized"})
        if path == "/health/live":
            return _json_response(
                200,
                {
                    "status": "alive",
                    "release": {**_RELEASE, "identifier": release_identifier},
                },
            )
        if path == "/health/ready":
            return _json_response(
                200,
                {
                    "status": "ready",
                    "database_ready": True,
                    "worker_ready": True,
                    "release": {**_RELEASE, "identifier": release_identifier},
                },
            )
        if path == "/health/worker":
            return _json_response(200, {"status": "ready", "ready": True})
        if path == "/operations/jobs":
            if authorization == "Bearer restricted-access":
                return _json_response(403, {"detail": "forbidden"})
            return _json_response(200, _JOBS)
        if path == "/operations/metrics":
            return _json_response(
                200,
                {
                    "dead_letter_job_count": 0,
                    "dead_letter_outbox_count": 0,
                },
            )
        if path in {
            "/assets/catalog",
            "/ticket-queues/all",
            "/work-orders",
            "/inventory/balances",
        }:
            return _json_response(200, {"items": [{}], "total": 1})
        if path == "/health":
            return _json_response(
                200,
                {
                    "status": "ok",
                    "raw_data_available": True,
                    "analytics_available": True,
                },
            )
        if path == "/summary":
            if authorization == "Bearer restricted-access":
                return _json_response(403, {"detail": "forbidden"})
            return _json_response(
                200,
                {
                    "total_assets": 20,
                    "total_records": 100,
                },
            )
        if path == "/notifications":
            restricted = authorization == "Bearer restricted-access"
            if empty_notifications:
                identifier = None
            elif shared_notification:
                identifier = "00000000-0000-0000-0000-000000000001"
            else:
                identifier = (
                    "00000000-0000-0000-0000-000000000002"
                    if restricted
                    else "00000000-0000-0000-0000-000000000001"
                )
            items = [] if identifier is None else [{"id": identifier}]
            return _json_response(
                200,
                {
                    "items": items,
                    "page": 1,
                    "page_size": 100,
                    "total": len(items),
                },
            )
        if path == "/notifications/unread-count":
            return _json_response(
                200,
                {"unread_count": 0 if empty_notifications else 1},
            )
        raise AssertionError(f"Unexpected request: {method} {path}")

    return httpx.MockTransport(handler)


def _run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    transport: httpx.MockTransport,
    evidence_dir: Path | None = None,
):
    monkeypatch.setenv("PM9_ALLOW_POST_START_VALIDATION", "true")
    return run_post_start_validation(
        base_url="https://pilot.example.test",
        operator_username="pilot-operator",
        operator_password="operator-secret-value",
        restricted_username="pilot-restricted",
        restricted_password="restricted-secret-value",
        expected_release_identifier="product-milestone-9",
        expected_release_commit=_COMMIT,
        expected_release_tag="product-milestone-9",
        expected_alembic_revision="20260726_0008",
        evidence_dir=evidence_dir,
        host_approved=True,
        intended_host=True,
        transport=transport,
    )


def test_post_start_validation_covers_release_auth_rbac_jobs_data_and_notifications(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report, report_path = _run(
        monkeypatch,
        transport=_transport(),
        evidence_dir=tmp_path / "evidence",
    )

    assert report.overall_status == "passed"
    assert report.intended_host_claim is True
    assert report.production_readiness_claim is False
    assert all(check.status == "passed" for check in report.checks)
    assert report.observations["operator_role"] == "administrator"
    assert report.observations["restricted_role"] == "helpdesk"
    assert report.observations["refresh_rotation_old_session_rejected"] is True
    assert report.observations["logout_session_revocations_verified"] == 2
    assert set(report.observations["business_record_counts"]) == {
        "assets",
        "tickets",
        "work_orders",
        "inventory_balances",
    }
    assert report_path is not None
    persisted = report_path.read_text(encoding="utf-8")
    assert "operator-secret-value" not in persisted
    assert "restricted-secret-value" not in persisted
    assert "pilot-operator" not in persisted
    assert "pilot-restricted" not in persisted


def test_release_mismatch_stops_before_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report, _ = _run(
        monkeypatch,
        transport=_transport(release_identifier="wrong-release"),
    )

    by_name = {check.name: check for check in report.checks}
    assert report.overall_status == "failed"
    assert by_name["release_and_readiness"].status == "failed"
    assert by_name["operator_authentication"].status == "not_executed"
    assert by_name["session_cleanup"].status == "passed"


@pytest.mark.parametrize(
    ("shared_notification", "empty_notifications"),
    [(True, False), (False, True)],
)
def test_notification_gate_requires_nonempty_owner_isolated_evidence(
    monkeypatch: pytest.MonkeyPatch,
    shared_notification: bool,
    empty_notifications: bool,
) -> None:
    report, _ = _run(
        monkeypatch,
        transport=_transport(
            shared_notification=shared_notification,
            empty_notifications=empty_notifications,
        ),
    )

    notification = next(
        check for check in report.checks if check.name == "notification_owner_isolation"
    )
    assert report.overall_status == "failed"
    assert notification.status == "failed"
    assert report.checks[-1].name == "session_cleanup"
    assert report.checks[-1].status == "passed"


def test_refresh_gate_requires_new_credentials_and_rejects_the_old_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report, _ = _run(
        monkeypatch,
        transport=_transport(rotate_refresh_credentials=False),
    )

    by_name = {check.name: check for check in report.checks}
    assert report.overall_status == "failed"
    assert by_name["operator_session_refresh"].status == "failed"
    assert report.observations["refresh_rotation_old_session_rejected"] is False


def test_cleanup_gate_requires_logout_to_revoke_access_and_refresh_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report, _ = _run(
        monkeypatch,
        transport=_transport(revoke_on_logout=False),
    )

    by_name = {check.name: check for check in report.checks}
    assert report.overall_status == "failed"
    assert by_name["session_cleanup"].status == "failed"
    assert report.observations["logout_session_revocations_verified"] == 0


def test_execution_and_transport_guards_precede_network_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PM9_ALLOW_POST_START_VALIDATION", raising=False)
    with pytest.raises(PostStartValidationError, match="PM9_ALLOW"):
        run_post_start_validation(
            base_url="https://pilot.example.test",
            operator_username="operator",
            operator_password="operator-password",
            restricted_username="restricted",
            restricted_password="restricted-password",
            expected_release_identifier="product-milestone-9",
            expected_release_commit=_COMMIT,
            expected_release_tag="product-milestone-9",
            expected_alembic_revision="20260726_0008",
            transport=_transport(),
        )

    monkeypatch.setenv("PM9_ALLOW_POST_START_VALIDATION", "true")
    with pytest.raises(PostStartValidationError, match="requires HTTPS"):
        run_post_start_validation(
            base_url="http://pilot.example.test",
            operator_username="operator",
            operator_password="operator-password",
            restricted_username="restricted",
            restricted_password="restricted-password",
            expected_release_identifier="product-milestone-9",
            expected_release_commit=_COMMIT,
            expected_release_tag="product-milestone-9",
            expected_alembic_revision="20260726_0008",
            transport=_transport(),
        )

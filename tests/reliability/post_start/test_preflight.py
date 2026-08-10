"""Behavior contract for no-network post-start preflight."""

import json
from inspect import signature
from pathlib import Path

import httpx
import pytest

from src.reliability import post_start_validation
from src.reliability.post_start import preflight as post_start_preflight
from src.reliability.post_start_validation import (
    PostStartValidationError,
    _PostStartPreflight,
    _load_manifest_expectations,
    _prepare_post_start_validation,
    _required_text,
    _validate_credentials,
    _validated_origin,
    validate_post_start_preconditions,
)


EXPECTED_JOBS = (
    "preventive_generation",
    "sla_escalation",
    "analytics_refresh",
    "inventory_reorder_detection",
)


def _manifest(path: Path, *, jobs: list[dict[str, object]] | None = None) -> Path:
    payload = {
        "versions": {"application": "0.1.0"},
        "scheduled_jobs": jobs
        if jobs is not None
        else [
            {"job_type": name, "enabled": index % 2 == 0}
            for index, name in enumerate(EXPECTED_JOBS)
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _arguments(manifest_path: Path) -> dict[str, object]:
    return {
        "base_url": "https://pilot.example.test",
        "operator_username": "operator",
        "operator_password": "operator-password",
        "restricted_username": "viewer",
        "restricted_password": "viewer-password",
        "expected_release_identifier": "pilot-2026-08",
        "expected_release_commit": "a" * 40,
        "expected_release_tag": "v0.1.0",
        "expected_alembic_revision": "20260726_0008",
        "manifest_path": manifest_path,
        "refresh_cookie_name": "maintenance_refresh",
        "csrf_cookie_name": "maintenance_csrf",
        "host_approved": False,
        "intended_host": False,
        "allow_loopback_http": False,
        "timeout_seconds": 10.0,
    }


def test_post_start_preflight_signatures_and_historical_bindings_are_stable() -> None:
    assert list(signature(validate_post_start_preconditions).parameters) == [
        "base_url",
        "operator_username",
        "operator_password",
        "restricted_username",
        "restricted_password",
        "expected_release_identifier",
        "expected_release_commit",
        "expected_release_tag",
        "expected_alembic_revision",
        "manifest_path",
        "refresh_cookie_name",
        "csrf_cookie_name",
        "host_approved",
        "intended_host",
        "allow_loopback_http",
        "timeout_seconds",
    ]
    assert list(signature(_prepare_post_start_validation).parameters) == [
        "base_url",
        "operator_username",
        "operator_password",
        "restricted_username",
        "restricted_password",
        "expected_release_identifier",
        "expected_release_commit",
        "expected_release_tag",
        "expected_alembic_revision",
        "manifest_path",
        "refresh_cookie_name",
        "csrf_cookie_name",
        "host_approved",
        "intended_host",
        "allow_loopback_http",
        "timeout_seconds",
    ]
    for name, value in (
        ("PostStartValidationError", PostStartValidationError),
        ("_PostStartPreflight", _PostStartPreflight),
        ("validate_post_start_preconditions", validate_post_start_preconditions),
        ("_prepare_post_start_validation", _prepare_post_start_validation),
        ("_load_manifest_expectations", _load_manifest_expectations),
        ("_validate_credentials", _validate_credentials),
        ("_validated_origin", _validated_origin),
        ("_required_text", _required_text),
    ):
        assert getattr(post_start_validation, name) is value


def test_post_start_preflight_owner_is_the_historical_facade_binding() -> None:
    for name in (
        "PostStartValidationError",
        "_PostStartPreflight",
        "validate_post_start_preconditions",
        "_prepare_post_start_validation",
        "_load_manifest_expectations",
        "_validate_credentials",
        "_validated_origin",
        "_required_text",
    ):
        assert getattr(post_start_validation, name) is getattr(post_start_preflight, name)


def test_execution_opt_in_is_the_first_fail_closed_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PM9_ALLOW_POST_START_VALIDATION", raising=False)
    arguments = _arguments(tmp_path / "missing.json")
    arguments["base_url"] = "invalid"

    with pytest.raises(
        PostStartValidationError,
        match="^Execution requires PM9_ALLOW_POST_START_VALIDATION=true[.]$",
    ):
        _prepare_post_start_validation(**arguments)  # type: ignore[arg-type]


def test_successful_preflight_is_deterministic_strips_release_text_and_has_no_http(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_POST_START_VALIDATION", "true")
    manifest = _manifest(tmp_path / "manifest.json")
    arguments = _arguments(manifest)
    arguments["expected_release_identifier"] = "  pilot-2026-08  "

    def forbidden_client(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("preflight must not construct an HTTP client")

    monkeypatch.setattr(httpx, "Client", forbidden_client)
    preflight = _prepare_post_start_validation(**arguments)  # type: ignore[arg-type]

    assert preflight == _PostStartPreflight(
        transport_scope="https",
        expected_jobs={name: index % 2 == 0 for index, name in enumerate(EXPECTED_JOBS)},
        expected_release={
            "identifier": "pilot-2026-08",
            "application_version": "0.1.0",
            "git_commit": "a" * 40,
            "git_tag": "v0.1.0",
            "alembic_revision": "20260726_0008",
        },
    )
    assert validate_post_start_preconditions(**arguments) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("base_url", "allow_loopback", "http_opt_in", "expected"),
    [
        ("https://pilot.example.test", False, False, "https"),
        ("http://127.0.0.1:8000", True, True, "loopback_http_test"),
        ("http://localhost", True, True, "loopback_http_test"),
    ],
)
def test_origin_validation_accepts_only_explicit_transport_scopes(
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
    allow_loopback: bool,
    http_opt_in: bool,
    expected: str,
) -> None:
    if http_opt_in:
        monkeypatch.setenv("PM9_ALLOW_HTTP_TEST_SMOKE", "true")
    else:
        monkeypatch.delenv("PM9_ALLOW_HTTP_TEST_SMOKE", raising=False)
    assert _validated_origin(base_url, allow_loopback_http=allow_loopback) == expected


@pytest.mark.parametrize(
    "base_url",
    [
        "http://pilot.example.test",
        "https://user:password@pilot.example.test",
        "https://pilot.example.test/path",
        "https://pilot.example.test?query=1",
        "https://pilot.example.test/#fragment",
        "not-a-url",
    ],
)
def test_origin_validation_rejects_external_http_credentials_and_non_origins(
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_HTTP_TEST_SMOKE", "true")
    with pytest.raises(PostStartValidationError):
        _validated_origin(base_url, allow_loopback_http=True)


def test_loopback_http_requires_both_test_opt_ins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PM9_ALLOW_HTTP_TEST_SMOKE", raising=False)
    with pytest.raises(
        PostStartValidationError,
        match="^Post-start validation requires HTTPS; loopback HTTP needs both test opt-ins[.]$",
    ):
        _validated_origin("http://127.0.0.1:8000", allow_loopback_http=True)
    monkeypatch.setenv("PM9_ALLOW_HTTP_TEST_SMOKE", "true")
    with pytest.raises(PostStartValidationError):
        _validated_origin("http://127.0.0.1:8000", allow_loopback_http=False)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"operator_username": ""}, "Both bounded smoke-account credentials are required."),
        ({"operator_password": "x" * 257}, "Both bounded smoke-account credentials are required."),
        (
            {"restricted_username": "OPERATOR"},
            "Operator and restricted smoke accounts must be different.",
        ),
    ],
)
def test_credential_validation_preserves_bounds_and_casefold_separation(
    changes: dict[str, str],
    message: str,
) -> None:
    values = {
        "operator_username": "operator",
        "operator_password": "operator-password",
        "restricted_username": "viewer",
        "restricted_password": "viewer-password",
    }
    values.update(changes)
    with pytest.raises(PostStartValidationError, match=f"^{message}$"):
        _validate_credentials(**values)


def test_host_cookie_text_and_timeout_boundaries_preserve_validation_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_POST_START_VALIDATION", "true")
    manifest = _manifest(tmp_path / "manifest.json")
    arguments = _arguments(manifest)
    arguments.update({"intended_host": True, "host_approved": False})
    with pytest.raises(
        PostStartValidationError,
        match="^An intended-host claim requires explicit pilot-host approval[.]$",
    ):
        _prepare_post_start_validation(**arguments)  # type: ignore[arg-type]

    arguments = _arguments(manifest)
    arguments["csrf_cookie_name"] = "maintenance_refresh"
    with pytest.raises(
        PostStartValidationError,
        match="^Refresh and CSRF cookie names must be distinct and valid[.]$",
    ):
        _prepare_post_start_validation(**arguments)  # type: ignore[arg-type]

    arguments = _arguments(manifest)
    arguments["timeout_seconds"] = 0
    with pytest.raises(
        PostStartValidationError,
        match="^Post-start request timeout must be between 1 and 60 seconds[.]$",
    ):
        _prepare_post_start_validation(**arguments)  # type: ignore[arg-type]

    assert _required_text("  release  ", "release") == "release"
    with pytest.raises(PostStartValidationError, match="^Expected release is invalid[.]$"):
        _required_text(" " * 4, "release")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "Deployment manifest root is invalid."),
        ({}, "Deployment manifest lacks jobs or versions."),
        ({"scheduled_jobs": [1], "versions": {}}, "Manifest scheduled-job row is invalid."),
        (
            {
                "scheduled_jobs": [
                    {"job_type": "preventive_generation", "enabled": True},
                    {"job_type": "preventive_generation", "enabled": False},
                ],
                "versions": {"application": "0.1.0"},
            },
            "Manifest scheduled-job catalog is invalid.",
        ),
        (
            {
                "scheduled_jobs": [{"job_type": "arbitrary", "enabled": True}],
                "versions": {"application": "0.1.0"},
            },
            "Manifest scheduled-job catalog is unsupported.",
        ),
        (
            {
                "scheduled_jobs": [{"job_type": name, "enabled": True} for name in EXPECTED_JOBS],
                "versions": {"application": ""},
            },
            "Manifest application version is unavailable.",
        ),
    ],
)
def test_manifest_expectations_fail_closed_with_exact_error_boundaries(
    tmp_path: Path,
    payload: object,
    message: str,
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PostStartValidationError, match=f"^{message}$"):
        _load_manifest_expectations(path)


def test_missing_and_malformed_manifest_share_the_safe_outer_error(tmp_path: Path) -> None:
    with pytest.raises(
        PostStartValidationError,
        match="^Deployment manifest is unavailable or invalid[.]$",
    ):
        _load_manifest_expectations(tmp_path / "missing.json")
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(
        PostStartValidationError,
        match="^Deployment manifest is unavailable or invalid[.]$",
    ):
        _load_manifest_expectations(malformed)

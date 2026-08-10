"""Runtime-environment tests grouped by validation capability."""

from __future__ import annotations

from ._runtime_environment_scenarios import (
    _finding,
    _findings,
    _only,
    _ready_environment,
    _ready_manifest,
    _validate_environment,
    contract_environment_validator,
    deepcopy,
    pytest,
    signature,
)


def test_ready_environment_is_deterministic_immutable_and_has_stable_signature() -> None:
    manifest = _ready_manifest()
    environment = _ready_environment()
    original_manifest = deepcopy(manifest)
    original_environment = dict(environment)

    first_result, first = _findings(manifest, environment)
    second_result, second = _findings(manifest, environment)

    assert first_result is None
    assert second_result is None
    assert first == []
    assert second == first
    assert manifest == original_manifest
    assert environment == original_environment
    assert list(signature(_validate_environment).parameters) == [
        "manifest",
        "environment",
        "repository_root",
        "findings",
    ]
    assert contract_environment_validator is _validate_environment


def test_required_environment_names_are_sorted_and_duplicate_rows_collapse() -> None:
    manifest = _ready_manifest()
    manifest["required_environment_variables"] = [
        {"name": "ZED", "secret": False},
        42,
        {"name": "ALPHA", "secret": False},
        {"name": "ZED", "secret": True},
        {"name": 1, "secret": False},
    ]
    environment = _ready_environment()
    environment.pop("ALPHA", None)
    environment.pop("ZED", None)

    assert _only(_findings(manifest, environment)[1], {"environment_variable_missing"}) == [
        _finding(
            "environment_variable_missing",
            "environment.ALPHA",
            "Thiếu environment variable bắt buộc: ALPHA.",
        ),
        _finding(
            "environment_variable_missing",
            "environment.ZED",
            "Thiếu environment variable bắt buộc: ZED.",
        ),
    ]


@pytest.mark.parametrize("value", ["", "TBD", "replace-with-value"])
def test_required_environment_missing_and_placeholder_are_distinct(value: str) -> None:
    environment = _ready_environment()
    environment["EMBEDDING_MODEL_NAME"] = value

    expected = (
        _finding(
            "environment_variable_missing",
            "environment.EMBEDDING_MODEL_NAME",
            "Thiếu environment variable bắt buộc: EMBEDDING_MODEL_NAME.",
        )
        if value == ""
        else _finding(
            "environment_placeholder",
            "environment.EMBEDDING_MODEL_NAME",
            "Environment variable EMBEDDING_MODEL_NAME vẫn chứa placeholder.",
        )
    )
    assert _only(
        _findings(environment=environment)[1],
        {"environment_variable_missing", "environment_placeholder"},
    ) == [expected]


def test_missing_declared_secret_has_both_presence_and_secret_findings() -> None:
    environment = _ready_environment()
    environment["DATABASE_URL"] = ""

    assert _only(
        _findings(environment=environment)[1],
        {"environment_variable_missing", "pilot_secret_missing"},
    ) == [
        _finding(
            "environment_variable_missing",
            "environment.DATABASE_URL",
            "Thiếu environment variable bắt buộc: DATABASE_URL.",
        ),
        _finding(
            "pilot_secret_missing",
            "environment.DATABASE_URL",
            "Pilot secret DATABASE_URL chưa được inject.",
        ),
    ]


def test_pilot_mode_storage_and_secure_cookie_findings_keep_order() -> None:
    environment = _ready_environment()
    environment.update(APP_ENVIRONMENT="PILOT", STORAGE_BACKEND="csv", AUTH_COOKIE_SECURE="0")

    assert _only(
        _findings(environment=environment)[1],
        {"pilot_environment_required", "postgresql_storage_required", "secure_cookie_required"},
    ) == [
        _finding(
            "pilot_environment_required",
            "environment.APP_ENVIRONMENT",
            "APP_ENVIRONMENT phải là pilot.",
        ),
        _finding(
            "postgresql_storage_required",
            "environment.STORAGE_BACKEND",
            "Pilot phải dùng PostgreSQL primary storage.",
        ),
        _finding(
            "secure_cookie_required",
            "environment.AUTH_COOKIE_SECURE",
            "Pilot phải bật secure refresh cookie.",
        ),
    ]


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "on"])
def test_secure_cookie_uses_current_truthy_normalization(value: str) -> None:
    environment = _ready_environment()
    environment["AUTH_COOKIE_SECURE"] = value

    assert "secure_cookie_required" not in {
        finding.code for finding in _findings(environment=environment)[1]
    }


def test_signing_secret_and_previous_rotation_findings_keep_order() -> None:
    environment = _ready_environment()
    environment["TOKEN_SIGNING_SECRET"] = "short"
    environment["TOKEN_SIGNING_PREVIOUS_SECRET"] = "short"

    assert _only(
        _findings(environment=environment)[1],
        {"pilot_signing_secret_invalid", "previous_signing_secret_invalid"},
    ) == [
        _finding(
            "pilot_signing_secret_invalid",
            "environment.TOKEN_SIGNING_SECRET",
            "Pilot signing secret thiếu độ dài hoặc vẫn là placeholder.",
        ),
        _finding(
            "previous_signing_secret_invalid",
            "environment.TOKEN_SIGNING_PREVIOUS_SECRET",
            "Previous signing secret không hợp lệ cho rotation overlap.",
        ),
    ]


def test_long_placeholder_previous_secret_is_currently_accepted() -> None:
    environment = _ready_environment()
    environment["TOKEN_SIGNING_PREVIOUS_SECRET"] = "TBD_" + "x" * 40

    assert "previous_signing_secret_invalid" not in {
        finding.code for finding in _findings(environment=environment)[1]
    }


def test_database_defaults_and_short_password_accumulate_in_loop_order() -> None:
    environment = _ready_environment()
    environment.update(
        POSTGRES_USER="maintenance", POSTGRES_PASSWORD="maintenance", POSTGRES_DB="TBD"
    )

    assert _only(
        _findings(environment=environment)[1],
        {"development_database_default", "database_password_too_short"},
    ) == [
        _finding(
            "development_database_default",
            "environment.POSTGRES_USER",
            "POSTGRES_USER vẫn dùng development default hoặc placeholder.",
        ),
        _finding(
            "development_database_default",
            "environment.POSTGRES_PASSWORD",
            "POSTGRES_PASSWORD vẫn dùng development default hoặc placeholder.",
        ),
        _finding(
            "development_database_default",
            "environment.POSTGRES_DB",
            "POSTGRES_DB vẫn dùng development default hoặc placeholder.",
        ),
        _finding(
            "database_password_too_short",
            "environment.POSTGRES_PASSWORD",
            "Pilot database password chưa đạt độ dài tối thiểu của contract.",
        ),
    ]


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@postgres/db",
        "postgresql+psycopg://postgres/db",
        "postgresql+psycopg://u:p@postgres:bad/db",
        "not-a-url",
    ],
)
def test_database_url_structural_failures_have_one_exact_finding(url: str) -> None:
    environment = _ready_environment()
    environment["DATABASE_URL"] = url

    assert _only(_findings(environment=environment)[1], {"database_url_invalid"}) == [
        _finding(
            "database_url_invalid",
            "environment.DATABASE_URL",
            "DATABASE_URL pilot không đủ PostgreSQL connection components.",
        )
    ]


def test_development_database_url_precedes_environment_mismatch() -> None:
    environment = _ready_environment()
    environment["DATABASE_URL"] = (
        "postgresql+psycopg://maintenance:maintenance@other:1234/maintenance"
    )

    assert _only(
        _findings(environment=environment)[1],
        {"development_database_url", "database_environment_mismatch"},
    ) == [
        _finding(
            "development_database_url",
            "environment.DATABASE_URL",
            "DATABASE_URL vẫn dùng development default hoặc placeholder.",
        )
    ]


def test_database_url_decoding_and_exact_service_match_are_preserved() -> None:
    environment = _ready_environment()
    environment.update(
        POSTGRES_USER="pilot user",
        POSTGRES_PASSWORD="password with space 123",
        POSTGRES_DB="pilot db",
    )
    environment["DATABASE_URL"] = (
        "postgresql+psycopg://pilot%20user:password%20with%20space%20123@postgres:5432/pilot%20db"
    )

    assert not {
        "database_url_invalid",
        "development_database_url",
        "database_environment_mismatch",
    } & {finding.code for finding in _findings(environment=environment)[1]}


def test_database_url_service_mismatch_is_terminal_branch() -> None:
    environment = _ready_environment()
    environment["DATABASE_URL"] = environment["DATABASE_URL"].replace("@postgres:5432", "@db:5433")

    assert _only(_findings(environment=environment)[1], {"database_environment_mismatch"}) == [
        _finding(
            "database_environment_mismatch",
            "environment.DATABASE_URL",
            "DATABASE_URL phải khớp PostgreSQL service, user, password và database đã khai báo.",
        )
    ]


def test_network_development_defaults_follow_declared_name_order() -> None:
    environment = _ready_environment()
    environment["CORS_ALLOWED_ORIGINS"] = "*,https://localhost"
    environment["TRUSTED_HOSTS"] = "testserver,127.0.0.1"

    assert _only(_findings(environment=environment)[1], {"development_network_default"})[:2] == [
        _finding(
            "development_network_default",
            "environment.CORS_ALLOWED_ORIGINS",
            "CORS_ALLOWED_ORIGINS vẫn dùng wildcard hoặc development host.",
        ),
        _finding(
            "development_network_default",
            "environment.TRUSTED_HOSTS",
            "TRUSTED_HOSTS vẫn dùng wildcard hoặc development host.",
        ),
    ]

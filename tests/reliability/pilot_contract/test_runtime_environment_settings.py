"""Runtime-environment tests grouped by validation capability."""

from __future__ import annotations

from ._runtime_environment_scenarios import (
    _finding,
    _findings,
    _only,
    _ready_environment,
    pytest,
)


def test_runtime_integer_mismatch_order_follows_section_and_mapping_order() -> None:
    environment = _ready_environment()
    for name in (
        "WORKER_POLL_INTERVAL_SECONDS",
        "DATABASE_POOL_SIZE",
        "OPERATIONAL_OUTBOX_AGE_ALERT_SECONDS",
    ):
        environment[name] = "wrong"

    assert _only(_findings(environment=environment)[1], {"runtime_environment_mismatch"})[:3] == [
        _finding(
            "runtime_environment_mismatch",
            "environment.WORKER_POLL_INTERVAL_SECONDS",
            "WORKER_POLL_INTERVAL_SECONDS phải là số nguyên khớp deployment manifest.",
        ),
        _finding(
            "runtime_environment_mismatch",
            "environment.DATABASE_POOL_SIZE",
            "DATABASE_POOL_SIZE phải là số nguyên khớp deployment manifest.",
        ),
        _finding(
            "runtime_environment_mismatch",
            "environment.OPERATIONAL_OUTBOX_AGE_ALERT_SECONDS",
            "OPERATIONAL_OUTBOX_AGE_ALERT_SECONDS phải là số nguyên khớp deployment manifest.",
        ),
    ]


@pytest.mark.parametrize("value", ["0", "61", "not-int"])
def test_bounded_integer_out_of_range_and_parse_failure_share_finding(value: str) -> None:
    environment = _ready_environment()
    environment["ACCESS_TOKEN_LIFETIME_MINUTES"] = value

    assert _only(_findings(environment=environment)[1], {"runtime_environment_out_of_range"}) == [
        _finding(
            "runtime_environment_out_of_range",
            "environment.ACCESS_TOKEN_LIFETIME_MINUTES",
            "ACCESS_TOKEN_LIFETIME_MINUTES phải là số nguyên nằm trong giới hạn pilot.",
        )
    ]


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ATTACHMENT_STORAGE_BACKEND", "postgresql"),
        ("AUTH_COOKIE_SAMESITE", "LAX"),
        ("LOG_LEVEL", "info"),
    ],
)
def test_runtime_allow_lists_are_exact(name: str, value: str) -> None:
    environment = _ready_environment()
    environment[name] = value

    assert _only(_findings(environment=environment)[1], {"environment_value_unsupported"}) == [
        _finding(
            "environment_value_unsupported",
            f"environment.{name}",
            f"{name} có giá trị ngoài allow-list.",
        )
    ]


@pytest.mark.parametrize("value", ["bad name", "bad.name", "x" * 65, ""])
def test_cookie_name_validation_and_empty_skip(value: str) -> None:
    environment = _ready_environment()
    environment["REFRESH_COOKIE_NAME"] = value

    findings = _only(_findings(environment=environment)[1], {"cookie_name_invalid"})
    if value:
        assert findings == [
            _finding(
                "cookie_name_invalid",
                "environment.REFRESH_COOKIE_NAME",
                "REFRESH_COOKIE_NAME không phải tên cookie an toàn.",
            )
        ]
    else:
        assert findings == []


def test_declared_port_environment_mismatch_and_bind_validation_keep_row_order() -> None:
    environment = _ready_environment()
    environment["PILOT_API_PORT"] = "9000"
    environment["PILOT_API_BIND_ADDRESS"] = "http://0.0.0.0/path"

    assert _only(
        _findings(environment=environment)[1],
        {"runtime_environment_mismatch", "bind_address_invalid"},
    )[-2:] == [
        _finding(
            "runtime_environment_mismatch",
            "environment.PILOT_API_PORT",
            "PILOT_API_PORT phải là số nguyên khớp deployment manifest.",
        ),
        _finding(
            "bind_address_invalid",
            "environment.PILOT_API_BIND_ADDRESS",
            "PILOT_API_BIND_ADDRESS không phải bind address hợp lệ.",
        ),
    ]


@pytest.mark.parametrize("value", ["ab", " host", "host/path", "host name", "x" * 129])
def test_host_identifier_uses_exact_opaque_identifier_pattern(value: str) -> None:
    environment = _ready_environment()
    environment["PILOT_HOST_IDENTIFIER"] = value

    assert _only(_findings(environment=environment)[1], {"pilot_host_identifier_invalid"}) == [
        _finding(
            "pilot_host_identifier_invalid",
            "environment.PILOT_HOST_IDENTIFIER",
            "PILOT_HOST_IDENTIFIER phải là opaque identifier, không phải đường dẫn.",
        )
    ]

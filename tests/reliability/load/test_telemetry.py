"""Behavior contract for read-only load API telemetry observation."""

from inspect import signature

import httpx

from src.reliability import load_harness
from src.reliability.load import telemetry as load_telemetry
from src.reliability.load_harness import (
    _ApiTelemetry,
    _collect_api_telemetry,
    _execution_status_counts,
    _outbox_metrics,
    _readiness_status,
    _record_telemetry_checks,
    _response_json,
    _safe_json,
    _telemetry_response,
    _valid_operations_metrics_payload,
    _worker_ready_status,
    _worker_stale_status,
)


def test_load_telemetry_signatures_and_historical_bindings_are_stable() -> None:
    expected = {
        "_ApiTelemetry": ["readiness", "worker_ready", "operations_metrics", "missing"],
        "_collect_api_telemetry": ["client", "headers", "timeout_seconds"],
        "_telemetry_response": ["client", "path", "headers", "timeout_seconds"],
        "_record_telemetry_checks": ["telemetry", "readiness_checks", "worker_unhealthy_checks"],
        "_valid_operations_metrics_payload": ["value"],
        "_safe_json": ["response"],
        "_response_json": ["response"],
        "_readiness_status": ["payload"],
        "_worker_ready_status": ["payload"],
        "_worker_stale_status": ["payload"],
        "_outbox_metrics": ["metrics"],
        "_execution_status_counts": ["page"],
    }
    for name, parameters in expected.items():
        value = globals()[name]
        assert list(signature(value).parameters) == parameters
        assert getattr(load_harness, name) is value


def test_load_telemetry_owner_is_the_historical_facade_binding() -> None:
    for name in (
        "_ApiTelemetry",
        "_collect_api_telemetry",
        "_telemetry_response",
        "_record_telemetry_checks",
        "_valid_operations_metrics_payload",
        "_safe_json",
        "_response_json",
        "_readiness_status",
        "_worker_ready_status",
        "_worker_stale_status",
        "_outbox_metrics",
        "_execution_status_counts",
    ):
        assert getattr(load_harness, name) is getattr(load_telemetry, name)


def test_collect_api_telemetry_preserves_request_order_headers_and_projection() -> None:
    requests: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, request.headers.get("authorization")))
        if request.url.path == "/health/ready":
            return httpx.Response(
                200,
                json={"status": "ready", "database_ready": True, "worker_ready": True},
            )
        if request.url.path == "/health/worker":
            return httpx.Response(503, json={"status": "stale", "ready": False})
        return httpx.Response(
            200,
            json={
                "pending_outbox_count": 1,
                "dead_letter_outbox_count": 0,
                "oldest_pending_outbox_age_seconds": None,
                "database_pool": {"size": 5, "checked_out": 1, "overflow": 0},
                "internal_detail": "not-persisted-by-this-observer",
            },
        )

    with httpx.Client(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    ) as client:
        telemetry = _collect_api_telemetry(
            client,
            headers={"Authorization": "Bearer opaque"},
            timeout_seconds=2.0,
        )

    assert requests == [
        ("/health/ready", "Bearer opaque"),
        ("/health/worker", "Bearer opaque"),
        ("/operations/metrics", "Bearer opaque"),
    ]
    assert telemetry.readiness is True
    assert telemetry.worker_ready is False
    assert telemetry.missing == ()
    assert telemetry.operations_metrics is not None
    assert telemetry.operations_metrics["pending_outbox_count"] == 1
    assert telemetry.complete is True


def test_collect_api_telemetry_missing_order_is_exact_for_malformed_responses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health/ready":
            return httpx.Response(500, json={"status": "ready"})
        if request.url.path == "/health/worker":
            return httpx.Response(200, json=["invalid"])
        return httpx.Response(200, json={"pending_outbox_count": True})

    with httpx.Client(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    ) as client:
        telemetry = _collect_api_telemetry(client, headers={}, timeout_seconds=1.0)

    assert telemetry == _ApiTelemetry(
        readiness=None,
        worker_ready=None,
        operations_metrics=None,
        missing=("readiness", "worker_health", "operations_metrics", "database_pool"),
    )
    assert telemetry.complete is False


def test_telemetry_response_maps_http_errors_and_malformed_json_without_raising() -> None:
    def failing_handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unavailable")

    with httpx.Client(
        base_url="http://testserver",
        transport=httpx.MockTransport(failing_handler),
    ) as client:
        assert _telemetry_response(client, "/health/ready", headers={}, timeout_seconds=1) == (
            None,
            None,
        )

    response = httpx.Response(503, content=b"not-json")
    assert _response_json(response) is None
    assert _safe_json(response) is None
    list_response = httpx.Response(200, json=[1, 2])
    assert _response_json(list_response) is None
    assert _safe_json(list_response) is None


def test_telemetry_check_recording_appends_only_observed_values() -> None:
    readiness = [False]
    worker_unhealthy = [False]
    telemetry = _ApiTelemetry(
        readiness=True,
        worker_ready=False,
        operations_metrics=None,
        missing=("operations_metrics",),
    )

    _record_telemetry_checks(
        telemetry,
        readiness_checks=readiness,
        worker_unhealthy_checks=worker_unhealthy,
    )
    _record_telemetry_checks(
        _ApiTelemetry(None, None, None, ("readiness", "worker_health")),
        readiness_checks=readiness,
        worker_unhealthy_checks=worker_unhealthy,
    )

    assert readiness == [False, True]
    assert worker_unhealthy == [False, True]


def test_readiness_and_worker_status_parsing_is_closed_and_type_strict() -> None:
    assert (
        _readiness_status({"status": "ready", "database_ready": True, "worker_ready": True}) is True
    )
    assert (
        _readiness_status({"status": "degraded", "database_ready": True, "worker_ready": True})
        is False
    )
    assert _readiness_status({"status": "ready", "database_ready": 1, "worker_ready": True}) is None
    assert _worker_ready_status({"status": "ready", "ready": True}) is True
    assert _worker_ready_status({"status": "stale", "ready": False}) is False
    assert _worker_ready_status({"status": "unknown", "ready": False}) is None
    assert _worker_stale_status({"status": "stale", "ready": False}) is True
    assert _worker_stale_status(None) is None


def test_operations_metrics_validation_and_outbox_projection_are_allow_listed() -> None:
    metrics = {
        "pending_outbox_count": 2,
        "dead_letter_outbox_count": 1,
        "oldest_pending_outbox_age_seconds": 3,
        "secret": "removed",
    }
    assert _valid_operations_metrics_payload(metrics) is True
    assert _valid_operations_metrics_payload({**metrics, "pending_outbox_count": True}) is False
    assert (
        _valid_operations_metrics_payload({**metrics, "oldest_pending_outbox_age_seconds": -1})
        is False
    )
    assert _outbox_metrics(metrics) == {
        "pending_outbox_count": 2,
        "oldest_pending_outbox_age_seconds": 3,
        "dead_letter_outbox_count": 1,
    }
    assert _outbox_metrics(None) is None


def test_execution_status_counts_ignore_invalid_rows_and_preserve_first_seen_order() -> None:
    page = {
        "items": [
            {"status": "running"},
            {"status": "completed"},
            {"status": "running"},
            {"status": 7},
            {"status": ""},
            "invalid",
        ]
    }
    assert _execution_status_counts(page) == {"running": 2, "completed": 1, "7": 1}
    assert _execution_status_counts({"items": "invalid"}) is None
    assert _execution_status_counts(None) is None

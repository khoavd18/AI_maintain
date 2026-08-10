"""Load tests grouped by stateful workflow dimension."""

from __future__ import annotations

from ._workflow_scenarios import (
    Path,
    SafetyThresholds,
    _assert_during_stage_degradation,
    _healthy_api_response,
    _is_profile_control_request,
    _one_stage_profile,
    _operations_metrics_payload,
    httpx,
    pytest,
    run_step_load,
    threading,
    time,
)


def test_during_stage_readiness_failure_cancels_new_submissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")
    telemetry_readiness_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal telemetry_readiness_count
        if request.url.path == "/health/ready" and threading.current_thread().name.startswith(
            "pm9-load-stage-"
        ):
            telemetry_readiness_count += 1
            healthy = telemetry_readiness_count == 1
            return httpx.Response(
                200,
                json={
                    "status": "ready" if healthy else "degraded",
                    "database_ready": healthy,
                    "worker_ready": True,
                },
            )
        if request.url.path not in {
            "/auth/login",
            "/health/ready",
            "/health/worker",
            "/operations/metrics",
            "/operations/executions",
        }:
            time.sleep(0.02)
        return _healthy_api_response(request)

    report, _ = run_step_load(
        profile=_one_stage_profile(
            "readiness-during",
            requests_per_second=100.0,
            concurrent_users=2,
        ),
        base_url="http://capacity.example.test",
        username="operator",
        password="test-password",
        output_dir=tmp_path,
        shutdown_grace_seconds=0.2,
        telemetry_interval_seconds=0.05,
        monitor_interval_seconds=0.05,
        transport=httpx.MockTransport(handler),
    )

    stage = report["stages"][0]
    assert report["capacity_evidence_status"] == "observed_degradation"
    assert report["capacity_stop_reason_codes"] == ["readiness_unhealthy"]
    assert report["first_observed_degradation_point"] == {
        "target_requests_per_second": 100.0,
        "concurrent_users": 2,
        "reason_codes": ["readiness_unhealthy"],
        "stop_phase": "during_stage",
    }
    assert stage["workload_started"] is True
    assert (
        stage["metrics"]["submitted_workload_request_count"]
        < stage["metrics"]["planned_workload_request_count"]
    )


def test_during_stage_unexpected_error_rate_stops_new_submissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_profile_control_request(request):
            return _healthy_api_response(request)
        return httpx.Response(500, json={"detail": "synthetic failure"})

    report, _ = run_step_load(
        profile=_one_stage_profile(
            "runtime-error-rate",
            requests_per_second=100.0,
            concurrent_users=2,
        ),
        base_url="http://capacity.example.test",
        username="operator",
        password="test-password",
        output_dir=tmp_path,
        timeout_seconds=1.0,
        shutdown_grace_seconds=0.2,
        telemetry_interval_seconds=0.05,
        monitor_interval_seconds=0.05,
        transport=httpx.MockTransport(handler),
    )

    _assert_during_stage_degradation(
        report,
        reason="unexpected_error_rate",
    )


def test_during_stage_p95_ceiling_stops_new_submissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_profile_control_request(request):
            return _healthy_api_response(request)
        time.sleep(0.03)
        return httpx.Response(200, json={})

    report, _ = run_step_load(
        profile=_one_stage_profile(
            "runtime-p95",
            requests_per_second=100.0,
            concurrent_users=2,
        ),
        base_url="http://capacity.example.test",
        username="operator",
        password="test-password",
        output_dir=tmp_path,
        timeout_seconds=1.0,
        thresholds=SafetyThresholds(
            max_unexpected_error_rate=1.0,
            max_p95_latency_ms=5.0,
        ),
        shutdown_grace_seconds=0.2,
        telemetry_interval_seconds=0.05,
        monitor_interval_seconds=0.05,
        transport=httpx.MockTransport(handler),
    )

    _assert_during_stage_degradation(
        report,
        reason="p95_latency_ceiling",
    )


def test_during_stage_repeated_timeouts_stop_new_submissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_profile_control_request(request):
            return _healthy_api_response(request)
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    report, _ = run_step_load(
        profile=_one_stage_profile(
            "runtime-timeouts",
            requests_per_second=100.0,
            concurrent_users=2,
        ),
        base_url="http://capacity.example.test",
        username="operator",
        password="test-password",
        output_dir=tmp_path,
        timeout_seconds=1.0,
        thresholds=SafetyThresholds(
            max_unexpected_error_rate=1.0,
            max_p95_latency_ms=1_000_000.0,
            repeated_timeout_limit=2,
        ),
        shutdown_grace_seconds=0.2,
        telemetry_interval_seconds=0.05,
        monitor_interval_seconds=0.05,
        transport=httpx.MockTransport(handler),
    )

    _assert_during_stage_degradation(
        report,
        reason="repeated_timeouts",
    )


def test_two_consecutive_outbox_growth_observations_stop_during_stage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")
    metrics_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal metrics_calls
        if request.url.path == "/operations/metrics":
            metrics_calls += 1
            payload = _operations_metrics_payload()
            payload["pending_outbox_count"] = 1 if metrics_calls in {2, 3} else 0
            return httpx.Response(200, json=payload)
        return _healthy_api_response(request)

    report, _ = run_step_load(
        profile=_one_stage_profile(
            "runtime-outbox-growth",
            requests_per_second=100.0,
            concurrent_users=2,
        ),
        base_url="http://capacity.example.test",
        username="operator",
        password="test-password",
        output_dir=tmp_path,
        timeout_seconds=1.0,
        shutdown_grace_seconds=0.2,
        telemetry_interval_seconds=0.05,
        monitor_interval_seconds=0.05,
        transport=httpx.MockTransport(handler),
    )

    _assert_during_stage_degradation(
        report,
        reason="unrecovered_outbox_growth",
    )
    assert metrics_calls >= 4
    assert report["stages"][0]["metrics"]["maximum_outbox_growth_breach_streak"] == 2


def test_one_transient_outbox_growth_observation_does_not_stop_stage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")
    metrics_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal metrics_calls
        if request.url.path == "/operations/metrics":
            metrics_calls += 1
            payload = _operations_metrics_payload()
            payload["pending_outbox_count"] = 1 if metrics_calls == 2 else 0
            return httpx.Response(200, json=payload)
        return _healthy_api_response(request)

    report, _ = run_step_load(
        profile=_one_stage_profile(
            "transient-outbox-growth",
            requests_per_second=20.0,
            concurrent_users=2,
        ),
        base_url="http://capacity.example.test",
        username="operator",
        password="test-password",
        output_dir=tmp_path,
        timeout_seconds=1.0,
        shutdown_grace_seconds=0.2,
        telemetry_interval_seconds=0.05,
        monitor_interval_seconds=0.05,
        transport=httpx.MockTransport(handler),
    )

    assert report["capacity_evidence_status"] == "completed_no_boundary_observed"
    assert report["capacity_stop_reason_codes"] == []
    assert report["first_observed_degradation_point"] is None
    assert report["stages"][0]["metrics"]["maximum_outbox_growth_breach_streak"] == 1


def test_dead_letter_growth_stops_on_first_during_stage_observation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")
    metrics_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal metrics_calls
        if request.url.path == "/operations/metrics":
            metrics_calls += 1
            payload = _operations_metrics_payload()
            payload["dead_letter_outbox_count"] = 0 if metrics_calls == 1 else 1
            return httpx.Response(200, json=payload)
        return _healthy_api_response(request)

    report, _ = run_step_load(
        profile=_one_stage_profile(
            "runtime-dead-letter",
            requests_per_second=100.0,
            concurrent_users=2,
        ),
        base_url="http://capacity.example.test",
        username="operator",
        password="test-password",
        output_dir=tmp_path,
        timeout_seconds=1.0,
        shutdown_grace_seconds=0.2,
        telemetry_interval_seconds=0.05,
        monitor_interval_seconds=0.05,
        transport=httpx.MockTransport(handler),
    )

    _assert_during_stage_degradation(
        report,
        reason="dead_letter_growth",
    )
    assert metrics_calls >= 3
    assert report["stages"][0]["metrics"]["maximum_outbox_growth_breach_streak"] == 0

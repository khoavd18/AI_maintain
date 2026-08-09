"""Safe, network-free PM9 load and capacity harness validation."""

from pathlib import Path
import threading
import time

import httpx
import pytest

from src.reliability.load_harness import (
    MonitorSnapshot,
    RequestSpec,
    SafetyThresholds,
    Sample,
    _evaluate_safety,
    _load_mutations,
    _summarize,
    _validated_base_url,
    run_profile,
    run_step_load,
)
from src.reliability.profiles import (
    PM9_STEP_LOAD_PROFILES,
    PROFILES,
    ReliabilityProfile,
    StepLoadProfile,
    StepLoadStage,
)


def _healthy_stage_report(*, p95: float = 20.0) -> dict[str, object]:
    outbox = {
        "pending_outbox_count": 0,
        "dead_letter_outbox_count": 0,
        "oldest_pending_outbox_age_seconds": None,
    }
    database_pool = {"size": 5, "checked_out": 1, "overflow": 0}
    return {
        "total_requests": 100,
        "throughput_requests_per_second": 4.0,
        "latency_ms": {"p50": 10.0, "p95": p95, "p99": p95 + 5.0},
        "expected_authorization_failures": 1,
        "unexpected_error_rate": 0.0,
        "unexpected_failures": 0,
        "timeouts": 0,
        "connection_failures": 0,
        "database_connection_failures": 0,
        "readiness_false_count": 0,
        "worker_stale_observations": 0,
        "outbox_before": outbox,
        "outbox_after": outbox,
        "database_pool_before": database_pool,
        "database_pool_after": database_pool,
        "mandatory_api_telemetry_complete": True,
        "api_telemetry_observation_count": 2,
        "workload_started": True,
        "target_request_count_reached": True,
        "stop_reason": None,
    }


def _operations_metrics_payload() -> dict[str, object]:
    return {
        "pending_outbox_count": 0,
        "dead_letter_outbox_count": 0,
        "oldest_pending_outbox_age_seconds": None,
        "database_pool": {"size": 5, "checked_out": 1, "overflow": 0},
    }


def _healthy_api_response(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/auth/login":
        return httpx.Response(200, json={"access_token": "test-token"})
    if path == "/health/ready":
        return httpx.Response(
            200,
            json={
                "status": "ready",
                "database_ready": True,
                "worker_ready": True,
            },
        )
    if path == "/health/worker":
        return httpx.Response(200, json={"status": "ready", "ready": True})
    if path == "/operations/metrics":
        return httpx.Response(200, json=_operations_metrics_payload())
    if path == "/operations/executions":
        return httpx.Response(200, json={"items": []})
    if path == "/notifications" and "authorization" not in request.headers:
        return httpx.Response(401, json={"detail": "unauthorized"})
    return httpx.Response(200, json={})


def _one_stage_profile(
    name: str,
    *,
    requests_per_second: float = 20.0,
    concurrent_users: int = 2,
) -> StepLoadProfile:
    return StepLoadProfile(
        name=name,
        stages=(StepLoadStage(requests_per_second, concurrent_users),),
        stage_duration_seconds=1,
    )


def _is_profile_control_request(request: httpx.Request) -> bool:
    path = request.url.path
    if path in {
        "/auth/login",
        "/health/ready",
        "/health/worker",
        "/operations/metrics",
    }:
        return True
    if path == "/notifications" and "authorization" not in request.headers:
        return True
    return path == "/operations/executions" and threading.current_thread().name.startswith(
        "pm9-load-stage-"
    )


def _assert_during_stage_degradation(
    report: dict[str, object],
    *,
    reason: str,
) -> None:
    assert report["capacity_evidence_status"] == "observed_degradation"
    assert report["capacity_stop_reason_codes"] == [reason]
    assert report["first_observed_degradation_point"] == {
        "target_requests_per_second": 100.0,
        "concurrent_users": 2,
        "reason_codes": [reason],
        "stop_phase": "during_stage",
    }
    stage = report["stages"][0]
    assert stage["outcome"] == "observed_degradation"
    assert stage["workload_started"] is True
    assert stage["metrics"]["stop_reason"] == reason
    assert stage["metrics"]["runtime_safety_reason_codes"] == [reason]
    assert (
        stage["metrics"]["submitted_workload_request_count"]
        < stage["metrics"]["planned_workload_request_count"]
    )


def test_pm9_profiles_have_increasing_steps_and_bounded_duration() -> None:
    capacity = PM9_STEP_LOAD_PROFILES["capacity"]
    assert [stage.requests_per_second for stage in capacity.stages] == [
        4.0,
        8.0,
        12.0,
        16.0,
        20.0,
    ]
    assert capacity.total_duration_seconds <= 900
    with pytest.raises(ValueError, match="must not exceed 900"):
        StepLoadProfile(
            name="unbounded",
            stages=(
                StepLoadStage(4.0, 4),
                StepLoadStage(8.0, 4),
            ),
            stage_duration_seconds=451,
        )
    with pytest.raises(ValueError, match="duration"):
        ReliabilityProfile(
            name="unbounded",
            concurrent_users=1,
            requests_per_second=1.0,
            duration_seconds=901,
            mutation_share=0.0,
            analytics_trigger_frequency_seconds=None,
        )


def test_slow_transport_keeps_in_flight_work_bounded_by_the_global_deadline(
    tmp_path: Path,
) -> None:
    slow_request_count = 0
    counter_lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal slow_request_count
        path = request.url.path
        if path not in {
            "/auth/login",
            "/health/ready",
            "/health/worker",
            "/operations/metrics",
            "/operations/executions",
        } and not (path == "/notifications" and "authorization" not in request.headers):
            with counter_lock:
                slow_request_count += 1
            time.sleep(0.1)
        return _healthy_api_response(request)

    profile = ReliabilityProfile(
        name="slow-transport-bound",
        concurrent_users=1,
        requests_per_second=100.0,
        duration_seconds=1,
        mutation_share=0.0,
        analytics_trigger_frequency_seconds=None,
    )
    started = time.monotonic()
    report, _ = run_profile(
        base_url="http://capacity.example.test",
        username="operator",
        password="test-password",
        profile=profile,
        output_dir=tmp_path,
        timeout_seconds=1.0,
        shutdown_grace_seconds=0.2,
        telemetry_interval_seconds=0.1,
        transport=httpx.MockTransport(handler),
    )
    elapsed = time.monotonic() - started

    assert elapsed < 3.0
    assert report["planned_workload_request_count"] == 100
    assert report["submitted_workload_request_count"] < 50
    assert report["completed_workload_request_count"] <= report["submitted_workload_request_count"]
    assert report["maximum_in_flight_requests"] == 2
    assert report["peak_in_flight_request_count"] <= 2
    assert report["target_request_count_reached"] is False
    assert report["mandatory_api_telemetry_complete"] is True
    assert slow_request_count < 50


def test_step_load_requires_pm9_opt_in_before_runner_is_called(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PM9_ALLOW_CAPACITY_TESTS", raising=False)
    called = False

    def runner(_profile: ReliabilityProfile) -> dict[str, object]:
        nonlocal called
        called = True
        return _healthy_stage_report()

    with pytest.raises(RuntimeError, match="PM9_ALLOW_CAPACITY_TESTS"):
        run_step_load(output_dir=tmp_path, runner=runner)
    assert called is False


def test_preflight_safety_stop_is_not_reported_as_observed_degradation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")
    runner_called = False

    def runner(_profile: ReliabilityProfile) -> dict[str, object]:
        nonlocal runner_called
        runner_called = True
        return _healthy_stage_report()

    report, _ = run_step_load(
        profile=_one_stage_profile("preflight-stop"),
        output_dir=tmp_path,
        runner=runner,
        monitor=lambda _phase, _profile: MonitorSnapshot(host_cpu_percent=95.0),
    )

    assert runner_called is False
    assert report["capacity_evidence_status"] == "preflight_safety_stop"
    assert report["first_observed_degradation_point"] is None
    assert report["automatic_safety_stop"] is True
    assert report["capacity_stop_reason_codes"] == ["host_cpu_threshold"]
    assert report["stages"][0]["executed"] is False


def test_runner_failure_is_not_reported_as_observed_degradation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")

    def runner(_profile: ReliabilityProfile) -> dict[str, object]:
        raise RuntimeError("sensitive runner detail")

    report, report_path = run_step_load(
        profile=_one_stage_profile("runner-failure"),
        output_dir=tmp_path,
        runner=runner,
    )

    assert report["capacity_evidence_status"] == "harness_failure"
    assert report["first_observed_degradation_point"] is None
    assert report["automatic_safety_stop"] is False
    assert report["capacity_stop_reason_codes"] == ["runner_failure"]
    assert "sensitive runner detail" not in report_path.read_text(encoding="utf-8")


def test_non_returning_test_double_hits_bounded_harness_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")

    def runner(_profile: ReliabilityProfile) -> dict[str, object]:
        time.sleep(2.0)
        return _healthy_stage_report()

    started = time.monotonic()
    report, _ = run_step_load(
        profile=_one_stage_profile("runner-deadline"),
        output_dir=tmp_path,
        runner=runner,
        shutdown_grace_seconds=0.05,
        monitor_interval_seconds=0.05,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 1.5
    assert report["capacity_evidence_status"] == "harness_failure"
    assert report["capacity_stop_reason_codes"] == ["runner_deadline_exceeded"]
    assert report["first_observed_degradation_point"] is None


def test_operator_cancellation_is_inconclusive_not_degradation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")

    def runner(_profile: ReliabilityProfile) -> dict[str, object]:
        time.sleep(0.15)
        return _healthy_stage_report()

    def monitor(
        phase: str,
        _profile: ReliabilityProfile,
    ) -> MonitorSnapshot:
        return MonitorSnapshot(operator_cancelled=phase == "during")

    report, _ = run_step_load(
        profile=_one_stage_profile("operator-cancelled"),
        output_dir=tmp_path,
        runner=runner,
        monitor=monitor,
        shutdown_grace_seconds=0.2,
        monitor_interval_seconds=0.05,
    )

    assert report["capacity_evidence_status"] == "inconclusive"
    assert report["capacity_stop_reason_codes"] == ["operator_cancelled"]
    assert report["first_observed_degradation_point"] is None
    assert report["automatic_safety_stop"] is True


def test_injected_runner_stops_at_first_observed_degradation_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")
    called_rates: list[float] = []

    def runner(profile: ReliabilityProfile) -> dict[str, object]:
        called_rates.append(profile.requests_per_second)
        p95 = 2_001.0 if profile.requests_per_second == 12.0 else 20.0
        return _healthy_stage_report(p95=p95)

    def monitor(
        phase: str,
        _profile: ReliabilityProfile,
    ) -> MonitorSnapshot:
        return MonitorSnapshot(
            readiness=True,
            worker_stale=False,
            pending_outbox_count=0,
            database_pool_timeout_count=0,
            host_cpu_percent=20.0 if phase == "before" else 25.0,
            host_memory_percent=30.0,
        )

    report, report_path = run_step_load(
        output_dir=tmp_path,
        runner=runner,
        monitor=monitor,
    )

    assert called_rates == [4.0, 8.0, 12.0]
    assert report["automatic_safety_stop"] is True
    assert report["capacity_evidence_status"] == "observed_degradation"
    assert report["evidence_mode"] == "synthetic_test_double"
    assert report["host_capacity_evidence_eligible"] is False
    assert report["first_observed_degradation_point"] == {
        "target_requests_per_second": 12.0,
        "concurrent_users": 8,
        "reason_codes": ["p95_latency_ceiling"],
        "stop_phase": "after_stage",
    }
    assert report["stages"][-1]["metrics"]["latency_ms"] == {
        "p50": 10.0,
        "p95": 2_001.0,
        "p99": 2_006.0,
    }
    assert report["observed_boundary_only"] is True
    assert report["sla_claim"] is False
    assert report["production_readiness_claim"] is False
    assert "not an SLA" in report["result_interpretation"]
    assert report_path.parent == tmp_path.resolve()


def test_missing_mandatory_api_telemetry_is_inconclusive_and_skips_workload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")
    workload_request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal workload_request_count
        if request.url.path == "/operations/metrics":
            return httpx.Response(503, json={"detail": "unavailable"})
        if request.url.path not in {
            "/auth/login",
            "/health/ready",
            "/health/worker",
            "/operations/executions",
        }:
            workload_request_count += 1
        return _healthy_api_response(request)

    report, _ = run_step_load(
        profile=_one_stage_profile("missing-telemetry"),
        base_url="http://capacity.example.test",
        username="operator",
        password="test-password",
        output_dir=tmp_path,
        shutdown_grace_seconds=0.2,
        telemetry_interval_seconds=0.05,
        monitor_interval_seconds=0.05,
        transport=httpx.MockTransport(handler),
    )

    assert workload_request_count == 0
    assert report["capacity_evidence_status"] == "inconclusive"
    assert report["first_observed_degradation_point"] is None
    assert report["host_capacity_evidence_eligible"] is False
    assert report["capacity_stop_reason_codes"] == ["mandatory_api_telemetry_missing"]
    assert report["stages"][0]["workload_started"] is False
    assert report["stages"][0]["metrics"]["submitted_workload_request_count"] == 0


def test_one_unhealthy_readiness_observation_stops_before_workload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")
    workload_request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal workload_request_count
        if request.url.path == "/health/ready":
            return httpx.Response(
                200,
                json={
                    "status": "degraded",
                    "database_ready": False,
                    "worker_ready": True,
                },
            )
        if request.url.path not in {
            "/auth/login",
            "/health/worker",
            "/operations/metrics",
            "/operations/executions",
        }:
            workload_request_count += 1
        return _healthy_api_response(request)

    report, _ = run_step_load(
        profile=_one_stage_profile("readiness-preflight"),
        base_url="http://capacity.example.test",
        username="operator",
        password="test-password",
        output_dir=tmp_path,
        shutdown_grace_seconds=0.2,
        telemetry_interval_seconds=0.05,
        monitor_interval_seconds=0.05,
        transport=httpx.MockTransport(handler),
    )

    assert workload_request_count == 0
    assert report["capacity_evidence_status"] == "preflight_safety_stop"
    assert report["capacity_stop_reason_codes"] == ["readiness_unhealthy"]
    assert report["first_observed_degradation_point"] is None
    assert report["stages"][0]["workload_started"] is False


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


def test_slow_healthy_control_plane_does_not_consume_the_workload_window(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {
            "/auth/login",
            "/health/ready",
            "/health/worker",
            "/operations/metrics",
            "/operations/executions",
        }:
            time.sleep(0.05)
        return _healthy_api_response(request)

    report, _ = run_step_load(
        profile=_one_stage_profile(
            "slow-healthy-control-plane",
            requests_per_second=4.0,
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
    assert report["capacity_evidence_status"] == "completed_no_boundary_observed"
    assert report["capacity_stop_reason_codes"] == []
    assert stage["metrics"]["target_request_count_reached"] is True
    assert (
        stage["metrics"]["submitted_workload_request_count"]
        == stage["metrics"]["planned_workload_request_count"]
    )


@pytest.mark.parametrize(
    ("report", "before", "after", "expected_reason"),
    [
        (
            {**_healthy_stage_report(), "unexpected_error_rate": 0.021},
            MonitorSnapshot(),
            MonitorSnapshot(),
            "unexpected_error_rate",
        ),
        (
            {**_healthy_stage_report(), "timeouts": 2},
            MonitorSnapshot(),
            MonitorSnapshot(),
            "repeated_timeouts",
        ),
        (
            _healthy_stage_report(),
            MonitorSnapshot(readiness=False),
            MonitorSnapshot(readiness=False),
            "readiness_unhealthy",
        ),
        (
            _healthy_stage_report(),
            MonitorSnapshot(worker_stale=False),
            MonitorSnapshot(worker_stale=True),
            "worker_stale",
        ),
        (
            _healthy_stage_report(),
            MonitorSnapshot(pending_outbox_count=2),
            MonitorSnapshot(pending_outbox_count=3),
            "unrecovered_outbox_growth",
        ),
        (
            _healthy_stage_report(),
            MonitorSnapshot(host_cpu_percent=50.0),
            MonitorSnapshot(host_cpu_percent=90.1),
            "host_cpu_threshold",
        ),
        (
            _healthy_stage_report(),
            MonitorSnapshot(host_memory_percent=50.0),
            MonitorSnapshot(host_memory_percent=90.1),
            "host_memory_threshold",
        ),
        (
            _healthy_stage_report(),
            MonitorSnapshot(database_pool_timeout_count=3),
            MonitorSnapshot(database_pool_timeout_count=5),
            "repeated_timeouts",
        ),
    ],
)
def test_automatic_stop_thresholds(
    report: dict[str, object],
    before: MonitorSnapshot,
    after: MonitorSnapshot,
    expected_reason: str,
) -> None:
    reasons = _evaluate_safety(
        report=report,
        before=before,
        after=after,
        thresholds=SafetyThresholds(),
    )
    assert expected_reason in reasons


def test_percentiles_are_deterministic_and_expected_auth_is_not_an_error() -> None:
    report = _summarize(
        profile=PROFILES["baseline"],
        samples=[
            Sample("/health/live", 200, 4.0, "success"),
            Sample("/notifications", 401, 1.0, "expected_authorization_failure"),
            Sample("/assets", 200, 3.0, "success"),
            Sample("/tickets", 200, 2.0, "success"),
        ],
        elapsed_seconds=1.0,
        before_metrics=None,
        after_metrics=None,
        base_url="http://127.0.0.1:8000",
    )
    assert report["latency_ms"] == {
        "p50": 2.0,
        "p95": 4.0,
        "p99": 4.0,
        "max": 4.0,
    }
    assert report["expected_authorization_failures"] == 1
    assert report["unexpected_error_rate"] == 0.0


def test_step_report_is_allowlisted_and_cannot_persist_runner_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")
    secret = "do-not-persist-this-secret"
    one_stage = StepLoadProfile(
        name="redaction",
        stages=(StepLoadStage(4.0, 2),),
        stage_duration_seconds=1,
    )

    def runner(_profile: ReliabilityProfile) -> dict[str, object]:
        return {
            **_healthy_stage_report(),
            "password": secret,
            "headers": {"Authorization": f"Bearer {secret}"},
            "raw_request_body": {"api_key": secret},
        }

    report, report_path = run_step_load(
        profile=one_stage,
        output_dir=tmp_path,
        runner=runner,
    )
    serialized = report_path.read_text(encoding="utf-8")
    assert secret not in serialized
    assert "Authorization" not in serialized
    assert "raw_request_body" not in serialized
    assert secret not in str(report)


def test_targets_reports_and_mutations_retain_safety_opt_ins(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="credential-free"):
        _validated_base_url("http://operator:secret@127.0.0.1:8000")

    fixture = tmp_path / "mutations.json"
    fixture.write_text(
        '[{"method":"GET","path":"//external.example.test/capture"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="local absolute paths"):
        _load_mutations(fixture)

    monkeypatch.setenv("PM9_ALLOW_CAPACITY_TESTS", "true")
    monkeypatch.delenv("PM8_ALLOW_MUTATIONS", raising=False)
    called = False

    def runner(_profile: ReliabilityProfile) -> dict[str, object]:
        nonlocal called
        called = True
        return _healthy_stage_report()

    with pytest.raises(RuntimeError, match="PM8_ALLOW_MUTATIONS"):
        run_step_load(
            output_dir=tmp_path,
            runner=runner,
            mutation_specs=(
                RequestSpec(
                    "POST",
                    "/tickets",
                    (201,),
                    {"title": "isolated fixture"},
                    "pm9-stable-key",
                ),
            ),
        )
    assert called is False

    repository_output = Path(__file__).resolve().parents[1] / "reports"
    with pytest.raises(ValueError, match="outside the repository"):
        run_step_load(output_dir=repository_output, runner=runner)

"""Load tests grouped by stateful workflow dimension."""

from __future__ import annotations

from ._workflow_scenarios import (
    MonitorSnapshot,
    Path,
    ReliabilityProfile,
    StepLoadProfile,
    StepLoadStage,
    _healthy_api_response,
    _healthy_stage_report,
    _one_stage_profile,
    httpx,
    pytest,
    run_step_load,
    time,
)


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

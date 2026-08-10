"""Load tests grouped by stateful workflow dimension."""

from __future__ import annotations

from ._workflow_scenarios import (
    PM9_STEP_LOAD_PROFILES,
    PROFILES,
    Path,
    ReliabilityProfile,
    RequestSpec,
    Sample,
    StepLoadProfile,
    StepLoadStage,
    _healthy_api_response,
    _healthy_stage_report,
    _load_mutations,
    _summarize,
    _validated_base_url,
    httpx,
    pytest,
    run_profile,
    run_step_load,
    threading,
    time,
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

    repository_output = Path(__file__).resolve().parents[3] / "reports"
    with pytest.raises(ValueError, match="outside the repository"):
        run_step_load(output_dir=repository_output, runner=runner)

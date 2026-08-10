"""Safe, network-free load profile and step-workflow validation."""

# ruff: noqa: F401 - split suites import their explicit scenario dependencies

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

"""Small authenticated HTTP reliability harness for a dedicated pilot test stack."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from src.reliability.profiles import (
    PM9_STEP_LOAD_PROFILES,
    PROFILES,
    ReliabilityProfile,
    StepLoadProfile,
)

_MUTATION_FLAG = "PM8_ALLOW_MUTATIONS"
_EXTENDED_FLAG = "PM8_ALLOW_EXTENDED_TESTS"
_STEP_LOAD_FLAG = "PM9_ALLOW_CAPACITY_TESTS"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SHUTDOWN_GRACE_SECONDS = 2.0
_DEFAULT_TELEMETRY_INTERVAL_SECONDS = 1.0
_DEFAULT_MONITOR_INTERVAL_SECONDS = 0.25
_MAX_IN_FLIGHT_MULTIPLIER = 2
_MIN_REQUEST_TIMEOUT_SECONDS = 0.05
_OUTBOX_GROWTH_BREACH_OBSERVATIONS = 2
_STAGE_CONTROL_REQUEST_COUNT = 8
_STAGE_CONTROL_FIXED_ALLOWANCE_SECONDS = 1.0
_SAFE_STAGE_STOP_REASONS = frozenset(
    {
        "dead_letter_growth",
        "external_safety_stop",
        "mandatory_api_telemetry_missing",
        "monitor_failure",
        "operator_cancelled",
        "p95_latency_ceiling",
        "readiness_unhealthy",
        "repeated_timeouts",
        "request_task_failure",
        "runner_deadline_exceeded",
        "runner_failure",
        "target_rate_not_achieved",
        "unexpected_error_rate",
        "unrecovered_outbox_growth",
        "worker_unhealthy",
    }
)
_OBSERVED_STAGE_STOP_REASONS = frozenset(
    {
        "dead_letter_growth",
        "p95_latency_ceiling",
        "readiness_unhealthy",
        "repeated_timeouts",
        "unexpected_error_rate",
        "unrecovered_outbox_growth",
        "worker_unhealthy",
    }
)
_SAFE_STOP_OBSERVATION_PHASES = frozenset({"preflight", "during_workload", "postflight"})


@dataclass(frozen=True)
class RequestSpec:
    method: str
    path: str
    expected_statuses: tuple[int, ...] = (200,)
    json_body: dict[str, Any] | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class Sample:
    name: str
    status_code: int | None
    elapsed_ms: float
    outcome: str
    idempotent_replay: bool = False


@dataclass(frozen=True)
class SafetyThresholds:
    """Operator-configured rehearsal stops; these values are not an SLA."""

    max_unexpected_error_rate: float = 0.02
    max_p95_latency_ms: float = 2_000.0
    repeated_timeout_limit: int = 2
    repeated_readiness_failure_limit: int = 1
    max_worker_stale_observations: int = 0
    max_unrecovered_outbox_growth: int = 0
    max_host_cpu_percent: float = 90.0
    max_host_memory_percent: float = 90.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_unexpected_error_rate, bool)
            or not isinstance(self.max_unexpected_error_rate, (int, float))
            or not math.isfinite(self.max_unexpected_error_rate)
            or not 0 <= self.max_unexpected_error_rate <= 1
        ):
            raise ValueError("Unexpected-error threshold must be between 0 and 1.")
        if (
            isinstance(self.max_p95_latency_ms, bool)
            or not isinstance(self.max_p95_latency_ms, (int, float))
            or not math.isfinite(self.max_p95_latency_ms)
            or self.max_p95_latency_ms <= 0
        ):
            raise ValueError("The p95 latency ceiling must be positive.")
        if (
            isinstance(self.repeated_timeout_limit, bool)
            or not isinstance(self.repeated_timeout_limit, int)
            or self.repeated_timeout_limit < 1
        ):
            raise ValueError("Timeout stop limit must be positive.")
        if (
            isinstance(self.repeated_readiness_failure_limit, bool)
            or not isinstance(self.repeated_readiness_failure_limit, int)
            or self.repeated_readiness_failure_limit < 1
        ):
            raise ValueError("Readiness-failure stop limit must be positive.")
        if (
            isinstance(self.max_worker_stale_observations, bool)
            or not isinstance(self.max_worker_stale_observations, int)
            or self.max_worker_stale_observations < 0
        ):
            raise ValueError("Worker-stale allowance cannot be negative.")
        if (
            isinstance(self.max_unrecovered_outbox_growth, bool)
            or not isinstance(self.max_unrecovered_outbox_growth, int)
            or self.max_unrecovered_outbox_growth < 0
        ):
            raise ValueError("Outbox-growth allowance cannot be negative.")
        for label, value in (
            ("CPU", self.max_host_cpu_percent),
            ("memory", self.max_host_memory_percent),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 < value <= 100
            ):
                raise ValueError(f"Host {label} threshold must be between 0 and 100.")


@dataclass(frozen=True)
class MonitorSnapshot:
    """Allow-listed monitor data captured before, during, or after a load stage."""

    readiness: bool | None = None
    worker_stale: bool | None = None
    pending_outbox_count: int | None = None
    database_pool_timeout_count: int | None = None
    host_cpu_percent: float | None = None
    host_memory_percent: float | None = None
    operator_cancelled: bool = False

    def __post_init__(self) -> None:
        for label, value in (
            ("readiness", self.readiness),
            ("worker stale", self.worker_stale),
        ):
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{label.title()} observation must be boolean.")
        if not isinstance(self.operator_cancelled, bool):
            raise ValueError("Operator-cancelled observation must be boolean.")
        for label, value in (
            ("pending outbox", self.pending_outbox_count),
            ("database pool timeout", self.database_pool_timeout_count),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{label.title()} count cannot be negative.")
        for label, value in (
            ("CPU", self.host_cpu_percent),
            ("memory", self.host_memory_percent),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
                or value > 100
            ):
                raise ValueError(f"Host {label} observation must be between 0 and 100.")


StepRunner = Callable[[ReliabilityProfile], Mapping[str, Any]]
StepMonitor = Callable[
    [str, ReliabilityProfile],
    MonitorSnapshot | Mapping[str, Any],
]


@dataclass(frozen=True)
class _ApiTelemetry:
    """One allow-listed API telemetry observation used only for safety decisions."""

    readiness: bool | None
    worker_ready: bool | None
    operations_metrics: dict[str, Any] | None
    missing: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing


@dataclass(frozen=True)
class _StageExecution:
    """Bounded result from invoking one stage runner in a daemon thread."""

    report: Mapping[str, Any] | None
    monitor_snapshot: MonitorSnapshot
    during_reason_codes: tuple[str, ...]
    failure_reason: str | None


DEFAULT_READS = (
    RequestSpec("GET", "/health/live"),
    RequestSpec("GET", "/health/ready", (200,)),
    RequestSpec("GET", "/assets"),
    RequestSpec("GET", "/assets/risk/top?limit=5"),
    RequestSpec("GET", "/tickets"),
    RequestSpec("GET", "/work-orders?page=1&page_size=10"),
    RequestSpec("GET", "/inventory/balances?page=1&page_size=10"),
    RequestSpec("GET", "/notifications?page=1&page_size=10"),
    RequestSpec("GET", "/notifications/unread-count"),
    RequestSpec("GET", "/operations/executions?page=1&page_size=10"),
)


def run_profile(
    *,
    base_url: str,
    username: str,
    password: str,
    profile: ReliabilityProfile,
    output_dir: Path | None = None,
    mutation_specs: tuple[RequestSpec, ...] = (),
    timeout_seconds: float = 10.0,
    shutdown_grace_seconds: float = _DEFAULT_SHUTDOWN_GRACE_SECONDS,
    telemetry_interval_seconds: float = _DEFAULT_TELEMETRY_INTERVAL_SECONDS,
    safety_thresholds: SafetyThresholds | None = None,
    cancellation_event: threading.Event | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run one wall-clock-bounded profile and emit only a summarized JSON report."""

    if profile.extended and os.getenv(_EXTENDED_FLAG) != "true":
        raise RuntimeError(f"{profile.name} requires {_EXTENDED_FLAG}=true.")
    if mutation_specs and os.getenv(_MUTATION_FLAG) != "true":
        raise RuntimeError(
            f"Mutation scenarios require {_MUTATION_FLAG}=true and isolated records."
        )
    report_dir = _validated_report_directory(output_dir)
    normalized_base = _validated_base_url(base_url)
    for spec in (*DEFAULT_READS, *mutation_specs):
        _validated_request_path(spec.path)
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= 60
    ):
        raise ValueError("HTTP timeout must be greater than 0 and at most 60 seconds.")
    if (
        isinstance(shutdown_grace_seconds, bool)
        or not isinstance(shutdown_grace_seconds, (int, float))
        or not math.isfinite(shutdown_grace_seconds)
        or not 0.05 <= shutdown_grace_seconds <= 10
    ):
        raise ValueError("Shutdown grace must be between 0.05 and 10 seconds.")
    if (
        isinstance(telemetry_interval_seconds, bool)
        or not isinstance(telemetry_interval_seconds, (int, float))
        or not math.isfinite(telemetry_interval_seconds)
        or not 0.05 <= telemetry_interval_seconds <= 30
    ):
        raise ValueError("Telemetry interval must be between 0.05 and 30 seconds.")

    active_thresholds = safety_thresholds or SafetyThresholds()
    samples: list[Sample] = []
    readiness_checks: list[bool] = []
    worker_unhealthy_checks: list[bool] = []
    telemetry_observations: list[_ApiTelemetry] = []
    before_metrics: dict[str, Any] | None = None
    after_metrics: dict[str, Any] | None = None
    execution_page: dict[str, Any] | None = None
    workload_started = False
    submitted_request_count = 0
    completed_request_count = 0
    cancelled_request_count = 0
    abandoned_in_flight_count = 0
    peak_in_flight_count = 0
    stop_reason: str | None = None
    stop_observation_phase: str | None = None
    runtime_safety_reason_codes: tuple[str, ...] = ()
    outbox_breach_streak = 0
    maximum_outbox_breach_streak = 0
    deadline_reached = False
    maximum_in_flight = max(
        profile.concurrent_users,
        profile.concurrent_users * _MAX_IN_FLIGHT_MULTIPLIER,
    )
    total_planned = max(1, math.ceil(profile.requests_per_second * profile.duration_seconds))
    workload_elapsed = 0.0
    client_kwargs: dict[str, Any] = {
        "base_url": normalized_base,
        "timeout": timeout_seconds,
    }
    if transport is not None:
        client_kwargs["transport"] = transport
    client = httpx.Client(**client_kwargs)
    pool: ThreadPoolExecutor | None = None
    pending: set[Future[Sample]] = set()

    def stop_for_runtime_reasons(reasons: tuple[str, ...]) -> None:
        nonlocal runtime_safety_reason_codes
        nonlocal stop_observation_phase
        nonlocal stop_reason
        if stop_reason is not None or not reasons:
            return
        runtime_safety_reason_codes = _ordered_unique(reasons)
        stop_reason = runtime_safety_reason_codes[0]
        stop_observation_phase = "during_workload"

    def evaluate_completed_samples() -> None:
        stop_for_runtime_reasons(
            _runtime_performance_safety_reasons(
                samples=samples,
                thresholds=active_thresholds,
            )
        )

    def evaluate_runtime_telemetry(metrics: Mapping[str, Any] | None) -> None:
        nonlocal maximum_outbox_breach_streak
        nonlocal outbox_breach_streak
        if stop_reason is not None:
            return
        reasons, outbox_breach_streak = _runtime_telemetry_safety_reasons(
            baseline_metrics=before_metrics,
            current_metrics=metrics,
            thresholds=active_thresholds,
            prior_outbox_breach_streak=outbox_breach_streak,
        )
        maximum_outbox_breach_streak = max(
            maximum_outbox_breach_streak,
            outbox_breach_streak,
        )
        stop_for_runtime_reasons(reasons)

    try:
        token = _login(client, username=username, password=password)
        headers = {"Authorization": f"Bearer {token}"}
        telemetry_timeout = min(
            timeout_seconds,
            max(_MIN_REQUEST_TIMEOUT_SECONDS, shutdown_grace_seconds / 3),
        )
        before_telemetry = _collect_api_telemetry(
            client,
            headers=headers,
            timeout_seconds=telemetry_timeout,
        )
        telemetry_observations.append(before_telemetry)
        _record_telemetry_checks(
            before_telemetry,
            readiness_checks=readiness_checks,
            worker_unhealthy_checks=worker_unhealthy_checks,
        )
        before_metrics = before_telemetry.operations_metrics
        if not before_telemetry.complete:
            stop_reason = "mandatory_api_telemetry_missing"
            stop_observation_phase = "preflight"
        elif before_telemetry.readiness is False:
            stop_reason = "readiness_unhealthy"
            stop_observation_phase = "preflight"
        elif before_telemetry.worker_ready is False:
            stop_reason = "worker_unhealthy"
            stop_observation_phase = "preflight"
        elif cancellation_event is not None and cancellation_event.is_set():
            stop_reason = "external_safety_stop"
            stop_observation_phase = "preflight"
        else:
            workload_started = True
            started = time.monotonic()
            deadline = started + profile.duration_seconds
            grace_deadline = deadline + shutdown_grace_seconds
            next_telemetry_at = min(
                deadline,
                started + telemetry_interval_seconds,
            )
            next_index = 0
            unauthorized = _sample_request(
                client,
                RequestSpec("GET", "/notifications", (401,)),
                {},
                timeout_seconds=min(
                    timeout_seconds,
                    max(
                        _MIN_REQUEST_TIMEOUT_SECONDS,
                        grace_deadline - time.monotonic(),
                    ),
                ),
            )
            samples.append(unauthorized)
            pool = ThreadPoolExecutor(max_workers=profile.concurrent_users)

            while next_index < total_planned and stop_reason is None:
                now = time.monotonic()
                if cancellation_event is not None and cancellation_event.is_set():
                    stop_reason = "external_safety_stop"
                    stop_observation_phase = "during_workload"
                    break
                if now >= deadline:
                    deadline_reached = True
                    break

                if now >= next_telemetry_at:
                    observed = _collect_api_telemetry(
                        client,
                        headers=headers,
                        timeout_seconds=min(
                            telemetry_timeout,
                            max(
                                _MIN_REQUEST_TIMEOUT_SECONDS,
                                grace_deadline - now,
                            ),
                        ),
                    )
                    telemetry_observations.append(observed)
                    _record_telemetry_checks(
                        observed,
                        readiness_checks=readiness_checks,
                        worker_unhealthy_checks=worker_unhealthy_checks,
                    )
                    next_telemetry_at = min(
                        deadline,
                        time.monotonic() + telemetry_interval_seconds,
                    )
                    if not observed.complete:
                        stop_reason = "mandatory_api_telemetry_missing"
                        stop_observation_phase = "during_workload"
                        break
                    if observed.readiness is False:
                        stop_reason = "readiness_unhealthy"
                        stop_observation_phase = "during_workload"
                        break
                    if observed.worker_ready is False:
                        stop_reason = "worker_unhealthy"
                        stop_observation_phase = "during_workload"
                        break
                    evaluate_runtime_telemetry(observed.operations_metrics)
                    if stop_reason is not None:
                        break

                if pending:
                    done, pending = wait(
                        pending,
                        timeout=0,
                        return_when=FIRST_COMPLETED,
                    )
                else:
                    done = set()
                if done:
                    completed, task_failed = _consume_request_futures(done, samples)
                    completed_request_count += completed
                    if task_failed:
                        stop_reason = "request_task_failure"
                        stop_observation_phase = "during_workload"
                        break
                    evaluate_completed_samples()
                    if stop_reason is not None:
                        break

                if len(pending) >= maximum_in_flight:
                    wait_budget = min(
                        0.05,
                        max(0.0, deadline - time.monotonic()),
                        max(0.0, next_telemetry_at - time.monotonic()),
                    )
                    if wait_budget > 0:
                        done, pending = wait(
                            pending,
                            timeout=wait_budget,
                            return_when=FIRST_COMPLETED,
                        )
                        completed, task_failed = _consume_request_futures(done, samples)
                        completed_request_count += completed
                        if task_failed:
                            stop_reason = "request_task_failure"
                            stop_observation_phase = "during_workload"
                        else:
                            evaluate_completed_samples()
                    continue

                target_time = started + (next_index / profile.requests_per_second)
                now = time.monotonic()
                if target_time > now:
                    wait_budget = min(
                        target_time - now,
                        max(0.0, deadline - now),
                        max(0.0, next_telemetry_at - now),
                        0.05,
                    )
                    if wait_budget > 0:
                        if cancellation_event is None:
                            time.sleep(wait_budget)
                        else:
                            cancellation_event.wait(wait_budget)
                    continue

                request_timeout = min(
                    timeout_seconds,
                    max(
                        _MIN_REQUEST_TIMEOUT_SECONDS,
                        grace_deadline - now,
                    ),
                )
                spec = _select_spec(next_index, profile, mutation_specs)
                pending.add(
                    pool.submit(
                        _sample_request,
                        client,
                        spec,
                        headers,
                        timeout_seconds=request_timeout,
                    )
                )
                peak_in_flight_count = max(peak_in_flight_count, len(pending))
                submitted_request_count += 1
                next_index += 1

            drain_deadline = grace_deadline
            if stop_reason is not None:
                drain_deadline = min(
                    drain_deadline,
                    time.monotonic() + shutdown_grace_seconds,
                )
            while pending and time.monotonic() < drain_deadline:
                now = time.monotonic()
                if (
                    stop_reason is None
                    and cancellation_event is not None
                    and cancellation_event.is_set()
                ):
                    stop_reason = "external_safety_stop"
                    stop_observation_phase = "during_workload"
                if stop_reason is None and now < deadline and now >= next_telemetry_at:
                    observed = _collect_api_telemetry(
                        client,
                        headers=headers,
                        timeout_seconds=min(
                            telemetry_timeout,
                            max(
                                _MIN_REQUEST_TIMEOUT_SECONDS,
                                drain_deadline - now,
                            ),
                        ),
                    )
                    telemetry_observations.append(observed)
                    _record_telemetry_checks(
                        observed,
                        readiness_checks=readiness_checks,
                        worker_unhealthy_checks=worker_unhealthy_checks,
                    )
                    next_telemetry_at = min(
                        deadline,
                        time.monotonic() + telemetry_interval_seconds,
                    )
                    if not observed.complete:
                        stop_reason = "mandatory_api_telemetry_missing"
                        stop_observation_phase = "during_workload"
                    elif observed.readiness is False:
                        stop_reason = "readiness_unhealthy"
                        stop_observation_phase = "during_workload"
                    elif observed.worker_ready is False:
                        stop_reason = "worker_unhealthy"
                        stop_observation_phase = "during_workload"
                    else:
                        evaluate_runtime_telemetry(observed.operations_metrics)
                    now = time.monotonic()

                if stop_reason is not None:
                    drain_deadline = min(
                        drain_deadline,
                        now + shutdown_grace_seconds,
                    )
                remaining = max(0.0, drain_deadline - now)
                wait_timeout = min(0.05, remaining)
                if stop_reason is None and now < deadline:
                    wait_timeout = min(
                        wait_timeout,
                        max(0.0, next_telemetry_at - now),
                    )
                if wait_timeout <= 0:
                    continue
                done, pending = wait(
                    pending,
                    timeout=wait_timeout,
                    return_when=FIRST_COMPLETED,
                )
                completed, task_failed = _consume_request_futures(done, samples)
                completed_request_count += completed
                if task_failed and stop_reason is None:
                    stop_reason = "request_task_failure"
                    stop_observation_phase = "during_workload"
                elif stop_reason is None:
                    evaluate_completed_samples()

            finished_at_shutdown = {future for future in pending if future.done()}
            if finished_at_shutdown:
                completed, task_failed = _consume_request_futures(
                    finished_at_shutdown,
                    samples,
                )
                completed_request_count += completed
                pending.difference_update(finished_at_shutdown)
                if task_failed and stop_reason is None:
                    stop_reason = "request_task_failure"
                    stop_observation_phase = "during_workload"
                elif stop_reason is None:
                    evaluate_completed_samples()
            for future in pending:
                if future.cancel():
                    cancelled_request_count += 1
            abandoned_in_flight_count = sum(
                not future.done() and not future.cancelled() for future in pending
            )
            pool.shutdown(wait=False, cancel_futures=True)
            pool = None
            workload_elapsed = max(time.monotonic() - started, 0.000001)

        after_telemetry = _collect_api_telemetry(
            client,
            headers=headers,
            timeout_seconds=telemetry_timeout,
        )
        telemetry_observations.append(after_telemetry)
        _record_telemetry_checks(
            after_telemetry,
            readiness_checks=readiness_checks,
            worker_unhealthy_checks=worker_unhealthy_checks,
        )
        after_metrics = after_telemetry.operations_metrics
        if stop_reason is None:
            if not after_telemetry.complete:
                stop_reason = "mandatory_api_telemetry_missing"
                stop_observation_phase = "postflight"
            elif after_telemetry.readiness is False:
                stop_reason = "readiness_unhealthy"
                stop_observation_phase = "postflight"
            elif after_telemetry.worker_ready is False:
                stop_reason = "worker_unhealthy"
                stop_observation_phase = "postflight"
        execution_status, execution_payload = _telemetry_response(
            client,
            "/operations/executions?page=1&page_size=100",
            headers=headers,
            timeout_seconds=telemetry_timeout,
        )
        execution_page = execution_payload if execution_status == 200 else None
    finally:
        if pool is not None:
            for future in pending:
                if future.cancel():
                    cancelled_request_count += 1
            pool.shutdown(wait=False, cancel_futures=True)
        client.close()

    report = _summarize(
        profile=profile,
        samples=samples,
        elapsed_seconds=max(workload_elapsed, 0.000001),
        before_metrics=before_metrics,
        after_metrics=after_metrics,
        base_url=normalized_base,
        execution_page=execution_page,
        readiness_checks=tuple(readiness_checks),
        worker_stale_checks=tuple(worker_unhealthy_checks),
    )
    missing_telemetry = sorted(
        {missing for observation in telemetry_observations for missing in observation.missing}
    )
    target_request_count_reached = submitted_request_count == total_planned
    report.update(
        {
            "bounded_wall_clock": True,
            "configured_duration_seconds": profile.duration_seconds,
            "shutdown_grace_seconds": shutdown_grace_seconds,
            "safety_thresholds": asdict(active_thresholds),
            "maximum_in_flight_requests": maximum_in_flight,
            "peak_in_flight_request_count": peak_in_flight_count,
            "planned_workload_request_count": total_planned,
            "submitted_workload_request_count": submitted_request_count,
            "completed_workload_request_count": completed_request_count,
            "cancelled_workload_request_count": cancelled_request_count,
            "abandoned_in_flight_request_count": abandoned_in_flight_count,
            "target_request_count_reached": target_request_count_reached,
            "workload_started": workload_started,
            "deadline_reached": deadline_reached,
            "stop_reason": stop_reason,
            "stop_observation_phase": stop_observation_phase,
            "runtime_safety_reason_codes": list(runtime_safety_reason_codes),
            "maximum_outbox_growth_breach_streak": maximum_outbox_breach_streak,
            "mandatory_api_telemetry_complete": (
                bool(telemetry_observations)
                and all(observation.complete for observation in telemetry_observations)
            ),
            "missing_mandatory_api_telemetry": missing_telemetry,
            "api_telemetry_observation_count": len(telemetry_observations),
            "database_pool_before": _database_pool_metrics(before_metrics),
            "database_pool_after": _database_pool_metrics(after_metrics),
        }
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = report_dir / f"pm8-{profile.name}-{timestamp}.json"
    _write_report(report_path, report)
    return report, report_path


def run_step_load(
    *,
    profile: StepLoadProfile = PM9_STEP_LOAD_PROFILES["capacity"],
    base_url: str = "http://127.0.0.1:8000",
    username: str | None = None,
    password: str | None = None,
    output_dir: Path | None = None,
    mutation_specs: tuple[RequestSpec, ...] = (),
    timeout_seconds: float = 10.0,
    thresholds: SafetyThresholds | None = None,
    runner: StepRunner | None = None,
    monitor: StepMonitor | None = None,
    shutdown_grace_seconds: float = _DEFAULT_SHUTDOWN_GRACE_SECONDS,
    telemetry_interval_seconds: float = _DEFAULT_TELEMETRY_INTERVAL_SECONDS,
    monitor_interval_seconds: float = _DEFAULT_MONITOR_INTERVAL_SECONDS,
    cancellation_event: threading.Event | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run an explicitly enabled, bounded step load and classify the evidence."""

    if os.getenv(_STEP_LOAD_FLAG) != "true":
        raise RuntimeError(f"PM9 step load requires {_STEP_LOAD_FLAG}=true on an approved host.")
    if mutation_specs and os.getenv(_MUTATION_FLAG) != "true":
        raise RuntimeError(
            f"Mutation scenarios require {_MUTATION_FLAG}=true and isolated records."
        )
    normalized_base = _validated_base_url(base_url)
    for spec in (*DEFAULT_READS, *mutation_specs):
        _validated_request_path(spec.path)
    report_dir = _validated_report_directory(output_dir)
    active_thresholds = thresholds or SafetyThresholds()
    if (
        isinstance(shutdown_grace_seconds, bool)
        or not isinstance(shutdown_grace_seconds, (int, float))
        or not math.isfinite(shutdown_grace_seconds)
        or not 0.05 <= shutdown_grace_seconds <= 10
    ):
        raise ValueError("Shutdown grace must be between 0.05 and 10 seconds.")
    if (
        isinstance(telemetry_interval_seconds, bool)
        or not isinstance(telemetry_interval_seconds, (int, float))
        or not math.isfinite(telemetry_interval_seconds)
        or not 0.05 <= telemetry_interval_seconds <= 30
    ):
        raise ValueError("Telemetry interval must be between 0.05 and 30 seconds.")
    if (
        isinstance(monitor_interval_seconds, bool)
        or not isinstance(monitor_interval_seconds, (int, float))
        or not math.isfinite(monitor_interval_seconds)
        or not 0.05 <= monitor_interval_seconds <= 5
    ):
        raise ValueError("Monitor interval must be between 0.05 and 5 seconds.")
    if runner is None and (not username or not password):
        raise RuntimeError("Username and password are required for the HTTP step-load runner.")

    evidence_mode = (
        "synthetic_test_double"
        if runner is not None
        else "synthetic_http_transport"
        if transport is not None
        else "live_http"
    )

    stages: list[dict[str, Any]] = []
    degradation: dict[str, Any] | None = None
    capacity_status = "completed_no_boundary_observed"
    capacity_stop_reasons: tuple[str, ...] = ()
    automatic_safety_stop = False
    for sequence, configured_stage in enumerate(profile.stages, start=1):
        stage_profile = profile.stage_profile(configured_stage)
        try:
            before = _call_monitor(monitor, "before", stage_profile)
        except Exception:  # noqa: BLE001 - report only an allow-listed failure code
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report={},
                before=MonitorSnapshot(),
                after=MonitorSnapshot(),
                reason_codes=("monitor_failure",),
                executed=False,
                workload_started=False,
                stop_phase="before_stage",
                outcome="harness_failure",
            )
            stages.append(entry)
            capacity_status = "harness_failure"
            capacity_stop_reasons = ("monitor_failure",)
            break

        preflight_reasons = _evaluate_safety(
            report={},
            before=before,
            after=before,
            thresholds=active_thresholds,
        )
        if cancellation_event is not None and cancellation_event.is_set():
            preflight_reasons = _ordered_unique((*preflight_reasons, "operator_cancelled"))
        if preflight_reasons:
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report={},
                before=before,
                after=before,
                reason_codes=preflight_reasons,
                executed=False,
                workload_started=False,
                stop_phase="before_stage",
                outcome="preflight_safety_stop",
            )
            stages.append(entry)
            capacity_status = "preflight_safety_stop"
            capacity_stop_reasons = preflight_reasons
            automatic_safety_stop = True
            break

        stage_cancellation = threading.Event()

        def invoke_stage() -> Mapping[str, Any]:
            if runner is not None:
                return runner(stage_profile)
            stage_report, _ = run_profile(
                base_url=normalized_base,
                username=str(username),
                password=str(password),
                profile=stage_profile,
                output_dir=report_dir,
                mutation_specs=mutation_specs,
                timeout_seconds=timeout_seconds,
                shutdown_grace_seconds=shutdown_grace_seconds,
                telemetry_interval_seconds=telemetry_interval_seconds,
                safety_thresholds=active_thresholds,
                cancellation_event=stage_cancellation,
                transport=transport,
            )
            return stage_report

        execution = _execute_stage(
            invoke=invoke_stage,
            stage_profile=stage_profile,
            before=before,
            monitor=monitor,
            thresholds=active_thresholds,
            stage_cancellation=stage_cancellation,
            external_cancellation=cancellation_event,
            shutdown_grace_seconds=shutdown_grace_seconds,
            monitor_interval_seconds=monitor_interval_seconds,
            stage_timeout_seconds=_stage_timeout_seconds(
                stage_profile=stage_profile,
                injected_runner=runner is not None,
                request_timeout_seconds=timeout_seconds,
                shutdown_grace_seconds=shutdown_grace_seconds,
            ),
        )
        if execution.failure_reason is not None or execution.report is None:
            failure_reasons = _ordered_unique(
                (
                    *execution.during_reason_codes,
                    execution.failure_reason or "runner_failure",
                )
            )
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report={},
                before=before,
                after=execution.monitor_snapshot,
                reason_codes=failure_reasons,
                executed=True,
                workload_started=False,
                stop_phase="during_stage",
                outcome="harness_failure",
            )
            stages.append(entry)
            capacity_status = "harness_failure"
            capacity_stop_reasons = failure_reasons
            break

        stage_result = execution.report
        workload_started = _report_workload_started(stage_result)
        after = execution.monitor_snapshot
        if not execution.during_reason_codes:
            try:
                after = _merge_monitor_snapshots(
                    after,
                    _call_monitor(monitor, "after", stage_profile),
                )
            except Exception:  # noqa: BLE001 - never serialize monitor exception text
                entry = _step_report_entry(
                    sequence=sequence,
                    stage_profile=stage_profile,
                    report=stage_result,
                    before=before,
                    after=after,
                    reason_codes=("monitor_failure",),
                    executed=True,
                    workload_started=workload_started,
                    stop_phase="after_stage",
                    outcome="harness_failure",
                )
                stages.append(entry)
                capacity_status = "harness_failure"
                capacity_stop_reasons = ("monitor_failure",)
                break

        if not _mandatory_stage_telemetry_complete(stage_result):
            reason_codes = ("mandatory_api_telemetry_missing",)
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report=stage_result,
                before=before,
                after=after,
                reason_codes=reason_codes,
                executed=True,
                workload_started=workload_started,
                stop_phase="during_stage" if workload_started else "before_stage",
                outcome="inconclusive",
            )
            stages.append(entry)
            capacity_status = "inconclusive"
            capacity_stop_reasons = reason_codes
            automatic_safety_stop = True
            break

        reason_codes = _evaluate_safety(
            report=stage_result,
            before=before,
            after=after,
            thresholds=active_thresholds,
        )
        runtime_reason_codes = _allowlisted_runtime_safety_reason_codes(
            stage_result.get("runtime_safety_reason_codes")
        )
        reason_codes = _ordered_unique(
            (
                *execution.during_reason_codes,
                *runtime_reason_codes,
                *reason_codes,
            )
        )
        reported_stop_reason = _allowlisted_stop_reason(stage_result.get("stop_reason"))
        if stage_result.get("stop_reason") is not None and reported_stop_reason is None:
            reported_stop_reason = "runner_failure"
        if reported_stop_reason in _OBSERVED_STAGE_STOP_REASONS:
            reason_codes = _ordered_unique((*reason_codes, reported_stop_reason))
        if reported_stop_reason in {"request_task_failure", "runner_failure"}:
            failure_reasons = _ordered_unique((*reason_codes, reported_stop_reason))
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report=stage_result,
                before=before,
                after=after,
                reason_codes=failure_reasons,
                executed=True,
                workload_started=workload_started,
                stop_phase="during_stage",
                outcome="harness_failure",
            )
            stages.append(entry)
            capacity_status = "harness_failure"
            capacity_stop_reasons = failure_reasons
            break

        safety_cancellation = "operator_cancelled" in reason_codes
        if (
            stage_result.get("target_request_count_reached") is False
            and not safety_cancellation
            and reported_stop_reason not in _OBSERVED_STAGE_STOP_REASONS
        ):
            reason_codes = _ordered_unique((*reason_codes, "target_rate_not_achieved"))

        if safety_cancellation:
            if not reason_codes:
                reason_codes = ("external_safety_stop",)
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report=stage_result,
                before=before,
                after=after,
                reason_codes=reason_codes,
                executed=True,
                workload_started=workload_started,
                stop_phase="during_stage",
                outcome="inconclusive",
            )
            stages.append(entry)
            capacity_status = "inconclusive"
            capacity_stop_reasons = reason_codes
            automatic_safety_stop = True
            break

        if reason_codes and not workload_started:
            entry = _step_report_entry(
                sequence=sequence,
                stage_profile=stage_profile,
                report=stage_result,
                before=before,
                after=after,
                reason_codes=reason_codes,
                executed=True,
                workload_started=False,
                stop_phase="before_stage",
                outcome="preflight_safety_stop",
            )
            stages.append(entry)
            capacity_status = "preflight_safety_stop"
            capacity_stop_reasons = reason_codes
            automatic_safety_stop = True
            break

        degradation_stop_phase = (
            "during_stage"
            if execution.during_reason_codes
            or (
                (reported_stop_reason in _OBSERVED_STAGE_STOP_REASONS or bool(runtime_reason_codes))
                and _allowlisted_stop_observation_phase(stage_result.get("stop_observation_phase"))
                == "during_workload"
            )
            else "after_stage"
        )
        entry = _step_report_entry(
            sequence=sequence,
            stage_profile=stage_profile,
            report=stage_result,
            before=before,
            after=after,
            reason_codes=reason_codes,
            executed=True,
            workload_started=workload_started,
            stop_phase=degradation_stop_phase if reason_codes else None,
            outcome="observed_degradation" if reason_codes else "completed",
        )
        stages.append(entry)
        if reason_codes:
            degradation = _degradation_point(entry)
            capacity_status = "observed_degradation"
            capacity_stop_reasons = reason_codes
            automatic_safety_stop = True
            break

    completed_all_stages = (
        len(stages) == len(profile.stages) and capacity_status == "completed_no_boundary_observed"
    )
    host_capacity_evidence_eligible = (
        evidence_mode == "live_http"
        and capacity_status in {"completed_no_boundary_observed", "observed_degradation"}
        and all(
            stage["metrics"]["mandatory_api_telemetry_complete"] is True
            for stage in stages
            if stage["executed"]
        )
    )
    report = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "internal-pilot-host-rehearsal",
        "base_url": normalized_base,
        "profile": asdict(profile),
        "thresholds": asdict(active_thresholds),
        "test_assumption_notice": (
            "Profile and stop values are rehearsal assumptions, not measured demand or an SLA."
        ),
        "observed_boundary_only": True,
        "sla_claim": False,
        "production_readiness_claim": False,
        "evidence_mode": evidence_mode,
        "host_capacity_evidence_eligible": host_capacity_evidence_eligible,
        "capacity_evidence_status": capacity_status,
        "capacity_stop_reason_codes": list(capacity_stop_reasons),
        "result_interpretation": (
            "Observed boundary only for this tested host and profile; this is not an "
            "SLA, production-readiness result, or production capacity guarantee."
        ),
        "completed_all_stages": completed_all_stages,
        "automatic_safety_stop": automatic_safety_stop,
        "first_observed_degradation_point": degradation,
        "stages": stages,
    }
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = report_dir / f"pm9-step-load-{profile.name}-{timestamp}.json"
    _write_report(report_path, report)
    return report, report_path


def _execute_stage(
    *,
    invoke: Callable[[], Mapping[str, Any]],
    stage_profile: ReliabilityProfile,
    before: MonitorSnapshot,
    monitor: StepMonitor | None,
    thresholds: SafetyThresholds,
    stage_cancellation: threading.Event,
    external_cancellation: threading.Event | None,
    shutdown_grace_seconds: float,
    monitor_interval_seconds: float,
    stage_timeout_seconds: float,
) -> _StageExecution:
    """Invoke a stage without allowing a non-returning test double to hang the CLI."""

    completed = threading.Event()
    holder: dict[str, Any] = {}

    def target() -> None:
        try:
            holder["report"] = invoke()
        except BaseException:  # noqa: BLE001 - only a fixed failure code is retained
            holder["failed"] = True
        finally:
            completed.set()

    thread = threading.Thread(
        target=target,
        name=f"pm9-load-stage-{stage_profile.name}",
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + stage_timeout_seconds
    observed = before
    during_reasons: tuple[str, ...] = ()
    failure_reason: str | None = None

    while not completed.is_set():
        if external_cancellation is not None and external_cancellation.is_set():
            during_reasons = _ordered_unique((*during_reasons, "operator_cancelled"))
            stage_cancellation.set()
            if not completed.wait(shutdown_grace_seconds):
                failure_reason = "runner_deadline_exceeded"
            break

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            stage_cancellation.set()
            if not completed.wait(shutdown_grace_seconds):
                failure_reason = "runner_deadline_exceeded"
            break
        if completed.wait(min(monitor_interval_seconds, remaining)):
            break
        if monitor is None:
            continue
        try:
            current = _call_monitor(monitor, "during", stage_profile)
        except Exception:  # noqa: BLE001 - never retain external monitor text
            stage_cancellation.set()
            completed.wait(shutdown_grace_seconds)
            failure_reason = "monitor_failure"
            break
        observed = _merge_monitor_snapshots(observed, current)
        current_reasons = _evaluate_safety(
            report={},
            before=before,
            after=observed,
            thresholds=thresholds,
        )
        if current_reasons:
            during_reasons = current_reasons
            stage_cancellation.set()
            if not completed.wait(shutdown_grace_seconds):
                failure_reason = "runner_deadline_exceeded"
            break

    if failure_reason is None and holder.get("failed") is True:
        failure_reason = "runner_failure"
    report = holder.get("report")
    if failure_reason is None and not isinstance(report, Mapping):
        failure_reason = "runner_failure"
        report = None
    return _StageExecution(
        report=report,
        monitor_snapshot=observed,
        during_reason_codes=during_reasons,
        failure_reason=failure_reason,
    )


def _stage_timeout_seconds(
    *,
    stage_profile: ReliabilityProfile,
    injected_runner: bool,
    request_timeout_seconds: float,
    shutdown_grace_seconds: float,
) -> float:
    """Reserve bounded control-plane time without shortening the workload window."""

    if injected_runner:
        return float(stage_profile.duration_seconds)
    telemetry_timeout = min(
        request_timeout_seconds,
        max(_MIN_REQUEST_TIMEOUT_SECONDS, shutdown_grace_seconds / 3),
    )
    return (
        stage_profile.duration_seconds
        + request_timeout_seconds
        + (_STAGE_CONTROL_REQUEST_COUNT * telemetry_timeout)
        + _STAGE_CONTROL_FIXED_ALLOWANCE_SECONDS
    )


def _report_workload_started(report: Mapping[str, Any]) -> bool:
    explicit = report.get("workload_started")
    if isinstance(explicit, bool):
        return explicit
    total_requests = _nonnegative_int(report.get("total_requests"))
    return total_requests is not None and total_requests > 0


def _mandatory_stage_telemetry_complete(report: Mapping[str, Any]) -> bool:
    if report.get("mandatory_api_telemetry_complete") is not True:
        return False
    if _database_pool_metrics(report.get("database_pool_before")) is None:
        return False
    if _database_pool_metrics(report.get("database_pool_after")) is None:
        return False
    return _valid_outbox_summary(report.get("outbox_before")) and (
        _valid_outbox_summary(report.get("outbox_after"))
    )


def _valid_outbox_summary(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    pending = _nonnegative_int(value.get("pending_outbox_count"))
    dead_letter = _nonnegative_int(value.get("dead_letter_outbox_count"))
    if "oldest_pending_outbox_age_seconds" not in value:
        return False
    oldest = value.get("oldest_pending_outbox_age_seconds")
    valid_oldest = oldest is None or _nonnegative_int(oldest) is not None
    return pending is not None and dead_letter is not None and valid_oldest


def _allowlisted_outbox_summary(value: Any) -> dict[str, Any] | None:
    if not _valid_outbox_summary(value):
        return None
    assert isinstance(value, Mapping)
    return {
        "pending_outbox_count": value["pending_outbox_count"],
        "dead_letter_outbox_count": value["dead_letter_outbox_count"],
        "oldest_pending_outbox_age_seconds": value["oldest_pending_outbox_age_seconds"],
    }


def _allowlisted_stop_reason(value: Any) -> str | None:
    return value if isinstance(value, str) and value in _SAFE_STAGE_STOP_REASONS else None


def _allowlisted_runtime_safety_reason_codes(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return _ordered_unique(
        tuple(
            reason
            for reason in value
            if isinstance(reason, str) and reason in _OBSERVED_STAGE_STOP_REASONS
        )
    )


def _allowlisted_stop_observation_phase(value: Any) -> str | None:
    return value if isinstance(value, str) and value in _SAFE_STOP_OBSERVATION_PHASES else None


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _merge_monitor_snapshots(
    previous: MonitorSnapshot,
    current: MonitorSnapshot,
) -> MonitorSnapshot:
    readiness_values = (previous.readiness, current.readiness)
    worker_values = (previous.worker_stale, current.worker_stale)
    return MonitorSnapshot(
        readiness=(
            False if False in readiness_values else True if True in readiness_values else None
        ),
        worker_stale=(True if True in worker_values else False if False in worker_values else None),
        pending_outbox_count=(
            current.pending_outbox_count
            if current.pending_outbox_count is not None
            else previous.pending_outbox_count
        ),
        database_pool_timeout_count=(
            current.database_pool_timeout_count
            if current.database_pool_timeout_count is not None
            else previous.database_pool_timeout_count
        ),
        host_cpu_percent=_maximum_supplied(
            previous.host_cpu_percent,
            current.host_cpu_percent,
        ),
        host_memory_percent=_maximum_supplied(
            previous.host_memory_percent,
            current.host_memory_percent,
        ),
        operator_cancelled=(previous.operator_cancelled or current.operator_cancelled),
    )


def _login(client: httpx.Client, *, username: str, password: str) -> str:
    response = client.post("/auth/login", json={"identifier": username, "password": password})
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Login response did not include an access token.")
    return str(token)


def _sample_request(
    client: httpx.Client,
    spec: RequestSpec,
    headers: dict[str, str],
    *,
    timeout_seconds: float | None = None,
) -> Sample:
    request_headers = dict(headers)
    if spec.idempotency_key:
        request_headers["Idempotency-Key"] = spec.idempotency_key
    started = time.perf_counter()
    try:
        request_arguments: dict[str, Any] = {
            "headers": request_headers,
            "json": spec.json_body,
        }
        if timeout_seconds is not None:
            request_arguments["timeout"] = timeout_seconds
        response = client.request(spec.method, spec.path, **request_arguments)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if response.status_code in spec.expected_statuses:
            outcome = (
                "expected_authorization_failure"
                if response.status_code in {401, 403}
                else "success"
            )
        elif response.status_code == 503:
            outcome = "database_connection_failure"
        else:
            outcome = "unexpected_failure"
        replay = False
        if response.status_code < 400:
            try:
                payload = response.json()
                replay = isinstance(payload, dict) and payload.get("created") is False
            except ValueError:
                replay = False
        return Sample(
            spec.path,
            response.status_code,
            elapsed_ms,
            outcome,
            idempotent_replay=replay,
        )
    except httpx.TimeoutException:
        return Sample(
            spec.path,
            None,
            (time.perf_counter() - started) * 1000,
            "timeout",
        )
    except httpx.HTTPError:
        return Sample(
            spec.path,
            None,
            (time.perf_counter() - started) * 1000,
            "connection_failure",
        )


def _summarize(
    *,
    profile: ReliabilityProfile,
    samples: list[Sample],
    elapsed_seconds: float,
    before_metrics: dict[str, Any] | None,
    after_metrics: dict[str, Any] | None,
    base_url: str,
    execution_page: dict[str, Any] | None = None,
    readiness_checks: tuple[bool, ...] = (),
    worker_stale_checks: tuple[bool, ...] = (),
) -> dict[str, Any]:
    latencies = sorted(sample.elapsed_ms for sample in samples)
    outcomes = Counter(sample.outcome for sample in samples)
    statuses = Counter(
        str(sample.status_code) for sample in samples if sample.status_code is not None
    )
    unexpected_error_count = sum(
        outcomes[outcome]
        for outcome in (
            "unexpected_failure",
            "timeout",
            "connection_failure",
            "database_connection_failure",
        )
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "internal-pilot-local-validation",
        "production_readiness_claim": False,
        "base_url": base_url,
        "profile": asdict(profile),
        "test_assumption_notice": (
            "Profile values are test assumptions, not measured customer demand or an SLA."
        ),
        "total_requests": len(samples),
        "successes": outcomes["success"],
        "expected_authorization_failures": outcomes["expected_authorization_failure"],
        "unexpected_error_rate": round(unexpected_error_count / len(samples), 6)
        if samples
        else 0.0,
        "unexpected_failures": outcomes["unexpected_failure"],
        "timeouts": outcomes["timeout"],
        "connection_failures": outcomes["connection_failure"],
        "database_connection_failures": outcomes["database_connection_failure"],
        "duplicate_idempotent_results": sum(sample.idempotent_replay for sample in samples),
        "throughput_requests_per_second": round(len(samples) / elapsed_seconds, 3),
        "latency_ms": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
            "max": round(latencies[-1], 3) if latencies else None,
        },
        "status_counts": dict(sorted(statuses.items())),
        "outbox_before": _outbox_metrics(before_metrics),
        "outbox_after": _outbox_metrics(after_metrics),
        "worker_execution_status_counts": _execution_status_counts(execution_page),
        "readiness_false_count": sum(value is False for value in readiness_checks),
        "worker_stale_observations": sum(value is True for value in worker_stale_checks),
    }


def _runtime_performance_safety_reasons(
    *,
    samples: list[Sample],
    thresholds: SafetyThresholds,
) -> tuple[str, ...]:
    if not samples:
        return ()

    reasons: list[str] = []
    unexpected_count = sum(
        sample.outcome
        in {
            "unexpected_failure",
            "timeout",
            "connection_failure",
            "database_connection_failure",
        }
        for sample in samples
    )
    unexpected_error_rate = unexpected_count / len(samples)
    if unexpected_error_rate > thresholds.max_unexpected_error_rate:
        reasons.append("unexpected_error_rate")

    latencies = sorted(sample.elapsed_ms for sample in samples)
    p95 = _percentile(latencies, 95)
    if p95 is not None and p95 > thresholds.max_p95_latency_ms:
        reasons.append("p95_latency_ceiling")

    timeout_count = sum(sample.outcome == "timeout" for sample in samples)
    if timeout_count >= thresholds.repeated_timeout_limit:
        reasons.append("repeated_timeouts")
    return tuple(reasons)


def _runtime_telemetry_safety_reasons(
    *,
    baseline_metrics: Mapping[str, Any] | None,
    current_metrics: Mapping[str, Any] | None,
    thresholds: SafetyThresholds,
    prior_outbox_breach_streak: int,
) -> tuple[tuple[str, ...], int]:
    baseline_pending = _outbox_metric_count(
        baseline_metrics,
        "pending_outbox_count",
    )
    current_pending = _outbox_metric_count(
        current_metrics,
        "pending_outbox_count",
    )
    baseline_dead_letter = _outbox_metric_count(
        baseline_metrics,
        "dead_letter_outbox_count",
    )
    current_dead_letter = _outbox_metric_count(
        current_metrics,
        "dead_letter_outbox_count",
    )
    if (
        baseline_pending is None
        or current_pending is None
        or baseline_dead_letter is None
        or current_dead_letter is None
    ):
        return (), 0

    reasons: list[str] = []
    if current_dead_letter > baseline_dead_letter:
        reasons.append("dead_letter_growth")

    pending_growth = max(0, current_pending - baseline_pending)
    if pending_growth > thresholds.max_unrecovered_outbox_growth:
        outbox_breach_streak = prior_outbox_breach_streak + 1
    else:
        outbox_breach_streak = 0
    if outbox_breach_streak >= _OUTBOX_GROWTH_BREACH_OBSERVATIONS:
        reasons.append("unrecovered_outbox_growth")
    return tuple(reasons), outbox_breach_streak


def _evaluate_safety(
    *,
    report: Mapping[str, Any],
    before: MonitorSnapshot,
    after: MonitorSnapshot,
    thresholds: SafetyThresholds,
) -> tuple[str, ...]:
    reasons: list[str] = []
    unexpected_error_rate = _unexpected_error_rate(report)
    if unexpected_error_rate > thresholds.max_unexpected_error_rate:
        reasons.append("unexpected_error_rate")

    latency = report.get("latency_ms")
    p95 = _finite_number(latency.get("p95")) if isinstance(latency, Mapping) else None
    if p95 is not None and p95 > thresholds.max_p95_latency_ms:
        reasons.append("p95_latency_ceiling")

    request_timeouts = _nonnegative_int(report.get("timeouts")) or 0
    pool_timeouts = _counter_growth(
        before.database_pool_timeout_count,
        after.database_pool_timeout_count,
    )
    if max(request_timeouts, pool_timeouts) >= thresholds.repeated_timeout_limit:
        reasons.append("repeated_timeouts")

    report_readiness_failures = _nonnegative_int(report.get("readiness_false_count")) or 0
    monitor_readiness_failures = sum(snapshot.readiness is False for snapshot in (before, after))
    if (
        max(report_readiness_failures, monitor_readiness_failures)
        >= thresholds.repeated_readiness_failure_limit
    ):
        reasons.append("readiness_unhealthy")

    report_worker_stale = _nonnegative_int(report.get("worker_stale_observations")) or 0
    monitor_worker_stale = sum(snapshot.worker_stale is True for snapshot in (before, after))
    if max(report_worker_stale, monitor_worker_stale) > thresholds.max_worker_stale_observations:
        reasons.append("worker_stale")

    dead_letter_before = _outbox_count_from_report(
        report,
        "outbox_before",
        "dead_letter_outbox_count",
    )
    dead_letter_after = _outbox_count_from_report(
        report,
        "outbox_after",
        "dead_letter_outbox_count",
    )
    if _counter_growth(dead_letter_before, dead_letter_after) > 0:
        reasons.append("dead_letter_growth")

    pending_before = (
        before.pending_outbox_count
        if before.pending_outbox_count is not None
        else _pending_outbox_from_report(report, "outbox_before")
    )
    pending_after = (
        after.pending_outbox_count
        if after.pending_outbox_count is not None
        else _pending_outbox_from_report(report, "outbox_after")
    )
    outbox_growth = _counter_growth(pending_before, pending_after)
    if outbox_growth > thresholds.max_unrecovered_outbox_growth:
        reasons.append("unrecovered_outbox_growth")

    host_cpu = _maximum_supplied(
        before.host_cpu_percent,
        after.host_cpu_percent,
    )
    if host_cpu is not None and host_cpu > thresholds.max_host_cpu_percent:
        reasons.append("host_cpu_threshold")
    host_memory = _maximum_supplied(
        before.host_memory_percent,
        after.host_memory_percent,
    )
    if host_memory is not None and host_memory > thresholds.max_host_memory_percent:
        reasons.append("host_memory_threshold")
    if before.operator_cancelled or after.operator_cancelled:
        reasons.append("operator_cancelled")
    return tuple(reasons)


def _step_report_entry(
    *,
    sequence: int,
    stage_profile: ReliabilityProfile,
    report: Mapping[str, Any],
    before: MonitorSnapshot,
    after: MonitorSnapshot,
    reason_codes: tuple[str, ...],
    executed: bool,
    workload_started: bool,
    stop_phase: str | None,
    outcome: str,
) -> dict[str, Any]:
    readiness_false_observations = max(
        _nonnegative_int(report.get("readiness_false_count")) or 0,
        sum(snapshot.readiness is False for snapshot in (before, after)),
    )
    worker_stale_observations = max(
        _nonnegative_int(report.get("worker_stale_observations")) or 0,
        sum(snapshot.worker_stale is True for snapshot in (before, after)),
    )
    pending_outbox_before = (
        before.pending_outbox_count
        if before.pending_outbox_count is not None
        else _pending_outbox_from_report(report, "outbox_before")
    )
    pending_outbox_after = (
        after.pending_outbox_count
        if after.pending_outbox_count is not None
        else _pending_outbox_from_report(report, "outbox_after")
    )
    return {
        "sequence": sequence,
        "target_requests_per_second": stage_profile.requests_per_second,
        "concurrent_users": stage_profile.concurrent_users,
        "duration_seconds": stage_profile.duration_seconds,
        "executed": executed,
        "workload_started": workload_started,
        "outcome": outcome,
        "metrics": _allowlisted_step_metrics(report),
        "monitor": {
            "readiness_false_observations": readiness_false_observations,
            "worker_stale_observations": worker_stale_observations,
            "pending_outbox_before": pending_outbox_before,
            "pending_outbox_after": pending_outbox_after,
            "database_pool_timeout_growth": _counter_growth(
                before.database_pool_timeout_count,
                after.database_pool_timeout_count,
            ),
            "host_cpu_percent_max": _maximum_supplied(
                before.host_cpu_percent,
                after.host_cpu_percent,
            ),
            "host_memory_percent_max": _maximum_supplied(
                before.host_memory_percent,
                after.host_memory_percent,
            ),
        },
        "safety_threshold_crossed": (
            bool(reason_codes) and outcome in {"preflight_safety_stop", "observed_degradation"}
        ),
        "safety_reason_codes": list(reason_codes),
        "stop_phase": stop_phase,
    }


def _degradation_point(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "target_requests_per_second": entry["target_requests_per_second"],
        "concurrent_users": entry["concurrent_users"],
        "reason_codes": entry["safety_reason_codes"],
        "stop_phase": entry["stop_phase"],
    }


def _allowlisted_step_metrics(report: Mapping[str, Any]) -> dict[str, Any]:
    latency = report.get("latency_ms")
    latency_percentiles = {
        name: _finite_number(latency.get(name)) if isinstance(latency, Mapping) else None
        for name in ("p50", "p95", "p99")
    }
    return {
        "total_requests": _nonnegative_int(report.get("total_requests")),
        "throughput_requests_per_second": _finite_number(
            report.get("throughput_requests_per_second")
        ),
        "latency_ms": latency_percentiles,
        "expected_authorization_failures": _nonnegative_int(
            report.get("expected_authorization_failures")
        ),
        "unexpected_error_rate": _unexpected_error_rate(report),
        "unexpected_failures": _nonnegative_int(report.get("unexpected_failures")),
        "timeouts": _nonnegative_int(report.get("timeouts")),
        "connection_failures": _nonnegative_int(report.get("connection_failures")),
        "database_connection_failures": _nonnegative_int(
            report.get("database_connection_failures")
        ),
        "planned_workload_request_count": _nonnegative_int(
            report.get("planned_workload_request_count")
        ),
        "submitted_workload_request_count": _nonnegative_int(
            report.get("submitted_workload_request_count")
        ),
        "completed_workload_request_count": _nonnegative_int(
            report.get("completed_workload_request_count")
        ),
        "cancelled_workload_request_count": _nonnegative_int(
            report.get("cancelled_workload_request_count")
        ),
        "abandoned_in_flight_request_count": _nonnegative_int(
            report.get("abandoned_in_flight_request_count")
        ),
        "maximum_in_flight_requests": _nonnegative_int(report.get("maximum_in_flight_requests")),
        "peak_in_flight_request_count": _nonnegative_int(
            report.get("peak_in_flight_request_count")
        ),
        "target_request_count_reached": (
            report.get("target_request_count_reached")
            if isinstance(report.get("target_request_count_reached"), bool)
            else None
        ),
        "mandatory_api_telemetry_complete": (
            report.get("mandatory_api_telemetry_complete")
            if isinstance(report.get("mandatory_api_telemetry_complete"), bool)
            else None
        ),
        "api_telemetry_observation_count": _nonnegative_int(
            report.get("api_telemetry_observation_count")
        ),
        "database_pool_before": _database_pool_metrics(report.get("database_pool_before")),
        "database_pool_after": _database_pool_metrics(report.get("database_pool_after")),
        "outbox_before": _allowlisted_outbox_summary(report.get("outbox_before")),
        "outbox_after": _allowlisted_outbox_summary(report.get("outbox_after")),
        "stop_reason": _allowlisted_stop_reason(report.get("stop_reason")),
        "runtime_safety_reason_codes": list(
            _allowlisted_runtime_safety_reason_codes(report.get("runtime_safety_reason_codes"))
        ),
        "maximum_outbox_growth_breach_streak": _nonnegative_int(
            report.get("maximum_outbox_growth_breach_streak")
        ),
        "stop_observation_phase": _allowlisted_stop_observation_phase(
            report.get("stop_observation_phase")
        ),
    }


def _unexpected_error_rate(report: Mapping[str, Any]) -> float:
    explicit_rate = _finite_number(report.get("unexpected_error_rate"))
    if explicit_rate is not None:
        return min(1.0, max(0.0, explicit_rate))
    total = _nonnegative_int(report.get("total_requests")) or 0
    if total == 0:
        return 0.0
    unexpected = sum(
        _nonnegative_int(report.get(key)) or 0
        for key in (
            "unexpected_failures",
            "timeouts",
            "connection_failures",
            "database_connection_failures",
        )
    )
    return round(unexpected / total, 6)


def _call_monitor(
    monitor: StepMonitor | None,
    phase: str,
    profile: ReliabilityProfile,
) -> MonitorSnapshot:
    if monitor is None:
        return MonitorSnapshot()
    value = monitor(phase, profile)
    if isinstance(value, MonitorSnapshot):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("Step monitor must return MonitorSnapshot or a mapping.")
    allowed = {
        field: value[field]
        for field in (
            "readiness",
            "worker_stale",
            "pending_outbox_count",
            "database_pool_timeout_count",
            "host_cpu_percent",
            "host_memory_percent",
            "operator_cancelled",
        )
        if field in value
    }
    return MonitorSnapshot(**allowed)


def _counter_growth(before: int | None, after: int | None) -> int:
    if before is None or after is None:
        return 0
    return max(0, after - before)


def _pending_outbox_from_report(
    report: Mapping[str, Any],
    key: str,
) -> int | None:
    return _outbox_count_from_report(
        report,
        key,
        "pending_outbox_count",
    )


def _outbox_count_from_report(
    report: Mapping[str, Any],
    report_key: str,
    metric_key: str,
) -> int | None:
    metrics = report.get(report_key)
    return _outbox_metric_count(metrics, metric_key)


def _outbox_metric_count(
    metrics: Mapping[str, Any] | None,
    key: str,
) -> int | None:
    if not isinstance(metrics, Mapping):
        return None
    return _nonnegative_int(metrics.get(key))


def _maximum_supplied(*values: float | None) -> float | None:
    supplied = [value for value in values if value is not None]
    return max(supplied) if supplied else None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    index = min(
        len(values) - 1,
        max(0, math.ceil((percentile / 100) * len(values)) - 1),
    )
    return round(values[index], 3)


def _collect_api_telemetry(
    client: httpx.Client,
    *,
    headers: dict[str, str],
    timeout_seconds: float,
) -> _ApiTelemetry:
    missing: list[str] = []

    readiness_status_code, readiness_payload = _telemetry_response(
        client,
        "/health/ready",
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
    readiness = (
        _readiness_status(readiness_payload) if readiness_status_code in {200, 503} else None
    )
    if readiness is None:
        missing.append("readiness")

    worker_status_code, worker_payload = _telemetry_response(
        client,
        "/health/worker",
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
    worker_ready = (
        _worker_ready_status(worker_payload) if worker_status_code in {200, 503} else None
    )
    if worker_ready is None:
        missing.append("worker_health")

    metrics_status_code, metrics_payload = _telemetry_response(
        client,
        "/operations/metrics",
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
    operations_metrics = (
        metrics_payload
        if metrics_status_code == 200 and _valid_operations_metrics_payload(metrics_payload)
        else None
    )
    if operations_metrics is None:
        missing.append("operations_metrics")
    if _database_pool_metrics(metrics_payload) is None:
        missing.append("database_pool")

    return _ApiTelemetry(
        readiness=readiness,
        worker_ready=worker_ready,
        operations_metrics=operations_metrics,
        missing=tuple(missing),
    )


def _telemetry_response(
    client: httpx.Client,
    path: str,
    *,
    headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[int | None, dict[str, Any] | None]:
    try:
        response = client.get(
            path,
            headers=headers,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError:
        return None, None
    return response.status_code, _response_json(response)


def _record_telemetry_checks(
    telemetry: _ApiTelemetry,
    *,
    readiness_checks: list[bool],
    worker_unhealthy_checks: list[bool],
) -> None:
    if telemetry.readiness is not None:
        readiness_checks.append(telemetry.readiness)
    if telemetry.worker_ready is not None:
        worker_unhealthy_checks.append(not telemetry.worker_ready)


def _consume_request_futures(
    futures: set[Future[Sample]],
    samples: list[Sample],
) -> tuple[int, bool]:
    task_failed = False
    for future in futures:
        try:
            sample = future.result()
        except Exception:  # noqa: BLE001 - retain only a fixed harness failure code
            task_failed = True
            continue
        if not isinstance(sample, Sample):
            task_failed = True
            continue
        samples.append(sample)
    return len(futures), task_failed


def _valid_operations_metrics_payload(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if _nonnegative_int(value.get("pending_outbox_count")) is None:
        return False
    if _nonnegative_int(value.get("dead_letter_outbox_count")) is None:
        return False
    if "oldest_pending_outbox_age_seconds" not in value:
        return False
    oldest = value["oldest_pending_outbox_age_seconds"]
    return oldest is None or (_nonnegative_int(oldest) is not None and not isinstance(oldest, bool))


def _database_pool_metrics(value: Any) -> dict[str, int] | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get("database_pool", value)
    if not isinstance(candidate, Mapping):
        return None
    metrics = {
        key: _nonnegative_int(candidate.get(key)) for key in ("size", "checked_out", "overflow")
    }
    if any(metric is None for metric in metrics.values()):
        return None
    return {key: int(metric) for key, metric in metrics.items() if metric is not None}


def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
    if response.status_code != 200:
        return None
    return _response_json(response)


def _response_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        value = response.json()
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _readiness_status(payload: dict[str, Any] | None) -> bool | None:
    if payload is None:
        return None
    status = payload.get("status")
    if status not in {"ready", "degraded"}:
        return None
    database_ready = payload.get("database_ready")
    worker_ready = payload.get("worker_ready")
    if not isinstance(database_ready, bool) or not isinstance(worker_ready, bool):
        return None
    return status == "ready" and database_ready and worker_ready


def _worker_ready_status(payload: dict[str, Any] | None) -> bool | None:
    if payload is None:
        return None
    status = payload.get("status")
    ready = payload.get("ready")
    if status not in {
        "ready",
        "starting",
        "stopping",
        "error",
        "stale",
        "missing",
    } or not isinstance(ready, bool):
        return None
    return status == "ready" and ready


def _worker_stale_status(payload: dict[str, Any] | None) -> bool | None:
    ready = _worker_ready_status(payload)
    if ready is None:
        return None
    return not ready


def _outbox_metrics(metrics: dict[str, Any] | None) -> dict[str, Any] | None:
    if metrics is None:
        return None
    return {
        key: metrics.get(key)
        for key in (
            "pending_outbox_count",
            "oldest_pending_outbox_age_seconds",
            "dead_letter_outbox_count",
        )
    }


def _execution_status_counts(
    page: dict[str, Any] | None,
) -> dict[str, int] | None:
    if page is None or not isinstance(page.get("items"), list):
        return None
    return dict(
        Counter(
            str(item.get("status"))
            for item in page["items"]
            if isinstance(item, dict) and item.get("status")
        )
    )


def _validated_report_directory(output_dir: Path | None) -> Path:
    report_dir = (
        output_dir or Path(tempfile.gettempdir()) / "ai-maintenance-copilot-reliability"
    ).resolve()
    if report_dir == _REPOSITORY_ROOT or report_dir.is_relative_to(_REPOSITORY_ROOT):
        raise ValueError("Reliability reports must be written outside the repository.")
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def _select_spec(
    index: int,
    profile: ReliabilityProfile,
    mutations: tuple[RequestSpec, ...],
) -> RequestSpec:
    if mutations and profile.mutation_share > 0:
        interval = max(1, round(1 / profile.mutation_share))
        if index % interval == 0:
            return mutations[(index // interval) % len(mutations)]
    return DEFAULT_READS[index % len(DEFAULT_READS)]


def _load_mutations(path: Path | None) -> tuple[RequestSpec, ...]:
    if path is None:
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) > 20:
        raise ValueError("Mutation fixture must be a JSON list of at most 20 requests.")
    specs = []
    for item in raw:
        method = str(item["method"]).upper()
        request_path = _validated_request_path(str(item["path"]))
        specs.append(
            RequestSpec(
                method=method,
                path=request_path,
                expected_statuses=tuple(item.get("expected_statuses", [200])),
                json_body=item.get("json_body"),
                idempotency_key=(
                    str(item.get("idempotency_key") or f"pm8-{uuid4()}")
                    if method != "GET"
                    else None
                ),
            )
        )
    return tuple(specs)


def _validated_base_url(value: str) -> str:
    """Return a credential-free HTTP origin safe to include in a report."""

    if value != value.strip():
        raise ValueError("Base URL must not contain surrounding whitespace.")
    parsed = urlsplit(value)
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Base URL contains an invalid port.") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Base URL must be a credential-free HTTP(S) origin without a path, query, or fragment."
        )
    return f"{parsed.scheme}://{parsed.netloc}"


def _validated_request_path(value: str) -> str:
    """Reject absolute or network-path targets that could receive the bearer token."""

    parsed = urlsplit(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
    ):
        raise ValueError(
            "Reliability request targets must be local absolute paths without "
            "a scheme, host, backslash, or fragment."
        )
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password-env", default="PM8_TEST_PASSWORD")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="baseline")
    parser.add_argument(
        "--step-load-profile",
        choices=sorted(PM9_STEP_LOAD_PROFILES),
        help=(
            "Explicit PM9 capacity rehearsal; also requires "
            f"{_STEP_LOAD_FLAG}=true on an approved host."
        ),
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--mutation-fixture", type=Path)
    args = parser.parse_args()
    password = os.getenv(args.password_env)
    if not password:
        raise RuntimeError(f"{args.password_env} must provide the test password.")
    mutations = _load_mutations(args.mutation_fixture)
    if args.step_load_profile:
        report, path = run_step_load(
            base_url=args.base_url,
            username=args.username,
            password=password,
            profile=PM9_STEP_LOAD_PROFILES[args.step_load_profile],
            output_dir=args.output_dir,
            mutation_specs=mutations,
        )
        point = report["first_observed_degradation_point"]
        observed = point["target_requests_per_second"] if point is not None else "not-observed"
        print(
            "PM9 observed-boundary-only step load: "
            f"first_degradation_rps={observed} report={path}; "
            "not an SLA or production claim."
        )
        return
    report, path = run_profile(
        base_url=args.base_url,
        username=args.username,
        password=password,
        profile=PROFILES[args.profile],
        output_dir=args.output_dir,
        mutation_specs=mutations,
    )
    print(
        f"PM8 {args.profile}: requests={report['total_requests']} "
        f"failures={report['unexpected_failures']} report={path}"
    )


if __name__ == "__main__":
    main()

"""Wall-clock-bounded authenticated load-profile execution workflow."""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import threading
import time
from typing import Any

import httpx

from .contracts import SafetyThresholds, Sample
from .execution_limits import (
    DEFAULT_SHUTDOWN_GRACE_SECONDS as _DEFAULT_SHUTDOWN_GRACE_SECONDS,
    DEFAULT_TELEMETRY_INTERVAL_SECONDS as _DEFAULT_TELEMETRY_INTERVAL_SECONDS,
    EXTENDED_FLAG as _EXTENDED_FLAG,
    MAX_IN_FLIGHT_MULTIPLIER as _MAX_IN_FLIGHT_MULTIPLIER,
    MIN_REQUEST_TIMEOUT_SECONDS as _MIN_REQUEST_TIMEOUT_SECONDS,
    MUTATION_FLAG as _MUTATION_FLAG,
)
from .http_sampling import _consume_request_futures, _login, _sample_request
from .metrics import _database_pool_metrics
from .profile_reporting import _summarize
from .profiles import ReliabilityProfile
from .report_storage import _validated_report_directory, _write_report
from .reporting import _ordered_unique
from .request_contracts import (
    DEFAULT_READS,
    RequestSpec,
    _select_spec,
    _validated_base_url,
    _validated_request_path,
)
from .safety import _runtime_performance_safety_reasons, _runtime_telemetry_safety_reasons
from .telemetry import (
    _ApiTelemetry,
    _collect_api_telemetry,
    _record_telemetry_checks,
    _telemetry_response,
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

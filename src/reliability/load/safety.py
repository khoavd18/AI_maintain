"""Deterministic stop-reason policy for the bounded load harness."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.reliability.load.contracts import MonitorSnapshot, SafetyThresholds, Sample
from src.reliability.load.metrics import (
    _counter_growth,
    _finite_number,
    _maximum_supplied,
    _nonnegative_int,
    _outbox_count_from_report,
    _outbox_metric_count,
    _pending_outbox_from_report,
    _percentile,
    _unexpected_error_rate,
)


_OUTBOX_GROWTH_BREACH_OBSERVATIONS = 2


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

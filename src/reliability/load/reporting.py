"""Allow-listed, secret-free report projection for bounded load stages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.reliability.load.contracts import MonitorSnapshot
from src.reliability.load.metrics import (
    _counter_growth,
    _database_pool_metrics,
    _finite_number,
    _maximum_supplied,
    _nonnegative_int,
    _pending_outbox_from_report,
    _unexpected_error_rate,
)
from src.reliability.load.profiles import ReliabilityProfile


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

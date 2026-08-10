"""Immutable observation and safety-threshold contracts for the load harness."""

from __future__ import annotations

from dataclasses import dataclass
import math


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

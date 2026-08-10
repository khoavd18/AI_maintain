"""Profile-level report projection from bounded load observations."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .contracts import Sample
from .metrics import _percentile
from .profiles import ReliabilityProfile
from .telemetry import _execution_status_counts, _outbox_metrics


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

"""Fail-closed numeric metric interpretation for load reports and safety policy."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any


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

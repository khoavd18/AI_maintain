"""Process-local safe API telemetry for the single-instance internal pilot."""

from __future__ import annotations

from collections import deque
import math
import threading


class ApiRequestMetrics:
    """Keep bounded aggregate latency/error samples without labels or payloads."""

    def __init__(self, max_samples: int = 10_000) -> None:
        self._lock = threading.Lock()
        self._latencies_ms: deque[int] = deque(maxlen=max_samples)
        self._request_count = 0
        self._error_count = 0
        self._service_unavailable_count = 0

    def record(self, *, duration_ms: int, status_code: int) -> None:
        with self._lock:
            self._request_count += 1
            self._latencies_ms.append(max(0, duration_ms))
            if status_code >= 500:
                self._error_count += 1
            if status_code == 503:
                self._service_unavailable_count += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            values = sorted(self._latencies_ms)
            return {
                "request_count": self._request_count,
                "error_count": self._error_count,
                "service_unavailable_count": self._service_unavailable_count,
                "latency_ms": {
                    "p50": _percentile(values, 50),
                    "p95": _percentile(values, 95),
                    "p99": _percentile(values, 99),
                },
                "sample_count": len(values),
            }

    def reset(self) -> None:
        """Reset process-local counters for isolated tests."""

        with self._lock:
            self._latencies_ms.clear()
            self._request_count = 0
            self._error_count = 0
            self._service_unavailable_count = 0


def _percentile(values: list[int], percentile: int) -> int | None:
    if not values:
        return None
    index = min(
        len(values) - 1,
        max(0, math.ceil((percentile / 100) * len(values)) - 1),
    )
    return values[index]


api_request_metrics = ApiRequestMetrics()

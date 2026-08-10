"""Read-only API telemetry observation and parsing for the load harness."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from src.reliability.load.metrics import _database_pool_metrics, _nonnegative_int


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

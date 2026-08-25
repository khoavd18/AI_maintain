"""Short authenticated concurrent benchmark for Stage 10 read-only analytics."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import time
from typing import Any
from uuid import UUID

import httpx
import psycopg

from data_platform.config import DataPlatformSettings
from data_platform.database import connect


UTC = timezone.utc
MAX_CLIENTS = 50
MAX_REQUESTS_PER_CLIENT = 10


@dataclass(frozen=True, slots=True)
class RequestSample:
    path: str
    status_code: int
    latency_ms: float
    valid_analytics_payload: bool
    error_class: str | None = None
    response_bytes: int = 0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _postgres_activity(settings: DataPlatformSettings) -> dict[str, int]:
    with connect(settings, read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT coalesce(state, 'unknown') AS state,
                   count(*)::integer,
                   count(*) FILTER (
                       WHERE state = 'active' AND wait_event_type IS NOT NULL
                   )::integer
            FROM pg_stat_activity
            WHERE datname = current_database() AND pid <> pg_backend_pid()
            GROUP BY state
            """
        ).fetchall()
    activity = {
        "total": 0,
        "active": 0,
        "idle": 0,
        "idle_in_transaction": 0,
        "waiting": 0,
    }
    for state, count, waiting in rows:
        normalized = str(state).replace(" ", "_")
        activity["total"] += int(count)
        activity["waiting"] += int(waiting)
        if normalized in activity:
            activity[normalized] += int(count)
    return activity


def _postgres_connections(settings: DataPlatformSettings) -> int:
    """Preserve the Stage 10 total-connection helper for callers and tests."""

    return _postgres_activity(settings)["total"]


def _container_observation(container: str) -> dict[str, str] | None:
    try:
        result = subprocess.run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{.CPUPerc}}|{{.MemUsage}}|{{.PIDs}}",
                container,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    values = result.stdout.strip().split("|")
    if len(values) != 3:
        return None
    return {"cpu_percent": values[0], "memory": values[1], "pids": values[2]}


async def _monitor_connections(
    settings: DataPlatformSettings,
    stop: asyncio.Event,
) -> dict[str, Any]:
    samples: list[dict[str, int]] = []
    sample_errors = 0
    while not stop.is_set():
        try:
            samples.append(await asyncio.to_thread(_postgres_activity, settings))
        except psycopg.OperationalError:
            sample_errors += 1
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.1)
        except TimeoutError:
            pass
    try:
        samples.append(await asyncio.to_thread(_postgres_activity, settings))
    except psycopg.OperationalError:
        sample_errors += 1
    return {"samples": samples, "sample_errors": sample_errors}


async def _request(
    client: httpx.AsyncClient,
    path: str,
) -> RequestSample:
    started = time.perf_counter()
    try:
        response = await client.get(path)
        latency = (time.perf_counter() - started) * 1_000
        valid = False
        if path.startswith("/analytics/domain/") and response.status_code == 200:
            payload = response.json()
            valid = isinstance(payload, list) and bool(payload)
        elif path == "/health" and response.status_code == 200:
            valid = isinstance(response.json(), dict)
        error_class = None if 200 <= response.status_code < 300 else f"http_{response.status_code}"
        return RequestSample(
            path,
            response.status_code,
            latency,
            valid,
            error_class,
            len(response.content),
        )
    except httpx.TimeoutException:
        return RequestSample(
            path,
            0,
            (time.perf_counter() - started) * 1_000,
            False,
            "timeout",
        )
    except httpx.HTTPError as exc:
        return RequestSample(
            path,
            0,
            (time.perf_counter() - started) * 1_000,
            False,
            type(exc).__name__,
        )


async def _runtime_observations(
    *,
    base_url: str,
    token: str,
    samples: int = 4,
) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = []
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(samples):
        observation: dict[str, object] = {}
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers=headers,
        ) as client:
            operations = await client.get("/operations/metrics")
            if operations.status_code == 200:
                payload = operations.json()
                if isinstance(payload, dict):
                    observation["database_pool"] = payload.get("database_pool")
                    observation["api_requests"] = payload.get("api_requests")
            analytics = await client.get("/analytics/domain/metrics/runtime")
            if analytics.status_code == 200:
                payload = analytics.json()
                if isinstance(payload, dict):
                    observation["domain_analytics"] = payload
        observations.append(observation)
    return observations


async def run_scenario(
    *,
    base_url: str,
    username: str,
    password: str,
    clients: int,
    requests_per_client: int,
    start_date: date,
    end_date: date,
    site_id: UUID | None,
    settings: DataPlatformSettings,
    container: str = "stage10-api",
) -> dict[str, Any]:
    """Run one bounded scenario using one real authenticated access token."""

    if not 1 <= clients <= MAX_CLIENTS:
        raise ValueError(f"clients must be between 1 and {MAX_CLIENTS}.")
    if not 1 <= requests_per_client <= MAX_REQUESTS_PER_CLIENT:
        raise ValueError(
            f"requests_per_client must be between 1 and {MAX_REQUESTS_PER_CLIENT}."
        )
    timeout = httpx.Timeout(35.0, connect=5.0)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as login_client:
        login_response = await login_client.post(
            "/auth/login",
            json={"identifier": username, "password": password},
        )
        login_response.raise_for_status()
        token = login_response.json().get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Authenticated benchmark login returned no access token.")

    observability_before = await _runtime_observations(
        base_url=base_url,
        token=token,
    )
    query = f"start_date={start_date.isoformat()}&end_date={end_date.isoformat()}&limit=25"
    if site_id is not None:
        query += f"&site_id={site_id}"
    paths = (
        "/health",
        f"/analytics/domain/maintenance_summary?{query}",
        f"/analytics/domain/site_reliability?{query}",
        f"/analytics/domain/ticket_sla?{query}",
        f"/analytics/domain/technician_workload?{query}",
        f"/analytics/domain/inventory_consumption?{query}",
        f"/analytics/domain/maintenance_cost_variance?{query}",
    )
    before_container = await asyncio.to_thread(_container_observation, container)
    before_activity = await asyncio.to_thread(_postgres_activity, settings)
    stop = asyncio.Event()
    monitor = asyncio.create_task(_monitor_connections(settings, stop))
    samples: list[RequestSample] = []
    started = time.perf_counter()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        headers=headers,
        limits=httpx.Limits(max_connections=clients, max_keepalive_connections=clients),
    ) as client:
        tasks = [
            asyncio.create_task(_request(client, paths[(worker + request) % len(paths)]))
            for worker in range(clients)
            for request in range(requests_per_client)
        ]
        for result in await asyncio.gather(*tasks):
            samples.append(result)
    duration = time.perf_counter() - started
    stop.set()
    connection_monitor = await monitor
    connection_samples = connection_monitor["samples"]
    after_activity = await asyncio.to_thread(_postgres_activity, settings)
    after_container = await asyncio.to_thread(_container_observation, container)
    observability_after = await _runtime_observations(
        base_url=base_url,
        token=token,
    )

    latencies = [sample.latency_ms for sample in samples]
    successes = sum(200 <= sample.status_code < 300 for sample in samples)
    analytics_samples = [
        sample for sample in samples if sample.path.startswith("/analytics/domain/")
    ]
    valid_analytics = sum(sample.valid_analytics_payload for sample in analytics_samples)
    status_distribution = Counter(str(sample.status_code) for sample in samples)
    error_classes = Counter(
        sample.error_class for sample in samples if sample.error_class is not None
    )
    endpoint_metrics: dict[str, dict[str, Any]] = {}
    for endpoint in sorted({sample.path.split("?", 1)[0] for sample in samples}):
        endpoint_samples = [
            sample for sample in samples if sample.path.split("?", 1)[0] == endpoint
        ]
        endpoint_latencies = [sample.latency_ms for sample in endpoint_samples]
        endpoint_metrics[endpoint] = {
            "requests": len(endpoint_samples),
            "latency_ms": {
                "p50": round(_percentile(endpoint_latencies, 0.50), 4),
                "p95": round(_percentile(endpoint_latencies, 0.95), 4),
                "p99": round(_percentile(endpoint_latencies, 0.99), 4),
                "maximum": round(max(endpoint_latencies, default=0.0), 4),
            },
            "status_distribution": dict(
                sorted(Counter(str(sample.status_code) for sample in endpoint_samples).items())
            ),
            "response_bytes": sum(sample.response_bytes for sample in endpoint_samples),
        }
    activity_maximum = {
        key: max((sample[key] for sample in connection_samples), default=before_activity[key])
        for key in before_activity
    }
    return {
        "clients": clients,
        "requests_per_client": requests_per_client,
        "requests": len(samples),
        "duration_seconds": round(duration, 6),
        "requests_per_second": round(len(samples) / max(duration, 0.001), 4),
        "latency_ms": {
            "p50": round(_percentile(latencies, 0.50), 4),
            "p95": round(_percentile(latencies, 0.95), 4),
            "p99": round(_percentile(latencies, 0.99), 4),
            "maximum": round(max(latencies, default=0.0), 4),
        },
        "success_count": successes,
        "error_count": len(samples) - successes,
        "error_rate_percent": round(100.0 * (len(samples) - successes) / len(samples), 4),
        "status_distribution": dict(sorted(status_distribution.items())),
        "error_classes": dict(sorted(error_classes.items())),
        "timeout_count": error_classes.get("timeout", 0),
        "analytics_request_count": len(analytics_samples),
        "valid_nonempty_analytics_count": valid_analytics,
        "endpoint_metrics": endpoint_metrics,
        "authentication": "real_bearer_token_from_login",
        "postgres_connections": {
            "before": before_activity["total"],
            "maximum_observed": activity_maximum["total"],
            "after": after_activity["total"],
            "sample_count": len(connection_samples),
            "sample_errors": connection_monitor["sample_errors"],
        },
        "postgres_activity": {
            "before": before_activity,
            "maximum_observed": activity_maximum,
            "after": after_activity,
            "sample_count": len(connection_samples),
            "sample_errors": connection_monitor["sample_errors"],
        },
        "container_observation": {
            "before": before_container,
            "after": after_container,
        },
        "runtime_observability": {
            "before": observability_before,
            "after": observability_after,
        },
        "started_at": datetime.now(UTC).isoformat(),
    }


async def _main_async(args: argparse.Namespace) -> dict[str, Any]:
    password = os.getenv("STAGE10_BENCHMARK_PASSWORD")
    if not password:
        raise RuntimeError("STAGE10_BENCHMARK_PASSWORD is required and is never printed.")
    settings = DataPlatformSettings.from_env()
    scenarios = []
    for index, clients in enumerate((25, 50)):
        scenarios.append(
            await run_scenario(
                base_url=args.base_url,
                username=args.username,
                password=password,
                clients=clients,
                requests_per_client=args.requests_per_client,
                start_date=args.start_date,
                end_date=args.end_date,
                site_id=args.site_id,
                settings=settings,
                container=args.container,
            )
        )
        if index == 0 and args.stabilization_seconds:
            await asyncio.sleep(args.stabilization_seconds)
    return {
        "benchmark": "stage10_authenticated_domain_analytics",
        "pipeline_state": args.pipeline_state,
        "production_sla_claim": False,
        "site_scope": str(args.site_id) if args.site_id is not None else None,
        "stabilization_seconds": args.stabilization_seconds,
        "scenarios": scenarios,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18082")
    parser.add_argument("--username", required=True)
    parser.add_argument("--requests-per-client", type=int, default=4)
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2024, 1, 1))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2024, 12, 31))
    parser.add_argument("--site-id", type=UUID)
    parser.add_argument("--container", default="stage10-api")
    parser.add_argument("--stabilization-seconds", type=int, choices=range(0, 61), default=0)
    parser.add_argument("--pipeline-state", choices=("idle", "running"), default="idle")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(_main_async(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": args.output.as_posix(),
                "scenarios": [
                    {
                        "clients": row["clients"],
                        "requests": row["requests"],
                        "requests_per_second": row["requests_per_second"],
                        "error_rate_percent": row["error_rate_percent"],
                    }
                    for row in result["scenarios"]
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

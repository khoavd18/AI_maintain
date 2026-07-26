"""Small authenticated HTTP reliability harness for a dedicated pilot test stack."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
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

from src.reliability.profiles import PROFILES, ReliabilityProfile

_MUTATION_FLAG = "PM8_ALLOW_MUTATIONS"
_EXTENDED_FLAG = "PM8_ALLOW_EXTENDED_TESTS"


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
) -> tuple[dict[str, Any], Path]:
    """Run one bounded profile and emit only a summarized JSON report."""

    if profile.extended and os.getenv(_EXTENDED_FLAG) != "true":
        raise RuntimeError(
            f"{profile.name} requires {_EXTENDED_FLAG}=true."
        )
    if mutation_specs and os.getenv(_MUTATION_FLAG) != "true":
        raise RuntimeError(
            f"Mutation scenarios require {_MUTATION_FLAG}=true and isolated records."
        )
    report_dir = (output_dir or (
        Path(tempfile.gettempdir()) / "ai-maintenance-copilot-reliability"
    )).resolve()
    repository = Path.cwd().resolve()
    if report_dir == repository or report_dir.is_relative_to(repository):
        raise ValueError("Reliability reports must be written outside the repository.")
    report_dir.mkdir(parents=True, exist_ok=True)
    normalized_base = _validated_base_url(base_url)
    for spec in (*DEFAULT_READS, *mutation_specs):
        _validated_request_path(spec.path)
    samples: list[Sample] = []
    sample_lock = threading.Lock()

    with httpx.Client(base_url=normalized_base, timeout=timeout_seconds) as client:
        token = _login(client, username=username, password=password)
        headers = {"Authorization": f"Bearer {token}"}
        before_metrics = _safe_json(client.get("/operations/metrics", headers=headers))
        unauthorized = _sample_request(
            client,
            RequestSpec("GET", "/notifications", (401,)),
            {},
        )
        samples.append(unauthorized)
        total_planned = max(
            1, math.ceil(profile.requests_per_second * profile.duration_seconds)
        )
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=profile.concurrent_users) as pool:
            futures = []
            for index in range(total_planned):
                target_time = started + (index / profile.requests_per_second)
                delay = target_time - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                spec = _select_spec(index, profile, mutation_specs)
                futures.append(
                    pool.submit(_sample_request, client, spec, headers)
                )
            for future in as_completed(futures):
                sample = future.result()
                with sample_lock:
                    samples.append(sample)
        elapsed = max(time.monotonic() - started, 0.000001)
        after_metrics = _safe_json(client.get("/operations/metrics", headers=headers))
        execution_page = _safe_json(
            client.get(
                "/operations/executions?page=1&page_size=100",
                headers=headers,
            )
        )

    report = _summarize(
        profile=profile,
        samples=samples,
        elapsed_seconds=elapsed,
        before_metrics=before_metrics,
        after_metrics=after_metrics,
        base_url=normalized_base,
        execution_page=execution_page,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = report_dir / f"pm8-{profile.name}-{timestamp}.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return report, report_path


def _login(client: httpx.Client, *, username: str, password: str) -> str:
    response = client.post(
        "/auth/login", json={"identifier": username, "password": password}
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Login response did not include an access token.")
    return str(token)


def _sample_request(
    client: httpx.Client,
    spec: RequestSpec,
    headers: dict[str, str],
) -> Sample:
    request_headers = dict(headers)
    if spec.idempotency_key:
        request_headers["Idempotency-Key"] = spec.idempotency_key
    started = time.perf_counter()
    try:
        response = client.request(
            spec.method,
            spec.path,
            headers=request_headers,
            json=spec.json_body,
        )
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
) -> dict[str, Any]:
    latencies = sorted(sample.elapsed_ms for sample in samples)
    outcomes = Counter(sample.outcome for sample in samples)
    statuses = Counter(
        str(sample.status_code) for sample in samples if sample.status_code is not None
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
        "expected_authorization_failures": outcomes[
            "expected_authorization_failure"
        ],
        "unexpected_failures": outcomes["unexpected_failure"],
        "timeouts": outcomes["timeout"],
        "connection_failures": outcomes["connection_failure"],
        "database_connection_failures": outcomes["database_connection_failure"],
        "duplicate_idempotent_results": sum(
            sample.idempotent_replay for sample in samples
        ),
        "throughput_requests_per_second": round(
            len(samples) / elapsed_seconds, 3
        ),
        "latency_ms": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
            "max": round(latencies[-1], 3) if latencies else None,
        },
        "status_counts": dict(sorted(statuses.items())),
        "outbox_before": _outbox_metrics(before_metrics),
        "outbox_after": _outbox_metrics(after_metrics),
        "worker_execution_status_counts": _execution_status_counts(
            execution_page
        ),
    }


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    index = min(
        len(values) - 1,
        max(0, math.ceil((percentile / 100) * len(values)) - 1),
    )
    return round(values[index], 3)


def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
    if response.status_code != 200:
        return None
    value = response.json()
    return value if isinstance(value, dict) else None


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
            "Base URL must be a credential-free HTTP(S) origin without a path, "
            "query, or fragment."
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
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--mutation-fixture", type=Path)
    args = parser.parse_args()
    password = os.getenv(args.password_env)
    if not password:
        raise RuntimeError(f"{args.password_env} must provide the test password.")
    report, path = run_profile(
        base_url=args.base_url,
        username=args.username,
        password=password,
        profile=PROFILES[args.profile],
        output_dir=args.output_dir,
        mutation_specs=_load_mutations(args.mutation_fixture),
    )
    print(
        f"PM8 {args.profile}: requests={report['total_requests']} "
        f"failures={report['unexpected_failures']} report={path}"
    )


if __name__ == "__main__":
    main()

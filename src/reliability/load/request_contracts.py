"""Validated load-harness request plans and mutation fixtures."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from .profiles import ReliabilityProfile


@dataclass(frozen=True)
class RequestSpec:
    method: str
    path: str
    expected_statuses: tuple[int, ...] = (200,)
    json_body: dict[str, Any] | None = None
    idempotency_key: str | None = None


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
            "Base URL must be a credential-free HTTP(S) origin without a path, query, or fragment."
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

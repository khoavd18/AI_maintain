"""Authenticated HTTP sampling and bounded future-result handling."""

from __future__ import annotations

from concurrent.futures import Future
import time
from typing import Any

import httpx

from .contracts import Sample
from .request_contracts import RequestSpec


def _login(client: httpx.Client, *, username: str, password: str) -> str:
    response = client.post("/auth/login", json={"identifier": username, "password": password})
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Login response did not include an access token.")
    return str(token)


def _sample_request(
    client: httpx.Client,
    spec: RequestSpec,
    headers: dict[str, str],
    *,
    timeout_seconds: float | None = None,
) -> Sample:
    request_headers = dict(headers)
    if spec.idempotency_key:
        request_headers["Idempotency-Key"] = spec.idempotency_key
    started = time.perf_counter()
    try:
        request_arguments: dict[str, Any] = {
            "headers": request_headers,
            "json": spec.json_body,
        }
        if timeout_seconds is not None:
            request_arguments["timeout"] = timeout_seconds
        response = client.request(spec.method, spec.path, **request_arguments)
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


def _consume_request_futures(
    futures: set[Future[Sample]],
    samples: list[Sample],
) -> tuple[int, bool]:
    task_failed = False
    for future in futures:
        try:
            sample = future.result()
        except Exception:  # noqa: BLE001 - retain only a fixed harness failure code
            task_failed = True
            continue
        if not isinstance(sample, Sample):
            task_failed = True
            continue
        samples.append(sample)
    return len(futures), task_failed

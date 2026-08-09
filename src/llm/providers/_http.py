"""Bounded HTTP helper shared by side-effect-free generation providers."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

import httpx

from src.llm.base import LLMProviderError, LLMTimeoutError, LLMUnavailableError

MAX_PROVIDER_RESPONSE_BYTES = 2 * 1024 * 1024
_STREAM_CHUNK_BYTES = 64 * 1024
_TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def post_json(
    *,
    url: str,
    payload: Mapping[str, Any],
    headers: Mapping[str, str],
    timeout_seconds: int,
    max_retries: int,
    client: httpx.Client | None,
) -> dict[str, Any]:
    """POST JSON with bounded transient retries and public-safe failures."""

    owns_client = client is None
    http_client = client or httpx.Client(
        timeout=httpx.Timeout(timeout_seconds),
        follow_redirects=False,
    )
    try:
        for attempt in range(max_retries + 1):
            try:
                with http_client.stream(
                    "POST",
                    url,
                    json=dict(payload),
                    headers=dict(headers),
                ) as response:
                    if response.status_code in _TRANSIENT_STATUS_CODES and attempt < max_retries:
                        continue
                    if response.status_code >= 400:
                        raise LLMProviderError("Nhà cung cấp LLM từ chối yêu cầu tạo phản hồi.")
                    return _read_bounded_json(response)
            except httpx.TimeoutException as exc:
                if attempt < max_retries:
                    continue
                raise LLMTimeoutError("Nhà cung cấp LLM vượt quá thời gian cho phép.") from exc
            except httpx.TransportError as exc:
                if attempt < max_retries:
                    continue
                raise LLMUnavailableError("Không thể kết nối nhà cung cấp LLM.") from exc
    finally:
        if owns_client:
            http_client.close()
    raise LLMProviderError("Nhà cung cấp LLM không hoàn tất yêu cầu.")


def _read_bounded_json(response: httpx.Response) -> dict[str, Any]:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = 0
        if declared_size > MAX_PROVIDER_RESPONSE_BYTES:
            raise _response_too_large()

    body = bytearray()
    for chunk in response.iter_bytes(chunk_size=_STREAM_CHUNK_BYTES):
        if len(body) + len(chunk) > MAX_PROVIDER_RESPONSE_BYTES:
            raise _response_too_large()
        body.extend(chunk)
    try:
        value = json.loads(body)
    except ValueError as exc:
        raise LLMProviderError("Nhà cung cấp LLM trả về JSON không hợp lệ.") from exc
    if not isinstance(value, dict):
        raise LLMProviderError("Nhà cung cấp LLM trả về cấu trúc không hợp lệ.")
    return value


def _response_too_large() -> LLMProviderError:
    return LLMProviderError("Phản hồi LLM vượt giới hạn kích thước cho phép.")

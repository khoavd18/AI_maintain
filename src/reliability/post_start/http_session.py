"""Bounded authenticated HTTP session and cleanup operations."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

import httpx

from .preflight import PostStartValidationError
from .response_contracts import _bearer, _nonnegative_int, _optional_cookie_value

_MAX_RESPONSE_BYTES = 1024 * 1024


def _login(
    client: httpx.Client,
    *,
    username: str,
    password: str,
) -> Mapping[str, Any]:
    return _request_json(
        client,
        "POST",
        "/auth/login",
        expected_status=200,
        expected_type=dict,
        json_body={"identifier": username, "password": password},
    )


def _logout_if_session_exists(
    client: httpx.Client,
    *,
    revocation_client: httpx.Client,
    refresh_cookie_name: str,
    csrf_cookie_name: str,
    access_token: str | None,
) -> bool:
    try:
        refresh = _optional_cookie_value(client, refresh_cookie_name)
        csrf = _optional_cookie_value(client, csrf_cookie_name)
        if refresh is None and csrf is None:
            return True
        if refresh is None or csrf is None:
            raise PostStartValidationError("Authentication session cookies are incomplete.")
        _expect_status(
            client,
            "POST",
            "/auth/logout",
            expected_status=204,
            headers={"X-CSRF-Token": csrf},
        )
        if access_token is not None:
            _expect_status(
                client,
                "GET",
                "/auth/me",
                expected_status=401,
                headers=_bearer(access_token),
            )
        _expect_refresh_rejected(
            revocation_client,
            refresh_cookie_name=refresh_cookie_name,
            csrf_cookie_name=csrf_cookie_name,
            refresh_token=refresh,
            csrf_token=csrf,
        )
    except (PostStartValidationError, httpx.HTTPError, ValueError):
        return False
    return True


def _expect_refresh_rejected(
    client: httpx.Client,
    *,
    refresh_cookie_name: str,
    csrf_cookie_name: str,
    refresh_token: str,
    csrf_token: str,
) -> None:
    _expect_status(
        client,
        "POST",
        "/auth/refresh",
        expected_status=401,
        headers={
            "X-CSRF-Token": csrf_token,
            "Cookie": (f"{refresh_cookie_name}={refresh_token}; {csrf_cookie_name}={csrf_token}"),
        },
    )


def _authenticated_identity(
    client: httpx.Client,
    access_token: str,
) -> Mapping[str, Any]:
    return _request_json(
        client,
        "GET",
        "/auth/me",
        expected_status=200,
        expected_type=dict,
        headers=_bearer(access_token),
    )


def _unread_count(client: httpx.Client, access_token: str) -> int:
    payload = _request_json(
        client,
        "GET",
        "/notifications/unread-count",
        expected_status=200,
        expected_type=dict,
        headers=_bearer(access_token),
    )
    return _nonnegative_int(payload.get("unread_count"))


def _request_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    expected_status: int,
    expected_type: type[dict] | type[list],
    headers: Mapping[str, str] | None = None,
    json_body: Mapping[str, Any] | None = None,
) -> Any:
    response = client.request(
        method,
        path,
        headers=dict(headers or {}),
        json=dict(json_body) if json_body is not None else None,
    )
    _validate_response(response, expected_status=expected_status)
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        raise PostStartValidationError("API returned invalid JSON.") from None
    if not isinstance(payload, expected_type):
        raise PostStartValidationError("API returned an unexpected JSON shape.")
    return payload


def _expect_status(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    expected_status: int,
    headers: Mapping[str, str] | None = None,
) -> None:
    response = client.request(method, path, headers=dict(headers or {}))
    _validate_response(response, expected_status=expected_status)


def _validate_response(response: httpx.Response, *, expected_status: int) -> None:
    if response.status_code != expected_status:
        raise PostStartValidationError("API returned an unexpected status.")
    if len(response.content) > _MAX_RESPONSE_BYTES:
        raise PostStartValidationError("API response exceeds the bounded smoke limit.")

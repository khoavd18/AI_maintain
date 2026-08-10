"""Post-start API response identity, authorization, and aggregate contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from .preflight import PostStartValidationError


def _require_release_identity(
    payload: Mapping[str, Any],
    expected: Mapping[str, str],
) -> None:
    release = payload.get("release")
    if not isinstance(release, Mapping):
        raise PostStartValidationError("Health response omits release identity.")
    if any(release.get(name) != value for name, value in expected.items()):
        raise PostStartValidationError(
            "Runtime release identity does not match the intended release."
        )


def _access_token(payload: Mapping[str, Any]) -> str:
    token = payload.get("access_token")
    if not isinstance(token, str) or not token or len(token) > 8192:
        raise PostStartValidationError("Authentication response has no bounded token.")
    return token


def _permission_set(identity: Mapping[str, Any]) -> frozenset[str]:
    permissions = identity.get("permissions")
    if not isinstance(permissions, list) or any(
        not isinstance(value, str) for value in permissions
    ):
        raise PostStartValidationError("Authenticated permission set is invalid.")
    return frozenset(permissions)


def _role(identity: Mapping[str, Any]) -> str:
    role = identity.get("role")
    if not isinstance(role, str) or not role or len(role) > 100:
        raise PostStartValidationError("Authenticated role is invalid.")
    return role


def _notification_ids(page: Mapping[str, Any]) -> frozenset[str]:
    items = page.get("items")
    if not isinstance(items, list):
        raise PostStartValidationError("Notification page has no item list.")
    ids: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
            raise PostStartValidationError("Notification page contains an invalid row.")
        identifier = item["id"]
        if identifier in ids:
            raise PostStartValidationError("Notification page contains a duplicate record.")
        ids.add(identifier)
    return frozenset(ids)


def _cookie_value(client: httpx.Client, name: str) -> str:
    value = _optional_cookie_value(client, name)
    if value is None:
        raise PostStartValidationError("Authentication session cookie is unavailable.")
    return value


def _optional_cookie_value(client: httpx.Client, name: str) -> str | None:
    values = [cookie.value for cookie in client.cookies.jar if cookie.name == name]
    if not values:
        return None
    if len(values) != 1 or not values[0] or len(values[0]) > 8192:
        raise PostStartValidationError("Authentication session cookie is unavailable.")
    return values[0]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PostStartValidationError("API aggregate count is invalid.")
    return value

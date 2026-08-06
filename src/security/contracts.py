"""ORM-free ports for security transaction families."""

from __future__ import annotations

from typing import Protocol


class SessionRevocationPort(Protocol):
    """Complete single-session logout/revocation operation."""

    def logout(
        self,
        *,
        refresh_token: str | None,
        csrf_token: str | None,
        request_id: str,
    ) -> None:
        """Revoke one authenticated refresh session when the request is valid."""

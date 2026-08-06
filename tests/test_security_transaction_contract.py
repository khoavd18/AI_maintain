"""Contract-level checks for the extracted logout transaction family."""

from __future__ import annotations

from typing import get_type_hints

from src.security.contracts import SessionRevocationPort


def test_session_revocation_port_is_orm_free_and_application_facing() -> None:
    hints = get_type_hints(SessionRevocationPort.logout)

    assert set(hints) == {"refresh_token", "csrf_token", "request_id", "return"}
    assert hints["refresh_token"] == str | None
    assert hints["csrf_token"] == str | None
    assert hints["request_id"] is str
    assert hints["return"] is type(None)
    assert all(
        name not in repr(annotation)
        for annotation in hints.values()
        for name in ("Session", "User", "RefreshSession", "SQLAlchemy")
    )

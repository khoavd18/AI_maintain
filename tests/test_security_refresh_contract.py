"""Application-facing refresh-rotation contract characterization."""

from __future__ import annotations

from inspect import signature

from src.security.service import AuthResult, AuthService


def test_refresh_contract_has_no_persistence_or_transport_parameters() -> None:
    parameters = signature(AuthService.refresh).parameters
    assert list(parameters) == [
        "self",
        "refresh_token",
        "csrf_token",
        "user_agent",
        "request_id",
    ]
    assert "AuthResult" in repr(signature(AuthService.refresh).return_annotation)
    assert all(
        name not in repr(parameter.annotation)
        for parameter in parameters.values()
        for name in ("Session", "User", "RefreshSession", "FastAPI", "Request")
    )
    assert AuthResult.__module__ == "src.security.service"

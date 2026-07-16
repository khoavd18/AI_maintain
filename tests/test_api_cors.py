"""Focused tests for browser access to the read-only API."""

from fastapi.testclient import TestClient

from src.api.main import create_app


def test_cors_allows_configured_nextjs_origin() -> None:
    client = TestClient(create_app())

    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "GET" in response.headers["access-control-allow-methods"]


def test_cors_does_not_allow_unlisted_origin() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/health",
        headers={"Origin": "http://untrusted.example"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers

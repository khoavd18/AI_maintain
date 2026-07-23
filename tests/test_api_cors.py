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
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "GET" in response.headers["access-control-allow-methods"]


def test_cors_does_not_allow_unlisted_origin() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/health",
        headers={"Origin": "http://untrusted.example"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_allows_local_write_methods() -> None:
    client = TestClient(create_app())

    for origin in ["http://localhost:3000", "http://127.0.0.1:3000"]:
        for method in ["POST", "PATCH"]:
            response = client.options(
                "/tickets",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": "authorization,content-type,x-csrf-token",
                },
            )

            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin
            assert method in response.headers["access-control-allow-methods"]
            assert "Content-Type" in response.headers["access-control-allow-headers"]
            assert "Authorization" in response.headers["access-control-allow-headers"]
            assert "X-CSRF-Token" in response.headers["access-control-allow-headers"]

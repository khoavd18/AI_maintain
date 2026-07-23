"""Smoke tests for the FastAPI application."""

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api.routes import _service
from src.api.services import ProcessedDataService


def test_health_endpoint_returns_ok() -> None:
    """The API should expose a minimal health endpoint."""

    app = create_app()
    app.dependency_overrides[_service] = lambda: ProcessedDataService()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "raw_data_available": True,
        "analytics_available": True,
    }

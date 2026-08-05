"""Smoke tests for the FastAPI application."""

from fastapi.testclient import TestClient

from src.api.main import create_app
import src.api.routes as api_routes
from src.api.routes import _service
from src.api.services import ProcessedDataService
from src.rag.vector_store import VectorStoreError


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


def test_rag_readiness_reports_collection_contract(monkeypatch) -> None:
    class ReadyStore:
        def __init__(self, **kwargs) -> None:
            pass

        def check_health(self, *, expected_vector_size: int) -> None:
            assert expected_vector_size == 384

    monkeypatch.setattr(api_routes, "QdrantVectorStore", ReadyStore)
    client = TestClient(create_app())

    response = client.get("/health/rag")

    assert response.status_code == 200
    assert response.json()["qdrant_ready"] is True


def test_rag_readiness_is_503_when_qdrant_is_not_ready(monkeypatch) -> None:
    class UnavailableStore:
        def __init__(self, **kwargs) -> None:
            pass

        def check_health(self, *, expected_vector_size: int) -> None:
            raise VectorStoreError("private detail")

    monkeypatch.setattr(api_routes, "QdrantVectorStore", UnavailableStore)
    client = TestClient(create_app())

    response = client.get("/health/rag")

    assert response.status_code == 503
    assert response.json()["qdrant_ready"] is False
    assert "private" not in response.text

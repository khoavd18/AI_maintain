"""Tests for the RAG Copilot FastAPI endpoint."""

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api.routes import _copilot_service
from src.api.services import AssetNotFoundError
from src.rag.copilot import SAFE_FALLBACK, CopilotAnswer, MaintenanceCopilot
from src.rag.vector_store import QdrantUnavailableError


def test_copilot_ask_endpoint_shape() -> None:
    """The copilot endpoint should return answer, context, sources, and chunks."""

    app = create_app()
    app.dependency_overrides[_copilot_service] = lambda: FakeCopilot()
    client = TestClient(app)

    response = client.post(
        "/copilot/ask",
        json={
            "question": "Vì sao GENERATOR_002 đang rủi ro cao?",
            "asset_id": "GENERATOR_002",
            "top_k": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert {"answer", "asset_context", "sources", "retrieved_chunks"}.issubset(payload)
    assert "dữ liệu rủi ro" in payload["answer"]
    assert payload["sources"][0]["doc_id"] == "DOC-001"
    assert {"retrieval_status", "relevance_status", "safety_notice", "filters_applied"}.issubset(
        payload
    )


def test_copilot_api_returns_safe_fallback_when_qdrant_is_unavailable() -> None:
    """RAG availability should not turn the Copilot response into an internal error."""

    app = create_app()
    app.dependency_overrides[_copilot_service] = lambda: MaintenanceCopilot(
        ApiAssetService(),
        UnavailableApiRetriever(),
    )
    client = TestClient(app)

    response = client.post(
        "/copilot/ask",
        json={
            "question": "Thiết bị này cần kiểm tra gì trước?",
            "asset_id": "GENERATOR_002",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["retrieval_status"] == "unavailable"
    assert payload["sources"] == []
    assert SAFE_FALLBACK in payload["answer"]
    assert "internal" not in response.text


def test_copilot_api_handles_invalid_asset_and_question_length() -> None:
    """Invalid asset IDs and oversized questions should use explicit HTTP errors."""

    app = create_app()
    app.dependency_overrides[_copilot_service] = lambda: MissingAssetCopilot()
    client = TestClient(app)

    invalid_asset = client.post(
        "/copilot/ask",
        json={"question": "Thiết bị này cần kiểm tra gì?", "asset_id": "UNKNOWN_999"},
    )
    oversized = client.post(
        "/copilot/ask",
        json={"question": "x" * 1001},
    )

    assert invalid_asset.status_code == 404
    assert oversized.status_code == 422


class FakeCopilot:
    """Small fake copilot for route tests."""

    def ask(
        self,
        question: str,
        asset_id: str | None = None,
        top_k: int = 5,
    ) -> CopilotAnswer:
        return CopilotAnswer(
            answer="Trả lời dựa trên dữ liệu rủi ro và SOP.",
            asset_context={"asset_id": asset_id},
            sources=[
                {
                    "doc_id": "DOC-001",
                    "title": "Checklist",
                    "doc_type": "Danh sách kiểm tra",
                    "asset_type": "Máy phát điện dự phòng",
                    "source": "Checklist nội bộ",
                    "score": 0.9,
                }
            ],
            retrieved_chunks=[
                {
                    "chunk_id": "chunk-1",
                    "doc_id": "DOC-001",
                    "text": "kiểm tra nhiên liệu",
                    "score": 0.9,
                }
            ],
        )


class ApiAssetService:
    """Minimal structured context for API fallback testing."""

    def get_asset_context(self, asset_id: str) -> dict[str, object]:
        return {
            "asset_id": asset_id,
            "latest_risk": {
                "asset_id": asset_id,
                "asset_name": "Máy phát điện 002",
                "asset_type": "Máy phát điện dự phòng",
                "location": "Tầng hầm B1",
                "final_risk_score": 81.0,
                "risk_level": "Khẩn cấp",
                "main_reasons": "Bảo trì quá hạn.",
            },
            "recent_anomalies": [],
            "latest_recommendation": "Ưu tiên kiểm tra.",
        }


class UnavailableApiRetriever:
    """Simulate an unavailable Qdrant connection without external services."""

    minimum_relevance_score = 0.55

    def search(self, *args: object, **kwargs: object) -> list[object]:
        raise QdrantUnavailableError("internal connection detail")


class MissingAssetCopilot:
    """Simulate structured asset validation failure at the route boundary."""

    def ask(self, *args: object, **kwargs: object) -> CopilotAnswer:
        raise AssetNotFoundError("Unknown asset_id: UNKNOWN_999")

"""Tests for the RAG Copilot FastAPI endpoint."""

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api.routes import _copilot_service
from src.rag.copilot import CopilotAnswer


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

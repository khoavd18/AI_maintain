"""Tests for the deterministic RAG Maintenance Copilot pipeline."""

from pathlib import Path
from typing import Any

import pandas as pd
from qdrant_client import QdrantClient

from src.rag.chunking import chunk_document, chunk_documents
from src.rag.copilot import MaintenanceCopilot
from src.rag.document_loader import MaintenanceDocument, load_documents
from src.rag.embeddings import HashEmbeddingProvider, prefix_passage, prefix_query
from src.rag.retriever import QdrantRetriever, RetrievalResult
from src.rag.vector_store import QdrantVectorStore, VectorSearchResult


def test_load_documents_reads_required_fields(tmp_path: Path) -> None:
    """documents.csv rows should load into typed maintenance documents."""

    document_path = tmp_path / "documents.csv"
    pd.DataFrame(
        [
            {
                "doc_id": "DOC-001",
                "title": "Checklist máy lạnh",
                "doc_type": "Danh sách kiểm tra",
                "asset_type": "Máy lạnh",
                "source": "Checklist nội bộ",
                "raw_text": "raw",
                "clean_text": "kiểm tra lưới lọc và ghi lại dòng điện",
                "created_at": "2026-06-01T09:00:00+00:00",
            }
        ]
    ).to_csv(document_path, index=False)

    documents = load_documents(document_path)

    assert len(documents) == 1
    assert documents[0].doc_id == "DOC-001"
    assert documents[0].asset_type == "Máy lạnh"
    assert documents[0].clean_text


def test_chunking_produces_chunks_with_metadata() -> None:
    """Chunking should preserve document metadata and Vietnamese section text."""

    document = _document(
        clean_text=(
            "Triệu chứng: điện năng tăng bất thường. "
            "Các bước kiểm tra: kiểm tra lưới lọc, dây curoa và cảm biến nhiệt. "
            "Hành động khuyến nghị: vệ sinh dàn coil và ghi lại dòng điện."
        )
    )

    chunks = chunk_document(document, max_chars=80, overlap=10)

    assert chunks
    assert {chunk.doc_id for chunk in chunks} == {"DOC-001"}
    assert {chunk.asset_type for chunk in chunks} == {"Máy lạnh"}
    assert all(chunk.chunk_id.startswith("DOC-001-chunk-") for chunk in chunks)
    assert any("Các bước kiểm tra" in chunk.text for chunk in chunks)


def test_hash_embedding_provider_interface_behavior() -> None:
    """The test embedding provider should expose document and query vectors."""

    provider = HashEmbeddingProvider(dimensions=16)

    document_vectors = provider.embed_documents(["kiểm tra máy bơm"])
    query_vector = provider.embed_query("máy bơm cần kiểm tra gì")

    assert len(document_vectors) == 1
    assert len(document_vectors[0]) == 16
    assert len(query_vector) == 16
    assert prefix_passage("abc") == "passage: abc"
    assert prefix_query("abc") == "query: abc"


def test_qdrant_vector_store_searches_with_asset_type_filter() -> None:
    """Vector store should upsert chunks and search with a metadata filter."""

    client = QdrantClient(":memory:")
    store = QdrantVectorStore(collection_name="maintenance_test", client=client)
    provider = HashEmbeddingProvider(dimensions=32)
    chunks = chunk_documents(
        [
            _document(
                doc_id="DOC-001",
                asset_type="Máy lạnh",
                clean_text="kiểm tra lưới lọc và vệ sinh dàn coil",
            ),
            _document(
                doc_id="DOC-002",
                asset_type="Máy bơm nước",
                clean_text="kiểm tra độ rung và áp suất bơm",
            ),
        ]
    )
    vectors = provider.embed_documents([chunk.text for chunk in chunks])

    store.create_collection(vector_size=provider.dimensions, recreate=True)
    upserted = store.upsert_chunks(chunks, vectors)
    results = store.search(
        query_vector=provider.embed_query("cần kiểm tra lưới lọc"),
        top_k=5,
        asset_type="Máy lạnh",
    )

    assert upserted == len(chunks)
    assert results
    assert {result.asset_type for result in results} == {"Máy lạnh"}


def test_retriever_returns_expected_structure() -> None:
    """Retriever should pass query vector and filters into the vector store."""

    class FakeEmbeddingProvider:
        dimensions = 2

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0]

    class FakeVectorStore:
        def __init__(self) -> None:
            self.asset_type: str | None = None

        def search(
            self,
            query_vector: list[float],
            top_k: int = 5,
            asset_type: str | None = None,
        ) -> list[VectorSearchResult]:
            self.asset_type = asset_type
            return [
                VectorSearchResult(
                    chunk_id="chunk-1",
                    doc_id="DOC-001",
                    title="Checklist",
                    doc_type="Danh sách kiểm tra",
                    asset_type=asset_type or "Máy lạnh",
                    source="source",
                    text="kiểm tra lưới lọc",
                    score=0.9,
                )
            ]

    vector_store = FakeVectorStore()
    retriever = QdrantRetriever(FakeEmbeddingProvider(), vector_store)  # type: ignore[arg-type]

    results = retriever.search("cần kiểm tra gì", limit=3, asset_type="Máy lạnh")

    assert vector_store.asset_type == "Máy lạnh"
    assert results[0].to_dict()["doc_id"] == "DOC-001"
    assert results[0].score == 0.9


def test_copilot_answer_includes_vietnamese_context_and_sources() -> None:
    """Copilot answers should include structured context and source citations."""

    copilot = MaintenanceCopilot(
        processed_data_service=FakeProcessedDataService(),
        retriever=FakeRetriever(),
    )

    response = copilot.ask(
        question="Vì sao HVAC_001 đang rủi ro cao?",
        asset_id="HVAC_001",
        top_k=2,
    )

    assert "Thiết bị HVAC_001" in response.answer
    assert "Lý do rủi ro chính" in response.answer
    assert "Hành động nên xem xét" in response.answer
    assert response.sources[0]["doc_id"] == "DOC-001"
    assert response.retrieved_chunks[0]["text"]


class FakeProcessedDataService:
    """Small fake for copilot unit tests."""

    def get_asset_context(self, asset_id: str) -> dict[str, Any]:
        return {
            "asset_id": asset_id,
            "latest_risk": {
                "asset_id": asset_id,
                "asset_name": "Máy lạnh 001",
                "asset_type": "Máy lạnh",
                "location": "Tầng 1",
                "final_risk_score": 82.5,
                "risk_level": "Khẩn cấp",
                "main_reasons": "Điểm bất thường cao; bảo trì quá hạn.",
                "recommended_action": "Ưu tiên kiểm tra lưới lọc và dàn coil.",
            },
            "recent_anomalies": [
                {
                    "date": "2026-06-30",
                    "is_anomaly": True,
                    "anomaly_type": "Tăng điện năng bất thường",
                    "anomaly_score": 91.0,
                    "anomaly_reasons": "Điện năng tiêu thụ tăng mạnh.",
                }
            ],
            "recent_features": [],
            "latest_recommendation": "Ưu tiên kiểm tra lưới lọc và dàn coil.",
        }


class FakeRetriever:
    """Small fake retriever for deterministic copilot tests."""

    def search(
        self,
        query: str,
        limit: int = 5,
        asset_type: str | None = None,
    ) -> list[RetrievalResult]:
        return [
            RetrievalResult(
                chunk_id="chunk-1",
                doc_id="DOC-001",
                title="Checklist bảo trì máy lạnh",
                doc_type="Danh sách kiểm tra",
                asset_type=asset_type or "Máy lạnh",
                source="Checklist nội bộ",
                text="kiểm tra lưới lọc, vệ sinh dàn coil và ghi lại dòng điện",
                score=0.95,
            )
        ]


def _document(
    doc_id: str = "DOC-001",
    asset_type: str = "Máy lạnh",
    clean_text: str = "kiểm tra lưới lọc",
) -> MaintenanceDocument:
    return MaintenanceDocument(
        doc_id=doc_id,
        title="Checklist bảo trì",
        doc_type="Danh sách kiểm tra",
        asset_type=asset_type,
        source="Checklist nội bộ",
        clean_text=clean_text,
        created_at="2026-06-01T09:00:00+00:00",
    )

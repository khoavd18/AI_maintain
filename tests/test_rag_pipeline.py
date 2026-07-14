"""Tests for the deterministic RAG Maintenance Copilot pipeline."""

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from qdrant_client import QdrantClient

from src.rag.chunking import chunk_document, chunk_documents
from src.api.services import AssetNotFoundError
from src.data_generation.generate_data import generate_dataset
from src.rag.copilot import SAFE_FALLBACK, SAFETY_NOTICE, MaintenanceCopilot
from src.rag.document_loader import MaintenanceDocument, load_documents
from src.rag.embeddings import HashEmbeddingProvider, prefix_passage, prefix_query
from src.rag.index_documents import index_documents
from src.rag.retriever import QdrantRetriever, RetrievalResult
from src.rag.vector_store import (
    CollectionEmptyError,
    CollectionMissingError,
    QdrantUnavailableError,
    QdrantVectorStore,
    VectorDimensionMismatchError,
    VectorSearchResult,
)


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
    assert chunks == chunk_document(document, max_chars=80, overlap=10)
    assert all(chunk.text.strip() for chunk in chunks)
    required_metadata = {
        "document_id",
        "title",
        "document_type",
        "asset_type",
        "failure_category",
        "version",
        "effective_date",
        "chunk_index",
    }
    assert required_metadata.issubset(chunks[0].to_payload())


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


def test_generated_documents_are_deterministic_safe_and_cover_focused_assets(
    tmp_path: Path,
) -> None:
    """The six-document source set should be repeatable and cover both workflows."""

    first = generate_dataset(asset_count=3, days=1, seed=17)["documents"]
    second = generate_dataset(asset_count=3, days=1, seed=99)["documents"]
    pd.testing.assert_frame_equal(first, second)
    document_path = tmp_path / "documents.csv"
    first.to_csv(document_path, index=False)

    documents = load_documents(document_path)

    assert len(documents) == 6
    assert {document.asset_type for document in documents} == {
        "Máy lạnh",
        "Máy bơm nước",
        "Máy phát điện dự phòng",
    }
    assert all(document.version == "1.0" for document in documents)
    assert all(document.effective_date == "2026-01-01" for document in documents)
    assert all("synthetic" in document.content for document in documents)
    assert all("An toàn:" in document.content for document in documents)
    assert all("Các bước kiểm tra:" in document.content for document in documents)
    assert all("Khi nào cần hỗ trợ chuyên môn:" in document.content for document in documents)
    assert all("nhà sản xuất" in document.content.casefold() for document in documents)
    assert sum(document.document_type == "Danh sách kiểm tra" for document in documents) == 3
    assert sum(bool(document.failure_category) for document in documents) == 3


def test_indexing_rebuild_is_repeatable_and_removes_stale_chunks(tmp_path: Path) -> None:
    """A repeated indexing run should replace, not append to, the collection."""

    document_path = tmp_path / "documents.csv"
    documents = generate_dataset(asset_count=3, days=1, seed=17)["documents"]
    documents.to_csv(document_path, index=False)
    provider = HashEmbeddingProvider(dimensions=128)
    store = QdrantVectorStore(
        collection_name="repeatable_index_test",
        client=QdrantClient(":memory:"),
    )

    first = index_documents(
        documents_path=document_path,
        embedding_provider=provider,
        vector_store=store,
    )
    second = index_documents(
        documents_path=document_path,
        embedding_provider=provider,
        vector_store=store,
    )

    assert first == second
    assert first.document_count == 6
    assert first.chunk_count == store.count_points()
    assert first.embedding_implementation == "HashEmbeddingProvider"

    documents.iloc[:-1].to_csv(document_path, index=False)
    reduced = index_documents(
        documents_path=document_path,
        embedding_provider=provider,
        vector_store=store,
    )

    assert reduced.document_count == 5
    assert reduced.chunk_count < first.chunk_count
    assert reduced.chunk_count == store.count_points()


def test_retrieval_supports_all_metadata_filters(tmp_path: Path) -> None:
    """Asset, document, and failure filters should be applied conjunctively."""

    document_path = tmp_path / "documents.csv"
    generate_dataset(asset_count=3, days=1, seed=17)["documents"].to_csv(
        document_path,
        index=False,
    )
    provider = HashEmbeddingProvider(dimensions=128)
    store = QdrantVectorStore(
        collection_name="metadata_filter_test",
        client=QdrantClient(":memory:"),
    )
    index_documents(
        documents_path=document_path,
        embedding_provider=provider,
        vector_store=store,
    )
    retriever = QdrantRetriever(provider, store)

    asset_results = retriever.search(
        "kiểm tra rung máy bơm",
        asset_type="Máy bơm nước",
    )
    document_results = retriever.search(
        "bảo trì định kỳ",
        document_type="Danh sách kiểm tra",
    )
    failure_results = retriever.search(
        "máy phát điện không khởi động",
        asset_type="Máy phát điện dự phòng",
        failure_category="Lỗi điện",
    )

    assert asset_results and {result.asset_type for result in asset_results} == {
        "Máy bơm nước"
    }
    assert document_results and {result.doc_type for result in document_results} == {
        "Danh sách kiểm tra"
    }
    assert failure_results and {result.failure_category for result in failure_results} == {
        "Lỗi điện"
    }
    assert failure_results[0].score >= retriever.minimum_relevance_score


def test_vector_store_reports_missing_empty_and_unavailable_collections() -> None:
    """Qdrant failure modes should map to public-safe exception classes."""

    client = QdrantClient(":memory:")
    missing_store = QdrantVectorStore(collection_name="missing_test", client=client)
    with pytest.raises(CollectionMissingError):
        missing_store.search([0.0] * 8)

    empty_store = QdrantVectorStore(collection_name="empty_test", client=client)
    empty_store.create_collection(vector_size=8)
    with pytest.raises(CollectionEmptyError):
        empty_store.search([0.0] * 8)
    with pytest.raises(VectorDimensionMismatchError):
        empty_store.create_collection(vector_size=16)

    class BrokenClient:
        def collection_exists(self, collection_name: str) -> bool:
            raise RuntimeError("internal endpoint and secret must not escape")

    unavailable_store = QdrantVectorStore(
        collection_name="unavailable_test",
        client=BrokenClient(),  # type: ignore[arg-type]
    )
    with pytest.raises(QdrantUnavailableError) as error:
        unavailable_store.search([0.0] * 8)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    ("retriever", "expected_status"),
    [
        ("empty", "empty"),
        ("low", "low_relevance"),
        ("unavailable", "unavailable"),
    ],
)
def test_copilot_uses_safe_fallbacks(retriever: str, expected_status: str) -> None:
    """Empty, weak, and unavailable retrieval must not compose guidance."""

    copilot = MaintenanceCopilot(
        processed_data_service=FakeProcessedDataService(),
        retriever=FallbackRetriever(retriever),
    )

    response = copilot.ask(
        "Thiết bị này cần kiểm tra gì trước?",
        asset_id="HVAC_001",
    )

    assert response.retrieval_status == expected_status
    assert response.sources == []
    assert response.retrieved_chunks == []
    assert SAFE_FALLBACK in response.answer
    assert SAFETY_NOTICE in response.answer


@pytest.mark.parametrize(
    ("question", "expected_status"),
    [
        ("Thời tiết hôm nay thế nào?", "unrelated"),
        ("Checklist cho thang máy là gì?", "unsupported_asset_type"),
        ("Thiết bị này cần kiểm tra gì?", "missing_asset_context"),
    ],
)
def test_copilot_rejects_non_focused_questions(question: str, expected_status: str) -> None:
    """The Copilot should not act as a general-purpose chatbot."""

    retriever = CountingRetriever()
    copilot = MaintenanceCopilot(FakeProcessedDataService(), retriever)

    response = copilot.ask(question)

    assert response.retrieval_status == expected_status
    assert retriever.calls == 0
    assert SAFE_FALLBACK in response.answer


def test_copilot_rejects_empty_long_and_invalid_asset_requests() -> None:
    """Invalid questions and asset identifiers should fail before retrieval."""

    copilot = MaintenanceCopilot(FakeProcessedDataService(), CountingRetriever())
    with pytest.raises(ValueError, match="để trống"):
        copilot.ask("   ")
    with pytest.raises(ValueError, match="1000"):
        copilot.ask("x" * 1001)

    class MissingAssetService(FakeProcessedDataService):
        def get_asset_context(self, asset_id: str) -> dict[str, Any]:
            raise AssetNotFoundError(f"Unknown asset_id: {asset_id}")

    with pytest.raises(AssetNotFoundError):
        MaintenanceCopilot(MissingAssetService(), CountingRetriever()).ask(
            "Thiết bị này cần kiểm tra gì?",
            asset_id="UNKNOWN_999",
        )


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
            document_type: str | None = None,
            failure_category: str | None = None,
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
    assert "Checklist hoặc bước kiểm tra được tìm thấy" in response.answer
    assert "Nguồn tài liệu" in response.answer
    assert SAFETY_NOTICE in response.answer
    assert response.sources[0]["doc_id"] == "DOC-001"
    assert response.retrieved_chunks[0]["text"]
    assert response.retrieval_status == "success"


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

    minimum_relevance_score = 0.15

    def search(
        self,
        query: str,
        limit: int = 5,
        asset_type: str | None = None,
        document_type: str | None = None,
        failure_category: str | None = None,
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
                version="1.0",
                effective_date="2026-01-01",
            )
        ]


class FallbackRetriever:
    """Configurable fake for fallback policy tests."""

    minimum_relevance_score = 0.5

    def __init__(self, mode: str) -> None:
        self.mode = mode

    def search(
        self,
        query: str,
        limit: int = 5,
        asset_type: str | None = None,
        document_type: str | None = None,
        failure_category: str | None = None,
    ) -> list[RetrievalResult]:
        if self.mode == "unavailable":
            raise QdrantUnavailableError("public-safe")
        if self.mode == "empty":
            return []
        return [
            RetrievalResult(
                chunk_id="weak-chunk",
                doc_id="DOC-WEAK",
                title="Tài liệu không liên quan",
                doc_type="Danh sách kiểm tra",
                asset_type=asset_type or "Máy lạnh",
                source="Nguồn synthetic",
                text="Nội dung không liên quan",
                score=0.1,
            )
        ]


class CountingRetriever:
    """Fake that records whether retrieval was attempted."""

    minimum_relevance_score = 0.5

    def __init__(self) -> None:
        self.calls = 0

    def search(
        self,
        query: str,
        limit: int = 5,
        asset_type: str | None = None,
        document_type: str | None = None,
        failure_category: str | None = None,
    ) -> list[RetrievalResult]:
        self.calls += 1
        return []


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

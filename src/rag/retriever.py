"""Retriever interfaces and Qdrant-backed implementation for maintenance RAG."""

from dataclasses import dataclass
from typing import Protocol

from src.rag.embeddings import EmbeddingProvider
from src.rag.document_loader import resolve_document_identity_metadata
from src.rag.vector_store import QdrantVectorStore

DETERMINISTIC_HASH_RELEVANCE_THRESHOLD = 0.15
SEMANTIC_RELEVANCE_THRESHOLD = 0.55


class RetrievalUnavailableError(RuntimeError):
    """Raised when the configured retrieval implementation is unavailable."""


@dataclass(frozen=True)
class RetrievalResult:
    """A retrieved context chunk."""

    chunk_id: str
    doc_id: str
    title: str
    doc_type: str
    asset_type: str
    source: str
    text: str
    score: float
    failure_category: str = ""
    version: str = ""
    effective_date: str = ""
    language: str = "vi"
    chunk_index: int = 0
    dense_score: float | None = None
    sparse_score: float | None = None
    reranker_score: float | None = None
    metadata_prior: float | None = None
    equipment_model_identifiers: tuple[str, ...] = ()
    document_revision_reference: str = ""

    def __post_init__(self) -> None:
        metadata = resolve_document_identity_metadata(
            source=self.source,
            equipment_model_identifiers=self.equipment_model_identifiers,
            document_revision_reference=self.document_revision_reference,
        )
        object.__setattr__(
            self, "equipment_model_identifiers", metadata.equipment_model_identifiers
        )
        object.__setattr__(
            self, "document_revision_reference", metadata.document_revision_reference
        )

    def to_dict(self, *, include_diagnostics: bool = False) -> dict[str, object]:
        """Return an API-safe dictionary."""

        payload: dict[str, object] = {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "document_id": self.doc_id,
            "title": self.title,
            "doc_type": self.doc_type,
            "document_type": self.doc_type,
            "asset_type": self.asset_type,
            "failure_category": self.failure_category,
            "version": self.version,
            "effective_date": self.effective_date,
            "language": self.language,
            "chunk_index": self.chunk_index,
            "source": self.source,
            "text": self.text,
            "content": self.text,
            "score": self.score,
        }
        if include_diagnostics:
            diagnostics = {
                "dense_score": self.dense_score,
                "sparse_score": self.sparse_score,
                "reranker_score": self.reranker_score,
                "metadata_prior": self.metadata_prior,
            }
            payload["score_components"] = {
                key: value for key, value in diagnostics.items() if value is not None
            }
        return payload


class Retriever(Protocol):
    """Protocol for context retrieval implementations."""

    def search(
        self,
        query: str,
        limit: int = 5,
        asset_type: str | None = None,
        document_type: str | None = None,
        failure_category: str | None = None,
        version: str | None = None,
        language: str | None = None,
    ) -> list[RetrievalResult]:
        """Return relevant chunks for a technician question."""
        ...


class QdrantRetriever:
    """Retrieve maintenance document chunks from Qdrant."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: QdrantVectorStore,
        minimum_relevance_score: float | None = None,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.minimum_relevance_score = (
            minimum_relevance_score
            if minimum_relevance_score is not None
            else _default_relevance_threshold(embedding_provider)
        )

    def search(
        self,
        query: str,
        limit: int = 5,
        asset_type: str | None = None,
        document_type: str | None = None,
        failure_category: str | None = None,
        version: str | None = None,
        language: str | None = None,
    ) -> list[RetrievalResult]:
        """Embed the query and search Qdrant."""

        query_vector = self.embedding_provider.embed_query(query)
        optional_filters = {
            key: value
            for key, value in {
                "document_type": document_type,
                "failure_category": failure_category,
                "version": version,
                "language": language,
            }.items()
            if value is not None
        }
        results = self.vector_store.search(
            query_vector=query_vector,
            top_k=limit,
            asset_type=asset_type,
            **optional_filters,
        )
        return [
            RetrievalResult(
                chunk_id=result.chunk_id,
                doc_id=result.doc_id,
                title=result.title,
                doc_type=result.doc_type,
                asset_type=result.asset_type,
                source=result.source,
                text=result.text,
                score=result.score,
                failure_category=result.failure_category,
                version=result.version,
                effective_date=result.effective_date,
                language=result.language,
                chunk_index=result.chunk_index,
                dense_score=result.score,
                equipment_model_identifiers=result.equipment_model_identifiers,
                document_revision_reference=result.document_revision_reference,
            )
            for result in results
        ]


class UnavailableRetriever:
    """Retriever used when optional embedding initialization is unavailable."""

    minimum_relevance_score = SEMANTIC_RELEVANCE_THRESHOLD

    def search(
        self,
        query: str,
        limit: int = 5,
        asset_type: str | None = None,
        document_type: str | None = None,
        failure_category: str | None = None,
        version: str | None = None,
        language: str | None = None,
    ) -> list[RetrievalResult]:
        """Fail with a public-safe availability error."""

        raise RetrievalUnavailableError(
            "Embedding hoặc kho tài liệu chưa sẵn sàng cho Maintenance Copilot."
        )


def _default_relevance_threshold(embedding_provider: EmbeddingProvider) -> float:
    if embedding_provider.__class__.__name__ == "HashEmbeddingProvider":
        return DETERMINISTIC_HASH_RELEVANCE_THRESHOLD
    return SEMANTIC_RELEVANCE_THRESHOLD

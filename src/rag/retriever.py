"""Retriever interfaces and Qdrant-backed implementation for maintenance RAG."""

from dataclasses import dataclass
from typing import Protocol

from src.rag.embeddings import EmbeddingProvider
from src.rag.vector_store import QdrantVectorStore


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

    def to_dict(self) -> dict[str, object]:
        """Return an API-safe dictionary."""

        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "title": self.title,
            "doc_type": self.doc_type,
            "asset_type": self.asset_type,
            "source": self.source,
            "text": self.text,
            "score": self.score,
        }


class Retriever(Protocol):
    """Protocol for context retrieval implementations."""

    def search(
        self,
        query: str,
        limit: int = 5,
        asset_type: str | None = None,
    ) -> list[RetrievalResult]:
        """Return relevant chunks for a technician question."""
        ...


class QdrantRetriever:
    """Retrieve maintenance document chunks from Qdrant."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: QdrantVectorStore,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store

    def search(
        self,
        query: str,
        limit: int = 5,
        asset_type: str | None = None,
    ) -> list[RetrievalResult]:
        """Embed the query and search Qdrant."""

        query_vector = self.embedding_provider.embed_query(query)
        results = self.vector_store.search(
            query_vector=query_vector,
            top_k=limit,
            asset_type=asset_type,
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
            )
            for result in results
        ]

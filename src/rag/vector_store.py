"""Qdrant vector store integration for maintenance knowledge chunks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from src.config.settings import get_settings
from src.rag.chunking import DocumentChunk


class VectorStoreError(RuntimeError):
    """Raised when Qdrant operations fail."""


@dataclass(frozen=True)
class VectorSearchResult:
    """A retrieved chunk and its score."""

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

        return asdict(self)


class QdrantVectorStore:
    """Qdrant-backed storage for document chunk vectors."""

    def __init__(
        self,
        url: str | None = None,
        collection_name: str | None = None,
        client: QdrantClient | None = None,
    ) -> None:
        settings = get_settings()
        self.url = url or settings.qdrant_url
        self.collection_name = collection_name or settings.qdrant_collection
        self.client = client or QdrantClient(url=self.url)

    def create_collection(self, vector_size: int, recreate: bool = False) -> None:
        """Create the Qdrant collection if needed."""

        try:
            exists = self.client.collection_exists(self.collection_name)
            if exists and recreate:
                self.client.delete_collection(self.collection_name)
                exists = False
            if exists:
                return
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
        except Exception as exc:
            raise VectorStoreError(f"Could not create Qdrant collection: {exc}") from exc

    def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
        batch_size: int = 64,
    ) -> int:
        """Upsert chunk vectors and payload metadata into Qdrant."""

        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length.")

        total = 0
        for start in range(0, len(chunks), batch_size):
            batch_chunks = chunks[start : start + batch_size]
            batch_vectors = vectors[start : start + batch_size]
            points = [
                models.PointStruct(
                    id=_point_id(chunk.chunk_id),
                    vector=vector,
                    payload=chunk.to_payload(),
                )
                for chunk, vector in zip(batch_chunks, batch_vectors, strict=True)
            ]
            try:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=points,
                    wait=True,
                )
            except Exception as exc:
                raise VectorStoreError(f"Could not upsert chunks into Qdrant: {exc}") from exc
            total += len(points)
        return total

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        asset_type: str | None = None,
    ) -> list[VectorSearchResult]:
        """Search for relevant chunks, optionally filtering by Vietnamese asset type."""

        query_filter = _asset_type_filter(asset_type) if asset_type else None
        try:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
        except Exception as exc:
            raise VectorStoreError(f"Could not search Qdrant collection: {exc}") from exc

        results: list[VectorSearchResult] = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                VectorSearchResult(
                    chunk_id=str(payload.get("chunk_id", "")),
                    doc_id=str(payload.get("doc_id", "")),
                    title=str(payload.get("title", "")),
                    doc_type=str(payload.get("doc_type", "")),
                    asset_type=str(payload.get("asset_type", "")),
                    source=str(payload.get("source", "")),
                    text=str(payload.get("text", "")),
                    score=float(point.score),
                )
            )
        return results


def _asset_type_filter(asset_type: str) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="asset_type",
                match=models.MatchValue(value=asset_type),
            )
        ]
    )


def _point_id(chunk_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, chunk_id))

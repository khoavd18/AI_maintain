"""Qdrant vector store integration for maintenance knowledge chunks."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from src.config.settings import get_settings
from src.rag.chunking import DocumentChunk
from src.rag.document_loader import resolve_document_identity_metadata


class VectorStoreError(RuntimeError):
    """Raised when Qdrant operations fail."""


class QdrantUnavailableError(VectorStoreError):
    """Raised when Qdrant cannot be reached."""


class CollectionMissingError(VectorStoreError):
    """Raised when the configured collection does not exist."""


class CollectionEmptyError(VectorStoreError):
    """Raised when the configured collection has no active points."""


class VectorDimensionMismatchError(VectorStoreError):
    """Raised when embedding and collection dimensions differ."""


class CollectionConfigurationError(VectorStoreError):
    """Raised when an existing collection violates the retrieval contract."""


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
    failure_category: str = ""
    version: str = ""
    effective_date: str = ""
    language: str = "vi"
    chunk_index: int = 0
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

    def to_dict(self) -> dict[str, object]:
        """Return an API-safe dictionary."""

        payload = asdict(self)
        payload.update(
            {
                "document_id": self.doc_id,
                "document_type": self.doc_type,
                "content": self.text,
            }
        )
        return payload


class QdrantVectorStore:
    """Qdrant-backed storage for document chunk vectors."""

    def __init__(
        self,
        url: str | None = None,
        collection_name: str | None = None,
        client: QdrantClient | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.url = url or settings.qdrant_url
        self.collection_name = collection_name or settings.qdrant_collection
        _validate_collection_name(self.collection_name)
        configured_key = api_key
        if configured_key is None:
            configured_key = settings.qdrant_api_key.get_secret_value()
        self.client = client or QdrantClient(
            url=self.url,
            api_key=configured_key or None,
            timeout=timeout_seconds or settings.qdrant_timeout_seconds,
        )

    def create_collection(self, vector_size: int, recreate: bool = False) -> None:
        """Create the Qdrant collection if needed."""

        _validate_vector_size(vector_size)
        try:
            exists = self.client.collection_exists(self.collection_name)
            if exists and recreate:
                self.client.delete_collection(self.collection_name)
                exists = False
            if exists:
                actual_size = self._collection_vector_size(validate_distance=True)
                if actual_size != vector_size:
                    raise VectorDimensionMismatchError(
                        "Kích thước vector của collection không khớp embedding hiện tại. "
                        "Hãy index lại kho tài liệu."
                    )
            else:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )
            self._ensure_payload_indexes()
        except VectorStoreError:
            raise
        except Exception as exc:
            raise QdrantUnavailableError(
                "Không thể kết nối hoặc khởi tạo kho tài liệu Qdrant."
            ) from exc

    def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
        batch_size: int = 64,
    ) -> int:
        """Upsert chunk vectors and payload metadata into Qdrant."""

        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length.")
        if not chunks:
            raise ValueError("At least one document chunk is required for indexing.")

        expected_size = self._collection_vector_size(validate_distance=True)
        if any(len(vector) != expected_size for vector in vectors):
            raise VectorDimensionMismatchError(
                "Kích thước vector không khớp collection. Hãy index lại kho tài liệu."
            )

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
                raise QdrantUnavailableError("Không thể ghi tài liệu vào Qdrant.") from exc
            total += len(points)
        return total

    def count_points(self) -> int:
        """Return the number of active points in the collection."""

        try:
            if not self.client.collection_exists(self.collection_name):
                raise CollectionMissingError(
                    "Chưa có collection tài liệu. Hãy chạy indexing trước khi hỏi Copilot."
                )
            return int(
                self.client.count(
                    collection_name=self.collection_name,
                    exact=True,
                ).count
            )
        except VectorStoreError:
            raise
        except Exception as exc:
            raise QdrantUnavailableError("Không thể đọc trạng thái Qdrant.") from exc

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        asset_type: str | None = None,
        document_type: str | None = None,
        failure_category: str | None = None,
        version: str | None = None,
        language: str | None = None,
    ) -> list[VectorSearchResult]:
        """Search relevant chunks with optional conjunctive metadata filters."""

        try:
            if not self.client.collection_exists(self.collection_name):
                raise CollectionMissingError(
                    "Chưa có collection tài liệu. Hãy chạy indexing trước khi hỏi Copilot."
                )
            if self.count_points() == 0:
                raise CollectionEmptyError(
                    "Collection tài liệu đang trống. Hãy index lại kho tài liệu."
                )
            expected_size = self._collection_vector_size(validate_distance=True)
            if len(query_vector) != expected_size:
                raise VectorDimensionMismatchError(
                    "Kích thước vector truy vấn không khớp collection. "
                    "Hãy index lại bằng embedding hiện tại."
                )
            query_filter = _metadata_filter(
                asset_type=asset_type,
                document_type=document_type,
                failure_category=failure_category,
                version=version,
                language=language,
            )
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
        except VectorStoreError:
            raise
        except Exception as exc:
            raise QdrantUnavailableError("Không thể truy xuất kho tài liệu Qdrant.") from exc

        results: list[VectorSearchResult] = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                VectorSearchResult(
                    chunk_id=str(payload.get("chunk_id", "")),
                    doc_id=str(payload.get("document_id") or payload.get("doc_id", "")),
                    title=str(payload.get("title", "")),
                    doc_type=str(payload.get("document_type") or payload.get("doc_type", "")),
                    asset_type=str(payload.get("asset_type", "")),
                    source=str(payload.get("source", "")),
                    text=str(payload.get("content") or payload.get("text", "")),
                    score=float(point.score),
                    failure_category=str(payload.get("failure_category", "")),
                    version=str(payload.get("version", "")),
                    effective_date=str(payload.get("effective_date", "")),
                    language=str(payload.get("language", "vi")),
                    chunk_index=int(payload.get("chunk_index", 0)),
                    equipment_model_identifiers=payload.get("equipment_model_identifiers", ()),
                    document_revision_reference=str(payload.get("document_revision_reference", "")),
                )
            )
        return results

    def list_chunks(self, *, max_chunks: int = 10000) -> list[VectorSearchResult]:
        """Load the bounded payload corpus once for the small-corpus BM25 index."""

        if max_chunks <= 0:
            raise ValueError("max_chunks must be positive.")
        try:
            if not self.client.collection_exists(self.collection_name):
                raise CollectionMissingError(
                    "Chưa có collection tài liệu. Hãy chạy indexing trước khi hỏi Copilot."
                )
            records: list[object] = []
            offset: object | None = None
            while True:
                page, offset = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=min(256, max_chunks + 1 - len(records)),
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                records.extend(page)
                if len(records) > max_chunks:
                    raise VectorStoreError(
                        "Kho tài liệu vượt giới hạn BM25 trong bộ nhớ; cần dùng sparse backend "
                        "được quản lý trước khi tiếp tục."
                    )
                if offset is None:
                    break
        except VectorStoreError:
            raise
        except Exception as exc:
            raise QdrantUnavailableError("Không thể tải chỉ mục tìm kiếm thưa từ Qdrant.") from exc
        return [self._payload_result(getattr(record, "payload", None) or {}) for record in records]

    def payloads_by_chunk_id(self, *, max_chunks: int = 100000) -> dict[str, dict[str, object]]:
        """Return existing payloads for deterministic non-destructive synchronization."""

        return {
            result.chunk_id: result.to_dict()
            for result in self.list_chunks(max_chunks=max_chunks)
            if result.chunk_id
        }

    def delete_chunk_ids(self, chunk_ids: list[str]) -> int:
        """Delete explicitly identified obsolete chunks during an authorized replace run."""

        if not chunk_ids:
            return 0
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(
                    points=[_point_id(chunk_id) for chunk_id in chunk_ids]
                ),
                wait=True,
            )
        except Exception as exc:
            raise QdrantUnavailableError("Không thể loại bỏ chunk lỗi thời khỏi Qdrant.") from exc
        return len(chunk_ids)

    def check_health(self, *, expected_vector_size: int | None = None) -> None:
        """Validate service reachability and the existing collection contract."""

        try:
            if not self.client.collection_exists(self.collection_name):
                raise CollectionMissingError("Collection tài liệu chưa được index.")
            actual_size = self._collection_vector_size(validate_distance=True)
            if expected_vector_size is not None and actual_size != expected_vector_size:
                raise VectorDimensionMismatchError(
                    "Kích thước vector của collection không khớp cấu hình embedding."
                )
        except VectorStoreError:
            raise
        except Exception as exc:
            raise QdrantUnavailableError("Không thể đọc trạng thái Qdrant.") from exc

    def _payload_result(self, payload: dict[str, object]) -> VectorSearchResult:
        return VectorSearchResult(
            chunk_id=str(payload.get("chunk_id", "")),
            doc_id=str(payload.get("document_id") or payload.get("doc_id", "")),
            title=str(payload.get("title", "")),
            doc_type=str(payload.get("document_type") or payload.get("doc_type", "")),
            asset_type=str(payload.get("asset_type", "")),
            source=str(payload.get("source", "")),
            text=str(payload.get("content") or payload.get("text", "")),
            score=0.0,
            failure_category=str(payload.get("failure_category", "")),
            version=str(payload.get("version", "")),
            effective_date=str(payload.get("effective_date", "")),
            language=str(payload.get("language", "vi")),
            chunk_index=int(payload.get("chunk_index", 0)),
            equipment_model_identifiers=payload.get("equipment_model_identifiers", ()),
            document_revision_reference=str(payload.get("document_revision_reference", "")),
        )

    def _ensure_payload_indexes(self) -> None:
        if getattr(self.client, "_client", None).__class__.__name__ == "QdrantLocal":
            return
        collection = self.client.get_collection(self.collection_name)
        existing_schema = getattr(collection, "payload_schema", {}) or {}
        for field_name in (
            "asset_type",
            "document_type",
            "failure_category",
            "version",
            "language",
        ):
            if field_name in existing_schema:
                continue
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )

    def _collection_vector_size(self, *, validate_distance: bool = False) -> int:
        try:
            collection = self.client.get_collection(self.collection_name)
            vectors = collection.config.params.vectors
            if isinstance(vectors, dict):
                if len(vectors) != 1:
                    raise VectorDimensionMismatchError(
                        "Collection phải có đúng một vector space cho MVP."
                    )
                vectors = next(iter(vectors.values()))
            size = getattr(vectors, "size", None)
            if not isinstance(size, int) or size <= 0:
                raise VectorDimensionMismatchError(
                    "Không đọc được kích thước vector của collection."
                )
            if validate_distance and getattr(vectors, "distance", None) != models.Distance.COSINE:
                raise CollectionConfigurationError(
                    "Collection Qdrant phải dùng cosine similarity; không tự động recreate."
                )
            return size
        except VectorStoreError:
            raise
        except Exception as exc:
            raise QdrantUnavailableError("Không thể đọc cấu hình Qdrant.") from exc


def _metadata_filter(
    *,
    asset_type: str | None,
    document_type: str | None,
    failure_category: str | None,
    version: str | None = None,
    language: str | None = None,
) -> models.Filter | None:
    values = {
        "asset_type": asset_type,
        "document_type": document_type,
        "failure_category": failure_category,
        "version": version,
        "language": language,
    }
    conditions = [
        models.FieldCondition(key=key, match=models.MatchValue(value=value))
        for key, value in values.items()
        if value
    ]
    return models.Filter(must=conditions) if conditions else None


def _point_id(chunk_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, chunk_id))


def _validate_collection_name(collection_name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,255}", collection_name):
        raise ValueError(
            "collection_name must contain only letters, numbers, underscores, or hyphens."
        )


def _validate_vector_size(vector_size: int) -> None:
    if not isinstance(vector_size, int) or vector_size <= 0:
        raise ValueError("vector_size must be a positive integer.")

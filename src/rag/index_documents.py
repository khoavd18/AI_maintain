"""Explicit, reportable maintenance-knowledge indexing CLI."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any

from src.config.settings import get_settings
from src.rag.chunking import DocumentChunk, chunk_documents
from src.rag.document_loader import (
    RAW_DOCUMENT_FILE,
    DocumentLoadError,
    DocumentValidationError,
    validate_document_source,
)
from src.rag.embeddings import (
    EmbeddingDependencyError,
    EmbeddingProvider,
    create_embedding_provider,
)
from src.rag.vector_store import QdrantVectorStore, VectorSearchResult, VectorStoreError


@dataclass(frozen=True)
class IndexingReport:
    """Machine-readable summary of one controlled indexing run."""

    total_records: int
    valid_records: int
    invalid_records: int
    document_count: int
    chunk_count: int
    added_points: int
    updated_points: int
    unchanged_points: int
    removed_points: int
    obsolete_points: int
    active_points: int
    validation_errors: tuple[dict[str, Any], ...]
    collection_name: str
    embedding_implementation: str
    vector_dimensions: int
    replace_mode: bool
    recreate_mode: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def index_documents(
    *,
    documents_path: Path = RAW_DOCUMENT_FILE,
    qdrant_url: str | None = None,
    collection_name: str | None = None,
    embedding_model: str | None = None,
    max_chars: int | None = None,
    overlap: int | None = None,
    replace: bool = False,
    recreate: bool = False,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: QdrantVectorStore | None = None,
) -> IndexingReport:
    """Validate and synchronize documents without destructive behavior by default."""

    settings = get_settings()
    chunk_size = max_chars if max_chars is not None else settings.rag_chunk_size
    chunk_overlap = overlap if overlap is not None else settings.rag_chunk_overlap
    if recreate and not replace:
        # Recreation is necessarily a full replacement; make that state explicit in the report.
        replace = True

    batch = validate_document_source(documents_path)
    if batch.report.errors:
        raise DocumentValidationError(batch.report)
    if not batch.documents:
        raise DocumentLoadError(f"No usable documents found in {documents_path}")
    chunks = chunk_documents(batch.documents, max_chars=chunk_size, overlap=chunk_overlap)
    if not chunks:
        raise ValueError("No non-empty document chunks were produced for indexing.")

    provider = embedding_provider or create_embedding_provider(embedding_model)
    store = vector_store or QdrantVectorStore(
        url=qdrant_url,
        collection_name=collection_name,
    )
    store.create_collection(vector_size=provider.dimensions, recreate=recreate)
    existing = {result.chunk_id: result for result in store.list_chunks() if result.chunk_id}
    classification = _classify_changes(chunks, existing)
    chunks_to_upsert = [
        chunk
        for chunk in chunks
        if chunk.chunk_id in classification["added_ids"]
        or chunk.chunk_id in classification["updated_ids"]
    ]
    vectors = provider.embed_documents([chunk.text for chunk in chunks_to_upsert])
    _validate_vectors(vectors, expected_count=len(chunks_to_upsert), dimensions=provider.dimensions)
    upserted = store.upsert_chunks(chunks_to_upsert, vectors) if chunks_to_upsert else 0
    if upserted != len(chunks_to_upsert):
        raise VectorStoreError("Số chunk ghi vào collection không khớp indexing plan.")

    removed = 0
    if replace:
        removed = store.delete_chunk_ids(sorted(classification["obsolete_ids"]))
    active_count = store.count_points()
    expected_minimum = len(chunks)
    if active_count < expected_minimum:
        raise VectorStoreError("Collection có ít điểm hơn bộ tài liệu vừa index.")
    if replace and active_count != len(chunks):
        raise VectorStoreError("Replace indexing không tạo đúng tập chunk canonical.")

    return IndexingReport(
        total_records=batch.report.total_records,
        valid_records=batch.report.valid_records,
        invalid_records=batch.report.invalid_records,
        document_count=len(batch.documents),
        chunk_count=len(chunks),
        added_points=len(classification["added_ids"]),
        updated_points=len(classification["updated_ids"]),
        unchanged_points=len(classification["unchanged_ids"]),
        removed_points=removed,
        obsolete_points=(0 if replace else len(classification["obsolete_ids"])),
        active_points=active_count,
        validation_errors=tuple(asdict(error) for error in batch.report.errors),
        collection_name=store.collection_name,
        embedding_implementation=_embedding_implementation(provider),
        vector_dimensions=provider.dimensions,
        replace_mode=replace,
        recreate_mode=recreate,
    )


def _classify_changes(
    chunks: list[DocumentChunk],
    existing: dict[str, VectorSearchResult],
) -> dict[str, set[str]]:
    incoming = {chunk.chunk_id: chunk for chunk in chunks}
    incoming_ids = set(incoming)
    existing_ids = set(existing)
    same_ids = incoming_ids & existing_ids
    unchanged_ids = {
        chunk_id
        for chunk_id in same_ids
        if _payload_matches(incoming[chunk_id], existing[chunk_id])
    }
    metadata_updated_ids = same_ids - unchanged_ids
    new_ids = incoming_ids - existing_ids
    obsolete_ids = existing_ids - incoming_ids

    obsolete_slots = {
        (existing[chunk_id].doc_id, existing[chunk_id].chunk_index): chunk_id
        for chunk_id in obsolete_ids
    }
    content_updated_ids = {
        chunk_id
        for chunk_id in new_ids
        if (incoming[chunk_id].doc_id, incoming[chunk_id].chunk_index) in obsolete_slots
    }
    return {
        "added_ids": new_ids - content_updated_ids,
        "updated_ids": metadata_updated_ids | content_updated_ids,
        "unchanged_ids": unchanged_ids,
        "obsolete_ids": obsolete_ids,
    }


def _payload_matches(chunk: DocumentChunk, existing: VectorSearchResult) -> bool:
    return (
        chunk.doc_id == existing.doc_id
        and chunk.title == existing.title
        and chunk.doc_type == existing.doc_type
        and chunk.asset_type == existing.asset_type
        and chunk.source == existing.source
        and chunk.text == existing.text
        and chunk.failure_category == existing.failure_category
        and chunk.version == existing.version
        and chunk.effective_date == existing.effective_date
        and chunk.language == existing.language
        and chunk.chunk_index == existing.chunk_index
    )


def _validate_vectors(
    vectors: list[list[float]],
    *,
    expected_count: int,
    dimensions: int,
) -> None:
    if len(vectors) != expected_count:
        raise ValueError("Embedding provider returned an unexpected vector count.")
    for vector in vectors:
        if len(vector) != dimensions or not all(math.isfinite(value) for value in vector):
            raise ValueError("Embedding provider returned an invalid vector shape or value.")
        norm = math.sqrt(sum(value * value for value in vector))
        if not math.isclose(norm, 1.0, abs_tol=1e-4):
            raise ValueError("Embedding provider must return normalized vectors.")


def main() -> None:
    """Index documents.csv only when explicitly invoked by an operator."""

    _configure_stdout()
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Index maintenance documents into Qdrant.")
    parser.add_argument("--documents-path", type=Path, default=RAW_DOCUMENT_FILE)
    parser.add_argument("--qdrant-url", default=settings.qdrant_url)
    parser.add_argument("--collection", default=settings.qdrant_collection)
    parser.add_argument("--embedding-model", default=settings.embedding_model_name)
    parser.add_argument("--max-chars", type=int, default=settings.rag_chunk_size)
    parser.add_argument("--overlap", type=int, default=settings.rag_chunk_overlap)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete only obsolete points after a successful validated upsert.",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Explicitly delete and recreate the collection before indexing.",
    )
    args = parser.parse_args()

    try:
        report = index_documents(
            documents_path=args.documents_path,
            qdrant_url=args.qdrant_url,
            collection_name=args.collection,
            embedding_model=args.embedding_model,
            max_chars=args.max_chars,
            overlap=args.overlap,
            replace=args.replace,
            recreate=args.recreate,
        )
    except DocumentValidationError as exc:
        print(json.dumps(exc.report.to_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1) from exc
    except (DocumentLoadError, EmbeddingDependencyError, VectorStoreError, ValueError) as exc:
        print(f"Document indexing failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))


def _embedding_implementation(provider: EmbeddingProvider) -> str:
    name = provider.__class__.__name__
    model_name = getattr(provider, "model_name", None)
    return f"{name} ({model_name})" if model_name else name


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()

"""CLI for indexing maintenance documents into Qdrant."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from src.config.settings import get_settings
from src.rag.chunking import chunk_documents
from src.rag.document_loader import RAW_DOCUMENT_FILE, DocumentLoadError, load_documents
from src.rag.embeddings import (
    EmbeddingDependencyError,
    EmbeddingProvider,
    create_embedding_provider,
)
from src.rag.vector_store import QdrantVectorStore, VectorStoreError


@dataclass(frozen=True)
class IndexingReport:
    """Summary of one deterministic document indexing run."""

    document_count: int
    chunk_count: int
    collection_name: str
    embedding_implementation: str
    vector_dimensions: int


def index_documents(
    *,
    documents_path: Path = RAW_DOCUMENT_FILE,
    qdrant_url: str | None = None,
    collection_name: str | None = None,
    embedding_model: str | None = None,
    max_chars: int = 800,
    overlap: int = 80,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: QdrantVectorStore | None = None,
) -> IndexingReport:
    """Replace the MVP collection with one deterministic document set."""

    documents = load_documents(documents_path)
    chunks = chunk_documents(documents, max_chars=max_chars, overlap=overlap)
    if not chunks:
        raise ValueError("No non-empty document chunks were produced for indexing.")

    provider = embedding_provider or create_embedding_provider(embedding_model)
    vectors = provider.embed_documents([chunk.text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise ValueError("Embedding provider returned an unexpected vector count.")
    if any(len(vector) != provider.dimensions for vector in vectors):
        raise ValueError("Embedding provider returned an unexpected vector dimension.")

    store = vector_store or QdrantVectorStore(
        url=qdrant_url,
        collection_name=collection_name,
    )
    store.create_collection(vector_size=provider.dimensions, recreate=True)
    upserted = store.upsert_chunks(chunks, vectors)
    active_count = store.count_points()
    if upserted != len(chunks) or active_count != len(chunks):
        raise VectorStoreError(
            "Số chunk trong collection không khớp bộ tài liệu vừa index."
        )

    return IndexingReport(
        document_count=len(documents),
        chunk_count=active_count,
        collection_name=store.collection_name,
        embedding_implementation=_embedding_implementation(provider),
        vector_dimensions=provider.dimensions,
    )


def main() -> None:
    """Index documents.csv into the configured Qdrant collection."""

    _configure_stdout()
    parser = argparse.ArgumentParser(description="Index maintenance documents into Qdrant.")
    parser.add_argument("--documents-path", type=Path, default=RAW_DOCUMENT_FILE)
    parser.add_argument("--qdrant-url", default=get_settings().qdrant_url)
    parser.add_argument("--collection", default=get_settings().qdrant_collection)
    parser.add_argument("--embedding-model", default=get_settings().embedding_model_name)
    parser.add_argument("--max-chars", type=int, default=800)
    parser.add_argument("--overlap", type=int, default=80)
    parser.add_argument("--recreate", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    try:
        report = index_documents(
            documents_path=args.documents_path,
            qdrant_url=args.qdrant_url,
            collection_name=args.collection,
            embedding_model=args.embedding_model,
            max_chars=args.max_chars,
            overlap=args.overlap,
        )
    except (DocumentLoadError, EmbeddingDependencyError, VectorStoreError, ValueError) as exc:
        print(f"Document indexing failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(
        f"Documents: {report.document_count}\n"
        f"Chunks: {report.chunk_count}\n"
        f"Collection: {report.collection_name}\n"
        f"Embedding: {report.embedding_implementation}\n"
        f"Vector dimensions: {report.vector_dimensions}"
    )


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

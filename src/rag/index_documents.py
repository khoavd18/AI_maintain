"""CLI for indexing maintenance documents into Qdrant."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config.settings import get_settings
from src.rag.chunking import chunk_documents
from src.rag.document_loader import RAW_DOCUMENT_FILE, DocumentLoadError, load_documents
from src.rag.embeddings import EmbeddingDependencyError, create_embedding_provider
from src.rag.vector_store import QdrantVectorStore, VectorStoreError


def main() -> None:
    """Index documents.csv into the configured Qdrant collection."""

    _configure_stdout()
    parser = argparse.ArgumentParser(description="Index maintenance documents into Qdrant.")
    parser.add_argument("--documents-path", type=Path, default=RAW_DOCUMENT_FILE)
    parser.add_argument("--qdrant-url", default=get_settings().qdrant_url)
    parser.add_argument("--collection", default=get_settings().qdrant_collection)
    parser.add_argument("--embedding-model", default=get_settings().embedding_model_name)
    parser.add_argument("--max-chars", type=int, default=800)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()

    try:
        documents = load_documents(args.documents_path)
        chunks = chunk_documents(documents, max_chars=args.max_chars, overlap=args.overlap)
        embedding_provider = create_embedding_provider(args.embedding_model)
        vectors = embedding_provider.embed_documents([chunk.text for chunk in chunks])
        vector_store = QdrantVectorStore(
            url=args.qdrant_url,
            collection_name=args.collection,
        )
        vector_store.create_collection(
            vector_size=embedding_provider.dimensions,
            recreate=args.recreate,
        )
        upserted = vector_store.upsert_chunks(chunks, vectors)
    except (DocumentLoadError, EmbeddingDependencyError, VectorStoreError, ValueError) as exc:
        print(f"Document indexing failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(
        f"Indexed {upserted} chunks from {len(documents)} documents "
        f"into Qdrant collection '{args.collection}'."
    )


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()

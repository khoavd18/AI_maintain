"""CLI for asking the grounded Maintenance Copilot with safe fallback."""

from __future__ import annotations

import argparse
import sys

from src.api.composition import get_copilot_service
from src.analytics.errors import AssetNotFoundError, ProcessedDataNotFoundError
from src.rag.embeddings import EmbeddingDependencyError
from src.rag.vector_store import VectorStoreError


def main() -> None:
    """Ask the optionally LLM-grounded Maintenance Copilot from the command line."""

    _configure_stdout()
    parser = argparse.ArgumentParser(description="Ask the RAG Maintenance Copilot.")
    parser.add_argument("question", nargs="+")
    parser.add_argument("--asset-id")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    question = " ".join(args.question)
    try:
        answer = get_copilot_service().ask(
            question=question,
            asset_id=args.asset_id,
            top_k=args.top_k,
        )
    except (
        AssetNotFoundError,
        ProcessedDataNotFoundError,
        EmbeddingDependencyError,
        VectorStoreError,
        ValueError,
    ) as exc:
        print(f"Copilot query failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(answer.answer)
    if answer.sources:
        print("\nNguồn:")
        for source in answer.sources:
            print(f"- {source['title']} ({source['source']})")


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()

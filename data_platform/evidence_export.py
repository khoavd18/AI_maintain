"""CLI for the bounded local Stage 10 RAG evidence export."""

from __future__ import annotations

import argparse
from itertools import chain
import json
from pathlib import Path

from data_platform.config import DataPlatformSettings
from src.rag.evidence_export import (
    export_evidence_jsonl,
    iter_local_documents,
    iter_postgres_evidence,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-candidates", type=int, default=1_000)
    parser.add_argument("--document-root", type=Path, default=Path("sop_docs"))
    args = parser.parse_args()
    settings = DataPlatformSettings.from_env()
    sources = chain(
        iter_local_documents(args.document_root),
        iter_postgres_evidence(settings, scan_limit=min(args.max_candidates * 4, 40_000)),
    )
    result = export_evidence_jsonl(
        sources,
        args.output,
        max_candidates=args.max_candidates,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

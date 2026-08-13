# Bounded BM25 retrieval

`src.rag.sparse_search.QdrantBM25Retriever` builds an in-memory, immutable BM25 snapshot from the existing bounded Qdrant chunk listing. It does not ingest evaluation data, make network calls beyond the configured Qdrant boundary, or have mutation authority. The enhanced `full` profile is used only by the new `shadow` and `bm25` modes; `disabled` retains the historical `legacy` sparse representation.

The frozen general-purpose parameters are `k1=1.5` and `b=0.75`. The indexed representation includes title, chunk text, document type, failure category, source, asset type, and version. Tokenization is NFC/case-folded, preserves technical identifiers, and adds an accent-folded Vietnamese token only when distinct. Results use descending score and then `chunk_id` for deterministic ties.

## Server-controlled modes

`RAG_SPARSE_MODE` is server-only and defaults to `disabled`.

- `disabled` preserves the existing hybrid retriever behavior and does no additional eager BM25 work.
- `shadow` invokes BM25 after the existing response path and returns the existing result unchanged. Diagnostics contain only bounded counters, never questions or source content.
- `bm25` uses the snapshot ranking at the existing retrieval boundary. A missing or unhealthy sparse snapshot falls back to the existing hybrid retriever.

Request analysis, metadata/applicability filters, controlled relaxation, relevance/minimum-evidence gates, unsafe-context handling, context bounds, and citation validation remain downstream of every mode.

## Refresh and rollback

For `shadow` and `bm25`, construction attempts an initial snapshot build before retrieval is selected; subsequent refreshes occur no more frequently than `RAG_SPARSE_REFRESH_SECONDS` (default 60) and are capped by `RAG_SPARSE_MAX_CHUNKS`. `disabled` preserves the pre-existing hybrid path without additional mode-specific build work. A lock prevents duplicate rebuilds. A completed snapshot replaces the old snapshot atomically; a refresh failure retains the old healthy snapshot and records only the failure category. Set `RAG_SPARSE_MODE=disabled` to roll back immediately without a code change.

This capability is not enabled for deployment by this change. Calibration results are deterministic fixture measurements, not production, field, semantic, or SME-approved accuracy claims.

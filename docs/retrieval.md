# Hybrid Retrieval

The serving path uses normalized multilingual E5 dense retrieval, BM25 sparse retrieval over a process-cached bounded Qdrant payload corpus, candidate deduplication, weighted fusion, and a multilingual cross-encoder.

Default pools are 20 dense, 20 sparse, 20 fused/reranked, and 5 returned. E5 uses `passage:` for indexed chunks, `query:` for questions, 384-dimensional normalized vectors, batching, configured device selection, and CPU fallback. BM25 preserves equipment identifiers such as `P-101`. Its in-memory corpus is capped by `RAG_SPARSE_MAX_CHUNKS`; exceeding the cap fails safely instead of scanning an unbounded corpus.

The default formula is:

```text
retrieval = 0.50 * normalized_dense + 0.50 * normalized_sparse
final = 0.55 * retrieval + 0.40 * normalized_reranker + 0.05 * metadata_prior
```

Weights are startup-validated. Metadata is bounded to `[0,1]`, and its configured contribution cannot exceed `0.10`. `RAG_RELEVANCE_THRESHOLD=0.55` is an evidence gate, not a diagnostic probability.

Qdrant uses cosine similarity, deterministic UUIDv5 point IDs, keyword payload indexes, and conjunctive filters for asset type, document type, failure category, version, and language. Existing collection dimensions/distance are validated and never silently recreated. `/health/rag` reports collection readiness without loading the embedding or reranker model.

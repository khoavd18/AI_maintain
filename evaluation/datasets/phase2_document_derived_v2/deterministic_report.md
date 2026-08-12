# RAG Evaluation Report

- Dataset version: `2.0.0`
- Provenance: `document_derived`
- Approval state: `draft`
- Readiness: `DRAFT_SME_REVIEW_REQUIRED`
- Backend: `in-memory-hash`
- Total cases: 300
- Retrieval-eligible cases: 300
- Manual-review-only cases: 3
- Embedding: `HashEmbeddingProvider(dimensions=384)`
- Reranker: `deterministic_lexical_fixture`
- LLM provider used: `none`

## Retrieval

| Metric | Value |
|---|---:|
| Recall@1 | 1.0000 |
| Recall@3 | 1.0000 |
| Recall@5 | 1.0000 |
| MRR | 1.0000 |
| NDCG@5 | 1.0000 |
| Metadata-filter accuracy | 1.0000 |
| Average latency (ms) | 4.485 |
| P50 latency (ms) | 4.407 |
| P95 latency (ms) | 5.186 |

## Answers And Safety

- No-answer accuracy: 1.0000
- Routing/status accuracy: 1.0000
- Intent accuracy: n/a
- Source precision: 1.0000
- Source coverage: 1.0000
- Multi-turn resolution: 1.0000
- Model/variant isolation: 1.0000
- Unsafe-request refusal routing: 1.0000
- Filter relaxation: n/a
- Unsupported-equipment rejection: n/a
- Asset-mismatch detection: n/a
- Citation validity: n/a
- Fallback rate: 1.0000

## Manual Review Boundaries

- Engineering guard accuracy: 1.0000
- Evidence isolation accuracy: 1.0000
- SME approval accuracy: n/a
- SME gate: All manual-review cases remain pending qualified SME review.

## Skipped Metrics

- unsupported_claim_rate: n/a — Requires SME-approved semantic claim labels; structural citation checks are separate.
- citation_validation: n/a — Deterministic fallback exposes retrieved sources but creates no provider claims.
- live_provider: n/a — mode=deterministic does not call the configured LLM provider.

## Limitations

- All cases are document-derived drafts, not field-observed tickets or work orders.
- Grundfos and Generac source currentness remains VERSION_AMBIGUOUS and blocks promotion.
- Daikin source currentness passed, but every case remains pending qualified SME review.
- Deterministic hash retrieval is an integration fixture, not semantic or production accuracy.
- In-memory hash embeddings are deterministic test fixtures, not semantic production embeddings.
- Ungrounded LLM mode is intentionally excluded because the product must not generate maintenance guidance without retrieved evidence.

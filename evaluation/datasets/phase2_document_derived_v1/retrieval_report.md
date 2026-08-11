# RAG Evaluation Report

- Dataset version: `0.1.0`
- Backend: `in-memory-hash`
- Dataset size: 27

## Retrieval

| Metric | Value |
|---|---:|
| Recall@1 | 0.8519 |
| Recall@3 | 0.9630 |
| Recall@5 | 1.0000 |
| MRR | 0.9086 |
| NDCG@5 | 0.9314 |
| Metadata-filter accuracy | 1.0000 |
| Average latency (ms) | 4.426 |
| P50 latency (ms) | 4.438 |
| P95 latency (ms) | 4.972 |

## Limitations

- This is a document-derived calibration batch, not field-observed ticket or work-order evidence.
- All case answers and Vietnamese corpus text are paraphrases of linked manufacturer manuals; SME review is still pending.
- Applicability is limited to the exact model and revision scope recorded in the source registry; instructions must not be generalized to other variants.
- Manufacturer PDFs are link-only and are not redistributed in this package; remote availability and checksums must be re-verified before controlled ingestion.
- The Grundfos CR 5 service source is an older Model A document and must be supersession-checked before any operational pilot.
- The batch is for schema, retrieval, citation, refusal, and review-workflow calibration; it is not evidence of production accuracy or safety approval.
- In-memory hash embeddings are deterministic test fixtures, not semantic production embeddings.
- Ungrounded LLM mode is intentionally excluded because the product must not generate maintenance guidance without retrieved evidence.

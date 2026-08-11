# AI Quality Phase 2 — Grounded RAG Implementation Checkpoint

## Scope and claims boundary

This checkpoint strengthens production RAG applicability guards and evaluation reporting for
the document-derived v0.1.0 calibration batch. It does not change the dataset's
`document_derived` provenance, `DRAFT_SME_REVIEW_REQUIRED` readiness, draft/pending-SME state,
three manual-review-only cases, source metadata, source checksums, or six validator warnings.

The in-memory hash backend is a deterministic wiring fixture. The configured-Qdrant result uses
the repository's configured semantic embedding and reranker against a dedicated local Phase 2
evaluation collection. Neither result is production accuracy, field accuracy, operational safety
approval, or SME approval.

## Production request path

```text
FastAPI /copilot/ask
→ shared Copilot composition root
→ request validation and conversation resolution
→ asset/model applicability and exact-parameter safety guards
→ hard metadata and post-retrieval applicability filters
→ hybrid dense+sparse retrieval
→ reranking
→ evidence safety/conflict/minimum-document gates
→ bounded context and grounded prompt
→ provider abstraction and structured output parser
→ claim-level citation validation
→ grounded response or deterministic safe fallback
```

Existing normalization, sparse retrieval, dense embeddings, hybrid fusion, reranking, asset
context, conversation state, evidence construction, provider abstraction, structured parsing,
citation validation, prompt-injection screening, and deterministic fallback remain the canonical
implementations. No evaluation-only RAG pipeline was added.

## Before-change failure matrix

The baseline reports were preserved outside the repository before implementation. Every rank-1
miss and manual-boundary mismatch was classified before code changed.

| Case | Observed baseline | Root-cause assessment | Owning layer | Smallest safe action and verification |
|---|---|---|---|---|
| P2-PUMP-004 | Hash fixture rank 2; semantic rank 1 | Hash/lexical near-tie between seal and gasket evidence | Deterministic fixture | No tuning. Preserve as fixture limitation; verify Recall gates do not regress. |
| P2-HVAC-002 | Hash fixture rank 5; semantic rank 1 | Safety intent is semantic; token overlap favors broader HVAC documents | Deterministic fixture | No case alias or question rewrite. Preserve measured semantic result. |
| P2-GEN-001 | Hash fixture rank 3; semantic rank 1 | Broad checklist wording overlaps several generator safety documents | Deterministic fixture | No tuning. Await SME adjudication of acceptable secondary evidence. |
| P2-GEN-003 | Hash and semantic rank 2 | Specific low-oil-pressure evidence is also relevant to the general shutdown/reset question | Dataset adjudication/reranking | Do not change gold labels or weights before SME review. Report ambiguity. |
| P2-HVAC-008 | Semantic rank 2; hash rank 1 | Cross-encoder confidence is weak on the unaccented query and reverses a stronger hybrid score | Reranking | Do not tune model/weights on 27 draft cases. Retain case-level evidence for a larger approved benchmark. |
| P2-GEN-002 | Semantic rank 3; hash rank 1 | Unaccented numeric safety wording is reranked behind oil/checklist chunks | Reranking | No case-specific alias. Retain as semantic calibration miss. |
| P2-GEN-004 | Semantic rank 3; hash rank 1 | Reranker overweights general protection evidence relative to regulator applicability | Reranking | No weight change without approved labels. Retain as semantic calibration miss. |
| P2-PUMP-009 | Generic `unrelated` fallback instead of clarification | No exact-torque missing-parameter guard | Request safety boundary | Add generic exact-parameter guard; require fastener size before torque retrieval. |
| P2-PUMP-010 | Generic `unrelated` fallback instead of model refusal | Selected asset model was absent from bounded RAG context; no same-family model comparison | Asset context/request/retrieval applicability | Add allow-listed profile facts, early CR5/CR10 mismatch refusal, and post-retrieval model isolation. |
| P2-GEN-010 | Generic `unrelated` fallback instead of insufficient-evidence response | No engine-specific oil-choice boundary | Request safety boundary | Refuse exact oil-grade choice without the applicable engine manual/context. |

Configured semantic traces also contained repeated chunks from the same documents. The sampled
chunks were not demonstrated to be near-duplicates, so context-selection behavior was not changed.

## Implementation

- `src/rag/applicability.py` extracts generic technical model identifiers and prevents explicit
  same-family, different-model evidence from crossing the selected-asset boundary.
- `src/rag/evidence_boundary.py` identifies exact high-risk parameter questions. Scoped torque
  questions such as M8 remain answerable; unscoped torque and exact oil-grade choices receive a
  clear safe fallback.
- The existing request and retrieval services invoke those capabilities before retrieval and as a
  post-retrieval defense. Asset, version, language, explicit document type, and other hard filters
  retain their previous behavior.
- The existing asset-context service now includes the already-authorized asset profile. The prompt
  receives only allow-listed profile fields and screens them as untrusted data.
- The evaluator loads manual cases from the manifest and executes them through
  `MaintenanceCopilot`, separately from retrieval Recall/MRR/NDCG denominators. Reports now include
  provenance, readiness, approval state, effective non-secret configuration, total/eligible/manual
  counts, manual-boundary results, skipped metrics, and exact `n/a` reasons.

No database schema, migration, transaction owner, worker, embedding model, reranker model,
generation model, Qdrant default collection, Compose default, or API request contract changed.

## Before/after measurements

| Backend / metric | Before | After | Interpretation |
|---|---:|---:|---|
| Hash fixture Recall@1 | 0.8519 | 0.8519 | No regression; not semantic accuracy |
| Hash fixture Recall@3 | 0.9630 | 0.9630 | No regression |
| Hash fixture Recall@5 | 1.0000 | 1.0000 | No regression |
| Hash fixture MRR | 0.9086 | 0.9086 | No regression |
| Hash fixture NDCG@5 | 0.9314 | 0.9314 | No regression |
| Hash fixture metadata-filter accuracy | 1.0000 | 1.0000 | Asset-type boundary only for this batch |
| Hash fixture follow-up accuracy | 3/3 | 3/3 | Real preceding backend state used |
| Configured semantic Recall@1 | 0.8519 | 0.8519 | Local configured benchmark, not field accuracy |
| Configured semantic Recall@3 | 1.0000 | 1.0000 | No regression |
| Configured semantic Recall@5 | 1.0000 | 1.0000 | No regression |
| Configured semantic MRR | 0.9136 | 0.9136 | No regression |
| Configured semantic NDCG@5 | 0.9356 | 0.9356 | No regression |
| Configured semantic metadata-filter accuracy | 1.0000 | 1.0000 | No regression |
| Manual boundary guard accuracy | 0/3 specific routes | 3/3 | Separate engineering guard check |
| Manual boundary evidence isolation | 3/3 | 3/3 | No manual case enters retrieval evidence |
| SME approval accuracy | n/a | n/a | All 30 cases remain pending SME review |
| Live-provider generation/citation accuracy | n/a | n/a | No LLM is configured; no paid provider was called |

Latency is reported per run but is not treated as deterministic. The configured semantic retrieval
average was approximately 633 ms before and 654 ms after on this machine; this variance is not a
quality regression claim.

## Reproduce

Validate the unchanged dataset and its legitimate warnings:

```powershell
.\.venv\Scripts\python.exe -m evaluation.validate_phase2_dataset `
  evaluation/datasets/phase2_document_derived_v1
```

Run deterministic retrieval and full deterministic safety/conversation reporting:

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation `
  --questions evaluation/datasets/phase2_document_derived_v1/retrieval_questions.jsonl `
  --conversation-sequences evaluation/datasets/phase2_document_derived_v1/conversation_sequences.jsonl `
  --documents evaluation/datasets/phase2_document_derived_v1/corpus_documents.csv `
  --manifest evaluation/datasets/phase2_document_derived_v1/manifest.json `
  --backend in-memory-hash `
  --mode deterministic
```

For configured semantic retrieval, index the same controlled corpus into a dedicated evaluation
collection and select that collection through `QDRANT_COLLECTION`; do not replace the normal
application collection. Offline model flags may be used to prove that only cached models load.

## Remaining gates

The validator must continue to report all six warnings:

1. no field-observed ticket/work-order evidence;
2. all 30 cases pending qualified SME review;
3. Daikin source checksum pending authorised download;
4. Generac source checksum pending authorised download;
5. Grundfos source checksum pending authorised download;
6. source currentness/supersession review pending.

The exact next content action is separate review of the pump, HVAC, and generator rows in
`review_queue.xlsx`, followed by adjudication without changing provenance. A live grounded-
generation benchmark remains blocked until an explicitly configured local/authorised provider is
available and the source/currentness/SME gates are satisfied.

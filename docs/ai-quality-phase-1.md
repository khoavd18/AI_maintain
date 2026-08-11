# AI Quality Phase 1

## Scope and safety boundary

Phase 1 repairs deterministic routing, bounded follow-up context, retrieval-filter
collisions, Vietnamese sparse matching, redundant citation-union handling, and
privacy-safe diagnostics. It does not change the generation model, embedding model,
embedding dimensions, reranker model, Qdrant collection, Compose defaults, transactional
workflows, or the read-only Copilot product boundary.

The Copilot remains maintenance decision support. Retrieved guidance is not an automatic
diagnosis or authorization to operate equipment, mutate business records, or bypass site
safety procedures.

## Controlled corpus assessment (2026-08-10)

The canonical CSV contains six synthetic demonstration documents and produces 30 chunks
with the current chunking settings. There are no real manufacturer or site-approved
documents in this corpus.

| Asset type | Demonstration coverage | Document IDs |
|---|---|---|
| Máy lạnh | periodic checklist; initial no-cooling checks | DOC-001, DOC-002 |
| Máy bơm nước | periodic checklist; initial vibration/abnormal-noise checks | DOC-003, DOC-004 |
| Máy phát điện dự phòng | periodic checklist; initial no-start checks | DOC-005, DOC-006 |

The six IDs and bodies are distinct, and no direct duplicate was found. That does not prove
that the content is current or conflict-free: the legacy CSV shape has no approval state,
supersession status, or active/inactive lifecycle. Version `1.0`, effective date
`2026-01-01`, and language `vi` are projected by the validated loader for this legacy
fixture rather than managed through a controlled publication workflow.

Known gaps:

- no manufacturer manuals, model/serial applicability, approved site SOPs, or approved
  safety procedures;
- no authoritative troubleshooting trees, measured limits, part numbers, or approved
  repair instructions;
- no document owner, reviewer, approval timestamp, expiry/review date, checksum, or
  supersession chain;
- no authoritative stale/conflict adjudication or active-only publication state;
- only three asset types and three focused troubleshooting categories are represented;
- synthetic text cannot establish operational accuracy, model accuracy, prevented
  failures, ROI, or production readiness.

## Phase 2 controlled ingestion plan

Phase 2 should remain a controlled operator workflow rather than a broad knowledge-base UI.

1. Accept explicitly selected PDF, DOCX, Markdown, and CSV files into a quarantined import
   run. Record source filename as display metadata only; generate a storage-safe ID and
   SHA-256 checksum. Never expose local paths to retrieval or API clients.
2. Extract text with a format-specific parser under file-size, page-count, and decompression
   bounds. Reject encrypted, malformed, unsupported, or instruction-injection content.
3. Require metadata before approval: stable document ID, title, asset type, applicable
   manufacturer/model where known, document type, failure category where applicable,
   language, semantic version, effective date, owner, approval state, reviewer, approval
   timestamp, and supersedes/superseded-by links.
4. Keep states explicit: `draft`, `in_review`, `approved`, `superseded`, and `withdrawn`.
   Only approved, effective, non-superseded documents may become retrieval-active. A new
   version never overwrites the prior version or its checksum.
5. Detect exact checksum duplicates, near-duplicate sections, overlapping applicability,
   contradictory safety statements, and missing lifecycle metadata. Route conflicts to a
   human document owner; do not ask an LLM to choose the authoritative instruction.
6. Use the canonical `src/rag/chunking.py` contract. Persist the source checksum, document
   version, approval state, and chunk checksum in the indexing manifest and Qdrant payload.
7. Build and validate a complete candidate index, then publish it atomically through a
   controlled collection/alias or manifest-version switch. Record document/chunk counts,
   added/updated/removed IDs, embedding identity, dimensions, and checksum. Do not mix
   embeddings with different dimensions or instruction formats.
8. Make retrieval active-only by an explicit hard metadata filter. Preserve explicit
   version and language filters, and never relax asset isolation or publication state.
9. Reindex only through the explicit indexing command. Invalidate/refresh process-local
   sparse state through the bounded freshness contract and verify dense/sparse corpus
   identity before promotion.
10. Run deterministic regression, configured-Qdrant retrieval, grounded generation,
    citation, safety, latency, and rollback checks before publishing a corpus version.

No database migration or administration UI is part of Phase 1.

## Phase 2 model benchmark matrix

No candidate is promoted by this plan. Each row requires a real configured-service run on
the approved corpus and held-out transformations; hash embeddings and stub answers remain
test fixtures only.

| Layer | Baseline | Candidate family | Required handling | Main measures |
|---|---|---|---|---|
| Generation | operator-configured Ollama model; none enabled at the Phase 1 checkpoint | general-purpose Qwen family at hardware-feasible quantizations | preserve strict JSON schema, Vietnamese output, no tool use, current citation gates | routing-independent answer validity, citation validity, unsupported-claim rejection, fallback reason, p50/p95 latency, RAM/VRAM |
| Embedding | `intfloat/multilingual-e5-small`, 384 dimensions | Qwen3 Embedding sizes that fit the benchmark host | keep E5 `query:`/`passage:` prefixes only for E5; use the candidate's documented query/document instructions | Recall@1/3/5, MRR, NDCG@5, unaccented slice, identifier slice, indexing/query latency, memory |
| Reranking | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | Qwen3 Reranker sizes that fit the benchmark host | use the candidate's required task/query/document template; do not reuse E5 prefixes blindly | NDCG@5, Recall@1, unsafe/conflict retention, p50/p95 latency, memory |

Benchmark combinations should first vary one layer at a time, then test the best
non-regressing combinations. Required gates are unchanged safety rejection, no cross-asset
retrieval, Recall@3/5 no worse than the Phase 1 expanded baseline, improved held-out
unaccented/shorthand retrieval, valid claim-level citations, and acceptable cold/warm
latency on the target host.

## Phase 1 host and provider inventory

- System RAM: 16,780,795,904 bytes total; 1,576,849,408 bytes free at inspection time.
- GPU: NVIDIA GeForce RTX 4060 Laptop GPU; `nvidia-smi` reported 8,188 MiB total and
  7,957 MiB free. An Intel UHD integrated GPU was also present.
- Ollama client: `0.32.6`. The server was unavailable, so `ollama list` and provider
  cold/warm generation latency were not available. A local manifest for
  `qwen2.5-coder:7b` exists; that is not evidence that the model server is usable or that
  this coding-tuned model is suitable for maintenance answers.
- Cached embedding: `intfloat/multilingual-e5-small`. Offline measurement was 7,563 ms
  initialization, 48 ms first query, and 18 ms warm query.
- Cached reranker: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`. Offline measurement for
  five candidates was 1,750 ms cold and 156 ms warm.
- Process working set was about 122 MB before model load, 814 MB after embedding, and
  1,182 MB after embedding plus reranker. The auto-selected run reported no allocated CUDA
  memory, so these measurements describe the observed CPU path.
- Qdrant was reachable at the configured local service and contained 30 active/listed
  chunks. The configured generation provider was disabled and had no model name.

These one-host measurements are characterization data, not capacity or production-readiness
claims.

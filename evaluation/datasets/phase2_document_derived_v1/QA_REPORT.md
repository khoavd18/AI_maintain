# Phase 2 Document-Derived Dataset — QA Report

Status: **DRAFT_SME_REVIEW_REQUIRED**

This report records engineering checks only. It does not approve the maintenance content, establish field accuracy, or replace review by qualified pump, HVAC, and generator specialists.

## Package checks

- Dataset validator: `PASS_WITH_WARNINGS` — 0 errors, 6 expected warnings.
- Counts: 3 official manufacturer sources, 30 cases, 26 evidence spans/corpus documents, 27 runner-eligible cases, 3 manual-review-only cases, and 3 two-turn conversations.
- Traceability: every case points to a corpus document and evidence span; every evidence span points to an official source plus manual page and section.
- Leakage: no evaluation question appears verbatim in the corpus.
- Review workbook: four rendered sheets inspected; 30 pending cases; formula scan matched 0 errors.
- Changed Python files: Ruff check and format check passed.

The six validator warnings are intentional release gates: field evidence is absent, all cases await SME review, all three manufacturer PDF checksums await an authorised download, and source currentness/supersession remains pending.

## Deterministic integration benchmark

The in-memory hash backend is a reproducible wiring check, not a production semantic benchmark.

| Metric | Result |
|---|---:|
| Retrieval questions | 27 |
| Recall@1 | 0.8519 |
| Recall@3 | 0.9630 |
| Recall@5 | 1.0000 |
| MRR | 0.9086 |
| NDCG@5 | 0.9314 |
| Asset-type filter accuracy | 1.0000 |
| Two-turn follow-up accuracy | 1.0000 (3/3) |

All answers in deterministic mode used the existing safe fallback path because no LLM was enabled. Metrics without an applicable case type are reported as `n/a` in the final deterministic report.

## Test evidence

- Phase 2 focused suite: **4 passed**.
- Whole-repository run: **1,212 passed, 87 skipped, 5 failed**.

The five remaining failures are baseline/source-archive blockers outside this change:

1. API health expects generated raw/analytics files that are absent from the supplied source archive.
2. Two Phase 1 evaluator tests require `data/raw/documents.csv`, also absent from the supplied archive.
3. The protected-repository AST hashes already differ from the source files in the supplied archive.
4. One Streamlit AppTest resolves its relative entrypoint under `tests/` and cannot find it.

No attempt was made to repair those unrelated baseline issues in this Phase 2 package.

## Promotion gates

Before counting any case as approved:

1. Confirm exact manual revision and supersession status, especially the older Grundfos Model A source.
2. Capture source SHA-256 values after an authorised download.
3. Complete separate pump, HVAC, and generator SME review in `review_queue.xlsx`.
4. Adjudicate disagreements and update evidence/cases while preserving source locators.
5. Run the configured embedding, reranker, and grounded-generation benchmark.
6. Keep this batch labelled document-derived; do not relabel it as field-observed.

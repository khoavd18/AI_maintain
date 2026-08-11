# Phase 2 Document-Derived Evaluation — Handover

This source tree adds a draft, source-traceable Phase 2 evaluation batch while preserving the existing Phase 1 fixture and default evaluator behavior.

## Added

- `evaluation/datasets/phase2_document_derived_v1/`: 30 cases, evidence registry, controlled CSV corpus, SME workbook, validation and benchmark reports.
- `evaluation/validate_phase2_dataset.py`: structural, traceability, leakage, source-host, and draft-state validator.
- `tests/test_phase2_document_dataset.py`: focused package and evaluator integration tests.
- `docs/ai-quality-phase-2-document-derived.md`: lifecycle, safety, and promotion guidance.

## Changed

- `evaluation/run_evaluation.py` accepts an additive custom corpus, conversation set, and manifest. Its original Phase 1 paths and version remain the defaults.
- Optional evaluation ratios now render as `n/a` when a dataset has no applicable denominator instead of displaying a misleading zero.

## Reproduce

From the repository root:

```bash
python -m evaluation.validate_phase2_dataset \
  evaluation/datasets/phase2_document_derived_v1

python -m evaluation.run_evaluation \
  --questions evaluation/datasets/phase2_document_derived_v1/retrieval_questions.jsonl \
  --conversation-sequences evaluation/datasets/phase2_document_derived_v1/conversation_sequences.jsonl \
  --documents evaluation/datasets/phase2_document_derived_v1/corpus_documents.csv \
  --manifest evaluation/datasets/phase2_document_derived_v1/manifest.json \
  --backend in-memory-hash \
  --mode deterministic
```

The package is deliberately blocked at `DRAFT_SME_REVIEW_REQUIRED`. Manufacturer PDFs are linked, not redistributed; all Vietnamese maintenance text is a concise paraphrase pending specialist review.

# Phase 2 Dataset Validation Report

- Status: **PASS_WITH_WARNINGS**
- Errors: 0
- Warnings: 3

## Observed counts

| Item | Count |
|---|---:|
| sources | 3 |
| asset_profiles | 3 |
| cases | 300 |
| cases_per_asset_profile | 100 |
| retrieval_questions | 300 |
| no_answer_cases | 30 |
| evidence_spans | 152 |
| corpus_documents | 3 |
| conversation_sequences | 30 |
| conversation_turns | 66 |
| review_queue_rows | 300 |
| original_cases_preserved | 30 |
| new_cases | 270 |

## Findings

- **WARNING — field_evidence_absent**: All 300 cases are document-derived; no field evidence exists.
- **WARNING — sme_review_pending**: All 300 cases remain pending qualified SME review.
- **WARNING — source_currentness_blocked**: Grundfos and Generac remain VERSION_AMBIGUOUS/HIGH and cannot be promoted.

## Decision

This validation checks package structure, traceability, projection consistency, and obvious leakage. It does not approve maintenance content or establish field accuracy.

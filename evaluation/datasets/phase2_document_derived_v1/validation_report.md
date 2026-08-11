# Phase 2 Dataset Validation Report

- Status: **PASS_WITH_WARNINGS**
- Errors: 0
- Warnings: 6

## Observed counts

| Item | Count |
|---|---:|
| sources | 3 |
| asset_profiles | 3 |
| cases | 30 |
| cases_per_asset_profile | 10 |
| runner_eligible_cases | 27 |
| manual_review_only_cases | 3 |
| evidence_spans | 26 |
| corpus_documents | 26 |
| conversation_sequences | 3 |
| conversation_turns | 6 |

## Findings

- **WARNING — field_evidence_absent**: No field-observed ticket or work-order evidence is present.
- **WARNING — sme_review_pending**: All 30 cases require domain-expert review before approval.
- **WARNING — source_checksum_pending**: SRC-DAIKIN-RZAG-4P695307-1B needs a SHA-256 after authorised download.
- **WARNING — source_checksum_pending**: SRC-GENERAC-MLG15-A0000381158 needs a SHA-256 after authorised download.
- **WARNING — source_checksum_pending**: SRC-GF-CR5-0407 needs a SHA-256 after authorised download.
- **WARNING — supersession_pending**: One or more sources require a currentness/supersession check.

## Decision

This validation checks package structure, traceability, projection consistency, and obvious leakage. It does not approve maintenance content or establish field accuracy.

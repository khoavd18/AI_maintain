# Phase 2 Document-Derived Evaluation — Draft v0.1.0

This directory adds a source-traceable calibration batch without changing or replacing the Phase 1 synthetic dataset.

## What this package is

- 30 Vietnamese evaluation cases: 10 pump, 10 HVAC, and 10 generator cases.
- 27 cases projected into the existing retrieval runner contract.
- 3 evidence-boundary/model-applicability cases reserved for manual and generation-level review.
- 3 ordered two-turn conversation sequences.
- 26 Vietnamese evidence paraphrases linked to exact manufacturer manual pages and sections.
- A review queue for a maintenance subject-matter expert.

All records are labelled `document_derived`, `draft`, and `pending_sme`. Nothing in this package is a field-observed ticket, a company-approved SOP, or an authorised repair decision.

## Selected asset profiles

| Asset type | Manufacturer/model scope | Source boundary |
|---|---|---|
| Pump | Grundfos CR 5 Model A, 50/60 Hz, 1/3 phase | Service instructions 96546866 0407 GB |
| HVAC | Daikin RZAG71-140N Sky Air Alpha-series | Installer reference guide 4P695307-1B, 2025.03 |
| Generator | Generac Mobile MLG15, SN 3004595385 and above | Owner's Manual A0000381158 |

## Copyright and source handling

Manufacturer PDFs are not copied into this package. `source_registry.jsonl` stores official links and metadata; `evidence_spans.jsonl` and `corpus_documents.csv` contain concise Vietnamese paraphrases for calibration. Before a real controlled ingestion, download the authorised source, capture its SHA-256, check for supersession, and obtain the necessary usage approval.

## Validation

From the repository root:

```bash
python -m evaluation.validate_phase2_dataset \
  evaluation/datasets/phase2_document_derived_v1
```

Run the additive retrieval fixture:

```bash
python -m evaluation.run_evaluation \
  --questions evaluation/datasets/phase2_document_derived_v1/retrieval_questions.jsonl \
  --conversation-sequences evaluation/datasets/phase2_document_derived_v1/conversation_sequences.jsonl \
  --documents evaluation/datasets/phase2_document_derived_v1/corpus_documents.csv \
  --manifest evaluation/datasets/phase2_document_derived_v1/manifest.json \
  --backend in-memory-hash \
  --mode retrieval
```

The in-memory hash run is only a deterministic integration check. Semantic quality requires the configured embedding/reranker/LLM benchmark and SME-approved sources.

## Promotion rule

Cases move through `draft -> SME_verified -> adjudicated -> approved`. Only `approved` cases may be counted toward the planned 300–500 source-derived evaluation set. High-risk electrical, refrigerant, fuel, pressure, and rotating-equipment instructions require a qualified reviewer.

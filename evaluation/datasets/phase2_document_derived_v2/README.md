# Phase 2 Document-Derived Evaluation — Draft v2.0.0

This additive package contains exactly 300 source-traceable draft cases: 100 each for Grundfos CR 1/3/5 Model A, Daikin RZAG71-140N, and Generac Mobile MLG15 SN 3004595385+.

The wording is synthetic but grounded in concise paraphrases of captured official OEM documents. It is not field-observed history, an approved SOP, or an automatic maintenance decision. The original 30 v1 questions and rubrics are logically preserved; 270 cases are new.

Grundfos and Generac remain `VERSION_AMBIGUOUS` and source-currentness blocked. Daikin is `VERIFIED_CURRENT`, but all 300 cases remain `pending` SME review and `promotion_eligible: false`.

Full copyrighted PDFs are not included. Validate with:

```bash
python -m evaluation.validate_phase2_dataset evaluation/datasets/phase2_document_derived_v2
```

The deterministic in-memory evaluation is a wiring and retrieval fixture, not semantic, field, production, or SME-approved accuracy.

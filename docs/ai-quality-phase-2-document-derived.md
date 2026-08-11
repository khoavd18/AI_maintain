# AI Quality Phase 2 — Document-Derived Calibration Batch

## Decision and boundary

The project owner selected the no-field-data path. This phase therefore uses public, manufacturer-hosted documentation for three bounded pilot profiles:

- Grundfos CR 5 Model A pump;
- Daikin RZAG71-140N Sky Air Alpha-series HVAC outdoor unit;
- Generac Mobile MLG15 diesel generator, serial number 3004595385 and above.

The resulting records are `document_derived`. They are not field-observed tickets, company-approved SOPs, or proof of production accuracy. Phase 1 remains unchanged as the deterministic synthetic regression baseline.

## Batch contents

The first calibration batch lives under `evaluation/datasets/phase2_document_derived_v1/` and contains:

- 30 draft single-turn cases, balanced 10/10/10 by asset profile;
- 27 cases projected into the existing retrieval evaluation contract;
- 3 evidence-boundary/model-isolation cases that must be judged at generation and human-review level;
- 3 two-turn sequences covering follow-up state;
- 26 page/section-traceable evidence spans;
- 26 Vietnamese paraphrase documents accepted by the existing controlled document loader;
- one SME review workbook.

Each case records facts that must appear, claims that must not appear, safety requirements, an answer boundary, required source IDs, and the reviewer role.

## Source policy

Only manufacturer-hosted HTTPS links are registered. Full manuals are deliberately excluded from the package. Before controlled pilot ingestion, the operator must:

1. confirm use rights;
2. download the exact revision through an authorised workflow;
3. calculate and register SHA-256;
4. verify that the document has not been superseded;
5. verify model, serial, voltage, frequency, refrigerant, engine, and local-regulation applicability;
6. obtain site approval where required.

The Grundfos source is an older Model A service document and therefore carries an explicit currentness blocker.

## Safety policy

The Copilot remains read-only. It may explain source-backed checks but may not operate equipment, bypass an interlock, confirm LOTO, modify a ticket/work order, or authorize maintenance. Electrical stored energy, refrigerant recovery, hot coolant, rotating equipment, fuel/exhaust, pressure, and load-transfer cases require a qualified reviewer and visible escalation language.

## Review lifecycle

The permitted state transition is:

```text
draft -> SME_verified -> adjudicated -> approved
```

No case in v0.1.0 is approved. Only approved cases may be counted toward the planned 300–500 evaluation set or used as a release gate.

## Evaluation use

The in-memory hash run proves only that the dataset can be parsed, filtered, retrieved, and reported deterministically. It is not a semantic benchmark. The configured benchmark must later measure Recall@1/3/5, MRR, NDCG@5, asset/model isolation, evidence-boundary refusal, citation validity, unsupported claims, safety escalation, multi-turn state, and cold/warm latency.

Generation-level scoring is blocked until the source documents and case rubrics are SME-verified. The three manual-only boundary cases intentionally prevent the current retrieval-only projection from treating missing parameters or a wrong model as ordinary answerable questions.

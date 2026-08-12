# Phase 2 v2 Dataset — QA Report

Status: **DRAFT_SME_REVIEW_REQUIRED**

## Construction summary

- Cases: 300 (30 logically preserved from v1; 270 new).
- Families: 100 pump, 100 HVAC, 100 generator.
- Evidence spans/corpus documents: 152 ({'SRC-GF-CR5-0407': 50, 'SRC-DAIKIN-RZAG-4P695307-1B': 51, 'SRC-GENERAC-MLG15-A0000381158': 51}).
- Review rows: 300, all Pending.
- Field-observed cases: 0.

## Duplicate analysis

- Unique case IDs: 300/300.
- Unique normalized questions: 300/300.
- Exact duplicate normalized questions: 0.
- Intentional robustness variants: 18 (6.0%; limit 15%).
- Near-duplicate gate: token-set Jaccard threshold 0.90; intentional robustness pairs are explicitly tagged and no untagged pair may exceed the threshold.

Cases vary by diagnostic goal, operational context, applicability condition, evidence need, response policy, or language. The validator is authoritative for quota, referential, numeric-grounding, UTF-8/LF, secret, checksum, and duplicate gates.

## Source promotion gates

- Daikin: VERIFIED_CURRENT / MEDIUM; source gate passed, SME pending.
- Grundfos: VERSION_AMBIGUOUS / HIGH; source gate blocked. Captured artifact identifies `96546866 03.2022` while the v1 registry named `96546866 0407 GB`; OEM resolution remains required.
- Generac: VERSION_AMBIGUOUS / HIGH; source gate blocked.

No deterministic fixture metric is a production, semantic, field, or SME-approved accuracy claim.

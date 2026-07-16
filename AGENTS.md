# Repository Guardrails

These rules apply to future agent work in this repository.

## Product Boundary

AI Maintenance Copilot is a batch analytics and AI decision-support layer for facility maintenance. It is not a complete CMMS, system of record, autonomous maintenance controller, or production-ready enterprise platform.

Human facility managers and technicians remain responsible for prioritization, safety checks, field inspection, maintenance execution, and final decisions. Never describe a score or recommendation as an automatic decision.

## Canonical Architecture

- Keep the primary MVP architecture CSV-first and batch-first.
- Keep FastAPI as the serving boundary. Streamlit must consume FastAPI and must not read raw or processed CSV files directly.
- Treat PostgreSQL as optional/experimental. Do not make it a prerequisite for the main demo or migrate serving to PostgreSQL without an explicit scope decision.
- Use Qdrant only for RAG document retrieval.
- Do not add real-time ingestion, streaming, or event-processing infrastructure.

## Canonical Analytics

Extend only these production paths:

- Feature engineering: `src/features/build_features.py`
- Anomaly detection: `src/models/anomaly_detection.py`
- Risk scoring: `src/risk/risk_scoring.py`
- Dashboard: `src/dashboard/app.py`
- RAG chunking: `src/rag/chunking.py`

Duplicate anomaly, risk, ingestion, sample-data, and dashboard wrappers were removed in the verified cleanup milestone. Do not recreate parallel implementations or compatibility entrypoints; extend only the canonical paths above.

## Scope Expansion Prohibited

Do not add or propose implementation work for the following areas unless the repository owner explicitly changes the MVP scope:

- spare-parts inventory or inventory optimization;
- QR code generation, scanning, or asset tagging;
- resident mobile applications;
- technician mobile applications;
- vendor or contract management;
- real-time IoT streaming or live event processing;
- complex approval workflows;
- enterprise authentication, authorization, or RBAC;
- automatic production work-order creation;
- exact failure-time prediction.

Historical `parts_replaced` data may remain in maintenance logs, but it must not grow into an inventory subsystem.

## Compatibility And Claims

- Preserve existing API contracts unless a task explicitly authorizes a change.
- Prefer additive, tested data-contract changes.
- Keep code, module, column, and API field names in English.
- Keep user-facing business values and operational explanations in Vietnamese.
- Clearly separate current behavior from future work in documentation.
- Do not claim production readiness, model accuracy, ROI, prevented failures, or business impact without measured evidence.
- Describe risk as prioritization, not a calibrated failure probability or guaranteed prediction.

## Verification

For repository changes, run the tests relevant to the modified area, then run:

```bash
python -m pytest
python -m ruff check .
```

Keep the main portfolio demo reproducible without PostgreSQL.

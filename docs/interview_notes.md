# Interview Notes

## What problem does this project solve?

It helps facility maintenance teams prioritize risky assets and decide what to inspect next. Instead of manually checking sensor readings, tickets, overdue maintenance, and SOP documents, the system turns those inputs into anomaly scores, explainable risk scores, recommendations, and source-grounded copilot answers.

## What is the input data?

The MVP uses deterministic Vietnamese synthetic maintenance data:

- assets;
- hourly sensor readings;
- maintenance tickets;
- maintenance logs;
- risk score snapshots;
- Vietnamese SOP/checklist/troubleshooting documents.

The data is generated as CSV files in `data/raw` and loaded into PostgreSQL. Processed outputs are written to `data/processed`.

## What is the output?

The main outputs are:

- daily asset-level features;
- anomaly results with Vietnamese anomaly reasons;
- explainable risk scores with `risk_level`, `main_reasons`, and `recommended_action`;
- FastAPI responses for dashboards/integrations;
- Streamlit dashboard views;
- RAG copilot answers with sources and retrieved chunks.

## How is risk predicted?

Risk is scored with an explainable formula:

```text
final_risk_score =
  35% anomaly_score
+ 20% maintenance_overdue_score
+ 20% recent_ticket_score
+ 15% criticality_score
+ 10% runtime_score
```

The score maps to Vietnamese risk levels:

- `Thấp`
- `Trung bình`
- `Cao`
- `Khẩn cấp`

This is a prioritization score, not a guaranteed failure prediction.

## Does it use machine learning?

Yes. The anomaly detection stage combines:

- rule-based thresholds for interpretable maintenance signals;
- scikit-learn Isolation Forest for multivariate outlier detection.

The RAG module also uses local sentence-transformers embeddings when installed.

## What does RAG do?

RAG retrieves relevant Vietnamese SOP/checklist/troubleshooting chunks from Qdrant and combines them with structured asset context from the API service layer. The current answer composer is deterministic: it summarizes risk/anomaly context, extracts recommended actions from retrieved chunks, and lists sources.

It does not require a paid API or external LLM.

## How is it different from a normal maintenance system?

A normal CMMS/S-Maintain system is the system of record for assets, work orders, technician assignments, inventory, approvals, and maintenance history.

This project is an AI decision-support layer. It analyzes CMMS-like data, detects abnormal patterns, prioritizes risky assets, explains risk drivers, and retrieves SOP/checklist context. In production, it would integrate with a CMMS rather than replace it.

## Why use PostgreSQL and Qdrant?

PostgreSQL is a strong fit for structured operational maintenance data: assets, readings, tickets, logs, and risk scores.

Qdrant is a vector database designed for semantic retrieval. It stores embeddings of SOP/checklist chunks and supports top-k search with metadata filters such as `asset_type`.

Together they support hybrid maintenance intelligence:

- structured context from PostgreSQL/processed features;
- semantic document context from Qdrant.

## What are the limitations?

- Synthetic data is realistic for demos but not production-validated.
- The API currently serves processed CSV outputs rather than live database queries.
- Risk scoring is explainable but heuristic.
- The copilot composer is deterministic and extractive, not LLM-based.
- RAG quality depends on indexed documents and local embedding availability.
- No authentication, authorization, scheduling, observability, or production deployment hardening is included.

## How would you improve it in production?

- Integrate with real CMMS/S-Maintain, BMS, IoT, and ticketing data.
- Replace processed CSV serving with database-backed query services.
- Add scheduled pipelines and model/retrieval monitoring.
- Add labeled historical failures and evaluate risk calibration.
- Add RAG evaluation for retrieval precision, answer faithfulness, and recommendation quality.
- Add an LLM answer composer with strict source grounding and fallback behavior.
- Add authentication, RBAC, audit logging, and observability.
- Add deployment automation and environment-specific configuration.

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

The data is generated as CSV files in `data/raw`. The canonical batch pipeline reads those CSVs directly and writes analytics outputs to `data/processed`. Loading the raw data into PostgreSQL is an optional experiment, not a requirement for the main demo.

## What is the output?

The main outputs are:

- daily asset-level features;
- anomaly results with Vietnamese anomaly reasons;
- explainable risk scores with `risk_level`, `main_reasons`, and `recommended_action`;
- preventive maintenance status, recurring issue groups, and a descriptive KPI snapshot;
- FastAPI responses for dashboards/integrations;
- four manager-facing Streamlit views for overview, asset inspection, anomaly/recurrence review, and Copilot;
- RAG copilot answers with sources and retrieved chunks.

## How is risk predicted?

Risk is scored with an explainable formula:

```text
final_risk_score =
  20% anomaly_score
+ 25% maintenance_overdue_score
+ 20% unresolved_ticket_score
+ 10% recent_ticket_score
+  7.5% recurring_issue_score
+ 10% criticality_score
+  5% follow_up_score
+  2.5% runtime_score
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

RAG retrieves relevant Vietnamese SOP/checklist/troubleshooting chunks from Qdrant and combines them with structured asset facts from the CSV-backed service layer. Khi asset được chọn, `asset_type` là retrieval filter bắt buộc; `document_type` và `failure_category` là optional filters. Ticket/failure text gần đây chỉ bổ sung query context, không thay đổi facts và không tạo diagnosis.

Indexer thay thế toàn bộ MVP collection trong mỗi lần chạy. Stable chunk IDs cùng full rebuild ngăn duplicate và stale chunks. Vector dimension, missing/empty collection và Qdrant availability được kiểm tra tường minh.

Copilot dùng relevance gate `0.15` cho deterministic hash test double và `0.55` cho local sentence-transformer. Các threshold này không phải confidence probability. Empty/low-relevance/unavailable retrieval trả safe fallback với sources rỗng thay vì compose từ unrelated content.

Current answer composer là deterministic: nó tách asset summary, retrieved checklist, sources, safety notice và recommendation limits. Mỗi successful answer có source; mọi answer nhắc rằng anomaly/risk không chứng minh failure và technician phải ưu tiên manual nhà sản xuất cùng quy trình an toàn.

It does not require a paid API or external LLM.

## How is it different from a normal maintenance system?

A normal CMMS/S-Maintain system is the system of record for assets, work orders, technician assignments, inventory, approvals, and maintenance history.

This project is an AI decision-support layer. It analyzes CMMS-like data, detects abnormal patterns, prioritizes risky assets, explains risk drivers, and retrieves SOP/checklist context. In production, it would integrate with a CMMS rather than replace it.

## Why keep PostgreSQL and Qdrant?

PostgreSQL is retained as an optional/experimental example of structured storage for assets, readings, tickets, logs, and risk snapshots. The current API and Copilot structured context do not query PostgreSQL; they use canonical processed CSV outputs.

Qdrant is a vector database designed for semantic retrieval. It stores embeddings of SOP/checklist chunks and supports top-k search with conjunctive metadata filters for `asset_type`, `document_type`, and `failure_category`.

In the current MVP, the active hybrid context is:

- structured context from processed CSV features, anomalies, and risks;
- semantic document context from Qdrant.

## What are the limitations?

- Synthetic data is realistic for demos but not production-validated.
- The API currently serves processed CSV outputs rather than live database queries.
- Asset, ticket, and maintenance-log API views read raw CSV contracts; analytics views read canonical processed CSVs.
- Risk scoring is explainable but heuristic.
- The copilot composer is deterministic and extractive, not LLM-based.
- RAG quality depends on six synthetic documents and local embedding availability; no labeled retrieval evaluation dataset is available yet.
- Relevance thresholds are transparent safeguards but have not been calibrated on real SOP collections.
- The Copilot is decision support, not an automatic diagnostic or failure-prediction system.
- No authentication, authorization, scheduling, observability, or production deployment hardening is included.
- The Streamlit workflow has API/client tests and startup smoke coverage, but no production browser regression suite.

## How would you improve it in production?

- Integrate with real CMMS/S-Maintain, BMS, IoT, and ticketing data.
- Replace processed CSV serving with database-backed query services.
- Add scheduled pipelines and model/retrieval monitoring.
- Add labeled historical failures and evaluate risk calibration.
- Add RAG evaluation for retrieval precision, answer faithfulness, and recommendation quality.
- Add an LLM answer composer with strict source grounding and fallback behavior.
- Add authentication, RBAC, audit logging, and observability.
- Add deployment automation and environment-specific configuration.

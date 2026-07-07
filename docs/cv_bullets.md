# CV Bullets

- Built an AI Maintenance Copilot that analyzes Vietnamese facility maintenance data to detect anomalies, score equipment risk, and generate SOP-grounded troubleshooting recommendations.
- Engineered daily asset-level features across 100 synthetic assets and 60 days of hourly readings, including rolling energy trends, vibration deltas, ticket frequency, maintenance overdue days, and criticality scores.
- Implemented rule-based and Isolation Forest anomaly detection, producing explainable Vietnamese anomaly labels and reasons for facility maintenance workflows.
- Designed an explainable risk scoring engine combining anomaly score, maintenance overdue status, recent ticket activity, asset criticality, and runtime behavior.
- Developed a CSV-backed FastAPI backend and Streamlit dashboard for maintenance summary metrics, top-risk asset monitoring, anomaly review, asset context inspection, and copilot interaction.
- Integrated Qdrant-based RAG retrieval over Vietnamese SOP/checklist documents to provide source-grounded technician recommendations without paid APIs.
- Added automated pytest and Ruff validation across data generation, ingestion, feature engineering, anomaly detection, risk scoring, API routes, dashboard helpers, and RAG components.

## Metrics To Customize

- Assets modeled: `100` synthetic assets by default.
- Sensor readings: about `144,000` hourly readings by default.
- Processed feature/risk records: about `6,000` daily asset rows by default.
- Test suite: replace with the latest `pytest` count from local verification.
- Retrieval corpus: replace with production SOP/checklist/ticket document counts when available.

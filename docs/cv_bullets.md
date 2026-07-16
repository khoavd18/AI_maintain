# AI Maintenance Copilot — Vietnamese Predictive Maintenance Decision Support

Built a CSV-first, batch analytics MVP that prioritizes facility equipment risk and retrieves Vietnamese SOP/checklist guidance for technicians. Integrated explainable analytics, FastAPI, a five-view Streamlit decision workflow and Qdrant-backed RAG with human safety controls.

## CV Bullets

- Engineered a deterministic Vietnamese maintenance dataset covering 27 HVAC, pump and generator assets, 77,760 hourly readings, 42 tickets and 86 maintenance logs.
- Built daily feature engineering and hybrid anomaly detection using rule-based signals plus Isolation Forest, producing 3,240 explainable anomaly records and 3,240 risk records per default run.
- Designed an explainable risk-prioritization formula combining anomaly, preventive-overdue, unresolved/recent ticket, recurrence, criticality, follow-up and runtime signals with Vietnamese contributing factors.
- Delivered a CSV-backed FastAPI service and five Streamlit workflows for KPIs, risk-to-action investigation, ticket assignment, maintenance result capture, anomaly/recurrence review and Copilot guidance.
- Implemented deterministic Qdrant indexing and metadata-filtered RAG over 6 Vietnamese synthetic SOP/checklist documents and 30 chunks, with source citations, relevance gates and safe fallback behavior; the complete MVP is validated by 122 automated tests.

## Technologies

Python, pandas, NumPy, scikit-learn, FastAPI, Streamlit, httpx, Qdrant, sentence-transformers, Pydantic, pytest, Ruff, Docker Compose; optional SQLAlchemy/PostgreSQL compatibility path.

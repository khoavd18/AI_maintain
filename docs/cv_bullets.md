# AI Maintenance Copilot — Vietnamese Predictive Maintenance Decision Support

Built a PostgreSQL-backed maintenance decision-support MVP that prioritizes facility equipment risk, controls work-order spare-parts usage and retrieves Vietnamese SOP/checklist guidance for technicians. Integrated transactional workflows, explainable batch analytics, FastAPI, Streamlit/Next.js frontends and Qdrant-backed RAG with human safety controls.

## CV Bullets

- Engineered a deterministic Vietnamese maintenance dataset covering 27 HVAC, pump and generator assets, 77,760 hourly readings, 42 tickets and 86 maintenance logs.
- Built daily feature engineering and hybrid anomaly detection using rule-based signals plus Isolation Forest, producing 3,240 explainable anomaly records and 3,240 risk records per default run.
- Designed an explainable risk-prioritization formula combining anomaly, preventive-overdue, unresolved/recent ticket, recurrence, criticality, follow-up and runtime signals with Vietnamese contributing factors.
- Designed an Alembic-managed PostgreSQL schema and repository/service layer with foreign keys, atomic ticket/log workflows, concurrent-safe generated IDs, optimistic conflict handling and idempotent 27/42/86 CSV seed import.
- Implemented preventive maintenance planning and standalone work orders with bounded timezone-aware recurrence, idempotent concurrent generation, immutable checklist snapshots, technician execution, evidence, exactly-once maintenance logs and independent verification.
- Built a PostgreSQL ticket-operations domain with backend-owned impact-by-urgency prioritization, business-calendar SLA snapshots, explicit lifecycle actions, append-only communication, nine operational queues and idempotent escalation evaluation.
- Implemented concurrent-safe spare-parts stock control across 8 deterministic demo parts and 5 stock locations, separating requirements, reservations, issues, consumption and returns with immutable movements, atomic transfers and idempotent commands.
- Preserved existing FastAPI and frontend contracts while migrating asset, ticket and maintenance-log persistence from mutable CSV files to PostgreSQL; added a validated PostgreSQL-to-CSV snapshot bridge for unchanged batch models.
- Implemented deterministic Qdrant indexing and metadata-filtered RAG over 6 Vietnamese synthetic SOP/checklist documents and 30 chunks, with source citations, relevance gates and safe fallback behavior.

## Technologies

Python, pandas, NumPy, scikit-learn, FastAPI, SQLAlchemy, PostgreSQL, Alembic, psycopg, Streamlit, Next.js, React Query, Zod, Qdrant, sentence-transformers, Pydantic, pytest, Vitest, Ruff and Docker Compose.

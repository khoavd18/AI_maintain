# Demo Script

Use this script for a recruiter, interviewer, or portfolio walkthrough. It assumes Python dependencies are installed and Docker is available.

## 1. Start Infrastructure

```bash
make services-up
```

This starts PostgreSQL and Qdrant from `docker-compose.yml`.

## 2. Generate Vietnamese Synthetic Data

```bash
make generate-data
```

Show `data/raw` and mention the generated assets, sensor readings, tickets, logs, risk snapshots, and Vietnamese SOP/checklist documents.

## 3. Initialize Database

```bash
make init-db
```

This creates the SQLAlchemy schema for structured maintenance data.

## 4. Load Data

```bash
make load-data
```

Explain that PostgreSQL is the structured data store for assets, readings, tickets, logs, risk scores, and documents.

## 5. Build Features

```bash
make build-features
```

Show `data/processed/asset_daily_features.csv`. Highlight rolling energy trends, vibration deltas, ticket counts, overdue maintenance days, and criticality score.

## 6. Detect Anomalies

```bash
make detect-anomalies
```

Show `data/processed/anomaly_results.csv`. Explain the hybrid method:

- rule-based thresholds for explainable maintenance patterns;
- Isolation Forest for multivariate outliers.

## 7. Score Risk

```bash
make score-risk
```

Show `data/processed/risk_scores.csv`. Explain the formula:

```text
final_risk_score =
  35% anomaly_score
+ 20% maintenance_overdue_score
+ 20% recent_ticket_score
+ 15% criticality_score
+ 10% runtime_score
```

## 8. Index Documents Into Qdrant

Install optional RAG dependencies if needed:

```bash
python -m pip install -e ".[dev,rag]"
```

Index Vietnamese SOP/checklist documents:

```bash
make index-documents
```

Explain the RAG path: `documents.csv -> chunks -> embeddings -> Qdrant maintenance_knowledge`.

## 9. Run FastAPI

Open a terminal:

```bash
make run-api
```

Open these URLs:

- `http://localhost:8000/health`
- `http://localhost:8000/summary`
- `http://localhost:8000/docs`

## 10. Run Streamlit Dashboard

Open a second terminal:

```bash
make run-dashboard
```

Open the Streamlit URL shown in the terminal.

## 11. Inspect Top Risky Asset

In the dashboard:

1. Open `Overview`.
2. Review total assets, anomalies, high-risk count, urgent-risk count, latest date, and average risk score.
3. Inspect `Top 10 Risky Assets`.
4. Open `Asset Risk Monitoring`.
5. Select a high-risk `asset_id`.
6. Show `main_reasons` and `recommended_action`.

## 12. Ask The Copilot

Open `Maintenance Copilot`.

Ask:

```text
Vì sao GENERATOR_002 đang rủi ro cao?
```

Use:

- `asset_id`: `GENERATOR_002`
- `top_k`: `5`

Show:

- Vietnamese answer;
- structured risk/anomaly context;
- SOP/checklist sources;
- retrieved chunks in the expander.

## 13. Close With The Product Story

Position the project as:

- not a CMMS replacement;
- an AI decision-support layer over existing CMMS/sensor/SOP data;
- a complete MVP showing data engineering, anomaly detection, explainable scoring, API serving, dashboarding, and RAG.

# Troubleshooting

## Qdrant Not Running

Symptoms:

- `make index-documents` fails with a Qdrant connection error.
- `/copilot/ask` returns a service unavailable error mentioning Qdrant.

Fix:

```bash
make services-up
```

Check Qdrant:

```bash
curl http://localhost:6333
```

## sentence-transformers Not Installed

Symptoms:

- `make index-documents` fails with a message saying `sentence-transformers is not installed`.
- `make rag-query` or `/copilot/ask` cannot create the embedding provider.

Fix:

```bash
python -m pip install -e ".[dev,rag]"
```

The default model is `intfloat/multilingual-e5-small`. The first run may download model files.

## Documents Not Indexed

Symptoms:

- The copilot answers that no SOP/checklist chunks were retrieved.
- Qdrant is running, but sources are empty.

Fix:

```bash
make index-documents
```

Then ask again:

```bash
make rag-query QUESTION="Vì sao GENERATOR_002 đang rủi ro cao?" ASSET_ID=GENERATOR_002
```

## API Not Reachable From Dashboard

Symptoms:

- Streamlit shows `Could not connect to FastAPI`.
- Dashboard pages do not load data.

Fix:

Start the API in one terminal:

```bash
make run-api
```

Start the dashboard in another terminal:

```bash
make run-dashboard
```

If the API is on another host or port, set `API_BASE_URL`:

```bash
API_BASE_URL=http://localhost:8000 make run-dashboard
```

Windows PowerShell:

```powershell
$env:API_BASE_URL = "http://localhost:8000"
make run-dashboard
```

## Processed CSV Files Missing

Symptoms:

- `/summary` returns a processed data file error.
- Risk or anomaly dashboard tables are empty because files are missing.

Fix:

Regenerate the pipeline:

```bash
make generate-data
make build-features
make detect-anomalies
make score-risk
```

Expected outputs:

- `data/processed/asset_daily_features.csv`
- `data/processed/anomaly_results.csv`
- `data/processed/risk_scores.csv`

## Database Load Fails

Symptoms:

- `make load-data` cannot connect to PostgreSQL.
- Database connection errors mention localhost port `5432`.

Fix:

```bash
make services-up
make init-db
make load-data
```

For quick tests without PostgreSQL, the database scripts also support SQLite URLs:

```bash
python -m src.database.init_db --database-url sqlite:///maintenance_demo.db --drop-existing
python -m src.ingestion.load_data --database-url sqlite:///maintenance_demo.db --replace
```

## Regenerate Data And Rerun Full Pipeline

Use this when the raw or processed files are stale:

```bash
make services-up
make generate-data
make init-db
make load-data
make build-features
make detect-anomalies
make score-risk
make index-documents
```

Then run the app:

```bash
make run-api
make run-dashboard
```

## Ruff Or Pytest Failures

Run:

```bash
make lint
make test
```

If failures reference missing optional RAG dependencies, install:

```bash
python -m pip install -e ".[dev,rag]"
```

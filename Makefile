.PHONY: install test lint services-up services-down init-db generate-data load-data build-features detect-anomalies score-risk index-documents rag-query run-api run-dashboard

PYTHON ?= python

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

services-up:
	docker compose up -d

services-down:
	docker compose down

init-db:
	$(PYTHON) -m src.database.init_db

generate-data:
	$(PYTHON) -m src.data_generation.generate_data

load-data:
	$(PYTHON) -m src.ingestion.load_data --replace

build-features:
	$(PYTHON) -m src.features.build_features

detect-anomalies:
	$(PYTHON) -m src.models.anomaly_detection

score-risk:
	$(PYTHON) -m src.risk.risk_scoring

index-documents:
	$(PYTHON) -m src.rag.index_documents

rag-query:
	$(PYTHON) -m src.rag.query "$(QUESTION)" $(if $(ASSET_ID),--asset-id $(ASSET_ID),)

run-api:
	$(PYTHON) -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

run-dashboard:
	$(PYTHON) -m streamlit run src/dashboard/app.py

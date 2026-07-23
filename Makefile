.PHONY: install test test-postgres lint services-up services-down postgres-up postgres-down qdrant-up qdrant-down init-db migrate-db reset-db create-test-db generate-data validate-data import-dry-run load-data replace-data seed-maintenance generate-work-orders generation-dry-run export-analytics-snapshot build-features detect-anomalies score-risk build-preventive build-recurring build-kpis index-documents rag-query bootstrap-admin seed-demo-users run-api run-dashboard run-frontend frontend-lint frontend-test frontend-build

PYTHON ?= python
ANALYTICS_INPUT_DIR ?= data/analytics_input

install:
	$(PYTHON) -m pip install -e ".[dev,rag,postgres]"

test:
	$(PYTHON) -m pytest

test-postgres:
	$(PYTHON) -m pytest -m postgres

lint:
	$(PYTHON) -m ruff check .

services-up:
	docker compose up -d

services-down:
	docker compose down

postgres-up:
	docker compose up -d postgres

postgres-down:
	docker compose stop postgres

qdrant-up:
	docker compose up -d qdrant

qdrant-down:
	docker compose stop qdrant

init-db:
	$(PYTHON) -m src.database.init_db

migrate-db:
	$(PYTHON) -m alembic upgrade head

reset-db:
	$(PYTHON) -m src.database.init_db --reset

create-test-db:
	$(PYTHON) -m src.database.create_test_database

generate-data:
	$(PYTHON) -m src.data_generation.generate_data

validate-data:
	$(PYTHON) -m src.ingestion.validation

import-dry-run:
	$(PYTHON) -m src.ingestion.load_data --dry-run

load-data:
	$(PYTHON) -m src.ingestion.load_data

replace-data:
	$(PYTHON) -m src.ingestion.load_data --replace

seed-maintenance:
	$(PYTHON) -m src.maintenance_management.cli seed-development $(if $(GENERATE),--generate,)

generate-work-orders:
	$(PYTHON) -m src.maintenance_management.cli generate $(if $(AS_OF),--as-of $(AS_OF),) $(if $(PLAN_ID),--plan-id $(PLAN_ID),)

generation-dry-run:
	$(PYTHON) -m src.maintenance_management.cli generate --dry-run $(if $(AS_OF),--as-of $(AS_OF),) $(if $(PLAN_ID),--plan-id $(PLAN_ID),)

export-analytics-snapshot:
	$(PYTHON) -m src.database.export_snapshot --replace

build-features:
	$(PYTHON) -m src.features.build_features --input-dir $(ANALYTICS_INPUT_DIR)

detect-anomalies:
	$(PYTHON) -m src.models.anomaly_detection

score-risk:
	$(PYTHON) -m src.risk.risk_scoring

build-preventive:
	$(PYTHON) -m src.features.build_features --input-dir $(ANALYTICS_INPUT_DIR) --analysis preventive

build-recurring:
	$(PYTHON) -m src.features.build_features --input-dir $(ANALYTICS_INPUT_DIR) --analysis recurring

build-kpis:
	$(PYTHON) -m src.features.build_features --input-dir $(ANALYTICS_INPUT_DIR) --analysis kpis

index-documents:
	$(PYTHON) -m src.rag.index_documents

rag-query:
	$(PYTHON) -m src.rag.query "$(QUESTION)" $(if $(ASSET_ID),--asset-id $(ASSET_ID),)

bootstrap-admin:
	$(PYTHON) -m src.security.cli create-admin --username "$(USERNAME)" --display-name "$(DISPLAY_NAME)" $(if $(EMAIL),--email "$(EMAIL)",)

seed-demo-users:
	$(PYTHON) -m src.security.cli seed-demo-users

run-api:
	$(PYTHON) -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

run-dashboard:
	$(PYTHON) -m streamlit run src/dashboard/app.py

run-frontend:
	npm --prefix frontend run dev

frontend-lint:
	npm --prefix frontend run lint

frontend-test:
	npm --prefix frontend run test

frontend-build:
	npm --prefix frontend run build

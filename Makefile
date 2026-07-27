.PHONY: install test test-postgres lint services-up services-down postgres-up postgres-down qdrant-up qdrant-down worker-docker-up worker-docker-down init-db migrate-db reset-db create-test-db generate-data validate-data import-dry-run load-data replace-data seed-maintenance seed-inventory generate-work-orders generation-dry-run seed-ticketing escalation-dry-run evaluate-escalations export-analytics-snapshot build-features detect-anomalies score-risk build-preventive build-recurring build-kpis index-documents rag-query bootstrap-admin seed-demo-users run-api run-dashboard run-frontend run-worker worker-once run-job set-job-enabled retry-job retry-outbox evaluate-operational-alerts job-status reliability-load backup-restore-drill attachment-integrity pilot-contract-validate pilot-decision-validate pilot-release-validate pilot-rehearsal-plan pilot-rehearsal-execute pilot-rehearsal-cleanup pilot-backup-schedule pilot-step-load frontend-lint frontend-test frontend-build

PYTHON ?= python
ANALYTICS_INPUT_DIR ?= data/analytics_input
PILOT_ENV_FILE ?= .env.pilot
PILOT_PROJECT_NAME ?= pm9-pilot-rehearsal
PILOT_DATA_MODE ?= existing_approved
PILOT_BACKUP_TARGET ?= pilot_primary
PILOT_POSTGRES_CONTAINER ?= $(PILOT_PROJECT_NAME)-postgres-1
PILOT_LOAD_PROFILE ?= capacity
PILOT_LOAD_PASSWORD_ENV ?= PM9_LOAD_PASSWORD
PILOT_AUTHENTICATED_POST_START ?= false

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

worker-docker-up:
	docker compose --profile worker up -d --build worker

worker-docker-down:
	docker compose --profile worker stop worker

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

seed-inventory:
	$(PYTHON) -m src.inventory_management.cli seed-development

generate-work-orders:
	$(PYTHON) -m src.maintenance_management.cli generate $(if $(AS_OF),--as-of $(AS_OF),) $(if $(PLAN_ID),--plan-id $(PLAN_ID),)

generation-dry-run:
	$(PYTHON) -m src.maintenance_management.cli generate --dry-run $(if $(AS_OF),--as-of $(AS_OF),) $(if $(PLAN_ID),--plan-id $(PLAN_ID),)

seed-ticketing:
	$(PYTHON) -m src.ticket_management.cli seed-defaults $(if $(ACTOR),--actor-username $(ACTOR),)

escalation-dry-run:
	$(PYTHON) -m src.ticket_management.cli evaluate-escalations --dry-run $(if $(AS_OF),--as-of $(AS_OF),) $(if $(ACTOR),--actor-username $(ACTOR),)

evaluate-escalations:
	$(PYTHON) -m src.ticket_management.cli evaluate-escalations $(if $(AS_OF),--as-of $(AS_OF),) $(if $(ACTOR),--actor-username $(ACTOR),)

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

run-worker:
	$(PYTHON) -m src.operations.worker

worker-once:
	$(PYTHON) -m src.operations.worker --once

run-job:
	$(PYTHON) -m src.operations.cli trigger "$(JOB)" --idempotency-key "$(IDEMPOTENCY_KEY)" $(if $(ACTOR),--actor-username "$(ACTOR)",)

set-job-enabled:
	$(PYTHON) -m src.operations.cli set-enabled "$(JOB)" --enabled "$(ENABLED)" --expected-version "$(EXPECTED_VERSION)" $(if $(ACTOR),--actor-username "$(ACTOR)",)

retry-job:
	$(PYTHON) -m src.operations.cli retry "$(EXECUTION_ID)" --idempotency-key "$(IDEMPOTENCY_KEY)" $(if $(ACTOR),--actor-username "$(ACTOR)",)

retry-outbox:
	$(PYTHON) -m src.operations.cli retry-outbox "$(OUTBOX_EVENT_ID)" --idempotency-key "$(IDEMPOTENCY_KEY)" $(if $(ACTOR),--actor-username "$(ACTOR)",)

evaluate-operational-alerts:
	$(PYTHON) -m src.operations.cli evaluate-alerts $(if $(ACTOR),--actor-username "$(ACTOR)",)

job-status:
	$(PYTHON) -m src.operations.cli status $(if $(ACTOR),--actor-username "$(ACTOR)",)

reliability-load:
	$(PYTHON) -m src.reliability.load_harness --profile "$(PROFILE)" --username "$(USERNAME)" $(if $(BASE_URL),--base-url "$(BASE_URL)",) $(if $(OUTPUT_DIR),--output-dir "$(OUTPUT_DIR)",)

backup-restore-drill:
	$(PYTHON) -m src.reliability.backup_restore --restore-database "$(RESTORE_DATABASE)" --output-dir "$(OUTPUT_DIR)" $(if $(DOCKER_CONTAINER),--docker-container "$(DOCKER_CONTAINER)",)

attachment-integrity:
	$(PYTHON) -m src.reliability.attachments

pilot-contract-validate:
	$(PYTHON) -m src.reliability.pilot_contract --manifest-only --skip-environment

pilot-decision-validate:
	$(PYTHON) -m src.reliability.pilot_contract --skip-environment

pilot-release-validate:
	$(PYTHON) -m src.reliability.pilot_contract --skip-environment $(if $(ACTUAL_RELEASE_COMMIT),--actual-commit "$(ACTUAL_RELEASE_COMMIT)",) $(if $(ACTUAL_RELEASE_TAG),--actual-tag "$(ACTUAL_RELEASE_TAG)",) $(if $(ACTUAL_RELEASE_TAG_TARGET_COMMIT),--actual-tag-target-commit "$(ACTUAL_RELEASE_TAG_TARGET_COMMIT)",) $(if $(ACTUAL_MIGRATION_REVISION),--actual-migration-revision "$(ACTUAL_MIGRATION_REVISION)",)

pilot-rehearsal-plan:
	$(PYTHON) -m src.reliability.deployment_rehearsal --environment-file "$(PILOT_ENV_FILE)" --project-name "$(PILOT_PROJECT_NAME)" --data-mode "$(PILOT_DATA_MODE)" $(if $(PILOT_INTENDED_HOST),--intended-host,)

pilot-rehearsal-execute:
	$(PYTHON) -m src.reliability.deployment_rehearsal --environment-file "$(PILOT_ENV_FILE)" --project-name "$(PILOT_PROJECT_NAME)" --data-mode "$(PILOT_DATA_MODE)" --execute $(if $(PILOT_EVIDENCE_DIR),--evidence-dir "$(PILOT_EVIDENCE_DIR)",) $(if $(PILOT_INTENDED_HOST),--intended-host,) $(if $(filter true,$(PILOT_AUTHENTICATED_POST_START)),--authenticated-post-start,)

pilot-rehearsal-cleanup:
	$(PYTHON) -m src.reliability.deployment_rehearsal --environment-file "$(PILOT_ENV_FILE)" --project-name "$(PILOT_PROJECT_NAME)" --cleanup-only

pilot-backup-schedule:
	$(PYTHON) -m src.reliability.backup_schedule --environment-file "$(PILOT_ENV_FILE)" --target-label "$(PILOT_BACKUP_TARGET)" --docker-container "$(PILOT_POSTGRES_CONTAINER)"

pilot-step-load:
	$(PYTHON) -m src.reliability.load_harness --step-load-profile "$(PILOT_LOAD_PROFILE)" --username "$(PILOT_LOAD_USERNAME)" --password-env "$(PILOT_LOAD_PASSWORD_ENV)" $(if $(PILOT_API_BASE_URL),--base-url "$(PILOT_API_BASE_URL)",) $(if $(PILOT_LOAD_OUTPUT_DIR),--output-dir "$(PILOT_LOAD_OUTPUT_DIR)",) $(if $(PILOT_MUTATION_FIXTURE),--mutation-fixture "$(PILOT_MUTATION_FIXTURE)",)

frontend-lint:
	npm --prefix frontend run lint

frontend-test:
	npm --prefix frontend run test

frontend-build:
	npm --prefix frontend run build

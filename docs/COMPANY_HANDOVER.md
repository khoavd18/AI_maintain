# Company Handover

## Handover Status

This repository is suitable for developer handover and controlled local demonstration after the documented setup. PostgreSQL integration, live Qdrant, a real Ollama provider, the full development Compose stack, and the authenticated multi-role workflow were exercised on an isolated local `_test` environment. It is still not a production acceptance package. Company owner assignments, approved secrets/provider, intended-host rehearsal, recovery evidence, support coverage, dependency remediation, and known-limitation acceptance remain external gates.

## System Ownership Map

| Area | Canonical owner in code |
|---|---|
| FastAPI composition and legacy analytics API | `src/api/` |
| Identity, RBAC, sessions, audit dependencies | `src/security/` |
| Asset lifecycle/files/QR | `src/asset_management/`, `postgres_assets.py` |
| Ticket lifecycle/SLA/escalation | `src/ticket_management/`, `postgres_tickets.py` |
| Preventive plans/work orders/logs | `src/maintenance_management/`, `postgres_maintenance.py` |
| Spare parts/stock ledger | `src/inventory_management/`, `postgres_inventory.py` |
| Only worker/jobs/outbox/notifications | `src/operations/`, `postgres_operations.py` |
| PostgreSQL schema | `src/database/models/`, `migrations/` |
| Batch analytics | `src/features/`, `src/models/anomaly_detection.py`, `src/risk/risk_scoring.py` |
| RAG retrieval/orchestration | `src/rag/` |
| LLM provider/prompt/parser/citations | `src/llm/` |
| Next.js workflows | `frontend/src/` |
| Reliability/rehearsal | `src/reliability/`, `deployment/`, PM9 docs |

## Non-Negotiable Architecture Rules

- PostgreSQL remains transactional truth; no silent CSV write fallback.
- Every schema change uses Alembic; startup never calls `metadata.create_all()`.
- Analytics remains batch-first.
- `src/operations/worker.py` remains the only worker and accepts only four cataloged operations.
- Notifications remain in-app only.
- Service boundaries own lifecycle/stock rules; routes/frontends never mutate models/balances directly.
- Work-order completion/verification never resolves a ticket or silently changes stock.
- Qdrant is only for controlled document retrieval.
- LLM output is never executed or persisted as authoritative business state.
- Human authorized users remain responsible for safety and final decisions.

## Fresh Local Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dashboard,dev,rag,postgres]"
npm --prefix frontend ci
Copy-Item .env.example .env
docker compose up -d postgres qdrant
python -m alembic upgrade head
python -m src.ingestion.load_data
python -m src.rag.index_documents
python -m src.security.cli seed-demo-users
```

Then start API, frontend, and optionally worker with the commands in README/operations runbook.

## Full Development Compose

```powershell
docker compose up --build
docker compose --profile worker up --build
```

The main Compose migration service applies Alembic before API startup. Seed/import, identity creation, maintenance/inventory seed, and document indexing remain explicit commands to prevent hidden data mutations.

The stricter intended-pilot topology is `docker-compose.pilot.yml`; do not treat the development Compose file as production configuration.

## LLM Operations

Generation is off by default. To enable:

1. Approve provider/model and data handling.
2. Configure `LLM_ENABLED`, `LLM_PROVIDER`, `LLM_MODEL`, and `LLM_BASE_URL`.
3. Inject `LLM_API_KEY` only when required.
4. Run `python -m src.llm.smoke`.
5. Run `python -m evaluation.run_evaluation --backend configured-qdrant --mode rag-llm`.
6. Review fallback rate and every small-dataset answer before demo/pilot.

Ollama should be preferred for offline/local defense. No model is pinned because hardware and approved model choice are owner decisions; record the selected model/version in release evidence.

## Knowledge Corpus

The current source is `data/raw/documents.csv`. Re-index with:

```powershell
python -m src.rag.index_documents
```

Stable chunk/point IDs prevent duplicates for unchanged documents. Rebuild/recreate is an explicit operator action. There is no web KB admin or persisted active/superseded lifecycle; do not accept arbitrary uploads through a new route without a full metadata, storage, audit, and migration design.

## Verification Checklist

```powershell
python -m compileall -q src tests evaluation
python -m pytest
python -m ruff check .
python -m alembic heads
docker compose config --quiet
docker compose --env-file .env.pilot.example -f docker-compose.pilot.yml config --quiet
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
python -m evaluation.run_evaluation --mode deterministic
python -m evaluation.run_evaluation --backend configured-qdrant --mode rag-llm
```

PostgreSQL integration:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://<user>:<password>@localhost:5432/<name>_test"
python -m alembic -x database_url=$env:TEST_DATABASE_URL upgrade head
python -m pytest -m postgres
```

Use only a dedicated database whose name ends in `_test`. Follow the repository’s actual test-database helper/commands; never run destructive setup against demo data.

Authenticated graduation rehearsal:

```powershell
$env:TEST_DATABASE_URL = "<protected PostgreSQL URL ending _test>"
$env:DEMO_USER_PASSWORD = "<temporary test password>"
python -m src.reliability.graduation_demo_smoke
```

The runner verifies API database fingerprint attestation before login and never persists credentials or tokens. See [Runtime verification](RUNTIME_VERIFICATION.md) for the executed commands and results.

## Backup, Recovery, And Release

See:

- [Operations runbook](operations_runbook.md)
- [Backup and restore](backup_restore.md)
- [Failure recovery](failure_recovery.md)
- [Pilot deployment](pilot_deployment.md)
- [Secret rotation](pilot_secret_rotation.md)
- [Operational ownership](operational_ownership.md)
- [Known limitations](known_limitations_acceptance.md)

Do not mark a real pilot GO based only on local/synthetic tests. Use the three-gate PM9 record and owner approvals.

## Monitoring And Troubleshooting

- `/health/live`: process liveness.
- `/health/ready`: primary storage/migration readiness.
- `/health/worker`: persisted heartbeat readiness.
- Operations pages/API: job execution, dead letters, outbox, notifications, metrics.
- Provider smoke: fixed structured output only, without maintenance/user data.
- Copilot fallback reasons: fixed categories; do not enable raw prompt/response logging during incident diagnosis.

Troubleshooting: [troubleshooting.md](troubleshooting.md).

## Known Handover Risks

| Severity | Risk | Required owner action |
|---|---|---|
| High | No approved production/pilot provider and data contract | Select local/hosted provider, retention/residency, key owner |
| High | PostgreSQL/attachments single-node and incomplete real restore evidence | Approve backup target, cadence, paired restore rehearsal |
| High | No SSO/MFA/shared rate limit/malware scanning | Accept internal-only boundary or fund production controls |
| High | No real corpus/model accuracy evidence | Supply approved documents and human-labeled evaluation |
| High | Next-owned PostCSS/Sharp advisories remain in the production tree | Track a stable Next release supporting patched dependency floors; do not force downgrade/overrides |
| Medium | Python/RAG Docker image is 9.16 GB and slow to unpack on Docker Desktop | Split/build-cache dependencies and measure a smaller supported runtime image without removing local embeddings |
| Medium | Oversized service/repository/frontend modules | Refactor incrementally along bounded contexts with tests |
| Medium | No central logs/alerts/on-call | Assign operations owner and platform |
| Medium | KB lifecycle is CLI/CSV-only | Design persisted document registry before admin upload UI |
| Medium | Citation validation is structural, not semantic | Add human claim/span judgments; keep human verification |

## First Week For A New Team

1. Run all local checks and reproduce the deterministic evaluation.
2. Reproduce the dedicated `_test` migration, 73 PostgreSQL tests, and authenticated graduation smoke from the runtime record.
3. Walk through asset → ticket → work order → inventory → explicit resolve.
4. Read architecture, data contract, business process, RAG/LLM design, and security review.
5. Decide provider/model and run a privacy-approved grounded evaluation.
6. Assign company owner/security/incident/support/backup responsibilities.
7. Only then schedule an intended-host rehearsal.

## Acceptance Sign-Off

Technical handover should record commit/tag, Alembic head, frontend lockfile hash, selected provider/model, test counts, skipped/external limitations, backup evidence, and named owners. A technical document cannot substitute for company authorization or production risk acceptance.

## Refactoring continuation checkpoint — 2026-08-06

The backend inventory is recorded in
[`backend-structural-inventory.md`](backend-structural-inventory.md). Phase A
moved the immutable authenticated principal to `src/security/principal.py`;
`src.security.service.CurrentUser` remains an identity-preserving historical
import. Phase B moved repository contracts into the bounded package
`src/repositories/contracts/` and preserved the historical import facade,
including new ticket/operations protocols. Focused validation passed (`14
passed, 43 skipped, 1 warning`) and PostgreSQL validation passed (`73 passed,
390 deselected, 1 warning`). Phase C moved concrete service wiring into
`src/composition/` and preserved legacy builder/dependency identities. No
transaction-heavy stock family, API, schema, frontend, or storage behavior was
changed. Phase D extracted inventory catalogue and stock-location orchestration
into `application/catalogue_mutation_service.py`; focused inventory validation
passed (`3 passed, 10 skipped, 1 warning`) and PostgreSQL validation passed
(`73 passed, 390 deselected, 1 warning`). The next safe phase is ticket
application-service decomposition.
Phase E extracted SLA calendar/policy administration into
`ticket_management/application/sla_service.py`; focused ticket validation
passed (`20 passed, 8 skipped, 1 warning`) and PostgreSQL validation passed
after correcting and rechecking one extraction call-shape defect (`73 passed,
390 deselected, 1 warning`). Ticket lifecycle, SLA snapshot, escalation, and
comment transaction families remain retained. The next safe phase is
maintenance application-service decomposition.
Phase F extracted checklist-template listing, immutable versioning, and archive
orchestration into `maintenance_management/application/template_service.py`;
focused maintenance validation passed (`15 passed, 9 skipped, 1 warning`) and
PostgreSQL validation passed (`73 passed, 390 deselected, 1 warning`). Plan,
generation, work-order, checklist-completion, verification, and evidence
transaction families remain retained. The next safe phase is security service
decomposition.

Phase G now includes an explicit ORM-free security transaction contract and one
complete transaction-family extraction. `src/security/identity.py` owns
identity projections; `src/security/errors.py` owns shared security errors;
`src/security/session_state.py` owns the pure access-state predicate; and
`src/security/contracts.py` plus `src/security/session_service.py` own the
single-session logout port and complete SQLAlchemy-backed transaction.
`src.security.service` remains the historical facade. Contract and PostgreSQL
tests protect one-session ownership, audit atomicity, idempotency, and facade
compatibility.

AuthService remains intact for login, access authentication, refresh rotation,
password changes, user administration, and their audit orchestration. No token,
password, session, audit, API, environment, schema, or frontend behavior
changed outside the selected complete logout family. Refresh rotation is
characterized in [`security-refresh-rotation-contract.md`](security-refresh-rotation-contract.md)
and remains in `AuthService` because its complete token/session family shares
the login session-result factory. The combined security characterization/
contract suite passed `14 passed`; the isolated PostgreSQL security suite passed
`13 passed`. Full backend validation passed (`404 passed, 86 skipped, 1
warning`); the final isolated PostgreSQL workflow passed (`86 passed, 404
deselected, 1 warning`). Ruff/compileall passed, and Alembic current/heads/
check remain clean at `20260726_0008` with no new operations.
The next single bounded backend phase requires a separately approved complete
transaction-family contract.

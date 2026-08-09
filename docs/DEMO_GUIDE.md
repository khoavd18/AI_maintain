# Graduation Demo Guide

## Demo Goal

Show that the system joins transactional maintenance workflows, batch analytics, real RAG retrieval, a real optional LLM generation stage, validated citations, and human-controlled execution without claiming automatic diagnosis or production readiness.

Target length: 15–20 minutes. Use the detailed operational script in [demo_script.md](demo_script.md) for extended ticket/SLA/inventory paths.

## Pre-Demo Setup

### 1. Configure

```powershell
Copy-Item .env.example .env
```

Replace PostgreSQL placeholders. For Ollama:

```dotenv
LLM_ENABLED=true
LLM_PROVIDER=ollama
LLM_MODEL=<MODEL_NAME>
LLM_BASE_URL=http://localhost:11434
LLM_API_KEY=
```

If FastAPI runs in Docker and Ollama runs on the host, use `http://host.docker.internal:11434`.

### 2. Start Ollama And Model

```powershell
ollama serve
ollama pull <MODEL_NAME>
python -m src.llm.smoke
```

Do not download a model during the live defense; do it beforehand.

### 3. Start Infrastructure And Prepare Data

Host-development path:

```powershell
docker compose up -d postgres qdrant
python -m alembic upgrade head
python -m src.ingestion.load_data
python -m src.database.export_snapshot --replace
python -m src.features.build_features --input-dir data/analytics_input
python -m src.models.anomaly_detection
python -m src.risk.risk_scoring
python -m src.features.build_features --input-dir data/analytics_input --analysis maintenance
python -m src.security.cli seed-demo-users
python -m src.maintenance_management.cli seed-development
python -m src.ticket_management.cli seed-defaults
python -m src.inventory_management.cli seed-development
python -m src.rag.index_documents
```

Commands are explicit and idempotent where documented. The user seed prompts for one demo password; there is no committed default.

### 4. Start Applications

```powershell
# Terminal 1
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# Terminal 2
python -m src.operations.worker

# Terminal 3
npm --prefix frontend run dev
```

Preflight:

```powershell
Invoke-RestMethod http://localhost:8000/health
python -m src.llm.smoke
python -m evaluation.run_evaluation --backend configured-qdrant --mode rag-llm
```

### Automated Full-Workflow Rehearsal

The repository now includes a bounded multi-role runtime runner. It deliberately refuses any API that does not attest to the same caller-supplied PostgreSQL database name ending `_test`.

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://<user>:<password>@localhost:<port>/<name>_test"
$env:DEMO_USER_PASSWORD = "<temporary-test-password>"
python -m src.reliability.graduation_demo_smoke `
  --base-url http://127.0.0.1:8000 `
  --frontend-url http://127.0.0.1:3000 `
  --timeout-seconds 240
```

It performs real login, asset/risk/anomaly reads, grounded Copilot, mismatch and insufficient-evidence checks, ticket/work-order transitions, part requirement/reservation/issue, independent verification, audit, metrics, frontend-route checks, and worker health. It does not persist tokens or replace the manual visual presentation.

The 2026-07-28 rehearsal passed with PostgreSQL, Qdrant, Ollama, API, worker, and frontend running together. See [Runtime verification](RUNTIME_VERIFICATION.md) for the exact evidence and remaining blockers.

## Presentation Flow

### 1. Problem And Boundary (1 minute)

Explain:

- PostgreSQL owns transactions; CSV is batch analytics/import/snapshot; Qdrant stores only document vectors.
- Human managers/technicians make final decisions.
- Risk is a priority indicator, not failure probability.
- LLM output is read-only support and never executes maintenance or stock actions.

### 2. Login And Asset Context (1 minute)

Log in as `manager.demo` with the password just seeded. Open Assets and select a representative generator, pump, or HVAC asset. Show location, maintenance state, latest priority risk score, contributing factors, and anomaly support signal.

Say: “These values came from the last batch. Creating a ticket will not recalculate them immediately.”

### 3. Create/Open Incident Ticket (2 minutes)

Open or create a ticket for the selected asset. Show backend-derived priority, SLA snapshot, reporter visibility rules, and explicit lifecycle actions. Do not resolve yet.

### 4. Grounded Copilot With LLM (3 minutes)

From the selected asset/ticket, ask a focused question, for example:

```text
Máy phát điện không khởi động thì cần kiểm tra gì trước?
```

Point out separately:

- retrieval status;
- “AI có căn cứ” response mode;
- evidence strength wording (not probability);
- claim citations `[S1]` and source card “Nguồn S1”;
- document ID/version/effective date;
- safety notice and escalation state.

Explain the server path: question/type validation → Qdrant filter/threshold → bounded untrusted context → configured LLM → Pydantic JSON parse → citation allow-list → response.

### 5. Safety Fallbacks (2 minutes)

Show at least one:

- select HVAC and ask about a pump: UI shows asset-context mismatch and no source blending;
- ask an unrelated question: zero-source scope fallback;
- temporarily set `LLM_ENABLED=false` and restart API: relevant RAG sources remain, but mode is deterministic fallback;
- use a question with insufficient evidence: no unsupported checklist is generated.

Avoid intentionally stopping services unless rehearsed. A screenshot or prepared response is acceptable for provider-timeout behavior.

### 6. Work Order And Checklist (2 minutes)

Create/link a corrective work order separately from ticket status. As technician, acknowledge/start, complete snapshotted checklist items, attach evidence if desired, and complete. Emphasize:

- work order execution is service-controlled;
- checklist template history is immutable;
- completion creates/links one maintenance log;
- ticket is not auto-resolved;
- independent verification uses a different authorized actor.

### 7. Spare Parts (2 minutes)

As Storekeeper, show current `on_hand`, `reserved`, and server-derived `available`. Reserve and issue an explicitly required part using stable idempotency keys; then show technician consumption and unused return if prepared.

Say: “Completion does not silently consume, release, or return stock.”

### 8. Explicit Ticket Resolution (1 minute)

Return as an authorized user and explicitly resolve the ticket after reviewing maintenance evidence. This demonstrates that AI, work orders, and ticket lifecycle are separated.

### 9. Audit, Notifications, Jobs, Dashboard (2 minutes)

Show append-only audit entries, the current user’s notification inbox, and Administrator job operations. Explain the closed four-job catalog and PostgreSQL leases/outbox. Show that analytics refresh is batch-triggered, not a transactional side effect.

### 10. Evaluation And Honest Conclusion (1 minute)

Show the evaluation JSON/table:

- six small corpus questions;
- Recall@K/MRR/filter accuracy;
- two no-answer cases;
- deterministic versus RAG+LLM commands;
- limitations.

Conclude that the title is technically true because a real provider call exists between grounded retrieval and validated output, while the small synthetic corpus does not prove production accuracy or business impact.

## Failure-Safe Demo Plan

If Ollama/provider is unavailable:

1. Do not hide it.
2. Show `response_mode=deterministic_fallback` and the fixed reason.
3. Demonstrate retrieved sources still render if evidence is sufficient.
4. Run `python -m src.llm.smoke` and state the exact provider configuration/service limitation.
5. Continue the transactional workflow; Qdrant/LLM failure does not block asset/ticket/work-order/inventory APIs.

If Qdrant is unavailable, show the zero-source RAG unavailable fallback and continue non-Copilot workflows.

## Claims To Avoid

- “The model predicts failure probability.”
- “The AI diagnoses the fault.”
- “Citations eliminate hallucinations.”
- “A high evaluation score proves real-world accuracy.”
- “The platform is production-ready.”
- “Work-order completion automatically resolves tickets or consumes stock.”

Preferred terms: “priority risk score”, “maintenance risk indicator”, “anomaly support signal”, “grounded decision support”, and “validated citation identifiers”.

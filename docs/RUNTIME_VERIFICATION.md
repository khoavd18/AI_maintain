# Runtime Verification

## Verification Scope

This record replaces the earlier service-unavailable assumptions with observed local runtime evidence. It does not certify production readiness, model accuracy, business impact, or facility safety.

Verification date: **2026-07-28** (`Asia/Ho_Chi_Minh`).

## Environment

| Component | Observed version |
|---|---|
| Operating system | Microsoft Windows 11 Home Single Language 10.0.26200, build 26200 |
| Python | 3.11.9 |
| Node.js / npm | 22.20.0 / 11.17.0 |
| Docker Engine / Compose | 29.1.2 / 2.40.3-desktop.1 |
| PostgreSQL | 16.14, Alpine |
| Qdrant | 1.10.1, commit `4aac02315bb3ca461a29484094cf6d19025fce99` |
| Ollama | 0.32.5 |
| Verified local model | `qwen2.5-coder:7b`, already installed before verification |
| Embedding model | `intfloat/multilingual-e5-small`, 384 dimensions |

No password, access token, refresh token, API key, or full prompt is recorded here. All PostgreSQL mutations used the isolated database `maintenance_runtime_test`; the pre-existing `maintenance_copilot` container and volume were not started or modified.

## Infrastructure And Migration

The fixed `container_name` values in development Compose initially prevented an isolated project. They were removed, Qdrant received a real `/readyz` health check, API now waits for `service_healthy`, and `APP_ENVIRONMENT` became an environment-selected development default. An isolated Compose project then created its own PostgreSQL/Qdrant volumes and host ports.

Observed health:

| Service | Result | Restart count |
|---|---|---:|
| PostgreSQL | `healthy`, `pg_isready` accepting connections | 0 |
| Qdrant | `healthy`, `/readyz` = `all shards are ready` | 0 |
| Migration | exited successfully, exit code 0 | n/a |
| FastAPI | `healthy`; `/health/live` = `alive`; `/health/ready` = `ready` | 0 |
| Worker | `healthy`; `/health/worker` = `ready` | 0 |
| Next.js | `healthy`; `/login` returned 200 | 0 |

The API container reached Qdrant at `http://qdrant:6333/readyz`. The host reached the same isolated service at its verification port. API and frontend images ran as non-root users `appuser` (UID 10001) and `node` (UID 1000).

Clean online migration evidence:

```powershell
python -m src.database.create_test_database --database-url <REDACTED_URL_ENDING_IN_test>
python -m alembic heads
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

Result: a single head `20260726_0008`; all eight revisions ran from base to head, including the live QR backfill in `20260718_0003`; no schema drift was detected.

## PostgreSQL Integration

Focused command:

```powershell
$env:TEST_DATABASE_URL = "<REDACTED_POSTGRESQL_URL_ENDING_IN_test>"
python -m pytest -m postgres
```

Result: **73 passed, 0 failed, 0 skipped, 331 deselected** in 363.52 seconds. Transaction, concurrency, inventory, ticket, work-order, audit, outbox, worker, reliability, and connection-termination tests executed against PostgreSQL rather than mocks.

Final full command used only `TEST_DATABASE_URL`; setting process-wide `DATABASE_URL` was deliberately avoided so independent settings tests retained their own environment assumptions:

```powershell
$env:TEST_DATABASE_URL = "<REDACTED_POSTGRESQL_URL_ENDING_IN_test>"
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:APP_ENVIRONMENT -ErrorAction SilentlyContinue
Remove-Item Env:STORAGE_BACKEND -ErrorAction SilentlyContinue
python -m pytest
```

Result: **420 passed, 0 failed, 0 skipped**, one upstream TestClient deprecation warning, in 348.97 seconds.

## Live Qdrant RAG

Canonical command was run against the real service three times, including once from inside the API container:

```powershell
python -m src.rag.index_documents
docker exec <api-container> python -m src.rag.index_documents
```

Observed collection:

| Field | Result |
|---|---|
| Collection | `maintenance_knowledge` |
| Status | green |
| Documents | 6 (`DOC-001` through `DOC-006`) |
| Chunks / unique point IDs | 30 / 30 |
| Vector size / distance | 384 / Cosine |
| Point-ID set SHA-256 after repeated indexing | `a03081475dd9d9916d1b710428c31a0acdbafceb4557ba72b663382299bf8cf9` |
| Count after second and container re-index | 30 / 30 |

Metadata included stable chunk IDs, document IDs, asset type, document type, failure category, version, effective date, source, and chunk index. Re-indexing did not add duplicates.

Representative live semantic queries:

| Question | Filter | Representative returned chunk | Score |
|---|---|---|---:|
| HVAC not cooling | `Máy lạnh` | `DOC-001-chunk-003-8c879a75` | 0.890543 |
| Pump vibration | `Máy bơm nước` | `DOC-003-chunk-003-b06b5731` | 0.888543 |
| Generator not starting | `Máy phát điện dự phòng` | `DOC-006-chunk-003-7d484e31` | 0.893149 |

All results in each filtered list had the requested asset type. The known troubleshooting document remained within the returned top five where the preventive chunk ranked first. Outside-domain handling occurs before generation and returned no sources.

Configured-Qdrant retrieval evaluation result:

- Recall@1: `0.833333`;
- Recall@3 and Recall@5: `1.0`;
- MRR: `0.916667`;
- asset-type filter accuracy: `1.0`;
- no-answer accuracy: `1.0`.

These small-corpus values are reproducibility evidence, not semantic generalization or model-accuracy evidence.

## Real LLM And RAG Plus LLM

Provider smoke:

```powershell
$env:LLM_ENABLED = "true"
$env:LLM_PROVIDER = "ollama"
$env:LLM_MODEL = "qwen2.5-coder:7b"
$env:LLM_BASE_URL = "http://127.0.0.1:11434"
python -m src.llm.smoke
```

Result: **pass** in 18.9 seconds before hardening and pass again afterward. Ollama returned schema-constrained JSON; the smoke output exposed only provider/model identifiers.

The first real `rag-llm` evaluation exposed a schema defect: three claim arrays were optional in JSON Schema even though local validation required checks, producing four `invalid_llm_output` fallbacks. The schema and related hardening were fixed. The repeated live evaluation then produced:

- real generation calls for all six supported cases;
- four accepted `llm_grounded` responses and two safe `invalid_citations` fallbacks;
- a grounded response for at least one HVAC, pump, and generator question;
- citation validity and coverage `1.0` among accepted generated responses;
- source coverage, no-answer accuracy, and safety-notice coverage `1.0`;
- no invalid alias exposed as a valid source.

The two periodic cases were rejected because top-level `source_ids` did not exactly equal the claim-level union. This is fail-closed behavior. A later authenticated API matrix returned `llm_grounded` for representative HVAC, pump, and generator troubleshooting questions with five response-local aliases, `citation_validation.valid=true`, and an empty `invalid_source_ids` list.

Safety cases observed against live services:

| Case | LLM called | Result |
|---|---:|---|
| Outside maintenance domain | no | `unrelated` deterministic fallback |
| User prompt injection | no | `prompt_injection` deterministic fallback |
| Selected HVAC with pump question | no | `asset_context_mismatch` |
| Selected pump with generator question | no | `asset_context_mismatch` |
| Provider TCP timeout | yes, one attempt | `llm_timeout` deterministic fallback with retrieved source |
| Injected instruction in temporary live-Qdrant chunk | no | `unsafe_context`; chunk removed; zero returned sources |

The temporary injection collection was deleted after verification; `maintenance_knowledge` remained the only collection.

## Authenticated End-To-End Smoke

No Playwright/Cypress installation existed. A bounded multi-role HTTP smoke runner was added at `src/reliability/graduation_demo_smoke.py`. It refuses to run unless `/health/live` attests to the same caller-supplied database name ending `_test`; credentials and bearer/cookie values remain in memory and are never included in its report.

Command:

```powershell
$env:TEST_DATABASE_URL = "<REDACTED_POSTGRESQL_URL_ENDING_IN_test>"
$env:DEMO_USER_PASSWORD = "<IN_MEMORY_TEST_PASSWORD>"
python -m src.reliability.graduation_demo_smoke `
  --base-url http://127.0.0.1:8000 `
  --frontend-url http://127.0.0.1:3000 `
  --timeout-seconds 240
```

Result: **pass** in 140 seconds. Observed workflow:

1. loaded `/login` and `/copilot` frontend routes;
2. logged in as manager, engineer, technician, and storekeeper;
3. loaded `GENERATOR_002`, 120 risk rows, and 10 recent anomaly rows;
4. created and started `TCK-000043`;
5. returned a real `ollama` / `qwen2.5-coder:7b` grounded answer with aliases `S1`–`S5`;
6. rejected mismatch and returned insufficient evidence for an empty filtered retrieval;
7. created part requirement, reservation, and issue with stable idempotency keys;
8. completed and independently verified `WO-000001`;
9. confirmed the ticket remained `in_progress` after work-order verification;
10. found the `work_order.verified` audit record and verified metric;
11. confirmed worker status remained `ready`.

This verifies the real browser-serving frontend routes and the complete authenticated FastAPI workflow. It is not a browser-DOM automation result; no browser E2E framework is installed.

## Docker Build Evidence

The first combined `docker compose ... up -d --build` command timed out after 20 minutes before application containers were created. Docker remained active rather than failing a build stage. Separate plain-progress builds showed all backend layers cached and **170.5 seconds spent only unpacking the 9.16 GB Python/RAG image** on Docker Desktop. Backend and frontend images subsequently built successfully, and `compose up --no-build` brought the full stack healthy.

This is a verified workstation performance limitation, not a hidden pass. The Python image size and cold-build/unpack time should be reduced before routine delivery, while retaining the local embedding capability.

## Dependency Advisory Status

`npm --prefix frontend audit --omit=dev` exits 1 with three high package findings and zero critical findings:

- Next 16.2.12 pins nested `postcss@8.4.31`; the combined patched floor is `>=8.5.18`;
- Next permits `sharp@^0.34.5`, resolved to 0.34.5; the patched floor is `>=0.35.0`;
- `next` is the aggregate third finding.

The separate root PostCSS 8.5.19 is not the vulnerable copy. No stable Next release available during verification supports both patched floors. `npm audit fix --force` proposes a breaking downgrade to Next 9.3.3 and was not used. Unsupported overrides and prerelease Next were also rejected.

Current reachability is reduced but not eliminated:

- CSS processing uses checked-in build inputs rather than user-supplied CSS;
- global `images.unoptimized=true` disables the runtime Next image optimizer; the sole existing image was already unoptimized;
- vulnerable packages remain present in the production dependency tree, so the deployment blocker remains.

## Final Quality Gates

| Command | Result |
|---|---|
| `python -m pytest` with isolated PostgreSQL | 420 passed, 0 failed, 0 skipped |
| `python -m ruff check .` | pass |
| changed-file `python -m ruff format --check` | 40 files formatted, pass |
| `python -m ruff format --check .` | fail: 67 pre-existing files would be reformatted |
| `python -m compileall -q src tests evaluation` | pass |
| `python -m alembic heads` | one head, `20260726_0008` |
| `python -m pip check` | pass |
| `npm --prefix frontend test` | 115 passed, 0 failed |
| frontend lint / typecheck / production build | pass / pass / pass; 32 routes |
| main and pilot Compose config | pass / pass |
| pilot contract tests | 28 passed |
| documentation links | 1 passed |
| `git diff --check` | pass for tracked diff |
| `npm --prefix frontend audit --omit=dev` | fail: 3 high, 0 critical |

## Readiness Conclusion

- Static code quality: verified pass, except the explicitly recorded repository-wide legacy format gate.
- Unit and PostgreSQL integration testing: verified pass.
- Live Qdrant, real Ollama, grounded RAG+LLM, full Docker runtime, and authenticated multi-role workflow: verified pass on this workstation.
- Graduation defense: verified ready for a controlled local rehearsal using the recorded service/model setup; perform the short preflight immediately before the defense.
- Production: verified fail. Dependency advisories, oversized/cold-build image behavior, lack of browser automation, small synthetic corpus, single-node operations, and outstanding organizational/security/recovery gates remain.

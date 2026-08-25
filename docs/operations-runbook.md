# Operations and Reproduction Runbook

This is the canonical safe operations guide for the final portfolio repository.
Commands target Windows PowerShell. They do not imply production readiness.

Normal review should use Offline verification. The full Stage 9-11 scale run is
historical synthetic evidence and is expensive to regenerate.

## Safety rules

- Run commands from the repository root.
- Keep credentials in an ignored local environment file or process environment;
  never print or commit them.
- Inspect before starting; start only the explicitly required service.
- Never reset, truncate, reseed, or advance a preserved benchmark watermark for
  a documentation check.
- Never remove volumes, prune Docker resources, or use a destructive Compose
  teardown as a normal stop procedure.
- Do not run the load benchmark, scale generators, or Airflow pipelines merely
  to verify documentation.
- Do not enable external LLM/embedding services for release verification.

## 1. Prerequisites

```powershell
Set-Location D:\code\rag\ai_maintain_copilot

git --version
Get-Command powershell
Get-Command python -ErrorAction SilentlyContinue
Get-Command docker -ErrorAction SilentlyContinue
Get-Command node -ErrorAction SilentlyContinue
```

Optional tool absence is acceptable for Offline mode. Check disk and memory
before any scale work:

```powershell
Get-PSDrive C,D | Select-Object Name,Used,Free
Get-CimInstance Win32_OperatingSystem |
  Select-Object TotalVisibleMemorySize,FreePhysicalMemory
```

Do not regenerate the Stage 10 fixture unless there is a separate approved
benchmark plan, at least tens of GB of free disk, sufficient Docker memory, and
time for generation, COPY, Airflow, and dbt.

## 2. Offline final verification

This path does not require a running Docker daemon:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\verify_final_release.ps1 -Mode Offline
```

Expected result: required checks are `PASS`, unavailable optional tools are
`SKIP`, and the process exits `0`. Required document, JSON, metric, link,
secret, public-IP, lineage, or generated-artifact failures exit nonzero.

Use `-RequireCleanCommit` only after a future approved Stage 12 commit and after
the explicitly protected local changes are no longer present:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\verify_final_release.ps1 `
  -Mode Offline -RequireCleanCommit
```

## 3. Compose validation without starting services

Docker Compose can parse files even when the engine is unavailable:

```powershell
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.test.yml config --quiet
docker compose -f docker-compose.scale.yml config --quiet
```

These commands resolve configuration only. They do not start, stop, or recreate
containers.

## 4. Inspect Docker and service state

```powershell
docker version
docker compose -f docker-compose.yml ps --all
docker compose -f docker-compose.scale.yml ps --all
```

If `docker version` cannot reach the engine, remain in Offline mode. Do not
start Docker Desktop solely to review the release documents.

## 5. Start only explicitly required local services

Create an ignored local `.env` and populate its secrets without displaying
them:

```powershell
Copy-Item .env.example .env
# Edit .env locally. Confirm that Git ignores it:
git check-ignore -v .env
```

Application path:

```powershell
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml up -d --wait postgres qdrant migrate api

# Start the UI only when it is part of the demo.
docker compose -f docker-compose.yml up -d --wait frontend

# Start the closed operations worker only for an approved worker demo.
docker compose -f docker-compose.yml --profile worker up -d --wait worker
```

Preserved scale path, only when its existing volumes already exist:

```powershell
docker compose -f docker-compose.scale.yml config --quiet
docker compose -f docker-compose.scale.yml up -d --no-deps --wait `
  --wait-timeout 180 stage9-scale-postgres
docker compose -f docker-compose.scale.yml up -d --no-deps --wait `
  --wait-timeout 120 stage10-api
```

Do not run the scale generators or Airflow DAGs for a normal demo.

## 6. Health checks

Application:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health
```

Scale Analytics API:

```powershell
Invoke-RestMethod http://127.0.0.1:18082/health/live
Invoke-RestMethod http://127.0.0.1:18082/health
```

Expected liveness is `alive`; public health is `ok`. Readiness may report a
degraded optional dependency without making public health unavailable. Use the
exact historical result in
[Stage 11 API performance](stage11-api-performance.md) when services are down.

The verifier provides non-mutating probes when requested:

```powershell
.\scripts\verify_final_release.ps1 -Mode LocalReadOnly
.\scripts\verify_final_release.ps1 -Mode ScaleReadOnly
```

## 7. Backend and frontend verification

Focused offline backend checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests\test_final_release_docs.py
.\.venv\Scripts\ruff.exe check tests\test_final_release_docs.py
.\.venv\Scripts\python.exe -m compileall -q src data_platform tests
```

Broader backend checks, when time permits:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
```

The PostgreSQL integration script is fixed to the isolated local
`maintenance_copilot_test` database. It must never target a scale/demo database:

```powershell
.\scripts\test-postgres.ps1 -Action test
```

Frontend checks, needed only when frontend files change or before an explicit
release:

```powershell
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
```

The historical Stage 10 totals are 1,365 backend, 87 PostgreSQL integration,
141 frontend, and 459 dbt checks: 2,052 total. Do not label them as a newly run
Stage 12 suite.

## 8. Alembic validation

Offline head inspection:

```powershell
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic -c data_platform\alembic.ini heads
```

Expected heads:

```text
20260726_0008 (head)
20260824_dp0003 (head)
```

Application database checks against the isolated test database are handled by
`scripts/test-postgres.ps1`. Data Platform migrations use an independent
`data_platform_alembic_version` table and explicit forward SQL.

## 9. Airflow DAG import validation

When a previously created Airflow container is already running, inspect imports
without starting the scheduler or triggering a DAG:

```powershell
docker exec stage9-airflow-api-server `
  airflow dags list-import-errors --output json
```

Expected output is `[]`. If Airflow dependencies or the container are absent,
use the historical machine evidence:

```powershell
(Get-Content -Raw docs\benchmark-results-domain-scale.json |
  ConvertFrom-Json).verification.airflow_import_errors
```

Expected historical value is `0`.

## 10. dbt parse, build, and tests

Parse is the preferred lightweight check when `dbt` is installed:

```powershell
dbt parse `
  --project-dir data_platform\dbt\maintenance_analytics `
  --profiles-dir data_platform\dbt\profiles `
  --target scale --no-partial-parse
```

Build/test requires a deliberately available scale database and may take
minutes:

```powershell
dbt build `
  --project-dir data_platform\dbt\maintenance_analytics `
  --profiles-dir data_platform\dbt\profiles `
  --target scale --no-partial-parse
```

Expected historical Stage 10 result is `459/459 PASS` (26 models and 433 data
tests). Generated `target/` and `logs/` directories are ignored.

## 11. Read-only watermark inspection

Only run this when the preserved scale PostgreSQL container is already running.
The query does not advance a watermark:

```powershell
docker exec stage9-scale-postgres psql -X `
  -U maintenance_scale -d maintenance_copilot_benchmark_scale `
  -c "SELECT domain_name, version, source_available_at, source_id
      FROM audit.domain_watermarks
      ORDER BY domain_name;"
```

Expected checkpoint: six rows, all version `2`. Pipeline state:

```powershell
docker exec stage9-scale-postgres psql -X `
  -U maintenance_scale -d maintenance_copilot_benchmark_scale `
  -c "SELECT status, count(*)
      FROM audit.domain_pipeline_runs
      GROUP BY status ORDER BY status;"
```

There should be zero `running` runs before any deliberate pipeline operation.

## 12. Read-only reconciliation inspection

```powershell
docker exec stage9-scale-postgres psql -X `
  -U maintenance_scale -d maintenance_copilot_benchmark_scale `
  -c "SELECT
        (SELECT count(*) FROM analytics_warehouse.fact_work_order) AS work_orders,
        (SELECT count(*) FROM analytics_warehouse.fact_work_order_status_duration) AS statuses,
        (SELECT count(*) FROM analytics_warehouse.fact_ticket_sla) AS tickets,
        (SELECT count(*) FROM analytics_warehouse.fact_inventory_movement) AS movements,
        (SELECT count(*) FROM analytics_warehouse.fact_work_order_cost) AS costs;"
```

Expected historical counts are 1,100,000; 3,300,000; 300,000; 1,500,000; and
1,100,000. The complete seven-domain map is in
[release-manifest.json](release-manifest.json).

## 13. Authenticated Analytics API smoke

Use only a pre-provisioned local benchmark identity and a password already held
in process memory. The commands never print the password or token:

```powershell
if (-not $env:STAGE10_BENCHMARK_PASSWORD) {
  throw 'Load the benchmark password from a local secret source first.'
}

$base = 'http://127.0.0.1:18082'
$login = Invoke-RestMethod -Method Post -Uri "$base/auth/login" `
  -ContentType 'application/json' `
  -Body (@{
    identifier = 'stage11.benchmark'
    password = $env:STAGE10_BENCHMARK_PASSWORD
  } | ConvertTo-Json)
$headers = @{ Authorization = "Bearer $($login.access_token)" }
$rows = Invoke-RestMethod -Headers $headers -Uri (
  "$base/analytics/domain/ticket_sla?" +
  'start_date=2024-01-01&end_date=2024-12-31&limit=25&' +
  'site_id=00020000-0000-0000-0000-000000000001'
)
$rows.Count
Remove-Variable login,headers,rows -ErrorAction SilentlyContinue
```

Expected site-scoped result is four rows in the preserved fixture. Login creates
normal authentication session/audit state; the analytics query itself is
read-only. Use historical evidence when no local credential is provisioned.

## 14. Deliberate load benchmark

Do not run this for normal verification. It performs the Stage 11 25/50-client
pair and writes an ignored raw artifact:

```powershell
if (-not $env:STAGE10_BENCHMARK_PASSWORD) {
  throw 'Load the benchmark password from a local secret source first.'
}
.\.venv\Scripts\python.exe -m data_platform.api_benchmark `
  --base-url http://127.0.0.1:18082 `
  --username stage11.benchmark `
  --requests-per-client 4 `
  --site-id 00020000-0000-0000-0000-000000000001 `
  --pipeline-state idle `
  --stabilization-seconds 10 `
  --output data/scale/stage11-api-performance/manual-review.json
```

The accepted report already contains one warm-up and three measured pairs. See
[Analytics API load test](analytics-api-load-test-stage11.md).

## 15. Safe stop without deleting volumes

Application:

```powershell
docker compose -f docker-compose.yml stop frontend api worker qdrant postgres
```

Scale services:

```powershell
docker compose -f docker-compose.scale.yml stop `
  stage10-api stage9-airflow-scheduler stage9-airflow-dag-processor `
  stage9-airflow-api-server stage9-airflow-postgres stage9-scale-postgres
```

These stop commands preserve containers, networks, and volumes. Never add a
volume-deletion or prune operation to the normal stop procedure.

## Troubleshooting

### Docker unavailable

Symptoms include failure to connect to the Docker named pipe or engine.

```powershell
docker context show
docker version
.\scripts\verify_final_release.ps1 -Mode Offline
```

Stay Offline unless runtime validation is explicitly required. Compose parsing
may still work when the engine is unavailable.

### Python import error

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -c "from src.api.main import app; print(app.title)"
```

Confirm that the command runs from the repository root and that no unrelated
`PYTHONPATH` overrides the editable install.

### Airflow import error

```powershell
docker exec stage9-airflow-api-server `
  airflow dags list-import-errors --output json
docker logs --tail 100 stage9-airflow-api-server
```

Check mounted DAG paths, Airflow 3 imports, and installed provider versions.
Do not trigger the DAG merely to diagnose parsing.

### Database unavailable

```powershell
docker compose -f docker-compose.scale.yml ps stage9-scale-postgres
docker logs --tail 100 stage9-scale-postgres
```

Verify health, disk space, memory, and local environment configuration. Do not
silently fall back to mutable CSV storage.

### Pool exhaustion

```powershell
# Protected aggregate metrics; use an existing authenticated local session.
Invoke-RestMethod -Headers $headers `
  http://127.0.0.1:18082/operations/metrics
Invoke-RestMethod -Headers $headers `
  http://127.0.0.1:18082/analytics/domain/metrics/runtime
```

Check worker count, pool size, overflow, checked-out connections, query slots,
slot wait time, and PostgreSQL activity. Do not raise `max_connections` as the
first response. The accepted scale budget is 24 theoretical API connections.

### Cache or site-scope failure

Confirm that cache keys include authorization identity, site, exact query,
dates, and limit. Cache must be bypassed without authorization scope. Compare
two sites using only IDs the actor is authorized to access; never print tokens
or payloads containing personal data.

### Disk or memory pressure

```powershell
Get-PSDrive C,D | Select-Object Name,Used,Free
docker system df
docker stats --no-stream
```

Stop optional services safely before rerunning a bounded check. Preserve
benchmark volumes unless separate deletion approval exists.

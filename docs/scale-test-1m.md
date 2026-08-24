# Stage 9 — Reproduce the 1M + Incremental Scale Test

## Mục đích và stop gate

Runbook này tạo đúng 1,000,000 baseline work orders, sau đó 100,000 work orders
mới và 10,000 updates trong isolated local scale environment. Nó không dùng
normal developer database/volume, AWS, S3, Qdrant, LLM hoặc embedding API.

Không bắt đầu generation nếu một trong các gate sau fail:

- target repo không phải `D:\code\rag\ai_maintain_copilot` hoặc có conflicting
  work cần operator quyết định;
- Docker unavailable hoặc Compose config invalid;
- Docker memory allocation dưới khoảng 8 GB (7.5 GiB) cho topology hiện tại;
- ổ chứa repository còn dưới **12 GiB free**;
- port `25432` hoặc `18081` đang bị process ngoài Stage 9 chiếm;
- container/database được resolve không có tên/suffix scale-specific.

Estimate để lập kế hoạch, không phải measured 1M result: sample deterministic
50,000-row chunks hiện khoảng 26 MB work-order CSV và 8.6 MB related log CSV.
Suy rộng baseline cùng dimension files khoảng 0.7–0.8 GiB; incremental/new/update
files khoảng 0.1–0.2 GiB. PostgreSQL source, raw versions, dbt tables/indexes,
WAL, temp files, Airflow logs và object copies có thể cần nhiều lần kích thước
CSV. Gate 12 GiB là conservative local working margin; measured final sizes phải
được lấy từ benchmark JSON, không thay estimate bằng claim.

## 1. Read-only preflight

Chạy từ PowerShell. Các lệnh dưới đây không prune, xóa volume hoặc mutate AWS:

```powershell
Set-Location D:\code\rag\ai_maintain_copilot
$runId = "stage9-1m-seed-20260823"
$env:DATA_PLATFORM_DB_NAME = "maintenance_copilot_benchmark_scale"

git status --short
Get-PSDrive -PSProvider FileSystem | Select-Object Name, Used, Free, Root
(docker info --format json | ConvertFrom-Json).MemTotal
docker system df
docker ps --all
docker compose -f docker-compose.scale.yml config --quiet
docker compose -f docker-compose.scale.yml ps --all
.\.venv\Scripts\python.exe -m data_platform.preflight --work-order-count 1100000
```

Xác nhận `D:` có ít nhất 12 GiB free và Docker có khoảng 8 GB (7.5 GiB)
allocated. Không
chạy `docker system prune`, không remove image/volume để vượt gate. Nếu thiếu
resource, dừng và ghi số byte/GiB thiếu vào report.

Kiểm tra port read-only:

```powershell
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object LocalPort -In 25432,18081 |
  Select-Object LocalAddress, LocalPort, OwningProcess
```

Port đã thuộc đúng Stage 9 container đang resume là hợp lệ; port của process khác
là blocker. Runtime tự fail closed nếu database name không kết thúc `_scale` hoặc
database user không scale-specific.

## 2. Verification trước full run

```powershell
.\.venv\Scripts\python.exe -m pytest tests\data_platform -q
.\.venv\Scripts\python.exe -m ruff check data_platform src\analytics\maintenance_adapter.py tests\data_platform
.\.venv\Scripts\python.exe -m compileall -q data_platform src\analytics\maintenance_adapter.py
docker compose -f docker-compose.scale.yml config --quiet
```

Final measured reference có 42 Data Platform tests và 307 dbt tests pass. Mỗi
reproduction vẫn phải ghi output mới; không dùng historical pass để che failure.

### Small rehearsal trên scale database trống

Để học/troubleshoot nhanh, có thể chạy cùng workflow với baseline 1,000,
incremental 100 và 10 updates. Chỉ dùng **thay cho** full run trên một Stage 9
database mới/trống; không trộn với full dataset và không truncate database đang
có. Sau bước migrate, fail closed nếu đã có source rows:

```powershell
$existingRows = docker compose -f docker-compose.scale.yml exec -T `
  stage9-scale-postgres psql `
  -U maintenance_scale `
  -d maintenance_copilot_scale `
  -tAc 'SELECT count(*) FROM public.work_orders'
if ([int64]$existingRows.Trim() -ne 0) {
  throw 'Small rehearsal requires a fresh empty Stage 9 database; no rows were changed.'
}

$smokeRunId = 'stage9-smoke-seed-20260823'
$env:DATA_PLATFORM_DB_NAME = 'maintenance_copilot_scale'
.\scripts\generate_scale_data.ps1 `
  -WorkOrderCount 1000 -Seed 20260823 -Phase baseline -BatchSize 1000 `
  -BaselineCount 1000 -UpdateCount 0 -RunId $smokeRunId -OutputRoot data/scale
.\.venv\Scripts\python.exe -m data_platform.loader load `
  --manifest "data/scale/$smokeRunId/baseline/manifest.json"

# Chạy baseline DAG theo section 5, dùng run ID "$smokeRunId-baseline".

.\scripts\generate_scale_data.ps1 `
  -WorkOrderCount 100 -Seed 20260823 -Phase incremental -BatchSize 1000 `
  -BaselineCount 1000 -UpdateCount 10 -RunId $smokeRunId -OutputRoot data/scale
.\.venv\Scripts\python.exe -m data_platform.loader load `
  --manifest "data/scale/$smokeRunId/incremental/manifest.json"

# Chạy incremental và empty DAG theo sections 7–8.
```

Expected correctness gate của profile này là 1,100 final unique, 1,110 raw
versions và 10 update versions. Đây chỉ là smoke; không đưa timings/sizes của nó
vào các marker 1M.

## 3. Start isolated source và migrate

```powershell
$dedicatedVolume = 'ai_maintenance_copilot_stage9_scale_pgdata_v1'
$volumeExists = docker volume ls -q --filter "name=^${dedicatedVolume}$"
if (-not $volumeExists) {
  # Chỉ set initial DB khi dedicated Stage 9 volume chưa từng được tạo.
  $env:STAGE9_POSTGRES_INITIAL_DB = $env:DATA_PLATFORM_DB_NAME
} else {
  Remove-Item Env:STAGE9_POSTGRES_INITIAL_DB -ErrorAction SilentlyContinue
}

docker compose -f docker-compose.scale.yml up -d --wait --wait-timeout 180 `
  stage9-scale-postgres
docker compose -f docker-compose.scale.yml ps stage9-scale-postgres

$benchmarkDb = 'maintenance_copilot_benchmark_scale'
$databaseExists = docker compose -f docker-compose.scale.yml exec -T `
  stage9-scale-postgres psql -U maintenance_scale -d postgres -tAc `
  "SELECT 1 FROM pg_database WHERE datname = '$benchmarkDb'"
if ($databaseExists.Trim() -ne '1') {
  docker compose -f docker-compose.scale.yml exec -T `
    stage9-scale-postgres createdb -U maintenance_scale -O maintenance_scale $benchmarkDb
}
$env:DATA_PLATFORM_DB_NAME = $benchmarkDb
.\.venv\Scripts\python.exe -m data_platform.loader migrate
```

Database creation ở đây chỉ nằm trong dedicated Stage 9 PostgreSQL volume. Nếu
name đã có, command reuse nguyên database; loader/manifest checks fail closed
thay vì truncate. Không chạy đoạn này trên normal application container.

`migrate` chạy application Alembic history trên **isolated** scale database rồi
chỉ nâng Data Platform history đến `20260824_dp0001`. Measured tuple-watermark
index ở revision tiếp theo chưa được áp dụng cho tới khi có before evidence.

## 4. Generate và COPY baseline 1,000,000

```powershell
$existingSourceRows = docker compose -f docker-compose.scale.yml exec -T `
  stage9-scale-postgres psql -U maintenance_scale -d $env:DATA_PLATFORM_DB_NAME `
  -tAc 'SELECT count(*) FROM public.work_orders'
if ([int64]$existingSourceRows.Trim() -ne 0) {
  throw 'Baseline requires an empty isolated benchmark database; no rows were changed.'
}

.\scripts\generate_scale_data.ps1 `
  -WorkOrderCount 1000000 `
  -Seed 20260823 `
  -Phase baseline `
  -BatchSize 50000 `
  -BaselineCount 1000000 `
  -UpdateCount 0 `
  -RunId $runId `
  -OutputRoot data/scale

.\.venv\Scripts\python.exe -m data_platform.loader load `
  --manifest "data/scale/$runId/baseline/manifest.json"
.\.venv\Scripts\python.exe -m data_platform.loader validate
```

Không chấp nhận manifest cho đến khi `actual_work_orders=1000000`,
`actual_updates=0`, mọi `row_count`, checksum và duration có mặt. Loader COPY theo
dependency order, ANALYZE source tables và ghi chunk restart markers. Replay cùng
manifest phải báo verified chunks đã skip; checksum khác cho cùng run/phase phải
fail.

## 5. Start Airflow và chạy baseline DAG

```powershell
docker compose -f docker-compose.scale.yml up -d --build `
  --wait --wait-timeout 600 `
  stage9-airflow-api-server `
  stage9-airflow-scheduler `
  stage9-airflow-dag-processor

docker compose -f docker-compose.scale.yml ps
docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  airflow dags list
docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  airflow dags unpause maintenance_scale_pipeline
docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  airflow dags trigger maintenance_scale_pipeline `
  --run-id "$runId-baseline"
docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  airflow dags list-runs maintenance_scale_pipeline --output table
```

Đợi run `$runId-baseline` ở trạng thái `success`; không trigger incremental khi
baseline còn queued/running. Xác nhận đủ 9/9 tasks success, retries và từng task
duration từ Airflow metadata/UI `http://127.0.0.1:18081`. DAG đã bao gồm dbt run,
dbt test, reconciliation và final audit.

Các lệnh dbt trực tiếp sau dùng đúng container/runtime của DAG, hữu ích để parse
trước run hoặc troubleshoot; không chạy song song với DAG:

```powershell
docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  dbt parse `
  --project-dir /opt/maintenance-platform/data_platform/dbt/maintenance_analytics `
  --profiles-dir /opt/maintenance-platform/data_platform/dbt/profiles `
  --target scale --no-partial-parse

docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  dbt run `
  --project-dir /opt/maintenance-platform/data_platform/dbt/maintenance_analytics `
  --profiles-dir /opt/maintenance-platform/data_platform/dbt/profiles `
  --target scale --no-partial-parse

docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  dbt build `
  --project-dir /opt/maintenance-platform/data_platform/dbt/maintenance_analytics `
  --profiles-dir /opt/maintenance-platform/data_platform/dbt/profiles `
  --target scale --no-partial-parse

docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  dbt test `
  --project-dir /opt/maintenance-platform/data_platform/dbt/maintenance_analytics `
  --profiles-dir /opt/maintenance-platform/data_platform/dbt/profiles `
  --target scale --no-partial-parse
```

Nếu Airflow không thể chạy nhưng cần isolate failure, manual pipeline order tương
đương là:

```powershell
$pipelineRun = "$runId-manual-baseline"
.\.venv\Scripts\python.exe -m data_platform.pipeline audit-start --run-id $pipelineRun
.\.venv\Scripts\python.exe -m data_platform.pipeline check-source
.\.venv\Scripts\python.exe -m data_platform.pipeline snapshot-dimensions --run-id $pipelineRun
.\.venv\Scripts\python.exe -m data_platform.pipeline extract --run-id $pipelineRun
.\.venv\Scripts\python.exe -m data_platform.pipeline load-raw --run-id $pipelineRun
# Chạy dbt run và dbt test trong Airflow container bằng hai lệnh phía trên.
.\.venv\Scripts\python.exe -m data_platform.pipeline reconcile --run-id $pipelineRun
.\.venv\Scripts\python.exe -m data_platform.pipeline audit-complete --run-id $pipelineRun
```

Manual isolation không thay thế completion criterion yêu cầu một Airflow DAG run
thành công.

## 6. Measure rồi áp dụng watermark index

Sau baseline thành công, đo query cùng parameters trước khi index:

```powershell
.\.venv\Scripts\python.exe -m data_platform.benchmark queries `
  --output "data/scale/$runId/query-before-watermark-index.json" `
  --label before-watermark-index `
  --executions 5 `
  --only incremental_watermark_query

.\.venv\Scripts\python.exe -m data_platform.loader apply-watermark-index

.\.venv\Scripts\python.exe -m data_platform.benchmark queries `
  --output "data/scale/$runId/query-after-watermark-index.json" `
  --label after-watermark-index `
  --executions 5 `
  --only incremental_watermark_query
```

Chỉ ghi optimization là hữu ích khi EXPLAIN/BUFFERS và p50/p95 thật cho thấy cải
thiện phù hợp. Giữ cả before/after JSON. Không thêm index khác chỉ vì column xuất
hiện trong filter.

## 7. Generate và COPY incremental 100,000 + 10,000 updates

```powershell
.\scripts\generate_scale_data.ps1 `
  -WorkOrderCount 100000 `
  -Seed 20260823 `
  -Phase incremental `
  -BatchSize 50000 `
  -BaselineCount 1000000 `
  -UpdateCount 10000 `
  -RunId $runId `
  -OutputRoot data/scale

.\.venv\Scripts\python.exe -m data_platform.loader load `
  --manifest "data/scale/$runId/incremental/manifest.json"
.\.venv\Scripts\python.exe -m data_platform.loader validate
```

Manifest phải có `actual_work_orders=100000`, `actual_updates=10000` và khớp seed,
baseline count/dimension counts của manifest baseline. Không reset watermark.

Trigger incremental DAG:

```powershell
docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  airflow dags trigger maintenance_scale_pipeline `
  --run-id "$runId-incremental"
docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  airflow dags list-runs maintenance_scale_pipeline --output table
```

Run phải capture đúng 110,000 source versions mới trong batch: 100,000 IDs mới và
10,000 versions của IDs đã có. Final source/raw unique/staging/fact phải đều đúng
1,100,000; raw versions phải đúng 1,110,000 nếu baseline raw có đúng 1,000,000
versions và không có replay version ngoài contract.

## 8. Immediate empty/idempotent rerun

Không load/generate thêm gì giữa incremental run và bước này:

```powershell
docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  airflow dags trigger maintenance_scale_pipeline `
  --run-id "$runId-idempotent-empty"
docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  airflow dags list-runs maintenance_scale_pipeline --output table

.\.venv\Scripts\python.exe -m data_platform.pipeline reconcile `
  --run-id "$runId-idempotent-empty"
```

Gate: extract/load raw row count bằng 0, watermark tuple không đổi, final counts
không đổi, 9 tasks vẫn success và không duplicate fact.

## 9. Final benchmark và evidence

```powershell
docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  dbt build `
  --project-dir /opt/maintenance-platform/data_platform/dbt/maintenance_analytics `
  --profiles-dir /opt/maintenance-platform/data_platform/dbt/profiles `
  --target scale --no-partial-parse

docker compose -f docker-compose.scale.yml exec stage9-airflow-api-server `
  dbt test `
  --project-dir /opt/maintenance-platform/data_platform/dbt/maintenance_analytics `
  --profiles-dir /opt/maintenance-platform/data_platform/dbt/profiles `
  --target scale --no-partial-parse

.\.venv\Scripts\python.exe -m data_platform.benchmark queries `
  --output "data/scale/$runId/query-benchmark-final.json" `
  --label final-1.1m `
  --executions 5

.\.venv\Scripts\python.exe -m data_platform.benchmark evidence `
  --output "data/scale/$runId/benchmark-evidence-final.json"

.\.venv\Scripts\python.exe -m data_platform.pipeline reconcile `
  --run-id "$runId-final-reconciliation"
.\.venv\Scripts\python.exe -m data_platform.loader validate
```

Query harness đo 10 closed cases: site/date, latest status, critical open,
technician workload, monthly completion, cost-data availability, asset failure
frequency, daily mart, monthly mart và tuple watermark. Mỗi case có warmup, năm
executions, p50/p95 và `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`.

Sau đó ghi các JSON/manifests, Airflow task evidence, dbt output và test output
vào [benchmark-results-1m.md](benchmark-results-1m.md). Không commit generated
CSV, objects, dbt target/logs hoặc reports; `.gitignore` phải tiếp tục ignore
chúng.

## 10. Safe stop và resume

Planned stop: chờ COPY/dbt/Airflow task hiện tại kết thúc, rồi:

```powershell
docker compose -f docker-compose.scale.yml stop
docker compose -f docker-compose.scale.yml ps --all
```

Lệnh này giữ nguyên cả ba dedicated volumes và generated files. Resume:

```powershell
docker compose -f docker-compose.scale.yml up -d --wait --wait-timeout 600 `
  stage9-scale-postgres `
  stage9-airflow-api-server `
  stage9-airflow-scheduler `
  stage9-airflow-dag-processor
```

Nếu generator bị `Ctrl+C`, file đang ghi giữ suffix `.partial`; rerun đúng command
và run ID. Nếu loader bị dừng, mỗi committed chunk đã có checksum marker; rerun
cùng manifest. Nếu Airflow task bị dừng, xem durable audit/task state và retry sau
khi service healthy; không sửa watermark hoặc row bằng SQL.

Không dùng `down --volumes`, `docker volume rm`, `docker system prune` hoặc xóa
`data/scale` như một phần của safe stop.

## 11. Destructive cleanup — bắt buộc xác nhận riêng

Không chạy các snippet này trong benchmark completion run. Chỉ operator có
thẩm quyền mới cleanup sau khi đã lưu evidence cần thiết.

Xem chính xác dedicated resources trước, rồi yêu cầu typed confirmation:

```powershell
docker compose -f docker-compose.scale.yml ps --all
docker volume ls --filter label=com.docker.compose.project=ai-maintenance-copilot-stage9

$confirmation = Read-Host 'Type DELETE-STAGE9-VOLUMES to remove ONLY Stage 9 containers and volumes'
if ($confirmation -ne 'DELETE-STAGE9-VOLUMES') {
  throw 'Cleanup cancelled; confirmation did not match.'
}
docker compose -f docker-compose.scale.yml down --volumes --remove-orphans
```

Generated files là cleanup riêng, không gộp với volume cleanup:

```powershell
$repoRoot = (Resolve-Path -LiteralPath '.').Path
$scaleRoot = (Resolve-Path -LiteralPath 'data/scale').Path
$expectedScaleRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot 'data/scale'))
if ($scaleRoot -ne $expectedScaleRoot) {
  throw "Refusing unexpected cleanup target: $scaleRoot"
}
$confirmation = Read-Host 'Type DELETE-STAGE9-FILES to remove generated data/scale files'
if ($confirmation -ne 'DELETE-STAGE9-FILES') {
  throw 'File cleanup cancelled; confirmation did not match.'
}
Remove-Item -LiteralPath $scaleRoot -Recurse -Force
```

Các command này không được trỏ vào normal Compose volumes, application database,
reference repository hoặc user files khác.

## Troubleshooting ngắn

- `Data Platform database name must end with '_scale'`: sửa Stage 9 env; không
  nới validation.
- Manifest checksum conflict: không sửa manifest/chunk; dùng run ID mới nếu
  dataset intent khác.
- Reconciliation mismatch: giữ watermark, kiểm tra extraction batch/raw load/dbt
  task đầu tiên fail; không `--full-refresh` hoặc reset để che lỗi.
- dbt relation missing: xác nhận baseline DAG `snapshot_dimensions` và `load_raw`
  đã success, rồi chạy `dbt parse`; không chạy dbt vào application DB.
- Airflow queued mãi: DAG phải unpaused, scheduler/dag-processor/API và hai
  PostgreSQL services phải healthy.
- Disk dưới gate: stop trước generation; báo required margin, không prune/xóa.

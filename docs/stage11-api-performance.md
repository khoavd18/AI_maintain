# Stage 11 — Analytics API Performance Optimization

## Scope và checkpoint

Stage 11 bắt đầu từ checkpoint `3de9e53d072097665c9ecf718ddd4c22d418b4e6`
(direct parent `9d556946d33bb7340dc28feee33b2fb5cebc5c02`) trên branch
`feat/stage11-api-performance`. Stage này chỉ tối ưu authenticated structured
Analytics API; không thêm data, migration/index, service mới, frontend, RAG,
LLM, embedding, Qdrant hoặc cloud work.

Hai protected pre-existing modifications không thuộc Stage 11:

- `src/llm/prompt_builder.py` — SHA-256
  `22a1300d658ae04a2f48f13c27e6407ec17d13fc56ca274ddb43b4c7063b64ff`;
- `tests/test_grounded_generation_repair.py` — SHA-256
  `663a59b8e564ee1392f955c124d077a9e8599c5ddd33a9e7bf4f5719c13b7836`.

Stage 10 historical evidence không bị sửa. Kết quả load test chi tiết ở
[analytics-api-load-test-stage11.md](analytics-api-load-test-stage11.md), dữ
liệu aggregate chuẩn ở
[benchmark-results-api-stage11.json](benchmark-results-api-stage11.json).

## Root cause

Stage 10 runtime dùng hai Uvicorn workers. Mỗi process có SQLAlchemy pool
`8+4`, đồng thời analytics adapter dùng direct psycopg với tám query slots.
Hai connection families độc lập tạo theoretical maximum:

```text
workers × (SQLAlchemy pool + overflow) + workers × direct query slots
2 × (8 + 4) + 2 × 8 = 40 connections
```

PostgreSQL thực tế có `max_connections=50`; Stage 11 không đổi setting này.
Budget 40 để quá ít headroom cho monitor/admin/health và gây queueing khi
thread-pool handlers, app pool transactions và direct analytics transactions
cùng fan out. Reproduced baseline quan sát đến 33 connections và multi-second
latency trên cả `/health`.

Representative read-only SQL có direct p50 `4,98..47,67 ms`; adapter idle p50
`21,85..91,79 ms`. `EXPLAIN (ANALYZE, BUFFERS)` đều đọc từ shared buffer với
zero shared reads. Vì vậy không có evidence cho index, query semantic change,
pre-aggregation hoặc framework rewrite. Bottleneck là concurrency/connection
fan-out và repeated identical analytics, không phải slow SQL.

## Experiment và accepted implementation

Experiment matrix bị giới hạn đúng bốn configurations:

| Configuration | Workers | Pool/overflow | Direct slots | Cache | Result |
|---|---:|---:|---:|---:|---|
| Original baseline | 2 | `8/4` | 8 | off | reproduced |
| Candidate 1 | 2 | `4/0` | 8 | off | reject: 7 errors, 6,1256 RPS ở first measured 50-client run |
| Candidate 2 | 1 | `8/4` | 8 | off | reject: warm-up 50-client chỉ 12,9589 RPS |
| Final combined | 2 | `6/0` | 6 | 5s, 256 entries | accepted |

Final connection budget:

```text
2 × (6 + 0) + 2 × 6 = 24 connections
50 - 24 = 26 connections theoretical headroom
```

Các thay đổi nhỏ, đo được:

- Compose cho phép validate/override worker, app pool/overflow, analytics slots
  và cache settings; final scale defaults là `2`, `6+0`, `6`, `5s`, `256`;
- `DataPlatformSettings` validate query slots `1..32`, TTL `0..60` và max entries
  `1..4096`; library default TTL bằng `0`, nên cache off ngoài explicit Compose;
- adapter process-local sở hữu bounded semaphore, LRU cache và aggregate metrics;
- cache key gồm authorization user ID, exact query, site, start/end date và limit;
- thiếu authorization scope thì cache fail-closed bằng cách bypass;
- cache lookup được kiểm tra lại sau khi lấy query slot để gộp identical requests
  đang queue; returned rows được copy để caller không mutate cached object;
- authenticated `GET /analytics/domain/metrics/runtime` expose aggregate slot,
  query timing và cache hit/miss/eviction, không có identity/query labels;
- benchmark runner ghi error classes, timeouts, status distribution,
  non-empty rate, endpoint latency, PostgreSQL activity, app pool và runtime
  observations.

Không đổi SQL, response model, auth permission, site parameter, read-only
transaction ownership, statement timeout hoặc PostgreSQL/container limits.

## Cache lifecycle

Cache là per-process; hai workers không chia sẻ entry. TTL-only invalidation cho
phép analytics response stale tối đa khoảng 5 giây sau write. Khi store, expired
entries được xóa rồi LRU entry cũ nhất bị evict nếu vượt 256 entries. Không có
write-through hoặc cross-process invalidation. Runtime metrics không lưu hoặc
expose token, credential, user/site/query label.

Trade-off này phù hợp với repeated, read-only analytics request trong benchmark;
nó không được mô tả là production distributed-cache design. Deployment nhiều
replicas hoặc yêu cầu read-after-write chặt cần explicit invalidation riêng ở
stage khác.

## Benchmark acceptance

Median comparable result:

| Clients | Metric | Baseline | Final | Change |
|---:|---|---:|---:|---:|
| 25 | RPS | 49,4449 | 64,5314 | +30,5117% |
| 25 | p50 | 1.076,9253 ms | 711,6275 ms | -33,9204% |
| 25 | p95 | 1.734,9344 ms | 1.154,0085 ms | -33,4840% |
| 25 | p99 | 1.821,1465 ms | 1.305,3856 ms | -28,3207% |
| 50 | RPS | 41,5979 | 57,8139 | +38,9827% |
| 50 | p50 | 2.221,5076 ms | 1.669,5379 ms | -24,8466% |
| 50 | p95 | 4.284,3778 ms | 2.805,6529 ms | -34,5143% |
| 50 | p99 | 4.404,4391 ms | 3.074,9623 ms | -30,1849% |

Sáu final measured scenarios có zero errors/timeouts, `774/774` analytics
responses non-empty và HTTP status `200` cho toàn bộ 900 requests. PostgreSQL
overall maximum là 23 connections (`<=27` gate), không có pool-exhaustion hoặc
database-connection error. Live site-isolation smoke trả bốn ticket-SLA rows
cho site 1 và bốn rows cho site 2; mỗi payload chỉ có requested site ID. Repeated
site-1 call là byte-equivalent và tạo cache hit.

## Reproduce an toàn

Các lệnh sau giả định existing Stage 10 scale database đã được xác minh và chỉ
recreate stateless `stage10-api`. Không chạy generator, loader, Airflow DAG,
watermark finalization hoặc database reset.

```powershell
Set-Location D:\code\rag\ai_maintain_copilot

# Nạp các giá trị database từ local secret store; không ghi chúng vào repository.
$env:DATA_PLATFORM_DB_HOST = '127.0.0.1'
$env:DATA_PLATFORM_DB_PORT = '25432'
$env:DATA_PLATFORM_DB_NAME = 'maintenance_copilot_benchmark_scale'
$env:DATA_PLATFORM_DB_USER = '<scale-user>'
$env:DATA_PLATFORM_DB_PASSWORD = '<local-secret>'
$env:DATABASE_URL = 'postgresql+psycopg://<scale-user>:<local-secret>@127.0.0.1:25432/maintenance_copilot_benchmark_scale'

docker compose -f docker-compose.scale.yml config --quiet
docker compose -f docker-compose.scale.yml build stage10-api
```

Bootstrap một benchmark administrator explicit nếu identity chưa tồn tại.
Password random chỉ ở process memory:

```powershell
$secretBytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($secretBytes)
$env:STAGE10_BENCHMARK_PASSWORD = [Convert]::ToBase64String($secretBytes)
$env:ADMIN_BOOTSTRAP_PASSWORD = $env:STAGE10_BENCHMARK_PASSWORD
.\.venv\Scripts\python.exe -m src.security.cli create-admin `
  --username stage11.benchmark --display-name 'Stage 11 Benchmark'
Remove-Item Env:ADMIN_BOOTSTRAP_PASSWORD
```

Recreate original baseline API only:

```powershell
$env:STAGE11_API_WORKERS = '2'
$env:STAGE11_API_DATABASE_POOL_SIZE = '8'
$env:STAGE11_API_DATABASE_MAX_OVERFLOW = '4'
$env:STAGE11_API_QUERY_SLOTS = '8'
$env:STAGE11_API_CACHE_TTL_SECONDS = '0'
$env:STAGE11_API_CACHE_MAX_ENTRIES = '256'
docker compose -f docker-compose.scale.yml up -d --no-deps `
  --force-recreate --wait --wait-timeout 120 stage10-api
```

Warm-up rồi chạy ba measured pairs. Runner tự chờ 10 giây giữa 25 và 50
clients; loop chờ thêm 10 giây giữa pairs:

```powershell
$common = @(
  '--base-url', 'http://127.0.0.1:18082',
  '--username', 'stage11.benchmark',
  '--requests-per-client', '4',
  '--site-id', '00020000-0000-0000-0000-000000000001',
  '--pipeline-state', 'idle',
  '--stabilization-seconds', '10'
)

.\.venv\Scripts\python.exe -m data_platform.api_benchmark @common `
  --output data/scale/stage11-api-performance/baseline-repeat/warmup.json
1..3 | ForEach-Object {
  .\.venv\Scripts\python.exe -m data_platform.api_benchmark @common `
    --output "data/scale/stage11-api-performance/baseline-repeat/run-$_.json"
  if ($_ -lt 3) { Start-Sleep -Seconds 10 }
}
```

Apply final configuration bằng API-only recreation rồi lặp lại warm-up/measured
commands với output directory `final`:

```powershell
$env:STAGE11_API_WORKERS = '2'
$env:STAGE11_API_DATABASE_POOL_SIZE = '6'
$env:STAGE11_API_DATABASE_MAX_OVERFLOW = '0'
$env:STAGE11_API_QUERY_SLOTS = '6'
$env:STAGE11_API_CACHE_TTL_SECONDS = '5'
$env:STAGE11_API_CACHE_MAX_ENTRIES = '256'
docker compose -f docker-compose.scale.yml up -d --no-deps `
  --force-recreate --wait --wait-timeout 120 stage10-api

.\.venv\Scripts\python.exe -m data_platform.api_benchmark @common `
  --output data/scale/stage11-api-performance/final/warmup.json
1..3 | ForEach-Object {
  .\.venv\Scripts\python.exe -m data_platform.api_benchmark @common `
    --output "data/scale/stage11-api-performance/final/run-$_.json"
  if ($_ -lt 3) { Start-Sleep -Seconds 10 }
}
Remove-Item Env:STAGE10_BENCHMARK_PASSWORD
```

Safe stop chỉ dừng stateless API và giữ mọi volume/database:

```powershell
docker compose -f docker-compose.scale.yml stop stage10-api
```

Nếu operator cũng cần dừng database sau khi đã xác nhận không có job chạy, lệnh
vẫn giữ volume là `docker compose -f docker-compose.scale.yml stop
stage9-scale-postgres`. Không dùng `down`, `--volumes`, prune, truncate hoặc
watermark reset.

## Validation contract

Stage 11 validation gồm focused config/cache/concurrency/API/auth/site-isolation
tests, affected backend tests, relevant isolated PostgreSQL tests, Ruff,
compileall, Compose config, Alembic heads, Airflow DagBag import, dbt parse,
API import/startup/liveness/public-health/read-only smoke, JSON consistency,
Markdown links/fences, secret/public-IP scan, protected hashes, unchanged dataset
and watermarks, clean reference repository và empty Git index.

Kết quả cuối:

- focused Stage 11: `26 passed`, một existing Starlette/TestClient warning;
- affected backend selection: `102 passed, 9 skipped`, cùng existing warning;
- isolated PostgreSQL: `87 passed, 1374 deselected`, Alembic
  current/head/check sạch;
- Ruff, compileall, Compose config và API import: pass;
- application/Data Platform heads: `20260726_0008` / `20260824_dp0003`;
- Airflow DagBag import errors: `0`; dbt parse: pass;
- live liveness/public health: `alive` / `ok`; site isolation, repeated payload,
  pool `6/0/0` và cache `5s/256` smoke: pass;
- benchmark JSON consistency, raw hashes, Markdown links/fences và
  `git diff --check`: pass;
- high-confidence secret scan: `11` Stage 11 files, `0` findings; public-IP
  scan: `0` findings.

API final configuration được để running và healthy; PostgreSQL container identity
không đổi. Stage 11 không commit, tag, push, gọi AWS/LLM/embedding/Qdrant hoặc
xóa Docker volume.

## Limitations

- Synthetic single-laptop result, không phải production capacity hoặc SLA.
- `docker stats` là before/after snapshots; không có PostgreSQL CPU/memory
  time-series peak.
- Cache là per-process TTL-only, không coherent giữa replicas.
- Workload read-only, site-scoped, fixed one-year range; không đại diện global
  analytics, concurrent ingestion, WAN/TLS ingress hoặc mixed writes.
- Raw ignored artifacts nằm dưới `data/scale/stage11-api-performance/`; tracked
  JSON là aggregate/checksum record để review và commit.

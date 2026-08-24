# Stage 10 — Multi-domain Scale Runbook

## Phạm vi đã hoàn tất

Stage 10 mở rộng nguyên database benchmark Stage 9
`maintenance_copilot_benchmark_scale`; không tái tạo 1,1 triệu work order, không
truncate và không reset watermark Stage 9. Dữ liệu mới hoàn toàn synthetic và nằm
trong volume scale riêng.

| Domain | Số dòng cuối | Grain phân tích |
|---|---:|---|
| Work orders được giữ nguyên | 1.100.000 | `work_order_id` |
| Work-order status history | 3.300.000 | `event_id` |
| Tickets | 300.000 | `ticket_id` |
| Ticket events | 900.000 | `event_id` |
| Spare parts | 25.000 | `part_id` |
| Inventory movements | 1.500.000 | `movement_id` |
| Work-order costs | 1.100.000 | `work_order_id` |

Mỗi count trên đã khớp tại source, raw unique grain, staging và fact/dimension
tương ứng. Ticket events dừng ở staging vì SLA fact có grain ticket, không phải
event.

## Kiến trúc

```text
public OLTP synthetic fixture
  -> analytics_source compatibility contracts
  -> six independent tuple watermarks
  -> local immutable object + checksum
  -> idempotent COPY into raw + durable audit
  -> dbt staging/facts/dimensions/marts
  -> authenticated closed-query FastAPI adapter

manual/SOP/approved free text
  -> bounded local evidence export
  -> no embedding, no external API, no Qdrant bulk load
```

Data Platform Alembic tiến từ `20260824_dp0002` đến `20260824_dp0003` bằng
forward migration. Application Alembic vẫn ở `20260726_0008`. Application
autogenerate bỏ qua một allow-list nhỏ gồm version table/index do Data Platform
sở hữu; ORM và application migration head không đổi.

## Sinh và COPY dữ liệu

Generator dùng seed `20260824`, batch size `50.000`, output streaming và manifest
per-file SHA-256. Dataset ID là `stage10-domain-seed-20260824`.

| Phase | Generated rows trong manifest | Thời gian | Throughput generator | COPY rows | COPY time | COPY throughput |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 7.647.217 | 423,152 s | 18.072,04 rows/s | 7.647.217 | 706,495 s | 10.824,17 rows/s |
| Incremental | 81.250 | 121,752 s | 667,34 rows/s | 81.250 | 15,495 s | 5.243,80 rows/s |

Baseline domain chính gồm 3.267.000 status events, 300.000 tickets, 891.000
ticket events, 25.000 parts, 1.475.000 movements và 1.089.000 costs. Incremental
bổ sung 33.000 late statuses, 9.000 late ticket events, 3.000 ticket updates, 250
part updates, 25.000 movements và 11.000 costs.

Manifest nguồn cục bộ:

- `data/scale/stage10-domain-seed-20260824/baseline/manifest.json`;
- `data/scale/stage10-domain-seed-20260824/incremental/manifest.json`.

Hai manifest và toàn bộ CSV được ignore; bản tóm tắt kiểm chứng nằm ở
[benchmark-manifest-domain-scale.json](benchmark-manifest-domain-scale.json).

## Chạy lại an toàn

Các lệnh này giả định Stage 9 volume đã tồn tại và database count đã được xác minh.
Không chạy lại generator Stage 9.

```powershell
Set-Location D:\code\rag\ai_maintain_copilot
$env:DATA_PLATFORM_DB_NAME = 'maintenance_copilot_benchmark_scale'

docker compose -f docker-compose.scale.yml config --quiet
docker compose -f docker-compose.scale.yml up -d --wait --wait-timeout 180 `
  stage9-scale-postgres

.\.venv\Scripts\python.exe -m alembic -c data_platform\alembic.ini upgrade head
.\scripts\generate_domain_scale_data.ps1 `
  -RunId stage10-domain-seed-20260824 -Phase baseline -Seed 20260824
.\.venv\Scripts\python.exe -m data_platform.domain_loader load `
  --manifest data/scale/stage10-domain-seed-20260824/baseline/manifest.json
```

Không load baseline nếu source counts không còn ở checkpoint Stage 9. Loader dùng
run ID, chunk checksum và durable markers; cùng manifest được replay thì skip
chunk đã commit, checksum khác thì fail closed.

Sau baseline, generate/load phase incremental bằng cùng run ID và `-Phase
incremental`. Trigger DAG `maintenance_domain_scale_pipeline` lần lượt với một
run ID baseline, incremental và empty; không chạy hai run đồng thời.

## Pipeline và watermarks

DAG versioned có 19 task instances mỗi run:

- preflight và run audit;
- sáu extractor độc lập;
- sáu raw loaders độc lập;
- dbt run, dbt test, reconciliation;
- atomic watermark finalization và terminal audit.

XCom chỉ mang batch ID/count/checksum/path. Sáu watermarks hiện đều ở version 2.
Empty run trích và insert 0 dòng ở cả sáu domain, giữ nguyên version.

Fault injection chỉ được bật explicit trong database scale. Bằng chứng failure và
retry nằm ở [reliability-failure-recovery.md](reliability-failure-recovery.md).

## dbt và analytical contracts

Stage 10 thêm sáu staging models, bốn domain facts, một spare-part dimension và
bốn marts: site reliability, ticket SLA, inventory consumption, maintenance
cost. `dbt build` cuối chạy 26 models + 433 data tests, tổng `459/459 PASS` trong
154,21 giây; normal incremental run không dùng `--full-refresh`.

Các custom tests bắt chronology, duplicate consecutive status, final-status
agreement, orphan ticket event, SLA evidence, signed inventory semantics, cost
arithmetic và source/raw/staging/fact reconciliation.

## Authenticated analytics

`GET /analytics/domain/{query_name}` yêu cầu permission `analytics.read`. Sáu query
name được allow-list; caller không truyền SQL. Mỗi request dùng read-only
transaction, bind parameters, date range tối đa 366 ngày, limit tối đa 200,
statement timeout 30 giây và tối đa 8 analytical queries đồng thời mỗi API
worker.

Các capability:

- `maintenance_summary`;
- `site_reliability`;
- `ticket_sla`;
- `technician_workload`;
- `inventory_consumption`;
- `maintenance_cost_variance`.

Load-test thật và giới hạn laptop được ghi ở
[analytics-api-load-test.md](analytics-api-load-test.md).

## RAG boundary

```powershell
.\.venv\Scripts\python.exe -m data_platform.evidence_export `
  --output data/scale/stage10-evidence-export.jsonl `
  --max-candidates 1000
```

Run đo được xuất 5 candidate, SHA-256
`fdb722a7b3150e18a31a8b841587889c3576202f30a0b6db7c91ad71a9831da9`, với
`embedding_calls=0` và `external_api_calls=0`. Structured rows không được
vectorize.

## Validation tối thiểu khi reproduce

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\test-postgres.ps1 -Action test
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m compileall -q src data_platform tests
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
docker exec stage9-airflow-scheduler airflow dags list-import-errors --output json
```

Application Alembic `upgrade/head/current/check` phải sạch. Data Platform
`upgrade/head/current` phải ở `20260824_dp0003`; `alembic check` không được dùng
làm drift gate cho lineage này vì `target_metadata=None` và migrations là raw
forward SQL.

## Safe stop

Lệnh dừng an toàn, giữ nguyên database, Airflow logs và mọi volume:

```powershell
docker compose -f docker-compose.scale.yml stop `
  stage10-api stage9-airflow-scheduler stage9-airflow-dag-processor `
  stage9-airflow-api-server stage9-airflow-postgres stage9-scale-postgres
```

Không dùng `down --volumes`, `docker volume rm`, `docker system prune`, truncate,
reset watermark hoặc xóa `data/scale` như một phần của safe stop.

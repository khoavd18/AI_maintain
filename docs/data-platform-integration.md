# Stage 9 — Data Platform Integration

## Trạng thái bằng chứng

`data_platform/` là bounded capability cho analytics có cấu trúc trong unified
repository. Full local synthetic run đã xác nhận 1,100,000 final unique work
orders, 1,110,000 raw versions, 10,000 update versions, 307 dbt tests và 42 Data
Platform tests. Exact timings, sizes và plans ở
[benchmark-results-1m.md](benchmark-results-1m.md).

Không suy diễn từ local synthetic benchmark rằng hệ thống production-ready,
chịu được production traffic hoặc đã được sử dụng tại doanh nghiệp.

## Current code ownership — post-Stage 12

The current multi-domain implementation is capability-owned under
`data_platform/ingestion/domains/`; `data_platform/domain_pipeline.py` remains
the historical import and CLI facade. See
[Data Platform Code Ownership](data-platform-code-ownership.md) for the module
map, whole transaction boundaries, domain-extension checklist, safe validation,
and correctness findings that remain explicitly deferred. This organization
change does not alter or rerun the Stage 9-12 evidence below.

The current Stage 10 domain path uses tuple
`(source_available_at, source_id)`, commits raw rows before a separate
reconciliation/finalization gate, and runs the 19-task
`maintenance_domain_scale_pipeline`. The next sections through the Stage 9
evidence table describe the historical Stage 9 work-order contract; do not apply
its single-watermark transaction rules to the Stage 10 domain package.

## Kiến trúc tích hợp — historical Stage 9 contract

```text
isolated scale PostgreSQL / public (OLTP fixture)
    -> analytics_source compatibility views
    -> Python tuple-watermark extract (updated_at, work_order_id)
    -> local partitioned objects, raw append-only versions, pipeline audit
    -> dbt staging -> dimensions + incremental fact -> daily/monthly marts
    -> Power BI-compatible reads / bounded maintenance analytics adapter

manuals, SOPs, approved free text -> RAG chunking -> Qdrant documents only
```

Ranh giới ownership:

| Boundary | Owner | Contract |
|---|---|---|
| Application OLTP | application Alembic history, domain services và PostgreSQL repositories | `public` là source of truth; scale fixture dùng database/container riêng, không ghi vào developer database |
| Source adapter | Data Platform Alembic revision `20260824_dp0001` | `analytics_source` views ổn định tên/cột analytics mà không đổi application tables |
| Ingestion | `data_platform.pipeline` | incremental extract theo tuple strict `WHERE (updated_at, id) > (...) ORDER BY updated_at, id`; local object storage mặc định |
| Raw và audit | schemas `raw`, `audit` | raw giữ version theo batch; watermark chỉ advance trong transaction đã load raw và cập nhật audit thành công; empty batch không advance |
| Transform | `data_platform/dbt/maintenance_analytics` | staging chọn version mới nhất; dimensions, `fact_work_order`, daily/monthly marts |
| Orchestration | `maintenance_scale_pipeline` | 9 tasks tuần tự, bounded timeout/retry, no heavy parse-time I/O, no large XCom |
| BI/read adapter | marts và `src.analytics.maintenance_adapter` | query catalog đóng, parameter binding, read-only transaction, tối đa 500 rows |
| RAG | canonical `src/rag/` và Qdrant | tài liệu phi cấu trúc; không lưu hoặc embed hàng triệu structured work-order rows |

`DataPlatformSettings` là configuration boundary duy nhất của runtime này. Nó
fail closed nếu host không phải loopback/`scale-postgres`, database không kết
thúc bằng `_scale`, user không phải scale-specific, batch size ngoài giới hạn,
hoặc S3 được bật mà thiếu bucket. S3 là optional adapter và bị tắt trong local
benchmark; AWS/RDS không được gọi hoặc mutate.

Scale topology được định nghĩa bởi `docker-compose.scale.yml` và dùng các
service, network và volume chuyên biệt:

- `stage9-scale-postgres`, host port mặc định `25432`, database
  `maintenance_copilot_scale`;
- Airflow metadata ở `stage9-airflow-postgres`, không dùng application database;
- network `ai_maintenance_copilot_stage9_network_v1`;
- volumes `ai_maintenance_copilot_stage9_scale_pgdata_v1`,
  `ai_maintenance_copilot_stage9_airflow_pgdata_v1` và
  `ai_maintenance_copilot_stage9_airflow_logs_v1`.

Không volume nào của normal application Compose được mount hoặc reused.

Hai tên database xuất hiện trong tài liệu vì chúng phục vụ hai trường hợp khác
nhau:

| Trường hợp | Database | Quy tắc |
|---|---|---|
| Fresh/default Compose | `maintenance_copilot_scale` | Đây là default của cả `DATA_PLATFORM_DB_NAME` và `STAGE9_POSTGRES_INITIAL_DB` trong `docker-compose.scale.yml`. |
| Preserved historical benchmark | `maintenance_copilot_benchmark_scale` | Read-only SQL trong operations runbook chủ đích trỏ vào database benchmark đã được tạo trong preserved volume. Phải chọn tên này rõ ràng; không suy ra nó tồn tại trong một fresh volume. |

Khi tạo volume lần đầu, giữ `DATA_PLATFORM_DB_NAME` và
`STAGE9_POSTGRES_INITIAL_DB` cùng một giá trị. Thay `POSTGRES_DB` sau khi volume
đã được khởi tạo không tự tạo hoặc rename database. Trước mọi read-only check,
inspect database hiện có và không chạy reset/generator chỉ để làm cho tên khớp.

### dbt source code và runtime storage

dbt SQL nằm trong repository, còn relation đã materialize nằm trong PostgreSQL;
không có database staging/warehouse riêng trong local scale topology:

| Layer | Source code | Runtime location |
|---|---|---|
| Staging | `data_platform/dbt/maintenance_analytics/models/staging/` | Views trong schema `analytics_staging` của database được chọn bởi `DATA_PLATFORM_DB_NAME`. |
| Warehouse | `data_platform/dbt/maintenance_analytics/models/warehouse/` | Tables/incremental facts trong schema `analytics_warehouse` của cùng database. |
| Marts | `data_platform/dbt/maintenance_analytics/models/marts/` | Tables trong schema `analytics_marts` của cùng database. |
| dbt compiled artifacts/logs | Generated, không phải business data | Host `data/scale/dbt/target/` và `data/scale/dbt/logs/`, bind-mounted vào Airflow và phải remain ignored. |

`analytics_staging`, `analytics_warehouse`, và `analytics_marts` được tạo từ dbt
base schema `analytics` cộng custom schema `staging`, `warehouse`, và `marts`.
PostgreSQL lưu bytes của các relation này trong volume
`ai_maintenance_copilot_stage9_scale_pgdata_v1`. Airflow metadata nằm riêng ở
`stage9-airflow-postgres`/
`ai_maintenance_copilot_stage9_airflow_pgdata_v1`; nó không chứa dbt warehouse
data.

## Source-to-warehouse mapping

| Application entity/field | Analytics projection | Trạng thái và giới hạn |
|---|---|---|
| `locations` | `analytics_source.sites` -> `raw.sites` -> `stg_sites` -> `dim_site` | Giữ UUID, parent site, `location_type`, `is_active` và source timestamps. “Site” là analytics name cho location hierarchy, không rename OLTP table. |
| `assets` | `analytics_source.assets` -> `raw.assets` -> `stg_assets` -> `dim_asset` | Giữ string `asset_id`, site FK, criticality, lifecycle/operational status và installed timestamp. |
| asset model | `manufacturer` và `model` trong `dim_asset` | Target không có canonical asset-model dimension riêng; không tạo surrogate business entity giả. |
| technician/user | technician-role rows trong `analytics_source.technicians` -> `dim_technician` | Chỉ user có `role = 'technician'`; giữ UUID/employee code và active flag. Null assignee của work order được giữ. |
| `work_orders` | `analytics_source.work_orders` -> `raw.work_orders` -> `stg_work_orders` -> incremental `fact_work_order` | Giữ UUID, stable number, asset/site/technician keys, enum values, lifecycle timestamps, priority/type/status và timezone-aware `updated_at`. |
| work-order status history/events | raw work-order versions | Target hiện **không có dedicated work-order status-history/event table**. Raw versions chứng minh các source snapshots đã quan sát, nhưng không được gọi là complete business event history. Audit/outbox records không bị repurpose làm status fact. |
| `preventive_maintenance_plans` | source fixture/FK support | Generator/load giữ plan và `(preventive_plan_id, due_date)` integrity cho preventive work orders; current dbt warehouse chưa có plan dimension/fact. |
| `maintenance_logs` | `analytics_source.maintenance_logs`; source fixture count | Logs liên quan được generate/load theo domain constraint để kiểm tra integrity. Current dbt project chưa materialize maintenance-log fact. |
| `maintenance_tickets` | không ingest trong Stage 9 scale fact | Ticket lifecycle/SLA vẫn thuộc application domain. Generator không tạo synthetic ticket analytics rows và không tự resolve ticket qua work order. |
| inventory/parts/movements | không ingest trong Stage 9 scale fact | Canonical inventory ledger tiếp tục thuộc OLTP. Không suy ra parts từ `MaintenanceLog.parts_replaced`, không tạo cost ledger. |
| `completion_summary` | `resolution_note` | Compatibility rename chỉ ở source view; original field/table không đổi. |
| estimated/actual cost | nullable compatibility columns | Target work order **không có canonical cost fields**. `estimated_cost`, `actual_cost`, variance và mart totals là `NULL`; adapter phải trả availability rõ ràng, không fabricate zero/cost savings. |

Target hiện không có tenant/organization key trong các mapped entities, vì vậy
Stage 9 không phát minh multi-tenancy. Soft lifecycle state (`is_active`,
`lifecycle_status`) được project; không hard-delete để tạo snapshot. Timestamps
được lưu/so sánh ở UTC; reporting calendar của dbt dùng
`Asia/Ho_Chi_Minh` theo cấu hình project.

## Incremental và idempotency contract

1. Extract đọc committed lower tuple watermark và stream theo
   `(updated_at, work_order_id)` để xử lý nhiều IDs có cùng timestamp.
2. Batch ID và local object key là deterministic theo pipeline run ID. Object
   được ghi qua partial file rồi atomic rename; S3 không được dùng trong scale run.
3. `load-raw` COPY vào temp table, append raw versions và update watermark trong
   cùng successful transaction. Failure downstream rollback cả phần watermark đã
   chạm trong transaction đó.
4. Empty batch được audit nhưng không advance watermark.
5. Loader của source fixture dùng PostgreSQL COPY, checksum và
   `audit.dataset_load_chunks`; replay cùng run ID/manifest skip verified chunks,
   còn checksum conflict fail closed.
6. dbt staging rank latest version; `fact_work_order` dùng non-null
   `unique_key=work_order_id` và `delete+insert` incremental strategy. Tests phát
   hiện duplicate, null, relationships và enum ngoài contract.

## Airflow contract

DAG `maintenance_scale_pipeline` chạy lần lượt:

1. `start_pipeline_audit`
2. `check_source_database`
3. `snapshot_dimensions`
4. `extract_work_orders_incremental`
5. `load_work_orders_raw`
6. `dbt_run`
7. `dbt_test`
8. `reconcile`
9. `complete_pipeline_audit`

DAG không schedule tự động, `max_active_runs=1`, `max_active_tasks=1`, task có
timeout và tối đa hai retries. Bash tasks đặt `do_xcom_push=False`; durable audit
chỉ giữ metadata nhỏ. Airflow này không thay thế `src/operations/worker.py` và
không thêm job thứ năm vào closed application worker catalog.

## Security và safety

- Không chạy scale loader với application `DATABASE_URL`; Data Platform config
  không đọc `.env` của application và tự kiểm tra suffix `_scale`.
- Không external LLM/embedding call, không Qdrant indexing, không upload S3 và
  không AWS mutation trong benchmark.
- `MaintenanceAnalyticsAdapter` không nhận SQL từ caller/model; chỉ bốn query
  keys được allow-list và mọi parameter đều bound.
- Structured analytics là decision-support. Manager/technician vẫn chịu trách
  nhiệm safety check, field inspection và quyết định cuối cùng.
- Generated users không phải người thật, đều inactive và dùng deliberately
  invalid, login-disabled password hashes; chúng chỉ phục vụ FK/distribution,
  không phải authentication/load users và không chứa PII thực.
- Dừng service phải bảo toàn volumes. Cleanup là destructive action riêng, chỉ
  chạy sau typed confirmation theo [scale-test-1m.md](scale-test-1m.md).

## Evidence đã xác nhận và giới hạn

| Check | Evidence |
|---|---:|
| final source/raw unique/staging/fact work orders | 1,100,000 mỗi layer |
| raw work-order versions / captured updates | 1,110,000 / 10,000 |
| incremental/empty Airflow | 9/9 success, 0 retries cho mỗi run |
| dbt / Data Platform tests | 307 / 42 passed |
| final database size | 2,532,267,699 bytes |

Benchmark không xác nhận production concurrency, HA, failover, company data
quality hoặc business impact. Xem runbook đầy đủ tại
[scale-test-1m.md](scale-test-1m.md), measured report tại
[benchmark-results-1m.md](benchmark-results-1m.md), và boundary AI tại
[structured-data-vs-rag.md](structured-data-vs-rag.md).

## Stage 10 extension

Stage 10 supersedes only the Stage 9 “not ingested” analytical limitations; it
does not change application ownership. Data Platform revision `20260824_dp0003`
adds compatibility contracts for synthetic status history, ticket/work-order
links and work-order costs, plus six source/raw/staging pipelines with independent
watermarks.

| Domain | Analytical path | Final grain/count |
|---|---|---:|
| Status history | `analytics_compat` → source/raw/staging → `fact_work_order_status_duration` | event / 3.300.000 |
| Tickets/events | source/raw/staging → `fact_ticket_sla` | ticket 300.000; event 900.000 staging |
| Spare parts | source/raw/staging → `dim_spare_part` | part / 25.000 |
| Inventory | source/raw/staging → `fact_inventory_movement` | movement / 1.500.000 |
| Costs | `analytics_compat` → source/raw/staging → `fact_work_order_cost` | work order / 1.100.000 |

Các cost/status records này là synthetic analytical compatibility data trong
database scale; chúng không tuyên bố application ORM đã có canonical cost ledger
hay canonical work-order event store. Application Alembic vẫn ở `20260726_0008`.

DAG `maintenance_domain_scale_pipeline` có 19 task instances: sáu extractors,
sáu raw loaders, dbt/reconciliation và atomic watermark/audit gates. XCom chỉ giữ
metadata nhỏ. Watermark version 2 ở cả sáu domain sau baseline + incremental;
empty run không advance.

“Sáu domain” ở đây là sáu independent Stage 10 watermarks. Historical
seven-count evidence gồm legacy `work_orders` của Stage 9 cộng sáu count keys của
Stage 10; nó không có nghĩa là có watermark thứ bảy.

Read boundary mới là `DomainAnalyticsAdapter` và authenticated route
`/analytics/domain/{query_name}`. Catalog có sáu exact names, parameter binding,
read-only transaction, 366-day/200-row bounds, 30-second statement timeout và
per-worker concurrency guard. Không có arbitrary hoặc model-generated SQL.

Historical measured counts, controlled-retry evidence và load results ở
[stage10-domain-scale.md](stage10-domain-scale.md),
[reliability-failure-recovery.md](reliability-failure-recovery.md) và
[analytics-api-load-test.md](analytics-api-load-test.md). Current code retains
the deferred controlled-failure marker persistence limitation documented in
[Data Platform Code Ownership](data-platform-code-ownership.md#deferred-correctness-findings);
the historical run is not a guarantee for every current retry path.

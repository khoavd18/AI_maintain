# Stage 10 — Domain-scale Benchmark Results

## Kết luận đo đạc

Stage 10 đã reconcile toàn bộ seven-domain dataset trong database local cô lập.
Đây là laptop benchmark trên dữ liệu synthetic, không phải production SLA,
capacity certification hay bằng chứng sử dụng tại doanh nghiệp.

Mốc code: branch `feat/stage10-domain-scale`, Stage 9 ancestor
`9d556946d33bb7340dc28feee33b2fb5cebc5c02`. Không commit/tag/push được tạo trong
run này.

## Counts cuối

| Domain | Source | Raw unique | Staging | Fact/dimension |
|---|---:|---:|---:|---:|
| Work orders | 1.100.000 | 1.100.000 | 1.100.000 | 1.100.000 |
| Status history | 3.300.000 | 3.300.000 | 3.300.000 | 3.300.000 |
| Tickets | 300.000 | 300.000 | 300.000 | 300.000 |
| Ticket events | 900.000 | 900.000 | 900.000 | n/a — ticket-grain SLA fact |
| Spare parts | 25.000 | 25.000 | 25.000 | 25.000 |
| Inventory movements | 1.500.000 | 1.500.000 | 1.500.000 | 1.500.000 |
| Work-order costs | 1.100.000 | 1.100.000 | 1.100.000 | 1.100.000 |

Inventory operations và movements cùng bằng 1.500.000. Tám integrity query đều
trả 0: final status mismatch, consecutive duplicate status, negative duration,
missing ticket resolution evidence, orphan ticket events, inventory operation
mismatch, invalid inventory balance và cost reconciliation.

## Generation và source COPY

| Phase | Generator time | Generator rows/s | COPY rows | COPY time | COPY rows/s | CSV bytes |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 423,152 s | 18.072,04 | 7.647.217 | 706,495 s | 10.824,17 | 2.084.094.135 |
| Incremental | 121,752 s | 667,34 | 81.250 | 15,495 s | 5.243,80 | 22.470.540 |

Generator throughput incremental thấp hơn vì phase này deterministic-select và
ghi nhiều file nhỏ/late-update partitions; COPY throughput được báo riêng.

## Airflow và dbt

| Run | Phase | State | Tasks | Retries | Airflow duration | dbt run | dbt test | Reconcile |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `stage10_baseline_20260824T103700Z` | baseline | success | 19/19 | 0 | 886,6 s | 103,9 s | 92,2 s | 4,7 s |
| `stage10_incremental_fault_20260824T105500Z` | incremental | success | 19/19 | 3 | 235,6 s resumed; 412,9 s wall/audit | 60,7 s | 159,1 s | 8,7 s |
| `stage10_empty_20260824T110200Z` | empty | success | 19/19 | 0 | 223,9 s | 51,3 s | 136,2 s | 11,2 s |

Final standalone `dbt build`: 6 incremental + 10 table + 10 view models và 433
tests, `PASS=459 WARN=0 ERROR=0 SKIP=0`, 154,21 giây. Warning còn lại khi `dbt
parse` là notice end-of-support do chính dbt 1.10.23 phát ra, không phải project
deprecation.

## Query benchmark trước/sau index

Mỗi query có warmup, 5 timed executions và `EXPLAIN (ANALYZE, BUFFERS, FORMAT
JSON)`.

| Query | Before p50/p95 ms | After p50/p95 ms |
|---|---:|---:|
| Latest status | 1,0409 / 2,3899 | 0,7370 / 1,7355 |
| Time in status | 23,9848 / 25,4687 | 9,9713 / 10,9847 |
| Ticket SLA breaches | 6,7151 / 8,2124 | 3,0165 / 3,9122 |
| Escalated unresolved | 76,0729 / 78,9693 | 1,0649 / 1,6225 |
| Inventory balance | 13,7350 / 14,3788 | 6,3534 / 7,4945 |
| High-consumption parts | 198,3775 / 268,9470 | 8,1481 / 9,6309 |
| Work-order cost variance | 5,0286 / 9,7354 | 1,5167 / 1,8832 |
| Site reliability | 6,7456 / 8,7562 | 1,0767 / 1,3361 |
| Combined work-order/ticket/cost | 407,7664 / 840,3066 | 21,4518 / 23,7709 |

Measured plan evidence:

- combined query đổi `Seq Scan` fact work order/ticket sang bitmap scan
  `ix_fact_work_order_site_created` và partial index
  `ix_fact_ticket_sla_work_order`; plan total giảm khoảng 225,1 xuống 13,1 ms;
- high-consumption đổi seq scan + sort mart 268.142 rows sang ordered index scan;
- escalated unresolved đổi seq scan 8.000 rows sang partial index
  `ix_fact_ticket_sla_escalated_unresolved`, plan scan còn khoảng 0,047 ms.

Partitioning không được triển khai. Với các incremental bounds và measured
indexes hiện tại, pruning/maintenance complexity chưa chứng minh lợi ích đủ lớn.

## Storage

Final database size tại audit cuối: `10.945.558.195 bytes`. Query artifact ngay
sau index build ghi `10.945.451.699 bytes`; chênh lệch nhỏ đến từ auth/audit rows
của API benchmark.

| Relation lớn nhất | Total bytes | Table bytes | Index bytes |
|---|---:|---:|---:|
| `fact_work_order_status_duration` | 1.123.958.784 | 750.993.408 | 372.727.808 |
| `raw.work_order_status_history` | 1.052.368.896 | 643.817.472 | 408.338.432 |
| `analytics_compat.work_order_status_history` | 906.625.024 | 360.448.000 | 546.045.952 |
| `fact_work_order` | 791.691.264 | 644.980.736 | 146.497.536 |
| `raw.work_orders` | 690.216.960 | 433.250.304 | 256.819.200 |
| `fact_inventory_movement` | 614.875.136 | 463.208.448 | 151.511.040 |
| `raw.inventory_movements` | 552.353.792 | 372.187.136 | 180.027.392 |

Docker audit cuối: images 17,77 GB; containers 408,8 MB; local volumes 15,52 GB;
build cache 11,94 GB. Không prune. D: còn 44,78 GiB; C: còn 26,91 GiB.

## Automated validation

- backend: 1.365 passed, 87 conditionally skipped, một existing TestClient warning;
- isolated PostgreSQL: 87 passed, 1.365 deselected;
- frontend: ESLint pass, TypeScript pass, 141 tests/23 files pass, Next.js build
  32 static pages và 9 dynamic routes pass;
- Ruff, compileall, 4 Compose config checks và DagBag (`[]`) pass;
- application Alembic upgrade/head/current/check pass at `20260726_0008`;
- Data Platform upgrade/head/current pass at `20260824_dp0003`;
- high-confidence secret scan: 1.021 files, 0 findings;
- generated-artifact `.gitignore` checks: pass.

Data Platform `alembic check` không phải drift gate: lineage dùng raw forward SQL
và `target_metadata=None`, vì vậy Alembic từ chối autogenerate theo thiết kế.

## Artifacts và giới hạn

Machine result: [benchmark-results-domain-scale.json](benchmark-results-domain-scale.json).
Dataset checksums: [benchmark-manifest-domain-scale.json](benchmark-manifest-domain-scale.json).
API load: [analytics-api-load-test.md](analytics-api-load-test.md).

Các giới hạn còn lại: laptop/local Docker only; không production SLA; không HA,
partitioning hay distributed rate limiting; API benchmark site-scoped và pipeline
idle; readiness của standalone API báo degraded vì worker application không chạy,
trong khi database ready và live/public health đều pass; không RAG quality eval.

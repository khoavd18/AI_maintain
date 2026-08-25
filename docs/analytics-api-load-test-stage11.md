# Stage 11 — Analytics API load test

## Kết luận

Stage 11 chấp nhận cấu hình `2 workers`, SQLAlchemy pool `6 + 0` mỗi worker,
`6` direct analytics slots mỗi worker và process-local cache `TTL=5s`, tối đa
`256` entries. So với reproduced baseline cùng methodology, median 50-client
RPS tăng `38,9827%`, p95 giảm `34,5143%`, không có error/timeout và PostgreSQL
cao nhất là `23` connections. Đây là synthetic laptop benchmark, không phải
production capacity claim hoặc SLA.

Machine-readable evidence chuẩn là
[benchmark-results-api-stage11.json](benchmark-results-api-stage11.json).
Stage 10 evidence trong [analytics-api-load-test.md](analytics-api-load-test.md)
được giữ nguyên và chỉ được dùng làm historical comparison.

## Methodology

Runner `python -m data_platform.api_benchmark` giữ nguyên Stage 10 route mix và
thêm error classes, timeout count, endpoint latency, `pg_stat_activity`, pool
metrics và label-free analytics runtime metrics. Mỗi cấu hình accepted có một
warm-up rồi ba measured pairs. Mỗi pair gồm:

- 25 clients × 4 requests = 100 requests;
- chờ 10 giây;
- 50 clients × 4 requests = 200 requests;
- chờ 10 giây trước measured pair tiếp theo.

Mỗi request dùng real Bearer token lấy từ `POST /auth/login`. Workload round-robin
`/health` và sáu authenticated analytics routes, dùng site
`00020000-0000-0000-0000-000000000001`, date range
`2024-01-01..2024-12-31`, `limit=25`. Có 87 analytics responses trong scenario
25 clients và 171 trong scenario 50 clients. Tất cả đều phải là non-empty JSON
list. Credential random chỉ tồn tại trong process environment và không nằm
trong raw/tracked artifact.

Pipeline ở trạng thái idle; running pipeline count bằng `0`. Dataset không đổi:
database ở benchmark checkpoint là `10,945,558,195` bytes; các count đã recheck là `1.100.000` work orders,
`3.300.000` status rows, `300.000` tickets, `25.000` spare parts, `1.500.000`
inventory movements và `1.100.000` cost rows. Sáu watermark versions đều bằng
`2`.

Mỗi metric median được lấy độc lập từ ba sample, không chọn best run và không
giả định mọi median thuộc cùng một raw run. Cache TTL là 5 giây nên 10 giây
stabilization bảo đảm mỗi scenario measured bắt đầu sau expiry.

## Historical Stage 10 và reproduced baseline

Historical Stage 10 là một run cũ, không được rerun hoặc relabel:

| Clients | RPS | p50 | p95 | p99 | Errors | PG max |
|---:|---:|---:|---:|---:|---:|---:|
| 25 | 30,1753 | 1.651,3223 ms | 2.814,8447 ms | 3.090,7980 ms | 0 | 27 |
| 50 | 23,6934 | 4.237,2542 ms | 7.588,8775 ms | 7.889,8302 ms | 0 | 30 |

Stage 11 phát hiện PostgreSQL thực tế đang có `max_connections=50`; Stage 11
không thay đổi setting này. Historical brief từng mô tả budget 30, vì vậy
historical connection values vẫn được ghi đúng như artifact cũ nhưng không dùng
để suy ra cấu hình hiện tại. Warm PostgreSQL/OS buffer cache, `max_connections`
thực tế lớn hơn và environmental drift giải thích reproduced baseline nhanh hơn
historical run. So với historical, reproduced median RPS tăng `63,9%`/`75,6%`
và p95 giảm `38,4%`/`43,5%` ở 25/50 clients. Optimization chỉ được đánh giá với
reproduced baseline cùng runner và môi trường hiện tại.

Reproduced samples với original Stage 10 runtime (`2 workers`, pool `8+4`,
direct slots `8`, cache off):

| Run | Clients | RPS | p50 | p95 | p99 | Errors/timeouts | Valid analytics | PG max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 25 | 49,4449 | 1.076,9253 | 1.649,8996 | 1.821,1465 | 0 / 0 | 87/87 | 25 |
| 2 | 25 | 44,2277 | 1.222,8907 | 1.894,5687 | 2.024,4138 | 0 / 0 | 87/87 | 33 |
| 3 | 25 | 49,9829 | 976,5716 | 1.734,9344 | 1.808,7198 | 0 / 0 | 87/87 | 29 |
| 1 | 50 | 37,2401 | 2.591,4497 | 4.645,7713 | 4.790,1160 | 0 / 0 | 171/171 | 32 |
| 2 | 50 | 41,8328 | 2.221,5076 | 4.284,3778 | 4.404,4391 | 0 / 0 | 171/171 | 32 |
| 3 | 50 | 41,5979 | 2.132,2304 | 4.231,6284 | 4.357,0098 | 0 / 0 | 171/171 | 31 |

## Diagnosis

Original theoretical fan-out có hai connection families độc lập:

```text
SQLAlchemy:       2 workers × (pool 8 + overflow 4) = 24
direct analytics: 2 workers × 8 query slots        = 16
theoretical total                                  = 40
```

SQLAlchemy dùng synchronous psycopg driver với `pool_pre_ping=True`,
`pool_timeout=30s`; mỗi Uvicorn process có engine/pool riêng. Analytics handlers
là synchronous FastAPI handlers chạy trong thread pool. Mỗi adapter call giữ
một direct psycopg read-only transaction trong suốt query/fetch rồi context
manager release connection. Stage 10 global `BoundedSemaphore(8)` cũng là
per-process, không phải global qua hai workers.

Read-only direct SQL timing và `EXPLAIN (ANALYZE, BUFFERS)` loại slow SQL/index
là primary cause:

| Query | Direct SQL p50 | Adapter idle p50 |
|---|---:|---:|
| `ticket_sla` | 4,98 ms | 21,85 ms |
| `technician_workload` | 21,78 ms | 26,78 ms |
| `site_reliability` | 26,82 ms | 51,10 ms |
| `inventory_consumption` | 37,37 ms | 38,74 ms |
| `maintenance_cost_variance` | 45,81 ms | 38,95 ms |
| `maintenance_summary` | 47,67 ms | 91,79 ms |

Các timing là independent medians nên không trừ từng hàng như paired timing.
Tất cả representative plans có zero shared reads ở thời điểm đo. Dưới
concurrency, ngay cả `/health` cũng lên multi-second latency; pool/query metrics
cho thấy slots đạt peak và thời gian queue tăng. Root cause vì vậy là
worker/pool/direct-query fan-out, connection/transaction contention và queueing,
không phải N+1, serialization, missing index hoặc client limit.

## Bounded experiment matrix

Tổng cộng đúng bốn configurations được dùng:

| Configuration | Workers | App pool | Direct slots | Cache | Budget | Decision |
|---|---:|---:|---:|---:|---:|---|
| Reproduced baseline | 2 | `8+4` | 8 | off | 40 | baseline |
| Candidate 1 | 2 | `4+0` | 8 | off | 24 | reject |
| Candidate 2 | 1 | `8+4` | 8 | off | 20 | reject after warm-up |
| Final combined | 2 | `6+0` | 6 | 5s/256 | 24 | accept |

Candidate 1 tách riêng hypothesis giảm SQLAlchemy pool. First measured
50-client sample chỉ đạt `6,1256 RPS`, p95 `31.614,1563 ms`, có `7/200` HTTP
errors (`3,5%`), nên không đủ reliability để tiếp tục đủ ba accepted runs.
Diagnostic repeat vẫn chỉ đạt `19,0057 RPS` và p95 `9.467,8698 ms`.

Candidate 2 tách riêng hypothesis giảm worker. Warm-up 50-client chỉ đạt
`12,9589 RPS`, p95 `13.625,7958 ms`, nên bị dừng trước measured runs.

Final giữ hai workers để không serialize toàn bộ request, dùng balanced pool
`6+0`, six direct slots và cache ngắn cho repeated identical analytics. Final
budget là `2×(6+0) + 2×6 = 24`, để lại 26 connections theoretical headroom dưới
actual PostgreSQL limit 50 và vẫn dưới Stage 11 acceptance gate 27 khi đo.

## Final samples và median comparison

| Run | Clients | RPS | p50 | p95 | p99 | Errors/timeouts | Valid analytics | PG max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 25 | 70,6584 | 711,6275 | 1.082,3887 | 1.203,3534 | 0 / 0 | 87/87 | 20 |
| 2 | 25 | 64,5314 | 661,6862 | 1.154,0085 | 1.305,3856 | 0 / 0 | 87/87 | 23 |
| 3 | 25 | 35,4981 | 1.585,6972 | 2.238,1546 | 2.563,0454 | 0 / 0 | 87/87 | 21 |
| 1 | 50 | 60,1402 | 1.500,1213 | 2.717,3636 | 2.854,0897 | 0 / 0 | 171/171 | 23 |
| 2 | 50 | 57,8139 | 1.669,5379 | 2.805,6529 | 3.074,9623 | 0 / 0 | 171/171 | 20 |
| 3 | 50 | 50,5020 | 1.774,0425 | 3.396,8330 | 3.545,4673 | 0 / 0 | 171/171 | 20 |

| Clients | Metric | Baseline median | Final median | Change |
|---:|---|---:|---:|---:|
| 25 | RPS | 49,4449 | 64,5314 | +30,5117% |
| 25 | p50 | 1.076,9253 ms | 711,6275 ms | -33,9204% |
| 25 | p95 | 1.734,9344 ms | 1.154,0085 ms | -33,4840% |
| 25 | p99 | 1.821,1465 ms | 1.305,3856 ms | -28,3207% |
| 50 | RPS | 41,5979 | 57,8139 | +38,9827% |
| 50 | p50 | 2.221,5076 ms | 1.669,5379 ms | -24,8466% |
| 50 | p95 | 4.284,3778 ms | 2.805,6529 ms | -34,5143% |
| 50 | p99 | 4.404,4391 ms | 3.074,9623 ms | -30,1849% |

Baseline measured PG maxima là `25/33/29` ở 25 clients và `32/32/31` ở
50 clients. Final giảm còn `20/23/21` và `23/20/20`; overall final maximum là
`23`. Không có pool timeout, database-connection error, request timeout hoặc
authorization error trong sáu final measured scenarios.

## Cache và correctness contract

Cache là process-local bounded LRU. Key gồm user authorization identity, site,
exact query enum, start date, end date và limit. Entry chỉ được tạo khi route
truyền authorization scope; direct adapter caller không có scope sẽ bypass cache.
Mỗi hit trả defensive row copies. Cache không lưu token, password hoặc query
label trong metrics. Runtime endpoint chỉ authenticated và chỉ trả aggregate
counts.

Invalidation là TTL-only: entry có thể stale tối đa khoảng 5 giây sau một write,
không có cross-worker invalidation. Đây là trade-off chấp nhận được cho read-only
analytics benchmark; cấu hình library mặc định vẫn cache off. Tests chứng minh
identity/site/TTL isolation, LRU bound, bypass thiếu auth scope và concurrency
peak không vượt slot bound. Live smoke so sánh byte-equivalent repeated response,
site 1/site 2 mỗi site trả đúng bốn ticket-SLA rows và không lẫn site ID.

## Resource observations

`docker stats` trong raw runner là snapshot ngay trước/sau scenario, không phải
time-series maximum. Baseline API memory nằm trong `349,9..393,4 MiB`; final nằm
trong `358,0..386,7 MiB`, cùng limit 1 GiB. CPU snapshots dao động
`0,39..15,97%` baseline và `0,39..20,58%` final; các điểm tức thời này quá nhiễu
để dùng làm throughput conclusion. PIDs có cùng range `38..86`.

Idle post-validation snapshot là API `0,48% / 314 MiB / 38 PIDs` và PostgreSQL
`0,00% / 411 MiB / 10 PIDs`; PostgreSQL vẫn có limit 2 GiB. Runner không ghi
time-series PostgreSQL CPU/memory, vì vậy kết luận resource chỉ dựa vào unchanged
limits, idle snapshot và connection samples 100 ms. Đây là limitation được giữ
rõ thay vì suy diễn peak không được đo.

## Acceptance

- Final có 900 total requests qua ba 25-client và ba 50-client scenarios, zero
  errors và zero timeouts.
- `261/261` 25-client và `513/513` 50-client analytics payloads là non-empty
  (`774/774` tổng cộng).
- 25-client RPS và p95 đều cải thiện, không chạm 10% degradation allowance.
- 50-client p95 giảm `34,5143%` và RPS tăng `38,9827%`, vượt cả hai material
  improvement thresholds.
- Overall PostgreSQL maximum `23 <= 27`.
- API contract, authentication, permission requirement và site isolation giữ
  nguyên.

Final run có variance đáng kể ở 25-client run 3; median vẫn vượt gate và cả ba
runs đều correctness-clean. Kết quả không đại diện WAN/TLS ingress, multi-host,
production writes, failover, cache coherence nhiều replicas hoặc production
SLA.

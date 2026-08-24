# Structured Maintenance Data vs RAG

## Quyết định kiến trúc

Hàng triệu operational/analytical work-order rows ở PostgreSQL; aggregations ở
dbt marts; Qdrant chỉ giữ chunks của tài liệu phi cấu trúc có lợi từ semantic
retrieval. Stage 9 không embed work-order fact, daily/monthly mart hoặc numerical
measure vào vector database.

```text
exact filters/counts/rates -> bounded SQL adapter -> PostgreSQL marts
manual/SOP/evidence text   -> RAG retrieval       -> Qdrant document chunks
combined technician view   -> application composes two typed results; no arbitrary SQL
```

| Câu hỏi/dữ liệu | Boundary đúng | Lý do |
|---|---|---|
| “Có bao nhiêu critical open work orders theo site?” | structured adapter / fact | Exact filter, group và count cần relational semantics. |
| “Workload của technician trong khoảng ngày?” | structured adapter / fact | UUID/date parameters và bounded aggregates. |
| “Completion rate theo tháng?” | `analytics_marts.monthly_site_work_orders` | dbt định nghĩa grain và metric; không dùng similarity để tính tỷ lệ. |
| “Cost variance?” | structured adapter với availability flag | Target không có canonical cost fields; kết quả phải nói unavailable/NULL, không bịa số. |
| “Quy trình lockout/tagout trong manual này?” | RAG | Cần semantic retrieval, document metadata, source/citation và safety gate. |
| “Resolution note nào giống triệu chứng này?” | RAG chỉ cho subset đã review và có provenance | Free text có thể hữu ích semantically; không index toàn bộ source table mặc định. |
| Work-order ID/status/due date cụ thể | parameterized application/SQL read | Exact lookup không cần vector retrieval. |
| Risk/anomaly score | canonical batch analytics | Đây là prioritization signal, không phải calibrated failure probability. |

## Structured analytics adapter

`src.analytics.maintenance_adapter.MaintenanceAnalyticsAdapter` là read-only
boundary độc lập với RAG. Caller chỉ chọn một trong bốn keys:

- `critical_open`
- `technician_workload`
- `monthly_completion`
- `cost_variance`

Adapter không nhận SQL text từ user/model. `site_id`, `start_date`, `end_date` và
`limit` được validate/bind; limit mặc định 100 và tối đa 500. Connection mở bằng
read-only transaction qua scale-specific `DataPlatformSettings`. Closed query
catalog chỉ đọc `analytics_warehouse` hoặc `analytics_marts`.

Đây là minimal internal adapter, chưa phải public conversational SQL tool. Nếu
được expose sau này, FastAPI/RBAC, resource scope, audit, timeout và response
schema vẫn phải được thiết kế/characterize riêng; model-generated arbitrary SQL
không được phép.

## RAG boundary

Canonical RAG tiếp tục phục vụ manuals, SOPs, checklists và approved technician
evidence có provenance. Retrieval phải giữ asset/document metadata filters,
relevance gate, source citations, conflict/safety handling và deterministic
fallback hiện có. QR, identity, authorization hoặc structured business state
không được chuyển thành vector authorization signal.

Không index các dataset sau vào Qdrant:

- toàn bộ `public.work_orders` hoặc `raw.work_orders`;
- fact/dimension/daily/monthly marts;
- user, ticket, audit, outbox hoặc inventory ledger rows;
- secrets, PII, attachment storage paths hoặc unrestricted notes;
- synthetic Stage 9 CSV chỉ để tăng vector corpus size.

Khi một approved free-text field như failure description/resolution evidence
được chọn cho RAG trong tương lai, ingestion cần explicit allow-list, access
scope, provenance, deletion/retention contract và bounded subset. Raw structured
row vẫn ở PostgreSQL.

## Combined experience và safety

Application có thể hiển thị structured metrics cạnh document guidance, nhưng
phải giữ provenance riêng:

- SQL result nêu query key, filters, reporting timezone và data freshness;
- RAG result nêu document sources/citations và applicability;
- không dùng citation của manual để “chứng minh” một count từ database;
- không dùng aggregate SQL để khẳng định một repair procedure an toàn;
- manager/technician xác minh hiện trường và quyết định cuối cùng.

Scale benchmark tắt external LLM/embedding calls và không index Qdrant. Điều này
đo Data Platform correctness/performance, không đo RAG relevance, generation
quality hay end-user impact.

## Cost và history limitations

Current target work order không có `estimated_cost`/`actual_cost` canonical.
Compatibility view giữ hai columns nullable để schema ổn định; fact/marts giữ
`NULL`, và cost adapter trả `cost_data_available` thay vì đổi missing thành zero.
Không công bố maintenance-cost reporting, savings hoặc ROI.

Target cũng không có dedicated work-order status history/event table. Raw
work-order versions cho biết snapshots mà incremental pipeline đã capture, nhưng
không đảm bảo mọi transition/event xảy ra giữa hai extracts. Không dùng raw
versions như audit trail thay thế application audit hoặc state machine history.

## Characterization tests

Tests dưới `tests/data_platform/` chứng minh:

- adapter query catalog đóng và reject near-match/arbitrary SQL;
- invalid UUID/date/limit/extra parameters bị reject trước connection;
- transaction read-only và result bound được giữ;
- adapter không import RAG, Qdrant, LLM hoặc embedding code;
- RAG modules không import structured aggregate adapter;
- structured SQL chỉ tham chiếu approved PostgreSQL analytics schemas.

Full validation có 42 Data Platform tests pass, và 1.1M structured rows được
reconcile mà không gọi RAG/LLM. Điều này không thay cho RAG quality hoặc human
evaluation. Xem integration mapping ở
[data-platform-integration.md](data-platform-integration.md) và scale procedure ở
[scale-test-1m.md](scale-test-1m.md).

## Stage 10 governed evidence update

Stage 10 thêm một deterministic question router: analytical intents được route
đến exact structured capability; semantic intents vẫn đi qua evidence policy.
Router không nhận hoặc sinh SQL.

`DomainAnalyticsAdapter` mở rộng structured catalog thành sáu capability:
maintenance summary, site reliability, ticket SLA, technician workload,
inventory consumption và maintenance cost variance. Date/UUID/limit đều được
validate/bind; response tối đa 200 rows và transaction read-only.

Local evidence export chỉ allow-list:

- manuals và SOPs;
- resolution summaries;
- technician notes;
- failure descriptions.

Export loại candidate marked sensitive/ineligible, email/phone-like content,
oversized text và duplicate fingerprint; giữ source ID/update time/provenance và
enforce maximum candidates. Run Stage 10 xuất 5 candidates trong bound 1.000,
SHA-256 `fdb722a7b3150e18a31a8b841587889c3576202f30a0b6db7c91ad71a9831da9`,
`embedding_calls=0`, `external_api_calls=0`.

Ticket, inventory, cost và status facts không được bulk vectorize. Synthetic free
text chỉ trở thành candidate sau allow-list nói trên; export local không đồng
nghĩa đã index Qdrant hoặc đã được duyệt cho production RAG.

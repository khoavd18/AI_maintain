# AI Maintenance Copilot

Nền tảng decision-support cho bảo trì thiết bị, kết hợp auditable asset lifecycle, ticket/SLA, preventive planning, standalone work orders, spare-parts stock control, Vietnamese batch analytics, explainable risk scoring và RAG retrieval trên SOP/checklist.

> Trạng thái: MVP đang chuyển sang internal pilot architecture. PostgreSQL đã là transactional source of truth, nhưng repository chưa production-ready và không thay thế CMMS/S-Maintain.

## Bài Toán

Facility Manager và technician thường phải tổng hợp thủ công thông tin từ asset register, ticket, maintenance log, operational readings và tài liệu hướng dẫn. AI Maintenance Copilot tạo một luồng thống nhất để:

- nhận diện asset có tín hiệu bất thường;
- xếp hạng thiết bị theo explainable risk score;
- giải thích nguyên nhân và hành động tham khảo bằng tiếng Việt;
- tìm SOP/checklist phù hợp và hiển thị nguồn cho technician.

Hệ thống là lớp hỗ trợ quyết định. Manager và technician chịu trách nhiệm xác minh dữ liệu, đánh giá điều kiện an toàn và đưa ra quyết định cuối cùng.

## Revised MVP Scope

MVP tập trung vào:

- thông tin asset cơ bản;
- hồ sơ kỹ thuật, location hierarchy, lifecycle, warranty, attachment và QR lookup có xác thực;
- ticket và maintenance history;
- preventive maintenance plan theo recurring interval có kiểm soát;
- standalone preventive/corrective/inspection work order, checklist execution, evidence, completion và independent verification;
- spare-part master, stock locations, immutable movements, work-order requirements/reservations, issue/consumption/return và low-stock visibility;
- operational data theo batch;
- anomaly detection và risk prioritization;
- recurring issue analysis và maintenance KPI ở mức mô tả;
- RAG retrieval cho SOP/checklist.

Synthetic data foundation hiện tập trung vào 27 assets thuộc HVAC, pump và generator, với 120 ngày operational readings theo giờ.

Không thuộc phạm vi:

- supplier, purchasing, purchase requisition hoặc purchase order;
- accounting/general ledger, maintenance-cost reporting hoặc inventory optimization;
- resident hoặc technician mobile app;
- vendor/contract management;
- complex approval workflow;
- real-time IoT streaming;
- SSO, MFA, external identity provider và enterprise IAM integration;
- hidden/distributed production scheduler hoặc startup work-order generation;
- exact failure-time prediction.

Chi tiết và tiêu chí thành công: [docs/mvp_scope.md](docs/mvp_scope.md).

## Current Features Và Future Work

Đã có implementation:

- deterministic Vietnamese synthetic data;
- CSV validation;
- daily asset-level feature engineering;
- rule-based signals kết hợp Isolation Forest scoring;
- explainable risk scoring và top risky assets;
- preventive maintenance status, recurring issue và maintenance KPI snapshots;
- PostgreSQL-backed FastAPI cho asset, ticket, preventive plan, checklist template, work order và maintenance-log transactions, giữ nguyên legacy API contracts;
- Alembic migrations, idempotent CSV seed import, optimistic concurrency và analytics snapshot export;
- local/internal-pilot authentication, RBAC và append-only PostgreSQL audit log;
- auditable asset registration, rich technical/warranty profile, hierarchical locations, lifecycle/operational transitions và archive/restore không phá lịch sử;
- attachment metadata trong PostgreSQL, bytes trong safe local storage, checksum-verified download và deterministic opaque QR lookup;
- deterministic preventive recurrence/generation, concurrency-safe work-order numbers, immutable checklist snapshots và auditable work-order state machine;
- corrective work order từ ticket không tự resolve incident; completion tạo đúng một MaintenanceLog và verification cập nhật asset dates;
- rich ticket intake với category/source/routing, backend `impact x urgency` priority, named lifecycle actions, server-side queues và append-only communication timeline;
- deterministic first-response/resolution SLA từ snapshotted business calendar/policy, idempotent escalation dry-run/execute qua API hoặc CLI;
- PostgreSQL spare-part master và stock locations; on-hand/reserved/available do backend quản lý bằng row locks và immutable movements;
- explicit work-order part requirements, reservation/replacement/release, issue, technician consumption, unused-part return, atomic transfer và controlled adjustment;
- low-stock/reorder visibility deterministic, protected inventory evidence và transaction-coupled audit, không tạo purchase order hoặc notification;
- Streamlit legacy development status page; protected product workflows dùng Next.js;
- Next.js authenticated frontend có ticket inbox/intake/detail/timeline, SLA/calendar/policy administration, escalation dashboard và ticket-to-maintenance workflow;
- Qdrant-based SOP/checklist retrieval với metadata filters và relevance gate;
- deterministic Maintenance Copilot response có sources, safety notice và safe fallback.

Các production concerns như SSO/MFA, distributed rate limiting, scheduler, centralized observability, managed secret storage và deployment hardening chưa thuộc internal pilot hiện tại.

## Canonical Architecture

Architecture là **PostgreSQL-primary cho transactional data** và **CSV batch-first cho analytics**.

```mermaid
flowchart LR
    Seed[Synthetic Vietnamese CSV seed] --> Import[Validate + idempotent import]
    Migration[Alembic migrations] --> DB[(PostgreSQL<br/>assets, tickets, plans, work orders,<br/>inventory, logs, identity, audit)]
    Import --> DB
    Files[(Local attachment storage<br/>single-node pilot)]
    DB <--> Service[Repositories + business services]
    Service <--> Files
    Service <--> API[FastAPI<br/>unchanged contracts]
    CLI[Explicit generation, escalation<br/>và inventory seed CLI] --> Service
    Service --> WO[Plan occurrence<br/>deterministic work order]
    API -->|public health only| Dashboard[Streamlit legacy status]
    API <--> Web[Next.js authenticated frontend]

    DB --> Snapshot[Validated analytics snapshot]
    Seed -->|readings + documents| Snapshot
    Snapshot --> Features[Daily features]
    Features --> Anomaly[Batch anomalies]
    Anomaly --> Risk[Explainable risk]
    Risk --> Processed[Processed CSV analytics]
    Processed --> Service

    Seed --> RAG[RAG indexing/retrieval]
    RAG --> Qdrant[(Qdrant)]
    Qdrant --> API
```

Canonical analytics implementations:

| Stage | Module | Output |
|---|---|---|
| Feature engineering | `src/features/build_features.py` | `data/processed/asset_daily_features.csv` |
| Anomaly detection | `src/models/anomaly_detection.py` | `data/processed/anomaly_results.csv` |
| Risk scoring | `src/risk/risk_scoring.py` | `data/processed/risk_scores.csv` |

FastAPI đọc transactional records qua repository/service layer và đọc latest processed CSV qua analytics service. Streamlit/Next.js chỉ gọi FastAPI. PostgreSQL unavailable làm API startup fail rõ ràng; normal product mode không fallback sang mutable CSV.

CSV vẫn dùng cho synthetic generation, seed/reset, database-to-analytics snapshot và batch artifacts. Qdrant chỉ phục vụ RAG. Xem [docs/architecture.md](docs/architecture.md).

## End-to-End User Story

1. Helpdesk intake sự cố với asset, category, impact và urgency; backend tính priority và snapshot SLA policy/calendar.
2. Manager dùng operational queues để tìm ticket critical, due-soon hoặc breached rồi assign support group/technician.
3. Technician acknowledge/start ticket, đọc timeline và Copilot checklist, hold/resume có lý do khi cần.
4. Chief Engineer lập part requirement; Storekeeper reserve rồi issue vật tư từ stock location hợp lệ. Reservation giảm available, còn issue mới giảm on-hand.
5. Technician ghi consumption rõ ràng; Storekeeper return phần chưa dùng. Work-order completion chỉ cảnh báo shortage/unresolved stock và không tự tạo movement.
6. Corrective work order và maintenance log ghi execution evidence độc lập; work-order completion/verification không tự resolve ticket.
7. Authorized actor resolve sau khi có maintenance log, close hoặc reopen bằng named action; comments, SLA, inventory và escalation history vẫn append-only.
8. Preventive generation và batch analytics chạy explicit; inventory transaction không tự thay Risk Score/KPI.
9. Con người xác minh thiết bị, an toàn và quyết định cuối cùng; Risk Score/SLA/reorder suggestion chỉ hỗ trợ prioritization.

Quy trình nghiệp vụ chi tiết: [docs/business_process.md](docs/business_process.md).

## Data Sources

Runtime transactional source:

- PostgreSQL `assets`;
- PostgreSQL `maintenance_tickets`;
- PostgreSQL `maintenance_logs`.
- PostgreSQL `spare_parts`, `stock_locations`, `inventory_positions` và immutable `inventory_movements`;
- PostgreSQL work-order part requirements, reservations, issues, consumptions và returns.

Canonical synthetic seed và batch sources:

- `data/raw/assets.csv`
- `data/raw/sensor_readings.csv`
- `data/raw/maintenance_tickets.csv`
- `data/raw/maintenance_logs.csv`
- `data/raw/documents.csv`

`src/database/export_snapshot.py` xuất PostgreSQL transactions và ghép generated readings/documents vào `data/analytics_input/` trước khi chạy batch. Tại boundary này, snapshot chuẩn hóa `next_maintenance_date` của asset/log theo legacy fixed interval để giữ nguyên validated analytics contract; lịch plan-derived thực tế vẫn nằm trong PostgreSQL plan/work order và không bị ghi đè.

Canonical processed outputs:

- `data/processed/asset_daily_features.csv`
- `data/processed/anomaly_results.csv`
- `data/processed/risk_scores.csv`
- `data/processed/preventive_maintenance_status.csv`
- `data/processed/recurring_issues.csv`
- `data/processed/maintenance_kpis.csv`

Default generation tạo 27 assets, 42 tickets, 86 logs và 120 ngày hourly readings. Generator không tạo raw risk result hoặc raw anomaly label; analytics output chỉ được tạo bởi canonical processed pipelines. Đây là synthetic demo data, không phải production dataset hoặc bằng chứng model accuracy.

Minimum field definitions: [docs/data_contract.md](docs/data_contract.md).

## Vietnamese Data Design

Code, module, column và API field dùng tiếng Anh. PostgreSQL lưu stable internal English enum codes; repository mapping trả business values và nội dung hiển thị bằng tiếng Việt.

Ví dụ:

- `asset_type`: `Máy lạnh`, `Máy bơm nước`, `Máy phát điện dự phòng`;
- `priority`: `Thấp`, `Trung bình`, `Cao`, `Khẩn cấp`;
- `risk_level`: `Thấp`, `Trung bình`, `Cao`, `Khẩn cấp`;
- `anomaly_type`: `Tăng điện năng bất thường`, `Độ rung tăng bất thường`.

## Feature Engineering

`src/features/build_features.py` tổng hợp daily asset-level features:

- energy, temperature, vibration và runtime aggregates;
- rolling 7-day baselines và delta signals;
- days since maintenance và days overdue;
- ticket counts trong 7/30 ngày;
- high-priority ticket counts;
- point-in-time unresolved ticket, recurring category và maintenance follow-up counts;
- asset age và criticality score.

Raw readings không còn chứa `pressure`. Feature pipeline tạm phát sinh `pressure = 0.0` để giữ compatibility với downstream anomaly/API contracts; đây không phải measurement mới.

## Anomaly Detection

`src/models/anomaly_detection.py` là implementation canonical. Nó kết hợp:

- rule-based signals để giải thích các pattern đã biết;
- Isolation Forest để bổ sung relative outlier score trong cùng asset type.

```text
anomaly_score = 70% rule_based_score + 30% isolation_forest_score
```

Trong implementation hiện tại, rule signals có vai trò chính trong quyết định `is_anomaly`; Isolation Forest chủ yếu điều chỉnh score và explanation. Đây là batch retrospective scoring, không phải real-time alerting.

Final flag dùng combined score threshold 60. Vì Isolation Forest chỉ đóng góp tối đa 30 điểm, nó không thể tự tạo final flag khi không có rule signal. Output bổ sung `anomalous_metrics` và Vietnamese contributing signals.

## Risk Scoring

`src/risk/risk_scoring.py` là implementation canonical.

```text
final_risk_score =
  20% anomaly_score
+ 25% maintenance_overdue_score
+ 20% unresolved_ticket_score
+ 10% recent_ticket_score
+  7.5% recurring_issue_score
+ 10% criticality_score
+  5% follow_up_score
+  2.5% runtime_score
```

Risk levels:

- `0-30`: `Thấp`
- `31-60`: `Trung bình`
- `61-80`: `Cao`
- `81-100`: `Khẩn cấp`

Risk score là heuristic prioritization score. Nó không phải calibrated failure probability và không dự đoán exact failure time.

Formula, component thresholds, preventive status, recurrence và KPI definitions: [docs/analytics.md](docs/analytics.md).

## Maintenance Reports

Canonical maintenance analytics cũng nằm trong `src/features/build_features.py`:

- preventive status phân loại `Quá hạn`, `Sắp đến hạn`, `Chưa đến hạn` và số ngày quá hạn;
- recurring issues group ticket theo `asset_id` + `failure_category`, với threshold cố định 3 occurrences;
- KPI snapshot mô tả ticket resolution, thời gian xử lý, preventive status, recurring groups, follow-up logs và high/critical risk assets.

Sau lần generate mặc định đã verify, outputs gồm 27 preventive rows, 25 asset/category recurring rows và 1 KPI snapshot. Đây là reporting trên synthetic data, không phải business-performance measurement.

## Authentication, RBAC Và Audit

Normal product mode yêu cầu đăng nhập. `POST /auth/login` trả access token ngắn hạn để Next.js giữ **trong memory**; refresh token ngẫu nhiên chỉ nằm trong `HttpOnly` cookie và được lưu ở PostgreSQL dưới dạng SHA-256 hash. Refresh rotation thu hồi session cũ, logout thu hồi active session, còn đổi mật khẩu hoặc vô hiệu hóa tài khoản thu hồi toàn bộ refresh sessions. Frontend không lưu token trong `localStorage`.

FastAPI kiểm tra permission ở server cho mọi route ngoại trừ `GET /health`. UI chỉ ẩn action không phù hợp để cải thiện trải nghiệm; đây không phải authorization boundary. Role và permission canonical nằm tại `src/security/permissions.py`, còn frontend nhận permission từ API thay vì duy trì một role matrix riêng.

| Role | Quyền chính trong milestone này |
|---|---|
| `administrator` | Toàn bộ permission; quản lý user và xem audit |
| `property_manager` | Ticket lifecycle/SLA/escalation oversight; quản lý asset; tạo/assign/verify WO; xem audit |
| `chief_engineer` | Assign/execute/resolve/reopen technical ticket; quản lý plan/checklist/generation và technical WO |
| `technician` | Acknowledge/execute/resolve ticket và WO được gán; internal comments/evidence; không assign, close hoặc tự verify |
| `helpdesk` | Intake/assign/acknowledge, requester communication, SLA read và escalation; không execute maintenance/resolve |
| `storekeeper` | Part/location master, receipt, reserve, issue, return, transfer, adjustment và inventory evidence |

Asset permissions bổ sung gồm `assets:create`, `assets:update`, `assets:change_status`, `assets:archive`, `assets:restore`; location và attachment có permission read/create/update/archive hoặc read/create/delete riêng. Property Manager quản lý lifecycle/location/archive, Chief Engineer quản lý hồ sơ kỹ thuật và attachments, Technician chỉ có operational-status update giới hạn. FastAPI vẫn là security boundary.

Mỗi business mutation thành công ghi audit event trong cùng PostgreSQL transaction. Audit state chỉ lấy field allow-list, không chứa password, token, cookie, Authorization header, reporter contact hoặc secret; trigger database chặn `UPDATE` và `DELETE`. Login failure và authorization denial chỉ lưu safe metadata. Xem [RBAC matrix](docs/rbac.md) và threat model tại [architecture](docs/architecture.md).

## FastAPI Contract

Existing endpoints được giữ nguyên:

- `GET /health`
- `GET /summary`
- `GET /assets/risk`
- `GET /assets/risk/top`
- `GET /assets/risk/{asset_id}`
- `GET /assets/anomalies`
- `GET /assets/anomalies/{asset_id}`
- `GET /assets/{asset_id}/context`
- `POST /copilot/ask`

Manager workflow endpoints:

- `GET /assets`
- `GET /assets/{asset_id}`
- `GET /assets/{asset_id}/details`
- `GET /maintenance/preventive`
- `GET /maintenance/recurring-issues`
- `GET /maintenance/kpis`
- `GET /tickets`
- `GET /maintenance/logs`
- `POST /tickets`
- `PATCH /tickets/{ticket_id}`
- `POST /maintenance/logs`

Rich ticket/SLA endpoints được thêm theo hướng additive; legacy `/tickets` contract ở trên vẫn giữ Vietnamese projection:

- `GET /ticketing/options`, `GET /ticketing/priority-preview`;
- `POST /tickets/intake`, `GET /ticket-queues/{queue_name}`, `GET /tickets/{ticket_id}`;
- `POST /tickets/{ticket_id}/assign|acknowledge|start|hold|resume|resolve|close|reopen|cancel`;
- `POST /tickets/{ticket_id}/priority|sla-policy`;
- `GET|POST /tickets/{ticket_id}/comments`;
- `GET|POST /ticketing/business-calendars`, `PATCH /ticketing/business-calendars/{calendar_id}`;
- `GET|POST /ticketing/sla-policies`, `PATCH /ticketing/sla-policies/{policy_id}`;
- `GET /ticketing/sla-summary`, `POST /ticketing/escalations/evaluate`.

Rich routes dùng code-level status, Vietnamese display labels, server-side filtering/pagination và `expected_version`. Priority chỉ do backend matrix tính; SLA state chỉ derive từ snapshot/timestamps. Escalation execute tạo idempotent event, không gửi notification hoặc tự đổi ticket. Xem [API reference](docs/api.md) và [Ticket Operations/SLA](docs/ticket_operations.md).

Asset lifecycle endpoints được thêm theo hướng additive; legacy `GET /assets` và asset analytics responses không đổi:

- `GET /assets/options`, `GET /assets/catalog`, `POST /assets`;
- `GET /assets/{asset_id}/profile`, `PATCH /assets/{asset_id}`;
- `POST /assets/{asset_id}/operational-status`;
- `POST /assets/{asset_id}/lifecycle-transition`;
- `POST /assets/{asset_id}/archive`, `POST /assets/{asset_id}/restore`;
- `GET /assets/{asset_id}/history`, `GET /assets/{asset_id}/qr`;
- `GET /asset-lookup/{lookup_token}`;
- `GET /locations`, `POST /locations`, `PATCH /locations/{location_id}`, `POST /locations/{location_id}/archive`;
- `GET|POST /assets/{asset_id}/attachments`;
- `GET|DELETE /assets/{asset_id}/attachments/{attachment_id}`.

Identity và administration endpoints được thêm theo hướng additive:

- `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`;
- `GET /auth/me`, `POST /auth/change-password`;
- `GET /users`, `POST /users`, `PATCH /users/{user_id}`;
- `GET /users/roles`;
- `GET /audit-logs` với filters và pagination metadata.

Preventive maintenance và work-order endpoints được thêm theo hướng additive:

- `GET|POST /maintenance-plans`, `GET|PATCH /maintenance-plans/{plan_id}`;
- `POST /maintenance-plans/{plan_id}/pause|resume|archive`;
- `GET /maintenance-plans/{plan_id}/occurrences`;
- `POST /maintenance-plans/generate/dry-run`, `POST /maintenance-plans/generate`;
- `GET|POST /checklist-templates`, `GET /checklist-templates/{template_id}`;
- `POST /checklist-templates/{template_id}/versions|archive`;
- `GET|POST /work-orders`, `GET|PATCH /work-orders/{work_order_id}`;
- `POST /work-orders/{work_order_id}/assign|transition|checklist|complete|verify|cancel|reopen`;
- `GET|POST /tickets/{ticket_id}/work-orders`;
- `GET|POST /work-orders/{work_order_id}/attachments`, `GET|DELETE /work-orders/{work_order_id}/attachments/{attachment_id}`;
- `GET /work-orders/calendar`, `GET /work-orders/metrics`, `GET /maintenance/options`.

Plan/work-order list endpoints có pagination và filters. Missing resource trả `404`; invalid transition, duplicate active corrective WO hoặc stale version trả `409`; request field invalid trả `422`. Overdue là derived field. Generation dry-run không write; real generation lock plan và dùng unique `(preventive_plan_id, due_date)` để retry/concurrent call không tạo duplicate.

Spare-parts inventory endpoints được thêm additive, không đổi PM1-PM5 contracts:

- `GET|POST /part-categories`, `GET|POST /units-of-measure`;
- `GET|POST /parts`, `GET|PATCH /parts/{part_id}`, `GET /parts/{part_id}/history`;
- `POST /parts/{part_id}/activate|deactivate|archive|restore`;
- `GET|POST /stock-locations`, `PATCH /stock-locations/{location_id}`;
- `POST /stock-locations/{location_id}/activate|deactivate|archive|restore`;
- `POST /parts/{part_id}/reorder-configurations`;
- `GET /inventory/balances|low-stock|movements|metrics|reservations`;
- `POST /inventory/opening-balances|receipts|transfers|adjustments`;
- `GET|POST /work-orders/{work_order_id}/part-requirements`;
- `POST /work-order-part-requirements/{requirement_id}/reservations`;
- `POST /stock-reservations/{reservation_id}/release|expire|replace`;
- `GET /work-orders/{work_order_id}/parts`, `POST /work-orders/{work_order_id}/part-issues`;
- `POST /part-issues/{issue_id}/consumptions|returns`;
- protected inventory movement attachment endpoints.

Stock-changing requests yêu cầu caller-stable `Idempotency-Key`. Server lock inventory positions, reject negative stock/oversubscription, commit transfer-out và transfer-in cùng transaction, và derive `available = on_hand - reserved`. Movement history không có update/delete API và được bảo vệ bằng PostgreSQL trigger.

`GET /health` là public. Tất cả route business còn lại cần Bearer access token và permission phù hợp. `/docs`, `/redoc` và OpenAPI schema chỉ được bật ở `development`/`test`.

Các list endpoint hỗ trợ filters theo data contract. `/assets/{asset_id}/details` gom asset profile, latest risk, preventive status, risk history, anomaly, ticket, log và recurring issues mà không thay đổi RAG logic.

Legacy write endpoints giữ nguyên request/response contract. New planning routes dùng explicit schemas và PostgreSQL transactions. Work-order completion tạo đúng một linked MaintenanceLog; verification bởi actor khác cập nhật asset maintenance dates. Creating/completing/verifying WO không resolve ticket và không chạy lại analytics ngay.

Ví dụ:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{"identifier":"manager.demo","password":"<DEMO_PASSWORD>"}'

# Lấy access_token từ response login và chỉ giữ trong memory của client.
curl http://localhost:8000/summary -H "Authorization: Bearer <ACCESS_TOKEN>"
curl "http://localhost:8000/assets/risk/top?limit=5" -H "Authorization: Bearer <ACCESS_TOKEN>"
curl http://localhost:8000/assets/GENERATOR_002/details -H "Authorization: Bearer <ACCESS_TOKEN>"
```

Tạo và nhận inspection ticket:

```bash
curl -X POST http://localhost:8000/tickets \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"asset_id":"GENERATOR_002","issue_description":"Kiểm tra khả năng khởi động theo tín hiệu risk batch.","priority":"Cao","failure_category":"Lỗi điện","technician_id":"TECH_001","manager_note":"Ưu tiên kiểm tra trong tuần."}'

curl -X PATCH http://localhost:8000/tickets/TCK-000043 \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"status":"Đang xử lý","technician_id":"TECH_002","note":"Đã nhận kiểm tra."}'
```

`ticket_id` trong ví dụ update phụ thuộc dữ liệu hiện tại; dùng ID trả về từ `POST /tickets`.

Sau kiểm tra, ghi log rồi resolve ticket khi kết quả không cần follow-up:

```bash
curl -X POST http://localhost:8000/maintenance/logs \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"ticket_id":"TCK-000043","asset_id":"GENERATOR_002","maintenance_date":"2026-07-18","inspection_result":"Ắc quy yếu, đầu cực oxy hóa.","actions_taken":"Vệ sinh đầu cực và kiểm tra điện áp.","parts_replaced":"Không thay vật tư","technician_note":"Đã chạy thử tại chỗ.","maintenance_result":"Đã xử lý","follow_up_required":false,"next_maintenance_date":"2026-11-15"}'

curl -X PATCH http://localhost:8000/tickets/TCK-000043 \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"status":"Đã xử lý","note":"Đã hoàn tất kiểm tra."}'
```

`next_maintenance_date` phải bằng ngày thực hiện cộng maintenance interval của asset. API không tự recalculation risk/KPI sau các request này.

Preview/generate preventive work order bằng actor có `maintenance_generation:run`:

```bash
curl "http://localhost:8000/maintenance-plans/<PLAN_ID>/occurrences?date_from=2026-07-20&date_to=2026-10-20" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"

curl -X POST http://localhost:8000/maintenance-plans/generate/dry-run \
  -H "Authorization: Bearer <ACCESS_TOKEN>" -H "Content-Type: application/json" \
  -d '{"as_of_date":"2026-07-20","plan_id":"<PLAN_ID>"}'

curl -X POST http://localhost:8000/maintenance-plans/generate \
  -H "Authorization: Bearer <ACCESS_TOKEN>" -H "Content-Type: application/json" \
  -d '{"as_of_date":"2026-07-20","plan_id":"<PLAN_ID>"}'
```

Technician dùng action endpoints theo `expected_version`; completion gửi một maintenance outcome và backend tạo log, frontend không gửi record thứ hai. Reviewer khác technician gọi `POST /work-orders/{id}/verify`. Exact request schemas có tại local `/docs` trong development.

Copilot request:

```bash
curl -X POST http://localhost:8000/copilot/ask \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"question":"Vì sao GENERATOR_002 đang rủi ro cao?","asset_id":"GENERATOR_002","top_k":5}'
```

Request giữ `question`, optional `asset_id` và `top_k`; có thể thêm optional `document_type` hoặc `failure_category`. Response vẫn giữ `answer`, `asset_context`, `sources`, `retrieved_chunks` và bổ sung `retrieval_status`, `relevance_status`, `safety_notice`, `filters_applied`.

## Streamlit Dashboard

Streamlit được giữ làm **legacy development client** theo strategy B. App chỉ gọi public `/health`, hiển thị trạng thái API và hướng người dùng sang Next.js; mọi protected analytics/write/Copilot workflow đã bị vô hiệu hóa. Không có hidden compatibility route hoặc auth bypass.

## Next.js Frontend

`frontend/` cung cấp authenticated operational frontend. Product Milestone 6 bổ sung:

- `/inventory` overview/metrics, `/inventory/stock`, `/inventory/low-stock`, `/inventory/movements` và `/inventory/reservations`;
- `/inventory/parts` và `/inventory/parts/[partId]` cho catalogue, lifecycle, balance và history;
- `/inventory/receiving`, `/inventory/transfers`, `/inventory/adjustments` và `/inventory/settings` cho named stock actions;
- work-order parts panel cho requirement, reserve/replace/release, issue, explicit consumption và return theo permission.

Product Milestone 5 surfaces vẫn giữ:

- `/tickets` cho chín operational queues, filters, pagination và SLA summary;
- `/tickets/new` cho rich intake với server-authoritative priority preview;
- `/tickets/[ticketId]` cho facts/PII redaction, named actions, comments, SLA/timeline và corrective work orders;
- `/admin/sla` cho versioned business calendar và effective SLA policy administration;
- `/admin/escalations` cho SLA KPIs, escalation dry-run và permission-controlled execute.

Các Product Milestone 4 surfaces vẫn giữ:

- `/maintenance/plans`, `/maintenance/plans/new`, `/maintenance/plans/[planId]` cho recurrence, occurrence preview, lifecycle và explicit generation;
- `/maintenance/checklists` cho immutable template versions và safety-critical steps;
- `/work-orders`, `/work-orders/[workOrderId]` cho filters, assignment, execution, checklist, evidence, completion, verification/cancel/reopen;
- `/work-orders/calendar` cho bounded schedule projection, không phải scheduling source thứ hai;
- ticket detail hiển thị linked corrective work orders; overview có additive PostgreSQL work-order metrics.

Technician controls được xếp dọc ở mobile width; server vẫn enforce ownership. `/scan/assets/[lookupToken]` là web route tối ưu cho mobile, không phải native app và vẫn yêu cầu đăng nhập.

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

Mặc định `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`. Next.js có login, session restoration, permission-aware navigation/actions, user management và audit views. Access token chỉ ở memory; API client thực hiện đúng một refresh/retry khi gặp eligible `401`. Sau logout, Query cache và auth memory được xóa. Existing asset, ticket, maintenance và Copilot contracts không đổi. Chi tiết: [frontend/README.md](frontend/README.md).

## RAG Maintenance Copilot

Current RAG workflow:

1. Đọc `data/raw/documents.csv`.
2. Chuẩn hóa legacy CSV fields thành `document_id`, `document_type`, `content`, `failure_category`, `version` và `effective_date`.
3. Chunk nội dung theo section marker và giữ đầy đủ source metadata cùng `chunk_index`.
4. Tạo local sentence-transformers embeddings với E5-style prefixes.
5. Thay thế toàn bộ Qdrant collection `maintenance_knowledge` và upsert stable chunk IDs.
6. Retrieve top-k chunks với `asset_type` filter; `document_type` và `failure_category` là optional filters.
7. Loại chunk dưới relevance threshold và chỉ compose answer khi còn nguồn đủ liên quan.
8. Kết hợp retrieved guidance với structured asset/ticket facts từ PostgreSQL và latest batch analytics.
9. Tạo deterministic Vietnamese response với năm phần: tình trạng, checklist, nguồn, an toàn và giới hạn.

Document coverage hiện tại:

| Asset type | Preventive document | Troubleshooting document |
|---|---|---|
| HVAC | Checklist kiểm tra định kỳ máy lạnh | Máy lạnh không làm mát |
| Pump | Checklist kiểm tra định kỳ máy bơm | Rung hoặc tiếng ồn bất thường |
| Generator | Checklist kiểm tra định kỳ máy phát | Không khởi động |

Default source set có 6 documents và tạo 30 chunks với cấu hình `max_chars=800`, `overlap=80`. `python -m src.rag.index_documents` luôn rebuild collection, vì vậy chạy lại cùng input không tạo duplicate và tài liệu bị xóa/đổi không để stale chunk active.

Relevance threshold là retrieval gate, không phải xác suất đúng:

- deterministic `HashEmbeddingProvider` trong unit tests: `0.15`;
- local `SentenceTransformerEmbeddingProvider`: `0.55`.

Khi kết quả rỗng, dưới threshold, câu hỏi ngoài phạm vi hoặc Qdrant unavailable, Copilot trả safe fallback và không tạo checklist từ unrelated chunks. API health và ba dashboard workflow còn lại không phụ thuộc Qdrant.

Copilot không sử dụng paid API và hiện không có generative LLM. Đây không phải automatic diagnostic system. Anomaly/Risk Score không chứng minh failure; manager/technician phải xác minh thiết bị và ưu tiên manual nhà sản xuất cùng quy trình an toàn tòa nhà.

Ví dụ câu hỏi trong phạm vi:

- `Thiết bị này cần kiểm tra gì trước?` khi đã chọn asset;
- `Máy bơm rung bất thường thì kiểm tra những bước nào?`;
- `Máy phát điện không khởi động thì tham khảo checklist nào?`;
- `SOP bảo trì định kỳ cho HVAC là gì?`.

## Setup

Yêu cầu: Python 3.11+, Docker và Node.js cho Next.js frontend.

Dependency groups:

| Nhóm | Vai trò |
|---|---|
| Core | FastAPI, Streamlit, batch analytics, SQLAlchemy, psycopg, Alembic và Qdrant client |
| `rag` | `sentence-transformers` cho multilingual E5 embeddings |
| `dev` | pytest và Ruff |
| `postgres` | Compatibility extra rỗng; PostgreSQL dependencies nay thuộc Core |

Canonical full-repository install giữ tên extras cũ để command tương thích. PostgreSQL là prerequisite của normal product demo; Qdrant chỉ là prerequisite của Copilot retrieval.

Configuration có sensible local defaults. Có thể tạo local `.env` bằng:

```powershell
Copy-Item .env.example .env
```

Các biến hữu ích:

| Variable | Default | Dùng cho |
|---|---|---|
| `APP_NAME` | `AI Maintenance Copilot` | FastAPI title |
| `APP_ENVIRONMENT` | `development` | Bật local docs và áp dụng security validation theo môi trường |
| `API_BASE_URL` | `http://localhost:8000` | Streamlit gọi FastAPI |
| `CORS_ALLOWED_ORIGINS` | hai local Next.js origins | Explicit browser origins với credentials |
| `TRUSTED_HOSTS` | local host names | Host header allow-list |
| `TOKEN_SIGNING_SECRET` | rỗng ở local | Ephemeral ở dev/test; bắt buộc secret >=32 ký tự ở pilot/production |
| `ACCESS_TOKEN_LIFETIME_MINUTES` | `15` | JWT access lifetime |
| `REFRESH_SESSION_LIFETIME_DAYS` | `7` | Revocable refresh-session lifetime |
| `AUTH_COOKIE_SECURE` | `false` ở local | Bắt buộc `true` ngoài dev/test và cần HTTPS |
| `AUTH_COOKIE_SAMESITE` | `lax` | Explicit refresh/CSRF cookie policy |
| `LOGIN_RATE_LIMIT_ATTEMPTS` | `5` | Basic per-process failed-login threshold |
| `STORAGE_BACKEND` | `postgresql` | Normal runtime; `csv` chỉ explicit fixture mode |
| `DATABASE_URL` | local PostgreSQL URL | Transactional source of truth |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | `5` | Startup connection timeout |
| `TEST_DATABASE_URL` | local database kết thúc `_test` | Isolated integration tests |
| `ATTACHMENT_STORAGE_BACKEND` | `local` | Storage abstraction; chỉ local implementation trong milestone này |
| `ATTACHMENT_STORAGE_ROOT` | `data/attachments` | Private local file root, không được serve trực tiếp |
| `ATTACHMENT_MAX_SIZE_BYTES` | `10485760` | Giới hạn mỗi PDF/PNG/JPG/JPEG |
| `FRONTEND_BASE_URL` | `http://localhost:3000` | Origin dùng để tạo opaque QR lookup URL |
| `QDRANT_URL` | `http://localhost:6333` | RAG indexing/retrieval |
| `QDRANT_HTTP_PORT` | `6333` | Local Docker host port cho Qdrant REST |
| `QDRANT_COLLECTION` | `maintenance_knowledge` | Qdrant collection |
| `EMBEDDING_MODEL_NAME` | `intfloat/multilingual-e5-small` | Local embeddings |

Các PostgreSQL credentials trong `.env.example` chỉ là local Docker defaults, không phải production secrets. `TOKEN_SIGNING_SECRET` cố ý để rỗng; không được dùng ephemeral dev secret cho pilot. File `.env` được gitignore.

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,rag,postgres]"
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,rag,postgres]"
```

## Windows PowerShell Quickstart

PowerShell không cần `make`:

```powershell
docker compose up -d postgres qdrant
python -m src.data_generation.generate_data
python -m src.ingestion.validation
python -m alembic upgrade head
python -m src.ingestion.load_data --dry-run
python -m src.ingestion.load_data
python -m src.database.export_snapshot --replace
python -m src.features.build_features --input-dir data/analytics_input
python -m src.models.anomaly_detection
python -m src.risk.risk_scoring
python -m src.features.build_features --input-dir data/analytics_input --analysis maintenance
python -m src.rag.index_documents
```

Importer từ chối database không rỗng. Chỉ dùng `python -m src.ingestion.load_data --replace` khi chủ động reset transactional demo data về canonical seed.

Tạo administrator đầu tiên bằng interactive password prompt; lệnh không in mật khẩu và từ chối normalized username/email bị trùng:

```powershell
python -m src.security.cli create-admin --username admin.local --display-name "Quản trị viên local"
```

Demo roles chỉ được tạo bằng lệnh explicit khi `APP_ENVIRONMENT=development`:

```powershell
python -m src.security.cli seed-demo-users
```

Seed checklist/plan đại diện và preview/generate work order bằng các user đã tồn tại. Lệnh idempotent, không tạo account/password và không chạy ở startup:

```powershell
python -m src.maintenance_management.cli seed-development
python -m src.maintenance_management.cli generate --dry-run --as-of 2026-07-20
python -m src.maintenance_management.cli generate --as-of 2026-07-20
```

Thay `--as-of` bằng business date dùng cho demo. Có thể thêm `--plan-id <UUID>`; rerun real generation trả skipped và không tạo duplicate occurrence.

Seed ticket reference/SLA defaults rồi preview hoặc ghi escalation bằng actor có permission:

```powershell
python -m src.ticket_management.cli seed-defaults
python -m src.ticket_management.cli evaluate-escalations --dry-run
python -m src.ticket_management.cli evaluate-escalations
```

Không lệnh nào chạy tự động khi API startup; escalation không gửi email/SMS.

Seed inventory demo sau khi đã có demo users và work orders:

```powershell
python -m src.inventory_management.cli seed-development
```

Lệnh tạo deterministic 6 categories, 3 UOM, 5 stock locations và 8 HVAC/pump/generator parts, rồi reconcile opening balances và selected work-order reservations qua named service actions. Chạy lại không tạo duplicate movement, requirement hoặc reservation.

Terminal API:

```powershell
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

Terminal Next.js:

```powershell
Set-Location frontend
Copy-Item .env.example .env.local -ErrorAction SilentlyContinue
npm install
npm run dev
```

Đăng nhập tại `http://localhost:3000/login`. Streamlit chỉ còn là optional legacy health/status page và không cung cấp protected workflows.

Verify:

```powershell
Invoke-RestMethod http://localhost:8000/health
$loginBody = @{ identifier = "manager.demo"; password = "<DEMO_PASSWORD>" } | ConvertTo-Json
$login = Invoke-RestMethod http://localhost:8000/auth/login `
  -Method Post -ContentType "application/json" -Body $loginBody -SessionVariable BrowserSession
$headers = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod http://localhost:8000/auth/me -Headers $headers
Invoke-RestMethod http://localhost:8000/summary -Headers $headers
```

Stop API/frontend bằng `Ctrl+C`, sau đó:

```powershell
docker compose stop
```

Equivalent Make targets: `services-up`, `postgres-up`, `migrate-db`, `generate-data`, `validate-data`, `load-data`, `replace-data`, `seed-maintenance`, `seed-inventory`, `generation-dry-run`, `generate-work-orders`, `seed-ticketing`, `escalation-dry-run`, `evaluate-escalations`, `export-analytics-snapshot`, `build-features`, `detect-anomalies`, `score-risk`, `build-preventive`, `build-recurring`, `build-kpis`, `index-documents`, `bootstrap-admin`, `seed-demo-users`, `run-api`, `run-dashboard`, `run-frontend`, `create-test-db`, `test`, `test-postgres`, `lint`, `frontend-lint`, `frontend-test` và `frontend-build`.

Demo 10–12 phút: [docs/demo_script.md](docs/demo_script.md).

## PostgreSQL Operations

Schema chỉ được quản lý bằng Alembic:

```powershell
docker compose up -d postgres
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

Dry-run và first import:

```powershell
python -m src.ingestion.load_data --dry-run
python -m src.ingestion.load_data
```

Explicit canonical reset sau khi đã backup dữ liệu cần giữ:

```powershell
python -m src.ingestion.load_data --replace
```

`--replace` xóa PM4-PM6 development plans/templates/work orders, ticket/SLA extensions, inventory data và evidence metadata trước khi khôi phục canonical `27/42/86`; private attachment backup/cleanup vẫn là trách nhiệm operator. Chạy lại các explicit seed commands sau reset nếu cần product demo data.

Dedicated test database:

```powershell
python -m src.database.create_test_database
$env:TEST_DATABASE_URL = "postgresql+psycopg://maintenance:maintenance@localhost:5432/maintenance_copilot_test"
python -m pytest -m postgres
```

Tests từ chối database name không kết thúc `_test` và không mutate developer/demo database.

## Verification

```powershell
python -m pytest
python -m ruff check .
```

Lần verify Milestone 4.5 ngày 2026-07-15: `122 passed`, Ruff và `git diff --check` đều đạt. Streamlit AppTest và live health smoke đạt; OpenAPI có đủ ba write methods. Manual `GENERATOR_002` workflow trên isolated CSV copies đã tạo/assign/resolve ticket, ghi log, qua full raw validation, mở Copilot checklist có nguồn và xác nhận risk/KPI không đổi trước batch tiếp theo. Còn một `StarletteDeprecationWarning` chỉ thuộc test client, được giải thích trong [troubleshooting](docs/troubleshooting.md). Các kết quả này xác nhận tính tái lập của portfolio demo, không chứng minh production readiness hoặc model accuracy.

Lần verify Frontend Milestone 3 ngày 2026-07-16: backend `125 passed`, frontend `43 passed`, Ruff, ESLint, Next.js production build và `git diff --check` đều đạt. Live workflow trên temporary CSV tạo `TCK-000043`, `LOG-000087`, đi qua assignment, `Đang xử lý`, maintenance result có follow-up và resolve; ticket/log xuất hiện đúng một lần, asset detail được refresh, còn risk/KPI không đổi. Sau test, canonical files vẫn giữ 27 assets, 42 tickets, 86 maintenance logs và 77.760 sensor readings.

Lần verify Frontend Milestone 4 ngày 2026-07-16: backend `125 passed`, frontend `61 passed`, focused RAG/API tests `20 passed`; Ruff, ESLint, Next.js production build, Markdown link check và `git diff --check` đều đạt. Live `GENERATOR_002` asset/ticket handoff retrieve đúng source máy phát điện với `retrieval_status=success`, sources và safety notice. Unrelated question trả zero-source fallback; khi dừng Qdrant, Copilot trả `unavailable` trong khi API/analytics/assets vẫn hoạt động, sau đó retry thành công khi Qdrant được khởi động lại. Desktop 1440px và mobile 390px route checks không có horizontal clipping. Canonical CSV counts và SHA-256 được kiểm tra, không có data file nào thay đổi trong Git worktree. Các kết quả này xác nhận demo workflow, không phải production readiness hoặc RAG accuracy.

Lần verify Product Milestone 1 ngày 2026-07-18: clean Alembic downgrade/upgrade đạt revision `20260718_0001`; CSV import dry-run và import thật xác nhận `27` assets, `42` tickets, `86` maintenance logs; analytics snapshot xác nhận thêm `77.760` readings và `6` documents. PostgreSQL-focused suite đạt `15 passed`, full backend đạt `140 passed`, Streamlit AppTest đạt `1 passed`, frontend đạt `61 passed`; Ruff, ESLint, Next.js production build, Alembic schema check, Markdown link check và `git diff --check` đều đạt. Concurrency, FK, status transition, log-before-resolution, atomic rollback và optimistic conflict đều có integration test trên isolated `_test` database. Restart container giữ nguyên migration revision và row counts. Live `GENERATOR_002` workflow tạo `TCK-000043` và `LOG-000087`, resolve ticket, giữ batch risk/KPI chưa đổi và Copilot trả một grounded source với safety notice; toàn bộ existing Next.js routes trả `200`. Đây là kết quả local internal-pilot verification, không phải bằng chứng production readiness, model accuracy hoặc business impact.

Lần verify Product Milestone 2 ngày 2026-07-18: clean Alembic downgrade/upgrade đạt revision `20260718_0002` và `alembic check` không có schema drift; explicit admin bootstrap và năm development roles thành công trên isolated `_test` database. Full backend đạt `156 passed`, frontend đạt `74 passed`; Ruff, ESLint, Next.js production build, Markdown link check, secret scan và `git diff --check` đều đạt. Live role workflow tạo `TCK-000043`, manager gán `TECH_002`, technician ghi `LOG-000087`, manager resolve; helpdesk/technician forbidden actions trả `403`, unauthenticated/revoked access trả `401`, Copilot vẫn trả response. Audit có đủ ticket/log/user actions, không lộ credential fields và database trigger từ chối sửa event. PostgreSQL restart giữ revision, 27 assets, 43 tickets, 87 logs, 5 users và 24 audit events. Đây là local internal-pilot security verification, không phải production security certification.

Lần verify Product Milestone 3 ngày 2026-07-18: clean Alembic downgrade/upgrade đạt revision `20260718_0003`, `alembic check` không có schema drift; seed dry-run/import giữ `27/42/86` và tạo 7 deterministic locations. Full PostgreSQL-enabled backend đạt `162 passed`, frontend đạt `80 passed`; Ruff, ESLint và Next.js production build đều đạt. Temporary analytics snapshot giữ đúng 10 legacy asset columns và tạo `3.240` feature/anomaly/risk rows cùng `27/25/1` maintenance reports. Live role workflow tạo `PM3_DEMO_ASSET`, upload/download một checksum-matched technical manual, archive/restore, xác nhận archived QR trả `410`, technician/helpdesk forbidden actions trả `403`, rồi tạo `TCK-000043` và `LOG-000087`. PostgreSQL restart giữ revision cùng `28` assets, `43` tickets, `87` logs, một active attachment và `29` audit events. Next.js login/assets/detail/QR/tickets/Copilot routes trả `200`. Đây là local internal-pilot verification, không phải production readiness, security certification hoặc business-impact evidence.

Lần verify Product Milestone 5 ngày 2026-07-23: isolated PostgreSQL clean downgrade/upgrade đạt revision `20260723_0005`, `alembic check` không có model drift; canonical import dry-run/import xác nhận `27/42/86`, còn PM4 maintenance regression đạt `10 passed`. PM5 focused backend đạt `28 passed`, full backend đạt `210 passed`, frontend đạt `95 passed` trên 14 files; Ruff, ESLint và Next.js production build 20 routes đều đạt. Live role workflow tạo critical `TCK-000044` và corrective `WO-000002`: Helpdesk intake/route, Technician acknowledge/start/hold/resume/comment/complete work order, ticket vẫn `in_progress` sau work-order completion, explicit resolve, Manager verify/close/reopen và escalation execute idempotent. PostgreSQL restart giữ ticket `reopened`, SLA occurrence 2, 2 comments, 11 SLA events, one ticket escalation, verified work order và counts `27/44/87`. OpenAPI có 91 paths, protected smoke trả `401`, 12 existing/new Next.js routes trả `200`, Markdown links và `git diff --check` đạt. Đây là local verification trên synthetic data, không phải production, security, SLA-performance hoặc business-impact certification.

Lần verify Product Milestone 6 ngày 2026-07-23: isolated PostgreSQL downgrade-to-base/clean upgrade đạt revision `20260723_0006`, `alembic check` không có model drift; canonical import vẫn đúng `27/42/86`. PM4 seed tạo 3 plans/4 work orders; PM6 seed tạo 6 categories, 3 UOM, 5 stock locations, 8 parts, 8 opening positions, 3 requirements và 3 reservations, còn lần chạy thứ hai không tạo duplicate. Focused PM6 đạt `14 passed`, PM4 regression đạt `10 passed`, PM5 ticket/SLA regression đạt `28 passed`; full backend đạt `224 passed`, frontend đạt `106 passed` trên 16 files. Ruff, ESLint và Next.js production build 30 pages đều đạt. Live workflow xác nhận admin lifecycle audit; Storekeeper receipt idempotent, atomic transfer, adjustment, issue và return; assigned Technician ghi consumption riêng; Helpdesk adjustment và Technician receipt đều trả `403`. PostgreSQL restart giữ revision, `27/42/86`, 4 work orders, 8 parts, 14 movements, 3 reservations, 1 issue, 1 consumption và 1 return. OpenAPI có 128 paths, 33 Next.js routes trả `200`; snapshot batch tạo `3.240/3.240/3.240` feature/anomaly/risk rows cùng `27/25/1` maintenance reports mà không đổi canonical output hashes. Đây vẫn chỉ là local verification trên synthetic data, không phải production, security, stock-accuracy hoặc business-impact certification.

## Limitations

- Synthetic data chưa được kiểm chứng bằng maintenance history thực tế.
- Analytics thresholds và risk weights là transparent demo heuristics, chưa được hiệu chuẩn trên dữ liệu thực tế.
- Synthetic chronology chỉ mô phỏng quy trình đơn giản và chưa được đối chiếu với quy tắc lịch bảo trì thực tế của một cơ sở cụ thể.
- API phục vụ PostgreSQL transactions cùng processed CSV analytics, chưa có scheduler hoặc production cache invalidation strategy.
- Preventive generation chỉ chạy qua explicit API/CLI; chưa có production scheduler, distributed worker, notification hoặc missed-run operations.
- SLA/escalation evaluation cũng chạy explicit qua API/CLI; chưa có background evaluator hoặc notification delivery.
- Recurrence chỉ hỗ trợ bounded interval day/week/month/year. Chưa có calendar exceptions, holiday rules hoặc arbitrary RRULE.
- Legacy asset `next_maintenance_date` là compatibility aggregate từ active plans; plan-specific dates và calendar mới là operational detail.
- Analytics snapshot cố ý project maintenance dates về fixed-interval legacy contract. Vì vậy preventive plan/work-order calendar là operational source cho scheduling, còn batch preventive KPI hiện vẫn phản ánh contract cũ.
- Reopen một completed-but-unverified work order giữ append-only linked MaintenanceLog và không tạo log thứ hai; chưa có full record-amendment/countersign workflow.
- Isolation Forest và risk formula chưa được đánh giá trên labeled failure outcomes.
- Copilot có relevance threshold minh bạch nhưng chưa có labeled retrieval evaluation dataset hoặc hiệu chuẩn trên tài liệu thực tế.
- Sáu SOP/checklist là synthetic/illustrative và không thay thế tài liệu nhà sản xuất.
- Deterministic composer là extractive decision support, không phải diagnosis hoặc generative reasoning.
- Next.js là authenticated internal-pilot workflow, chưa có production caching, accessibility audit hoặc browser-level regression suite; Streamlit chỉ còn legacy status client.
- PostgreSQL workflow có transactions, foreign keys, sequences, optimistic conflict detection và append-only audit events nhưng chưa có load test hoặc production operations hardening.
- Attachment bytes dùng atomic local storage cho single-node pilot; chưa có S3-compatible implementation, malware scanning, object versioning hoặc distributed transaction giữa file store và PostgreSQL.
- QR là lookup identifier có xác thực, không phải access-control credential; chưa có fleet label operations, camera-scanner test matrix hoặc offline workflow.
- Ticket/log mới không làm risk hoặc KPI đổi ngay; cần chạy lại canonical batch pipeline.
- Work-order completion/verification không resolve linked ticket và không trigger analytics; hai action cần được operator thực hiện riêng.
- Inventory movement ledger/position dùng PostgreSQL single-database transactions nhưng chưa có barcode scanning, cycle-count workflow, lot/serial tracking, procurement, supplier, accounting hoặc stock valuation.
- Low-stock suggestions chỉ là deterministic threshold view; không phải demand forecast, inventory optimization hay automatic replenishment.
- Local inventory evidence có cùng single-node storage limitation như asset/work-order attachment; chưa có malware scanning hoặc object-store reconciliation.
- Reporter PII có RBAC redaction nhưng chưa có field-level encryption, retention policy hoặc data-subject workflow.
- Local auth chưa có SSO, MFA, account recovery, distributed login throttling, key rotation, centralized observability hoặc external security review.
- Refresh cookie cần HTTPS và `Secure=true` ngoài local; `.env.example` chỉ là development configuration.

## Earlier MVP Cleanup

Earlier MVP cleanup đã xóa duplicate anomaly/risk implementations, ingestion helpers, sample-data wrapper và duplicate dashboard entrypoint. Product Milestone 1 sau đó hợp nhất PostgreSQL modules thành canonical transactional path; CSV repository chỉ còn compatibility adapter. Chi tiết: [docs/architecture.md](docs/architecture.md).

## Repository Layout

```text
src/config/           Settings và Vietnamese value mappings
src/data_generation/  Synthetic maintenance data
src/ingestion/        CSV validation và PostgreSQL seed import
src/database/         Canonical models, migrations và analytics snapshot export
src/repositories/     Storage-neutral contract, PostgreSQL và CSV adapters
src/asset_management/ Asset lifecycle, hierarchy, attachment storage và QR helpers
src/ticket_management/ Ticket lifecycle, priority, SLA, queues, communication và escalation
src/maintenance_management/ Preventive recurrence, work-order state machine, routes và CLI
src/inventory_management/ Spare-part master, stock-control service, routes và seed CLI
src/features/         Canonical daily feature pipeline
src/models/           Canonical anomaly pipeline
src/risk/             Canonical risk pipeline
src/rag/              Document retrieval và Copilot composition
src/api/              Storage-neutral FastAPI services và routes
src/dashboard/        Streamlit app và API client
tests/                Automated tests
docs/                 Scope, architecture, process, contracts và demo docs
```

## Supporting Documentation

- [MVP scope](docs/mvp_scope.md)
- [Business process](docs/business_process.md)
- [Data contract](docs/data_contract.md)
- [Canonical architecture](docs/architecture.md)
- [Analytics pipeline](docs/analytics.md)
- [Ticket operations and SLA](docs/ticket_operations.md)
- [Inventory business process](docs/inventory_business_process.md)
- [Product Milestone 5 release notes](docs/releases/product_milestone_5.md)
- [Product Milestone 6 release notes](docs/releases/product_milestone_6.md)
- [Work-order business process](docs/work_order_business_process.md)
- [RBAC matrix](docs/rbac.md)
- [FastAPI contract](docs/api.md)
- [Demo script](docs/demo_script.md)
- [Interview notes](docs/interview_notes.md)
- [Troubleshooting](docs/troubleshooting.md)
- [CV bullets](docs/cv_bullets.md)

# AI Maintenance Copilot

Nền tảng decision-support cho bảo trì thiết bị, kết hợp auditable asset lifecycle, ticket/SLA, preventive planning, standalone work orders, spare-parts stock control, Vietnamese batch analytics, explainable risk scoring và RAG retrieval trên SOP/checklist.

> Trạng thái: **Product Milestone 9 engineering implementation complete — pilot-ready
> by design, not pilot-verified in practice.** Repository chưa production-ready,
> chưa có sponsoring organization hoặc approved pilot host, và không thay thế
> CMMS/S-Maintain. Overall external pilot decision:
> `NO-GO / WAITING FOR PILOT SPONSOR`.

**Pilot-ready by design** means that the system contains the architecture,
deployment contracts, validation tooling, recovery procedures, and operational
templates needed to begin a pilot when a sponsoring organization and approved
environment become available.

**Pilot-verified in practice** means that those procedures have actually been
executed on an approved pilot host with real organizational owners, pilot-grade
secrets, representative data, and real users.

Current PM9 gates:

| Gate | Result | Meaning |
|---|---|---|
| Engineering readiness | `PASS` | Repository architecture, tooling, contracts, tests, runbooks, and release procedures are complete for the recorded scope |
| Local rehearsal | `PARTIAL` | Deterministic/local/synthetic checks passed, but live Compose, soak, mutation, capacity, live worker kill, and paired restore were not executed |
| Real-company pilot | `BLOCKED — EXTERNAL DEPENDENCY` | No sponsor, approved host, company owners, real users/data, pilot secrets, or organizational acceptance exists |

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
- arbitrary scheduler/job queue ngoài closed PM7 worker catalog hoặc startup work-order generation;
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
- deterministic first-response/resolution SLA từ snapshotted business calendar/policy, idempotent escalation qua API, CLI hoặc closed background job;
- PostgreSQL spare-part master và stock locations; on-hand/reserved/available do backend quản lý bằng row locks và immutable movements;
- explicit work-order part requirements, reservation/replacement/release, issue, technician consumption, unused-part return, atomic transfer và controlled adjustment;
- low-stock/reorder visibility deterministic, protected inventory evidence và deduplicated in-app alert cycle, không tạo purchase order;
- PostgreSQL-backed worker với durable job execution, leases, bounded retry/dead-letter, transactional outbox và append-only delivery attempts;
- owner-isolated in-app notification inbox, health/readiness/metrics, safe structured logs và Administrator operator controls;
- Streamlit legacy development status page; protected product workflows dùng Next.js;
- Next.js authenticated frontend có ticket/work-order/inventory workflows, notification inbox và Administrator job operations page;
- Qdrant-based SOP/checklist retrieval với metadata filters và relevance gate;
- deterministic Maintenance Copilot response có sources, safety notice và safe fallback.
- versioned PM9 pilot manifest/environment contract, closed Compose rehearsal,
  release/ownership/limitation records, opt-in step-load safety, operator-driven
  backup publication, synthetic disk-capacity và bounded attachment-recovery
  helpers.

PM9 tooling không có nghĩa các host-dependent gate đã pass. SSO/MFA, distributed
rate limiting, HA/failover, automated PITR, external notification delivery,
centralized observability/on-call, managed secrets, object storage, malware
scanning, multi-tenancy, Kubernetes và cloud deployment vẫn ngoài completed
boundary.

## Stage 9 Data Platform

`data_platform/` bổ sung local-only structured analytics trong database/container
scale riêng: compatibility views, tuple-watermark ingestion, raw versions, dbt
warehouse/marts, Airflow DAG 9 tasks và bounded read-only aggregate adapter. RAG
vẫn dành cho documents; không embed một triệu work orders. Full local benchmark
đã reconcile 1,100,000 final unique rows, 1,110,000 raw versions và 10,000
updates; incremental/empty Airflow runs đều 9/9 tasks, 0 retries; dbt pass 307
tests và focused Data Platform pass 42 tests. Đây vẫn là synthetic local
evidence, không phải production traffic hoặc company usage.

```powershell
docker compose -f docker-compose.scale.yml config --quiet
docker compose -f docker-compose.scale.yml up -d --wait --wait-timeout 180 stage9-scale-postgres
.\scripts\generate_scale_data.ps1 -WorkOrderCount 1000000 -Seed 20260823 -Phase baseline -BatchSize 50000 -BaselineCount 1000000 -UpdateCount 0 -RunId stage9-1m-seed-20260823
```

Full baseline/incremental/Airflow/dbt commands và safe stop/confirmed cleanup ở
[scale-test-1m](docs/scale-test-1m.md). Xem [integration/domain mapping](docs/data-platform-integration.md),
[measured benchmark report](docs/benchmark-results-1m.md),
[machine JSON](docs/benchmark-results-1m.json),
[dataset manifest](docs/benchmark-manifest-1m.json) và
[structured data vs RAG](docs/structured-data-vs-rag.md).

## Canonical Architecture

Architecture là **PostgreSQL-primary cho transactional data** và **CSV batch-first cho analytics**.

```mermaid
flowchart LR
    Seed[Synthetic Vietnamese CSV seed] --> Import[Validate + idempotent import]
    Migration[Alembic migrations] --> DB[(PostgreSQL<br/>business state, identity, audit,<br/>jobs, outbox, notifications)]
    Import --> DB
    Files[(Local attachment storage<br/>single-node pilot)]
    DB <--> Service[Repositories + business services]
    Service <--> Files
    Service <--> API[FastAPI<br/>unchanged contracts]
    CLI[Explicit domain/operator CLI] --> Service
    Worker[Independent PM7 worker<br/>leases + bounded retry] <--> DB
    Worker -->|existing services only| Service
    Service -->|selected events<br/>same transaction| DB
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
    Qdrant --> Grounding[Score/filter/context gate]
    Grounding --> LLM[Ollama or OpenAI-compatible LLM]
    LLM --> Validate[Schema + citation validation]
    Validate --> API
    Grounding -->|disabled/error/insufficient| Fallback[Deterministic safe fallback]
    Fallback --> API
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
8. Closed background jobs có thể chạy preventive generation, SLA evaluation, analytics refresh và low-stock detection; mọi execution/outbox/notification đều persist trong PostgreSQL.
9. Inventory/ticket transaction không tự thay Risk Score/KPI; analytics chỉ publish ở batch tiếp theo và giữ output hợp lệ gần nhất khi failure.
10. Con người xác minh thiết bị, an toàn và quyết định cuối cùng; Risk Score/SLA/reorder suggestion chỉ hỗ trợ prioritization.

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

FastAPI kiểm tra permission ở server cho mọi route ngoại trừ bốn health route
`GET /health`, `/health/live`, `/health/ready` và `/health/worker`. UI chỉ ẩn
action không phù hợp để cải thiện trải nghiệm; đây không phải authorization
boundary. Role và permission canonical nằm tại `src/security/permissions.py`,
còn frontend nhận permission từ API thay vì duy trì một role matrix riêng.

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

Rich routes dùng code-level status, Vietnamese display labels, server-side filtering/pagination và `expected_version`. Priority chỉ do backend matrix tính; SLA state chỉ derive từ snapshot/timestamps. Escalation execute tạo idempotent event và PM7 có thể chuyển event đó thành in-app notification; ticket status vẫn không tự đổi. Xem [API reference](docs/api.md) và [Ticket Operations/SLA](docs/ticket_operations.md).

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

PM7 background operations và notification endpoints được thêm additive:

- `GET /health/live`, `GET /health/ready`, `GET /health/worker`;
- `GET /notifications`, `GET /notifications/unread-count`;
- `POST /notifications/{notification_id}/read|unread|dismiss`, `POST /notifications/read-all`;
- `GET /operations/jobs`, `PATCH /operations/jobs/{job_key}`, `POST /operations/jobs/{job_key}/trigger`;
- `GET /operations/executions`, `POST /operations/executions/{execution_id}/retry`;
- `GET /operations/outbox`, `GET /operations/metrics`.

Manual trigger/retry yêu cầu Administrator permission và caller-stable `Idempotency-Key`; API chỉ persist execution, worker mới chạy. Job key thuộc closed four-job catalog và không nhận arbitrary executable configuration. Notification route luôn scope current user. Xem [PM7 API contract](docs/api_contract.md).

Legacy `GET /health` cùng ba PM7 health routes là public. Tất cả route business còn lại cần Bearer access token và permission phù hợp. `/docs`, `/redoc` và OpenAPI schema chỉ được bật ở `development`/`test`.

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

Feature ownership is organized under `frontend/src/features/`. Inventory,
work-order parts, ticket detail, and SLA administration have feature entrypoints
there; the historical component paths remain thin compatibility facades so
existing imports and tests continue to work. Route pages import the feature
entrypoints directly. The UI, API calls, query keys, permissions, and mutation
behavior are unchanged.

`frontend/` cung cấp authenticated operational frontend. Product Milestone 7 bổ sung:

- notification bell với unread count và quick actions trong authenticated shell;
- `/notifications` cho personal inbox, severity/unread filters, pagination và related-entity links;
- `/admin/jobs` cho Administrator xem fixed job catalog, enable/disable, manual trigger, execution/dead-letter history, safe retry, outbox status và health metrics.

Product Milestone 6 surfaces vẫn giữ:

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

Current grounded RAG + LLM workflow:

1. Đọc `data/raw/documents.csv`.
2. Validate mọi row và báo lỗi có cấu trúc cho field bắt buộc, date/version, duplicate ID, asset ngoài scope và instruction-like content; không silently drop row.
3. Chunk theo section/procedure boundary, lặp lại heading ở continuation chunk và tạo BLAKE2b content-derived chunk ID.
4. Tạo normalized 384-dimensional embeddings bằng `intfloat/multilingual-e5-small`, `passage:` cho chunk và `query:` cho câu hỏi.
5. Upsert Qdrant bằng UUIDv5 point ID. Default không xóa collection/chunk; `--replace` xóa đúng obsolete points và `--recreate` là destructive opt-in rõ ràng.
6. Lấy candidate pool lớn từ dense Qdrant và in-memory BM25, deduplicate theo chunk ID, rồi fuse normalized scores.
7. Rerank fused candidates bằng multilingual cross-encoder. Final score = `0.55 * retrieval + 0.40 * reranker + 0.05 * bounded metadata prior`; metadata không thể lấn át relevance.
8. Áp filters `asset_type`, `document_type`, `failure_category`, `version`, `language`, relevance/no-answer gate và final top-k.
9. Từ chối asset mismatch, câu hỏi ngoài maintenance scope, prompt injection, shell/SQL/tool directive và yêu cầu tự động thay đổi business state; chỉ cho phép nhánh xã giao hẹp gồm chào hỏi, danh tính, khả năng và cảm ơn/tạm biệt.
10. Kết hợp retrieved guidance với allow-listed asset facts; retrieved text luôn là untrusted data, không phải system instruction.
11. Khi `LLM_ENABLED=true`, gọi Ollama hoặc OpenAI-compatible bằng strict JSON Schema rồi parse lại bằng Pydantic tại application boundary. Câu xã giao không chạy retrieval; câu kỹ thuật vẫn bắt buộc evidence gate và citation.
12. Đối chiếu citation ở từng summary/cause/check/safety claim với đúng local source ID và lexical-support guard; lỗi validation chuyển sang deterministic grounded fallback.

Document coverage hiện tại:

| Asset type | Preventive document | Troubleshooting document |
|---|---|---|
| HVAC | Checklist kiểm tra định kỳ máy lạnh | Máy lạnh không làm mát |
| Pump | Checklist kiểm tra định kỳ máy bơm | Rung hoặc tiếng ồn bất thường |
| Generator | Checklist kiểm tra định kỳ máy phát | Không khởi động |

Default source set có 6 documents. Số chunk phụ thuộc section boundary với cấu hình `RAG_CHUNK_SIZE=800`, `RAG_CHUNK_OVERLAP=80`. `python -m src.rag.index_documents` là idempotent, non-destructive upsert; dùng `--replace` khi muốn đồng bộ canonical set và loại obsolete chunks sau khi validation/upsert thành công.

Relevance threshold là retrieval gate, không phải xác suất đúng:

- deterministic `HashEmbeddingProvider` trong unit tests: `0.15`;
- local `SentenceTransformerEmbeddingProvider`: `0.55`.

Khi kết quả rỗng, dưới threshold, câu hỏi ngoài phạm vi, context không khớp hoặc Qdrant unavailable, Copilot trả safe fallback và không tạo checklist từ unrelated chunks. `/health/rag` kiểm tra riêng Qdrant collection/dimension; liveness và các transactional workflow khác không bị biến thành phụ thuộc RAG.

Generative LLM là opt-in và không có model mặc định. Ollama là lựa chọn local/demo; OpenAI-compatible dùng base URL/model/key hoàn toàn từ environment. LLM không có tools và không thể mutate ticket, work order, inventory hoặc database. Đây không phải automatic diagnostic system. Anomaly/Risk Score không chứng minh failure; manager/technician phải xác minh thiết bị và ưu tiên manual nhà sản xuất cùng quy trình an toàn tòa nhà. Thiết kế chi tiết: [RAG/LLM design](docs/RAG_LLM_DESIGN.md).

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
| Core | FastAPI, batch analytics, SQLAlchemy, psycopg, Alembic và Qdrant client |
| `rag` | `sentence-transformers` cho multilingual E5 embeddings |
| `dashboard` | Streamlit legacy development/status UI; excluded from API/worker images |
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
| `TOKEN_SIGNING_PREVIOUS_SECRET` | rỗng | Chỉ dùng tạm để verify access token trong signing-key rotation |
| `ACCESS_TOKEN_LIFETIME_MINUTES` | `15` | JWT access lifetime |
| `REFRESH_SESSION_LIFETIME_DAYS` | `7` | Revocable refresh-session lifetime |
| `AUTH_COOKIE_SECURE` | `false` ở local | Bắt buộc `true` ngoài dev/test và cần HTTPS |
| `AUTH_COOKIE_SAMESITE` | `lax` | Explicit refresh/CSRF cookie policy |
| `LOGIN_RATE_LIMIT_ATTEMPTS` | `5` | Basic per-process failed-login threshold |
| `COPILOT_RATE_LIMIT_REQUESTS` | `20` | Per-user Copilot requests trong một process/window |
| `COPILOT_RATE_LIMIT_WINDOW_SECONDS` | `60` | Copilot limiter window; distributed gateway limit vẫn cần trước scale-out |
| `STORAGE_BACKEND` | `postgresql` | Normal runtime; `csv` chỉ explicit fixture mode |
| `DATABASE_URL` | local PostgreSQL URL | Transactional source of truth |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | `5` | Startup connection timeout |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` | `5` / `10` | Explicit single-process pool capacity; không phải production sizing |
| `DATABASE_POOL_TIMEOUT_SECONDS` | `30` | Bounded pool checkout wait |
| `DATABASE_STATEMENT_TIMEOUT_SECONDS` | `30` | PostgreSQL statement safety bound |
| `DATABASE_LOCK_TIMEOUT_SECONDS` | `5` | PostgreSQL lock wait safety bound |
| `DATABASE_IDLE_TRANSACTION_TIMEOUT_SECONDS` | `60` | Idle transaction safety bound |
| `TEST_DATABASE_URL` | local database kết thúc `_test` | Isolated integration tests |
| `ATTACHMENT_STORAGE_BACKEND` | `local` | Storage abstraction; chỉ local implementation trong milestone này |
| `ATTACHMENT_STORAGE_ROOT` | `data/attachments` | Private local file root, không được serve trực tiếp |
| `ATTACHMENT_MAX_SIZE_BYTES` | `10485760` | Giới hạn mỗi PDF/PNG/JPG/JPEG |
| `FRONTEND_BASE_URL` | `http://localhost:3000` | Origin dùng để tạo opaque QR lookup URL |
| `LOG_LEVEL` | `INFO` | Safe structured API/worker logging level |
| `WORKER_POLL_INTERVAL_SECONDS` | `2` | Bounded delay giữa worker iterations |
| `WORKER_HEARTBEAT_INTERVAL_SECONDS` | `10` | Lease renewal/heartbeat cadence cho long job |
| `WORKER_HEARTBEAT_STALE_SECONDS` | `60` | Ngưỡng worker readiness |
| `WORKER_OUTBOX_LEASE_SECONDS` | `120` | Lease cho claimed outbox event |
| `WORKER_BATCH_SIZE` | `20` | Bounded schedule/outbox batch |
| `OPERATIONAL_OUTBOX_AGE_ALERT_SECONDS` | `300` | Backlog age threshold |
| `OPERATIONAL_REPEATED_JOB_FAILURE_THRESHOLD` | `3` | Consecutive failure threshold |
| `OPERATIONAL_ANALYTICS_STALE_SECONDS` | `172800` | Enabled analytics staleness threshold |
| `OPERATIONAL_BACKUP_OVERDUE_SECONDS` | `604800` | Restore-validated backup age threshold |
| `ANALYTICS_SOURCE_DIR` | `data/raw` | Sensor/document source cho snapshot job |
| `ANALYTICS_PROCESSED_DIR` | `data/processed` | Atomically published batch outputs |
| `QDRANT_URL` | `http://localhost:6333` | RAG indexing/retrieval |
| `QDRANT_HTTP_PORT` | `6333` | Local Docker host port cho Qdrant REST |
| `QDRANT_COLLECTION` | `maintenance_knowledge` | Qdrant collection |
| `QDRANT_API_KEY` | rỗng | Optional secret for protected Qdrant; never put credentials in URL |
| `QDRANT_TIMEOUT_SECONDS` | `5` | Bounded Qdrant request timeout |
| `EMBEDDING_MODEL_NAME` | `intfloat/multilingual-e5-small` | Multilingual E5 embeddings |
| `EMBEDDING_DEVICE` / `RAG_RERANKER_DEVICE` | `auto` | `auto`, `cpu`, `cuda[:index]`, or `mps`; explicit accelerator falls back safely to CPU |
| `EMBEDDING_BATCH_SIZE` / `EMBEDDING_DIMENSIONS` | `32` / `384` | Batched normalized embedding contract |
| `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` | `800` / `80` | Structure-aware chunking controls |
| `RAG_DENSE_CANDIDATES` / `RAG_SPARSE_CANDIDATES` | `20` / `20` | Pre-fusion candidate pools |
| `RAG_FUSED_CANDIDATES` / `RAG_FINAL_TOP_K` | `20` / `5` | Pre-rerank and final result bounds |
| `RAG_RELEVANCE_THRESHOLD` | `0.55` | Evidence gate, not diagnostic probability |
| `RAG_DENSE_WEIGHT` / `RAG_SPARSE_WEIGHT` | `0.50` / `0.50` | Normalized retrieval fusion |
| `RAG_RETRIEVAL_WEIGHT` / `RAG_RERANKER_WEIGHT` / `RAG_METADATA_WEIGHT` | `0.55` / `0.40` / `0.05` | Final score weights; metadata is validated at maximum `0.10` |
| `RAG_RERANKER_MODEL` | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | Multilingual cross-encoder |
| `RAG_SPARSE_MAX_CHUNKS` | `10000` | Hard bound for small-corpus in-memory BM25 |
| `LLM_ENABLED` | `true` trong local Docker (`false` ở bare Settings) | Local Docker luôn cấu hình LLM; false vẫn giữ deterministic fallback khi operator chủ động tắt |
| `LLM_PROVIDER` | `ollama` | `ollama` hoặc `openai_compatible` |
| `LLM_MODEL` | `qwen2.5-coder:7b` trong local Docker | Pilot/provider khác vẫn phải cấu hình model được phê duyệt |
| `LLM_BASE_URL` | `http://host.docker.internal:11434` trong local Docker | Provider API root; Ollama chạy trên host và API chạy trong container |
| `LLM_API_KEY` | rỗng | Secret injection cho provider cần Bearer key; không log hoặc trả qua API |
| `LLM_TIMEOUT_SECONDS` | `30` | Bounded outbound generation timeout |
| `LLM_TEMPERATURE` | `0.0` | Low-variance grounded generation |
| `LLM_MAX_TOKENS` | `1200` | Output bound |
| `LLM_MAX_RETRIES` | `1` | Retry chỉ cho transient side-effect-free generation failures |
| `LLM_MAX_CONTEXT_CHARS` | `12000` | Prompt retrieval-context bound |
| `LLM_MIN_RELEVANT_DOCUMENTS` | `1` | Minimum distinct relevant documents before generation |

Các PostgreSQL values trong `.env.example` là replacement placeholders, không
phải local hay production credentials. `TOKEN_SIGNING_SECRET` cố ý để rỗng;
không được dùng ephemeral dev secret cho pilot. File `.env` được gitignore.

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dashboard,dev,rag,postgres]"
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dashboard,dev,rag,postgres]"
```

### Ollama local generation

Install Ollama from its official distribution, start the service, and download the local Docker model (or override it with an operator-approved model):

```powershell
ollama serve
ollama pull qwen2.5-coder:7b
```

Configure `.env`:

```dotenv
LLM_ENABLED=true
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:7b
LLM_BASE_URL=http://host.docker.internal:11434
LLM_API_KEY=
```

Then verify the provider boundary inside the API container with `docker compose exec api python -m src.llm.smoke`.

### OpenAI-compatible generation

Use an operator-approved Chat Completions implementation that supports strict `response_format` JSON Schema:

```dotenv
LLM_ENABLED=true
LLM_PROVIDER=openai_compatible
LLM_MODEL=<PROVIDER_MODEL_ID>
LLM_BASE_URL=https://<PROVIDER_API_ORIGIN>/v1
LLM_API_KEY=<INJECT_FROM_SECRET_SOURCE>
```

Do not commit the populated `.env`. The provider key is represented by `SecretStr`, used only in the outbound Authorization header, and excluded from application responses/log messages.

### Docker full-stack path

The development Compose file now builds PostgreSQL, Qdrant, runs `alembic upgrade head`, then starts FastAPI and Next.js. The worker remains an explicit profile:

The multi-stage Python image keeps migration/worker targets free of Torch and Streamlit. The API target installs Torch from the official CPU wheel index by default to avoid shipping unused CUDA runtimes. GPU deployments must be designed and built explicitly; setting an embedding device alone does not add CUDA libraries to the image.

```powershell
docker compose up --build
docker compose --profile worker up --build
```

On a fresh database, seed/import and index remain explicit rather than startup side effects:

```powershell
docker compose exec api python -m src.ingestion.load_data
docker compose exec api python -m src.security.cli seed-demo-users
docker compose exec api python -m src.maintenance_management.cli seed-development
docker compose exec api python -m src.ticket_management.cli seed-defaults
docker compose exec api python -m src.inventory_management.cli seed-development
docker compose exec api python -m src.rag.index_documents --replace
```

The demo-user command prompts for a password (or reads the documented protected environment variable); no default password is committed and startup never creates users.

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

PM7 seed bốn supported jobs ở trạng thái disabled. Xem version hiện tại rồi enable có kiểm soát bằng Administrator:

```powershell
python -m src.operations.cli status
python -m src.operations.cli set-enabled sla_escalation `
  --enabled true --expected-version <VERSION> `
  --actor-username admin.demo
```

Terminal worker:

```powershell
python -m src.operations.worker
```

Một iteration để smoke test: `python -m src.operations.worker --once`. Manual trigger chỉ persist execution và yêu cầu idempotency key:

```powershell
python -m src.operations.cli trigger sla_escalation `
  --idempotency-key "local-sla-20260726-01" `
  --actor-username admin.demo
```

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

Stop worker/API/frontend bằng `Ctrl+C`, sau đó:

```powershell
docker compose stop
```

Equivalent Make targets: `services-up`, `postgres-up`, `migrate-db`,
`generate-data`, `validate-data`, `load-data`, `replace-data`,
`seed-maintenance`, `seed-inventory`, `generation-dry-run`,
`generate-work-orders`, `seed-ticketing`, `escalation-dry-run`,
`evaluate-escalations`, `export-analytics-snapshot`, `build-features`,
`detect-anomalies`, `score-risk`, `build-preventive`, `build-recurring`,
`build-kpis`, `index-documents`, `rag-query`, `llm-smoke`, `evaluate-rag`, `bootstrap-admin`, `seed-demo-users`,
`run-api`, `run-dashboard`, `run-frontend`, `run-worker`, `worker-once`,
`run-job`, `set-job-enabled`, `retry-job`, `retry-outbox`,
`evaluate-operational-alerts`, `job-status`, `reliability-load`,
`backup-restore-drill`, `attachment-integrity`, `worker-docker-up`,
`worker-docker-down`, `create-test-db`, `test`, `test-postgres`, `lint`,
`pilot-contract-validate`, `pilot-decision-validate`,
`pilot-release-validate`, `pilot-rehearsal-plan`,
`pilot-rehearsal-execute`, `pilot-rehearsal-cleanup`,
`pilot-backup-schedule`, `pilot-step-load`, `frontend-lint`,
`frontend-typecheck`, `frontend-test` và `frontend-build`.

Demo 10–12 phút: [docs/demo_script.md](docs/demo_script.md).

## PM9 Pilot Rehearsal

Development quickstart ở trên không phải pilot deployment. PM9 dùng
[separate pilot Compose](docker-compose.pilot.yml), versioned
[manifest](deployment/pilot_manifest.json) và protected environment được tạo từ
[`.env.pilot.example`](.env.pilot.example).

Plan-only:

```powershell
python -m src.reliability.deployment_rehearsal `
  --environment-file "<protected-pilot-env>"
```

Execution cần approved host, `PM9_ALLOW_DEPLOYMENT_REHEARSAL=true`,
`PILOT_HOST_APPROVED=true` trong protected env và evidence directory ngoài
repository. Opt-in `--authenticated-post-start` validator đã được implement và
unit-test cho approved-data reads, auth/RBAC, exact four-job state,
notifications và batch analytics; nó chưa chạy trên live PM9 stack. Make target
chỉ thêm flag khi set `PILOT_AUTHENTICATED_POST_START=true`, nên default vẫn
fail với các post-start gate là `not_executed`.

Current developer workstation chưa được xác nhận là intended pilot host; full
deployment, live authenticated smoke, soak/mutation/capacity,
release/rollback, real secret rotation và paired PostgreSQL/attachment recovery
chưa chạy.

Không copy local `.env` development làm pilot config. Không commit populated
environment, backup, attachment bytes, raw report, log hoặc `.next`. Xem
[pilot deployment](docs/pilot_deployment.md),
[pilot environment](docs/pilot_environment.md) và
[internal-pilot checklist](docs/internal_pilot_checklist.md).

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

`--replace` xóa PM4–PM8 development runtime data theo dependency order, gồm
plans/templates/work orders, ticket/SLA extensions, inventory,
outbox/redrive/execution/notification/heartbeat history và reliability evidence;
fixed PM7 job catalog được trả về disabled trước khi khôi phục canonical
`27/42/86`. Private attachment backup/cleanup vẫn là trách nhiệm operator. Chạy
lại các explicit seed commands sau reset nếu cần product demo data.

Dedicated test database:

```powershell
.\scripts\test-postgres.ps1 -Action reset
.\scripts\test-postgres.ps1 -Action test -Keep
```

Tests từ chối database name không kết thúc `_test` và không mutate developer/demo database.

The helper uses the isolated `maintenance_copilot_test` database on loopback
port `15433`, runs migrations and `pytest -m postgres -q`, and accepts `-Full`
for the complete suite. Tests reject database names that do not end in `_test`
and must never mutate the developer/demo database. See
[`docs/testing-postgresql.md`](docs/testing-postgresql.md) for the safety
validator and manual URL requirements.

## Verification

```powershell
python -m pytest
python -m ruff check .
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
docker compose config --quiet
```

RAG/LLM evaluation:

```powershell
# Reproducible local fixture without Qdrant/model downloads
python -m evaluation.run_evaluation --mode deterministic --output reports/rag_evaluation.json

# Configured semantic Qdrant retrieval
python -m evaluation.run_evaluation --backend configured-qdrant --mode deterministic

# Configured grounded LLM; requires LLM_ENABLED=true and provider availability
python -m evaluation.run_evaluation --backend configured-qdrant --mode rag-llm
```

Implementation verification on 2026-07-28 started from a clean baseline of `308 passed, 73 skipped` backend and `112 passed` frontend tests. The new grounded-LLM focused matrix passed `40` tests, the Copilot rate-limit/API matrix passed `24`, the evaluation/PM9 manifest matrix passed `30`, both Compose files validated, and the deterministic evaluation ranked all six expected corpus documents at rank 1. These small synthetic results validate contracts and reproducibility only; they do not establish real-world model accuracy. Final full-suite counts are recorded in [Project audit](docs/PROJECT_AUDIT.md) after the handover verification run.

Lần verify Milestone 4.5 ngày 2026-07-15: `122 passed`, Ruff và `git diff --check` đều đạt. Streamlit AppTest và live health smoke đạt; OpenAPI có đủ ba write methods. Manual `GENERATOR_002` workflow trên isolated CSV copies đã tạo/assign/resolve ticket, ghi log, qua full raw validation, mở Copilot checklist có nguồn và xác nhận risk/KPI không đổi trước batch tiếp theo. Còn một `StarletteDeprecationWarning` chỉ thuộc test client, được giải thích trong [troubleshooting](docs/troubleshooting.md). Các kết quả này xác nhận tính tái lập của portfolio demo, không chứng minh production readiness hoặc model accuracy.

Lần verify Frontend Milestone 3 ngày 2026-07-16: backend `125 passed`, frontend `43 passed`, Ruff, ESLint, Next.js production build và `git diff --check` đều đạt. Live workflow trên temporary CSV tạo `TCK-000043`, `LOG-000087`, đi qua assignment, `Đang xử lý`, maintenance result có follow-up và resolve; ticket/log xuất hiện đúng một lần, asset detail được refresh, còn risk/KPI không đổi. Sau test, canonical files vẫn giữ 27 assets, 42 tickets, 86 maintenance logs và 77.760 sensor readings.

Lần verify Frontend Milestone 4 ngày 2026-07-16: backend `125 passed`, frontend `61 passed`, focused RAG/API tests `20 passed`; Ruff, ESLint, Next.js production build, Markdown link check và `git diff --check` đều đạt. Live `GENERATOR_002` asset/ticket handoff retrieve đúng source máy phát điện với `retrieval_status=success`, sources và safety notice. Unrelated question trả zero-source fallback; khi dừng Qdrant, Copilot trả `unavailable` trong khi API/analytics/assets vẫn hoạt động, sau đó retry thành công khi Qdrant được khởi động lại. Desktop 1440px và mobile 390px route checks không có horizontal clipping. Canonical CSV counts và SHA-256 được kiểm tra, không có data file nào thay đổi trong Git worktree. Các kết quả này xác nhận demo workflow, không phải production readiness hoặc RAG accuracy.

Lần verify Product Milestone 1 ngày 2026-07-18: clean Alembic downgrade/upgrade đạt revision `20260718_0001`; CSV import dry-run và import thật xác nhận `27` assets, `42` tickets, `86` maintenance logs; analytics snapshot xác nhận thêm `77.760` readings và `6` documents. PostgreSQL-focused suite đạt `15 passed`, full backend đạt `140 passed`, Streamlit AppTest đạt `1 passed`, frontend đạt `61 passed`; Ruff, ESLint, Next.js production build, Alembic schema check, Markdown link check và `git diff --check` đều đạt. Concurrency, FK, status transition, log-before-resolution, atomic rollback và optimistic conflict đều có integration test trên isolated `_test` database. Restart container giữ nguyên migration revision và row counts. Live `GENERATOR_002` workflow tạo `TCK-000043` và `LOG-000087`, resolve ticket, giữ batch risk/KPI chưa đổi và Copilot trả một grounded source với safety notice; toàn bộ existing Next.js routes trả `200`. Đây là kết quả local internal-pilot verification, không phải bằng chứng production readiness, model accuracy hoặc business impact.

Lần verify Product Milestone 2 ngày 2026-07-18: clean Alembic downgrade/upgrade đạt revision `20260718_0002` và `alembic check` không có schema drift; explicit admin bootstrap và năm development roles thành công trên isolated `_test` database. Full backend đạt `156 passed`, frontend đạt `74 passed`; Ruff, ESLint, Next.js production build, Markdown link check, secret scan và `git diff --check` đều đạt. Live role workflow tạo `TCK-000043`, manager gán `TECH_002`, technician ghi `LOG-000087`, manager resolve; helpdesk/technician forbidden actions trả `403`, unauthenticated/revoked access trả `401`, Copilot vẫn trả response. Audit có đủ ticket/log/user actions, không lộ credential fields và database trigger từ chối sửa event. PostgreSQL restart giữ revision, 27 assets, 43 tickets, 87 logs, 5 users và 24 audit events. Đây là local internal-pilot security verification, không phải production security certification.

Lần verify Product Milestone 3 ngày 2026-07-18: clean Alembic downgrade/upgrade đạt revision `20260718_0003`, `alembic check` không có schema drift; seed dry-run/import giữ `27/42/86` và tạo 7 deterministic locations. Full PostgreSQL-enabled backend đạt `162 passed`, frontend đạt `80 passed`; Ruff, ESLint và Next.js production build đều đạt. Temporary analytics snapshot giữ đúng 10 legacy asset columns và tạo `3.240` feature/anomaly/risk rows cùng `27/25/1` maintenance reports. Live role workflow tạo `PM3_DEMO_ASSET`, upload/download một checksum-matched technical manual, archive/restore, xác nhận archived QR trả `410`, technician/helpdesk forbidden actions trả `403`, rồi tạo `TCK-000043` và `LOG-000087`. PostgreSQL restart giữ revision cùng `28` assets, `43` tickets, `87` logs, một active attachment và `29` audit events. Next.js login/assets/detail/QR/tickets/Copilot routes trả `200`. Đây là local internal-pilot verification, không phải production readiness, security certification hoặc business-impact evidence.

Lần verify Product Milestone 5 ngày 2026-07-23: isolated PostgreSQL clean downgrade/upgrade đạt revision `20260723_0005`, `alembic check` không có model drift; canonical import dry-run/import xác nhận `27/42/86`, còn PM4 maintenance regression đạt `10 passed`. PM5 focused backend đạt `28 passed`, full backend đạt `210 passed`, frontend đạt `95 passed` trên 14 files; Ruff, ESLint và Next.js production build 20 routes đều đạt. Live role workflow tạo critical `TCK-000044` và corrective `WO-000002`: Helpdesk intake/route, Technician acknowledge/start/hold/resume/comment/complete work order, ticket vẫn `in_progress` sau work-order completion, explicit resolve, Manager verify/close/reopen và escalation execute idempotent. PostgreSQL restart giữ ticket `reopened`, SLA occurrence 2, 2 comments, 11 SLA events, one ticket escalation, verified work order và counts `27/44/87`. OpenAPI có 91 paths, protected smoke trả `401`, 12 existing/new Next.js routes trả `200`, Markdown links và `git diff --check` đạt. Đây là local verification trên synthetic data, không phải production, security, SLA-performance hoặc business-impact certification.

Lần verify Product Milestone 6 ngày 2026-07-23: isolated PostgreSQL downgrade-to-base/clean upgrade đạt revision `20260723_0006`, `alembic check` không có model drift; canonical import vẫn đúng `27/42/86`. PM4 seed tạo 3 plans/4 work orders; PM6 seed tạo 6 categories, 3 UOM, 5 stock locations, 8 parts, 8 opening positions, 3 requirements và 3 reservations, còn lần chạy thứ hai không tạo duplicate. Focused PM6 đạt `14 passed`, PM4 regression đạt `10 passed`, PM5 ticket/SLA regression đạt `28 passed`; full backend đạt `224 passed`, frontend đạt `106 passed` trên 16 files. Ruff, ESLint và Next.js production build 30 pages đều đạt. Live workflow xác nhận admin lifecycle audit; Storekeeper receipt idempotent, atomic transfer, adjustment, issue và return; assigned Technician ghi consumption riêng; Helpdesk adjustment và Technician receipt đều trả `403`. PostgreSQL restart giữ revision, `27/42/86`, 4 work orders, 8 parts, 14 movements, 3 reservations, 1 issue, 1 consumption và 1 return. OpenAPI có 128 paths, 33 Next.js routes trả `200`; snapshot batch tạo `3.240/3.240/3.240` feature/anomaly/risk rows cùng `27/25/1` maintenance reports mà không đổi canonical output hashes. Đây vẫn chỉ là local verification trên synthetic data, không phải production, security, stock-accuracy hoặc business-impact certification.

Lần verify Product Milestone 7 ngày 2026-07-26: isolated PostgreSQL clean base-to-head và PM7 downgrade/re-upgrade đạt revision `20260726_0007`; `alembic check` không có model drift. PM7 focused đạt `6` pure tests và `8` PostgreSQL integration tests; targeted PM4-PM6/auth regressions đạt `73 passed`; full backend đạt `238 passed`. Frontend PM7 đạt `6 passed`, full frontend đạt `112 passed` trên 17 files; Ruff, ESLint, Next.js production build 32 pages, Markdown link check, secret/unsafe-path scan và `git diff --check` đều đạt. Docker worker trở thành healthy, one-iteration worker kết thúc với heartbeat `stopping`, manual SLA trigger replay dùng cùng execution, outbox tạo ba role-based notifications, owner actions hoạt động và `/notifications` cùng `/admin/jobs` trả `200`. Analytics publish ở temporary path và canonical outputs không đổi. PostgreSQL restart giữ revision, 27 assets, 44 tickets, 87 logs và bốn fixed jobs; verification execution/outbox/notification/heartbeat records được cleanup về 0. Đây là local internal-pilot operational verification, không phải production, security, availability, SLA-performance hoặc business-impact certification.

Checkpoint Product Milestone 8 ngày 2026-07-26: isolated PostgreSQL clean
base-to-head, populated PM8 downgrade/re-upgrade và `alembic check` đạt revision
`20260726_0008`; full backend đạt `257 passed`, full frontend đạt `112 passed`
trên 17 files; Ruff, ESLint và Next.js production build 32 pages đạt. Bounded
baseline 4 req/s và stress 12 req/s không có unexpected failure hoặc outbox
backlog; stress chỉ là điểm cao nhất đã test, không phải capacity limit.
API/worker reconnect, protected redrive, alert raise/recovery, isolated
backup/restore và restored health smoke đạt trên disposable `_test` stack.
Kết luận vẫn là `NO-GO / NOT YET VERIFIED` do owner/contact/acceptance, real
pilot secrets, soak/capacity, representative attachment restore và intended
pilot-host rehearsal còn mở. Đây là historical PM8 evidence. Xem
[PM8 release note](docs/releases/product_milestone_8.md).

Product Milestone 9 implementation session ngày 2026-07-26 bổ sung pilot
deployment/environment contract, separate Compose rehearsal, draft release/
ownership/limitation records, opt-in step-load safety, operator-driven
checksummed backup-artifact publication tooling, opt-in authenticated post-start
validation, injected disk-capacity và attachment archive/restore helpers.

Deployment/manifest reconciliation đạt `22 passed`; Ruff, Compose config, Make
dry-runs và `git diff --check` đều pass.

Checkpoint PostgreSQL trên một disposable local PostgreSQL 16 database kết thúc
`_test` đạt `73 passed, 239 deselected`. Ba test dùng
`pg_terminate_backend` thật đã xác nhận job completion lease recovery, outbox
delivery recovery với đúng một notification, và ticket + outbox rollback cùng
transaction. Đây là connection-termination boundary evidence, không phải live
worker-process kill. Một generated non-empty PDF được upload qua authorized API,
trả `201`, archive/restore bytes, download `200` với matching bytes cho
Administrator và `403` cho Helpdesk; test này dùng original `_test` metadata và
không restore PostgreSQL dump cùng metadata/bytes.

Authenticated post-start tooling đã được focused unit-test với mocked HTTP
transport (`16 passed`) nhưng chưa contact live stack. Không có PM9 full
deployment trên intended host, live authenticated deployed workflow, soak,
mutation load, capacity/degradation, live worker-process kill, real secret
rotation, durable disk alert hay paired PostgreSQL dump + attachment restore.
Local disposable `_test` drill đã chạy một valid `pg_dump` và một
invalid-database failure mà không publish partial hoặc thay last-good index; đây
không phải intended-host/service-account evidence. Technical stewardship is
recorded for the solo developer, while company owner/incident/acceptance
authority and rollback rehearsal remain externally blocked.

Final local verification trên settled worktree đạt `374 passed` cho full backend
với cả `73` PostgreSQL-marked tests trên fresh disposable PostgreSQL 16 `_test`;
container được xóa ngay sau run. PM9-focused run riêng đạt `103 passed, 3
skipped` khi không inject database, còn ba test bị skip đều pass trong full
database-enabled run. Full frontend đạt `112 passed` trên 17 files, ESLint pass
và Next.js production build tạo 32 pages rồi `.next` được xóa. Ruff check toàn
repository pass; 19 PM9 Python files pass focused format check. Alembic có một
head `20260726_0008`, current/check pass và fresh `_test` database migrate sạch
từ base đến head. Pilot Compose config pass. Manifest-only technical validation
continues to fail closed with generic `NO-GO / NOT YET VERIFIED`; the complete
three-gate release record classifies the external decision separately.

PM9 closure decision:

```text
PILOT-READY BY DESIGN
NOT PILOT-VERIFIED IN PRACTICE

Engineering readiness: PASS
Local rehearsal: PARTIAL
Real-company pilot: BLOCKED — EXTERNAL DEPENDENCY
Overall: NO-GO / WAITING FOR PILOT SPONSOR
```

Xem [PM9 release note](docs/releases/product_milestone_9.md) và
[PM9 load results](docs/pilot_load_results.md). Future external work is
[Pilot 01 — Company-Specific Deployment](docs/pilot_01_company_specific_deployment.md),
not PM10. PM8 measurements không được
đổi nhãn thành PM9 evidence.

## Limitations

- Synthetic data chưa được kiểm chứng bằng maintenance history thực tế.
- Analytics thresholds và risk weights là transparent demo heuristics, chưa được hiệu chuẩn trên dữ liệu thực tế.
- Synthetic chronology chỉ mô phỏng quy trình đơn giản và chưa được đối chiếu với quy tắc lịch bảo trì thực tế của một cơ sở cụ thể.
- API phục vụ PostgreSQL transactions cùng processed CSV analytics; PM7 worker
  chỉ là internal-pilot PostgreSQL polling process. PM8 đã chạy bounded local
  baseline/stress; PM9 có safety tooling nhưng chưa chạy soak,
  mutation/capacity-to-degradation hoặc intended-host rehearsal. Không có HA
  hay production cache invalidation strategy.
- Closed scheduler chỉ hỗ trợ bốn existing operations; chưa có distributed queue partitioning, autoscaling hoặc production missed-run/on-call operations.
- Notification chỉ nằm trong in-app inbox; chưa có email/SMS/push, user preferences, acknowledgement hoặc external delivery monitoring.
- Health/metrics và structured logs chưa có centralized collection, alert routing hoặc production observability platform.
- Recurrence chỉ hỗ trợ bounded interval day/week/month/year. Chưa có calendar exceptions, holiday rules hoặc arbitrary RRULE.
- Legacy asset `next_maintenance_date` là compatibility aggregate từ active plans; plan-specific dates và calendar mới là operational detail.
- Analytics snapshot cố ý project maintenance dates về fixed-interval legacy contract. Vì vậy preventive plan/work-order calendar là operational source cho scheduling, còn batch preventive KPI hiện vẫn phản ánh contract cũ.
- Reopen một completed-but-unverified work order giữ append-only linked MaintenanceLog và không tạo log thứ hai; chưa có full record-amendment/countersign workflow.
- Isolation Forest và risk formula chưa được đánh giá trên labeled failure outcomes.
- Copilot có dataset/evaluation nhỏ cho 6 tài liệu synthetic, nhưng chưa có corpus/labeled judgments từ cơ sở thực tế hoặc human-rated unsupported-claim benchmark.
- Sáu SOP/checklist là synthetic/illustrative và không thay thế tài liệu nhà sản xuất.
- Grounded LLM là opt-in, schema/citation controlled và luôn có deterministic fallback; không có semantic fact-checker độc lập, tool use hoặc diagnosis authority.
- Next.js là authenticated internal-pilot workflow, chưa có production caching, accessibility audit hoặc browser-level regression suite; Streamlit chỉ còn legacy status client.
- PostgreSQL workflow có transactions, foreign keys, sequences, optimistic
  conflict detection, append-only audit và bounded local load/recovery
  hardening; chưa có production operations validation.
- Attachment bytes dùng atomic local storage cho single-node pilot; chưa có S3-compatible implementation, malware scanning, object versioning hoặc distributed transaction giữa file store và PostgreSQL.
- QR là lookup identifier có xác thực, không phải access-control credential; chưa có fleet label operations, camera-scanner test matrix hoặc offline workflow.
- Ticket/log mới không làm risk hoặc KPI đổi ngay; cần chạy lại canonical batch pipeline.
- Work-order completion/verification không resolve linked ticket và không trigger analytics; hai action cần được operator thực hiện riêng.
- Inventory movement ledger/position dùng PostgreSQL single-database transactions nhưng chưa có barcode scanning, cycle-count workflow, lot/serial tracking, procurement, supplier, accounting hoặc stock valuation.
- Low-stock suggestions chỉ là deterministic threshold view; không phải demand forecast, inventory optimization hay automatic replenishment.
- Local inventory evidence có cùng single-node storage limitation như asset/work-order attachment; chưa có malware scanning hoặc object-store reconciliation.
- Reporter PII có RBAC redaction nhưng chưa có field-level encryption, retention policy hoặc data-subject workflow.
- Local auth hỗ trợ một previous signing key trong bounded rotation grace period,
  nhưng chưa chạy real pilot rotation và chưa có SSO, MFA, account recovery,
  distributed login throttling, managed secret/JWKS, centralized observability
  hoặc external security review.
- Refresh cookie cần HTTPS và `Secure=true` ngoài local; `.env.example` chỉ là development configuration.
- Pilot chỉ có một API, một worker và một PostgreSQL instance; không có automatic
  failover hoặc automated PITR.
- Operational/release/rollback/backup/security/support owners, incident path và
  support coverage chưa được assign.
- Tất cả critical known limitations còn `pending`; không có customer-facing SLA.

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
src/operations/       Closed jobs/events, worker, notification/operator API và CLI
src/reliability/      Bounded load/deployment/backup/disk/attachment rehearsal tooling
src/features/         Canonical daily feature pipeline
src/models/           Canonical anomaly pipeline
src/risk/             Canonical risk pipeline
src/rag/              Document retrieval và Copilot composition
src/llm/              Provider, prompt, structured parsing và citation validation
src/api/              Storage-neutral FastAPI services và routes
src/dashboard/        Streamlit app và API client
evaluation/           Small reproducible RAG/LLM dataset and runner
tests/                Automated tests
docs/                 Scope, architecture, process, contracts và demo docs
```

## Supporting Documentation

- [Repository architecture map](ARCHITECTURE.md)
- [Staged refactoring plan and current validation baseline](REFACTOR_PLAN.md)
- [MVP scope](docs/mvp_scope.md)
- [Business process](docs/business_process.md)
- [Data contract](docs/data_contract.md)
- [Canonical architecture](docs/architecture.md)
- [Project audit](docs/PROJECT_AUDIT.md)
- [RAG/LLM design](docs/RAG_LLM_DESIGN.md)
- [RAG/LLM evaluation](docs/RAG_LLM_EVALUATION.md)
- [RAG ingestion contract](docs/ingestion.md)
- [Hybrid retrieval scoring](docs/retrieval.md)
- [LLM and claim-level citations](docs/llm-and-citations.md)
- [Copilot safety boundary](docs/safety.md)
- [Evaluation quick reference](docs/evaluation.md)
- [Executed runtime verification](docs/RUNTIME_VERIFICATION.md)
- [Security review](docs/SECURITY_REVIEW.md)
- [Graduation demo guide](docs/DEMO_GUIDE.md)
- [Company handover](docs/COMPANY_HANDOVER.md)
- [Analytics pipeline](docs/analytics.md)
- [Ticket operations and SLA](docs/ticket_operations.md)
- [Inventory business process](docs/inventory_business_process.md)
- [Product Milestone 5 release notes](docs/releases/product_milestone_5.md)
- [Product Milestone 6 release notes](docs/releases/product_milestone_6.md)
- [Product Milestone 7 release notes](docs/releases/product_milestone_7.md)
- [Work-order business process](docs/work_order_business_process.md)
- [RBAC matrix](docs/rbac.md)
- [FastAPI contract](docs/api.md)
- [PM7 API contract](docs/api_contract.md)
- [Background jobs and outbox](docs/background_jobs.md)
- [In-app notifications](docs/notifications.md)
- [Operations runbook](docs/operations_runbook.md)
- [Security boundary](docs/security.md)
- [Testing guide](docs/testing.md)
- [Isolated PostgreSQL testing](docs/testing-postgresql.md)
- [Application-service decomposition](docs/application-services.md)
- [Repository transaction map](docs/repository-transaction-map.md)
- [Backend decomposition checkpoint](docs/repository-transaction-map.md)
- [PM8 reliability validation](docs/reliability_validation.md)
- [PM8 load test plan](docs/load_test_plan.md)
- [Backup and restore drill](docs/backup_restore.md)
- [Failure recovery drills](docs/failure_recovery.md)
- [Secret rotation](docs/secret_rotation.md)
- [Internal-pilot go/no-go checklist](docs/internal_pilot_checklist.md)
- [Product Milestone 8 release](docs/releases/product_milestone_8.md)
- [PM9 pilot deployment](docs/pilot_deployment.md)
- [PM9 pilot environment](docs/pilot_environment.md)
- [PM9 release and rollback rehearsal](docs/pilot_release_rehearsal.md)
- [PM9 load results](docs/pilot_load_results.md)
- [PM9 backup schedule](docs/pilot_backup_schedule.md)
- [PM9 secret rotation](docs/pilot_secret_rotation.md)
- [PM9 attachment recovery](docs/pilot_attachment_recovery.md)
- [PM9 operational ownership](docs/operational_ownership.md)
- [PM9 known-limitations acceptance](docs/known_limitations_acceptance.md)
- [Product Milestone 9 release](docs/releases/product_milestone_9.md)
- [Demo script](docs/demo_script.md)
- [Interview notes](docs/interview_notes.md)
- [Troubleshooting](docs/troubleshooting.md)
- [CV bullets](docs/cv_bullets.md)

## Current decomposition checkpoint

The current decomposition keeps `src/composition/copilot.py` as the shared
Copilot composition root; `src/application/copilot_factory.py` is a historical
compatibility import. Canonical RAG code has no API reverse dependency. The
first four frontend hotspots remain feature-owned behind their historical
component re-export paths.

Ticket application ownership is explicit under
`src/ticket_management/application/`: intake, assignment, named lifecycle
actions, SLA administration/runtime, and escalation are collaborators behind
the stable `TicketWorkflowService` facade.

Maintenance application intent is now capability-owned under
`src/maintenance_management/application/`: preventive plans, work-order
planning, lifecycle/checklists, completion/verification, preventive generation,
calendar/metrics reporting, templates, evidence, and read queries. The stable
`MaintenancePlanningService` facade preserves all 34 public signatures and its
historical module bindings. `PostgresMaintenancePlanningRepository` remains the
sole transaction owner for row locks, optimistic versions, occurrence
uniqueness, maintenance-log/asset-date coupling, audit/outbox writes,
commit/rollback, and exception mapping. Inventory stock-changing families and
the transaction-heavy PostgreSQL repository methods remain deliberately intact.

The reliability pilot contract is organized by capability. Deployment
declarations live under `pilot_contract/deployment_manifest/`; runtime
environment checks live under `runtime_environment/`; release-record checks
live under `release_record/`; deployment runtime/retry/recovery policy lives
under `runtime_policy/`; and ownership, escalation, and limitation validation
lives under `operational_governance/`. `manifest.py`, `environment.py`,
`release.py`, `runtime.py`, and `ownership.py` preserve ordered orchestration or
historical private bindings. The former broad `support.py` owner is gone;
finding, document-shape/value/safety, path, and evidence contracts now have
narrow names. FastAPI health routes, the PM7 runtime catalog, worker, and durable
operations state are unchanged.

The historical `src/reliability/drills.py` import surface is a 65-line facade
over `operator_drills/`. The backup publication lock/index atomicity and
attachment archive/restore integrity boundaries remain intact; no database or
application record mutation moved.

`load_harness.py` is an 81-line historical facade. Under `reliability/load/`,
profile and step workflows each retain one complete scheduling/cancellation
loop; request contracts, HTTP sampling, telemetry, safety, report projection,
report storage, execution limits, and CLI wiring have explicit owners. Live
stop state, deadlines, sampling, and HTTP order are unchanged.

`post_start_validation.py` is a 33-line historical facade. The `post_start/`
package separates no-network preflight, environment input, report contracts,
HTTP/session helpers, response contracts, atomic evidence storage, and CLI
wiring. Its 534-line runner deliberately retains the exact ordered checks and
unconditional three-client logout/revocation cleanup as one stateful boundary.
Transaction-heavy repositories remain complete atomic owners.

Capability tests now mirror production under `tests/reliability/`; the
organization/split preserved exactly 719 collected tests. Current validation
evidence, including full backend and isolated PostgreSQL results, is recorded
in `docs/COMPANY_HANDOVER.md`. See
[`docs/application-services.md`](docs/application-services.md) and
[`docs/backend-structural-inventory.md`](docs/backend-structural-inventory.md)
for the ownership map; do not treat older milestone paragraphs as current
validation evidence.

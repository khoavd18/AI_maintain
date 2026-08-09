# Product Milestone 7: Background Operations Và In-App Notifications

## Trạng Thái Release

Product Milestone 7 bổ sung operational foundation cho internal pilot:
PostgreSQL-backed worker, transactional outbox, in-app notifications, bounded
retry/dead-letter, operator controls và safe health/metrics/logging.

Release không thay đổi PM1-PM6 API contracts, analytics formulas, ticket/work
order lifecycle, inventory balance rules hoặc RAG thresholds. Đây không phải
production-readiness certification.

## Architecture Decisions

- PostgreSQL là authority cho schedule, execution, lease, outbox, delivery
  attempt, notification, alert cycle và heartbeat.
- Một worker độc lập tại `src/operations/worker.py`; FastAPI startup không chạy
  scheduler.
- `src/operations/domain.py` là closed catalog cho bốn jobs và selected events.
- Worker chỉ gọi existing canonical services; không có arbitrary cron/code,
  generic workflow designer hoặc business domain mới.
- Business mutation và selected outbox event commit trong cùng transaction.
- Notification chỉ in-app và owner-isolated; không có email, SMS, push hoặc
  webhook.

## Migration Và Schema

Alembic revision `20260726_0007` kế tiếp `20260723_0006` tạo:

| Table | Vai trò chính |
|---|---|
| `scheduled_jobs` | Fixed job definition, enable state, interval, run-as actor, retry/lease policy |
| `job_executions` | Durable lifecycle, attempt, worker lease, summary, safe error, idempotency |
| `outbox_events` | Same-transaction event, bounded payload/hash, claim/retry/dead letter |
| `outbox_delivery_attempts` | Append-only attempt history |
| `notifications` | Per-user in-app record, read/dismiss/version/dedup |
| `notification_alert_states` | Low-stock recovery/re-alert cycle |
| `worker_heartbeats` | Worker readiness và current execution signal |

Migration thêm FK, check/unique constraints, claim/history indexes và
append-only PostgreSQL trigger cho delivery attempts. Bốn jobs được seed
disabled. Downgrade xóa toàn bộ PM7 operational history và phải được backup
trước.

## Worker Và Retry

Worker:

- fail fast khi PostgreSQL/schema không ready;
- bounded poll và batch;
- materialize/claim bằng `FOR UPDATE SKIP LOCKED`;
- `forbid_overlap` cho cùng job;
- renew long-running lease và recover expired lease;
- persist success summary hoặc safe failure;
- exponential bounded retry;
- dead-letter khi hết configured attempts;
- graceful SIGINT/SIGTERM;
- JSON structured logs với correlation ID và allow-listed fields.

Manual trigger/retry tạo persisted execution, yêu cầu caller-stable
`Idempotency-Key` và không chạy trong API request. Retry tạo record mới; dead
history cũ giữ nguyên.

## Supported Jobs

| Job | Existing behavior reused | Boundary |
|---|---|---|
| `preventive_generation` | Bounded recurrence + unique plan/due work order | Không đổi WO lifecycle |
| `sla_escalation` | Business-calendar SLA + idempotent escalation | Không auto-resolve ticket |
| `analytics_refresh` | Snapshot, feature, anomaly, risk và reports | Staging + atomic publication; giữ last valid output khi fail |
| `inventory_reorder_detection` | Canonical available/reorder derivation | Không đổi stock hoặc tạo purchase order |

Low-stock event chỉ phát ở đầu alert cycle; recovery rồi low-stock lại mới
eligible.

## Transactional Outbox

Selected events:

- critical ticket created;
- ticket assigned, held, resumed;
- SLA warning, breach, escalation;
- work order assigned/completed awaiting verification;
- preventive work orders generated;
- inventory issue completed;
- inventory stock below reorder;
- analytics refresh terminal failure.

Payload theo explicit schema, tối đa 16 KiB, có hash/idempotency và loại
credential, token, cookie, reporter PII, storage path/file bytes. Outbox API
không expose payload. Consumer tạo per-recipient deduplicated notification và
append-only attempt.

## Notifications Và Recipients

- Assignment events đến assigned user.
- Ticket SLA/critical events đến relevant manager/engineer/admin roles và
  assignee khi có.
- Work-order assignment đến technician; completion đến Property Manager/Chief
  Engineer.
- Inventory events đến Storekeeper và relevant issued user.
- Low-stock đến Administrator/Chief Engineer/Storekeeper.
- Analytics terminal failure đến Administrator/Property Manager.

Mọi role có thể đọc/mutate inbox của chính mình. Administrator operator quyền
không cấp generic cross-user inbox. Notification có Vietnamese title/body,
severity, read/unread/dismiss và related-entity link.

## API Và Frontend

Additive health:

```text
GET /health/live
GET /health/ready
GET /health/worker
```

Additive notifications:

```text
GET  /notifications
GET  /notifications/unread-count
POST /notifications/{id}/read
POST /notifications/{id}/unread
POST /notifications/{id}/dismiss
POST /notifications/read-all
```

Administrator operations:

```text
GET   /operations/jobs
PATCH /operations/jobs/{job_key}
POST  /operations/jobs/{job_key}/trigger
GET   /operations/executions
POST  /operations/executions/{id}/retry
GET   /operations/outbox
GET   /operations/metrics
```

Next.js thêm notification bell, `/notifications` và `/admin/jobs`. UI có
loading/empty/error/unauthorized state, filters, versioned actions, execution
history, safe trigger/retry và outbox/health metrics. Frontend không duy trì job
catalog hoặc recipient rules riêng.

## Docker Và Commands

Root `Dockerfile` chạy worker package. Docker Compose thêm opt-in `worker`
profile, PostgreSQL health dependency và heartbeat health check. Local commands:

```powershell
python -m src.operations.worker
python -m src.operations.worker --once
python -m src.operations.cli status
python -m src.operations.cli trigger <JOB> --idempotency-key <KEY>
python -m src.operations.cli retry <EXECUTION_ID> --idempotency-key <KEY>
```

Make targets tương ứng: `run-worker`, `worker-once`, `run-job`,
`set-job-enabled`, `retry-job`, `job-status`, `worker-docker-up` và
`worker-docker-down`.

## Compatibility

- Legacy `GET /health` contract giữ nguyên.
- Existing PM1-PM6 endpoints/schemas giữ nguyên.
- Ticket/work-order lifecycle vẫn độc lập.
- Work-order/inventory operations không tự đổi ticket status.
- Inventory vẫn dùng `available = on_hand - reserved`; reorder detection không
  ghi stock.
- Ticket/log write không trigger immediate analytics refresh.
- Analytics tests publish ngoài canonical path.
- Canonical demo reset xóa PM7 runtime rows và disable job catalog có chủ đích.

## Verification Ngày 2026-07-26

Verification thực tế trên current revision:

- PM7 focused backend: `6 passed` pure tests và `8 passed` PostgreSQL
  integration tests; targeted PM4-PM6/auth regressions: `73 passed`.
- Full backend với isolated database `maintenance_copilot_test`: `238 passed`;
  Ruff, `git diff --check` và documentation link test đều đạt. Còn một
  `StarletteDeprecationWarning` đã biết từ test client.
- Frontend PM7 focused: `6 passed`; full frontend: `112 passed` trên 17 test
  files. ESLint đạt và Next.js production build tạo thành công 32 pages, gồm
  `/notifications` và `/admin/jobs`.
- Isolated PostgreSQL upgrade sạch từ base đến `20260726_0007`, downgrade PM7
  về `20260723_0006` rồi re-upgrade đều đạt. `alembic current` xác nhận head và
  `alembic check` không phát hiện model drift.
- API import, legacy/additive health, worker startup, one-iteration worker,
  Docker worker health, manual SLA trigger idempotency, outbox delivery,
  notification ownership/actions và hai frontend routes đều smoke thành công.
  One-iteration worker kết thúc với heartbeat `stopping`, không để lại
  false-ready state.
- Analytics job test publish vào temporary path, giữ last-valid output khi
  failure và không đổi canonical analytics files.
- PostgreSQL restart giữ nguyên revision, 27 assets, 44 tickets, 87 maintenance
  logs và bốn fixed job definitions. Pending execution, outbox, notification và
  heartbeat records đều được cleanup về 0.
- Secret scan không tìm thấy private key hoặc high-confidence token. Các
  credential-shaped URL còn lại chỉ là non-secret local defaults/test fixtures.
  Unsafe-path scan không tìm thấy hard-coded host path; runtime-artifact scan
  không tìm thấy log, dump, snapshot hoặc temporary PM7 file.

Đây là local internal-pilot verification trên synthetic data, không phải
production, security, availability, SLA-performance hoặc business-impact
certification.

Product Milestone 8 chưa bắt đầu. PM7 chỉ hoàn tất nền tảng operational cho
internal pilot trong phạm vi release này.

## Remaining Risks

- Worker là single PostgreSQL polling architecture, chưa có HA, autoscaling,
  partitioning hoặc load test.
- Job catalog dùng fixed interval, chưa có production calendar/missed-run
  operations.
- Outbox dead-letter chưa có generic redrive API; operator cần điều tra theo
  runbook.
- Notification chỉ in-app, chưa có preferences, acknowledgement hoặc external
  delivery.
- Health/metrics/logging chưa có centralized collector hoặc alert routing.
- Local authentication, local attachment storage, secret rotation, backup/PITR
  và failover vẫn là internal-pilot gaps.
- Không có production readiness, availability, security, SLA-performance hoặc
  business-impact claim.

## Rollback

1. Dừng worker.
2. Backup PostgreSQL và private attachment bytes.
3. Xác nhận không còn PM7 client phụ thuộc additive endpoints.
4. Chạy `alembic downgrade 20260723_0006`.
5. Deploy PM6 API/frontend code.

Downgrade xóa PM7 jobs, execution/outbox histories và notifications. PM1-PM6
business records không bị migration PM7 sửa hoặc xóa.

## Out-Of-Scope Confirmation

PM7 không thêm procurement, supplier, accounting/valuation, lot/serial/barcode,
inventory optimization, external notification delivery, multi-tenancy, SSO,
MFA, Kubernetes, cloud deployment, generative LLM, automatic ticket resolution,
automatic work-order completion hoặc arbitrary executable jobs.

PM8 chưa bắt đầu trong release này.

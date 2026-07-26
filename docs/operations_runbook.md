# Operations Runbook

## Mục Tiêu

Runbook này dành cho local/internal-pilot operator của PM7. Nó không thay thế
backup policy, incident response hoặc SRE runbook cấp production.

## Startup Chuẩn

```powershell
docker compose up -d postgres qdrant
python -m alembic upgrade head
python -m alembic current
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
python -m src.operations.worker
npm --prefix frontend run dev
```

Worker có thể chạy trong Docker profile riêng:

```powershell
docker compose --profile worker up -d --build worker
```

Không chạy đồng thời local worker và Docker worker trừ khi đang kiểm tra
concurrent claim. Nhiều worker an toàn ở claim boundary, nhưng internal pilot
chưa có capacity/HA sizing.

## Preflight

1. `GET /health/live` phải trả `200` và `{"status":"alive"}`.
2. `GET /health/ready` phải báo `database_ready=true`.
3. Sau khi worker chạy, `GET /health/worker` phải có `ready=true` và age dưới
   `WORKER_HEARTBEAT_STALE_SECONDS`.
4. Administrator mở `/admin/jobs`, xác nhận bốn fixed jobs và không có unexpected
   executable configuration.
5. Kiểm tra `/operations/metrics`: pending/dead-letter counts và oldest outbox
   age.

Legacy `GET /health` vẫn giữ contract cũ để không phá client.

## Enable Hoặc Disable Job

Job được seed disabled. Qua Next.js `/admin/jobs`, protected API hoặc CLI:

```powershell
python -m src.operations.cli set-enabled preventive_generation `
  --enabled true --expected-version 1 `
  --actor-username admin.local
python -m src.operations.cli status --actor-username admin.local
```

Enable snapshot Administrator làm run-as actor. Không disable account đó khi job
còn cần chạy. Disable ngăn scheduled claim mới; nó không kill execution đang
chạy.

## Manual Trigger

```powershell
python -m src.operations.cli trigger sla_escalation `
  --idempotency-key "pilot-sla-20260726-01" `
  --actor-username admin.local
```

Key phải ổn định cho cùng operator intent. Replay cùng key trả execution đã có.
Manual trigger chỉ nhận một trong bốn job keys và tạo `pending` execution; worker
mới thực thi.

## Safe Retry

1. Xem safe error code/summary, execution attempt và related service health.
2. Sửa nguyên nhân: database, source file, permission, active run-as actor hoặc
   output path.
3. Không sửa row bằng SQL.
4. Retry `failed`/`dead_lettered` execution bằng key mới cho operator intent:

```powershell
python -m src.operations.cli retry <EXECUTION_UUID> `
  --idempotency-key "retry-<EXECUTION_UUID>-01" `
  --actor-username admin.local
```

Retry tạo execution mới; history cũ giữ nguyên. Không retry liên tục khi nguyên
nhân chưa được khắc phục.

## Worker Downtime

Scheduled definitions, next run, pending executions và outbox đều nằm trong
PostgreSQL. Sau downtime:

1. xác nhận PostgreSQL đã healthy và migration ở head;
2. khởi động đúng một worker;
3. kiểm tra heartbeat;
4. worker tự recover expired execution/outbox leases;
5. theo dõi pending count và oldest outbox age giảm;
6. kiểm tra skipped occurrences do `forbid_overlap`;
7. xác nhận latest valid analytics outputs trước khi cho phép refresh.

Worker không backfill vô hạn preventive plans; canonical recurrence service vẫn
giữ 366-day catch-up bound và paused-backlog policy.

## Dead-Letter Triage

### Job execution

- Filter `status=dead_lettered` tại `/operations/executions`.
- Xem job key, attempt, timestamps, correlation ID và safe error.
- Kiểm tra structured log theo correlation ID.
- Retry bằng action/API/CLI sau khi khắc phục.

### Outbox

- Filter `status=dead_lettered` tại `/operations/outbox`.
- API cố ý không trả payload.
- Xác minh event type có trong closed catalog và active recipient data hợp lệ.
- Không update/delete outbox hoặc append-only attempt history.
- PM7 chưa có generic operator redrive endpoint cho outbox dead letter; cần điều
  tra database/service và thực hiện correction có kiểm soát trong milestone sau.

## Analytics Failure

Analytics job chạy hoàn toàn trong staging. Failure phải giữ nguyên directory
output hợp lệ gần nhất và tạo notification sau khi execution dead-lettered.

Kiểm tra:

- `ANALYTICS_SOURCE_DIR` có canonical raw sensor/document CSV;
- `ANALYTICS_PROCESSED_DIR` không phải repository/filesystem root và khác source;
- process có quyền tạo staging/rename trong parent directory;
- không có execution analytics khác đang running;
- row counts và timestamps trong execution summary.

Không copy partial staging files vào output.

## Backup Và Restore

Trước migration, enable job hoặc demo reset:

```powershell
docker compose exec postgres pg_dump `
  -U maintenance -d maintenance_copilot -Fc `
  -f /tmp/maintenance_copilot.dump
docker cp maintenance_postgres:/tmp/maintenance_copilot.dump `
  .\maintenance_copilot.dump
```

Backup file phải nằm ngoài repository và được bảo vệ theo chính sách công ty.
Local attachment bytes dưới `ATTACHMENT_STORAGE_ROOT` cần backup riêng; PostgreSQL
dump chỉ chứa metadata.

Restore phải dùng database riêng trước:

```powershell
docker cp .\maintenance_copilot.dump `
  maintenance_postgres:/tmp/maintenance_copilot.dump
docker compose exec postgres createdb -U maintenance maintenance_restore
docker compose exec postgres pg_restore `
  -U maintenance -d maintenance_restore --clean --if-exists `
  /tmp/maintenance_copilot.dump
```

Sau restore, chạy `alembic current`, row-count checks, attachment checksum checks
và worker `--once` trước khi chuyển traffic. Xóa bản tạm trong container sau khi
đã xác nhận backup/restore.

## Migration Và Rollback

```powershell
python -m alembic upgrade 20260726_0007
python -m alembic current
python -m alembic check
```

Downgrade PM7:

```powershell
python -m alembic downgrade 20260723_0006
```

Downgrade xóa job, execution, outbox, attempt, notification, alert-state và
heartbeat tables. Phải backup trước; notification/history PM7 không thể phục hồi
từ PM1-PM6 tables. Dừng worker trước downgrade. API PM1-PM6 contracts vẫn là
rollback boundary.

## Canonical Demo Reset

`python -m src.ingestion.load_data --replace` là destructive development/demo
action. PM7 reset xóa runtime heartbeat, execution, outbox, attempt,
notification và alert-cycle rows rồi disable job catalog trước khi khôi phục
canonical `27/42/86`. Nó không backup attachment bytes.

## Shutdown

1. Gửi `Ctrl+C`/SIGTERM cho local worker và chờ log `worker.stopped`.
2. Dừng API/frontend.
3. Với Docker: `docker compose --profile worker stop worker`, sau đó
   `docker compose stop`.
4. Không dùng kill cưỡng bức trừ khi process treo; lease recovery sẽ xử lý
   unfinished work khi worker khởi động lại.

## Escalation Boundary

Health/metrics hiện là JSON API và structured local logs. Không có Prometheus,
central log sink, email/SMS alert, automatic failover hoặc on-call integration.
Dead-letter và stale heartbeat cần Administrator chủ động kiểm tra.

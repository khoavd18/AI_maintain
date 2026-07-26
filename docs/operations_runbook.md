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
- Sau khi sửa nguyên nhân, Administrator dùng PM8 audited redrive với stable
  idempotency key; API/CLI chỉ ghi intent, existing worker mới deliver.

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

Trước migration, enable job hoặc demo reset, tạo và restore-validate backup vào
database riêng. Output bắt buộc ngoài repository:

```powershell
$backupDir = Join-Path $env:TEMP "maintenance-pm8-backup"
$env:PM8_ALLOW_DESTRUCTIVE_TESTS = "true"
python -m src.reliability.backup_restore `
  --restore-database maintenance_pilot_restore `
  --output-dir $backupDir `
  --docker-container maintenance_postgres
```

Backup file phải nằm ngoài repository và được bảo vệ theo chính sách công ty.
Local attachment bytes dưới `ATTACHMENT_STORAGE_ROOT` cần backup riêng; PostgreSQL
dump chỉ chứa metadata.

Module tự checksum, restore vào database `_restore`, đối chiếu revision/count/
integrity, chạy restored FastAPI health smoke và drop restore database trong
`finally`. Attachment bytes vẫn cần backup/restore/checksum riêng. Xóa archive
và manifest tạm sau khi evidence đã được ghi vào approved release/incident
record.

## Migration Và Rollback

```powershell
python -m alembic upgrade 20260726_0008
python -m alembic current
python -m alembic check
```

Quiesce API và worker trước khi downgrade riêng PM8 về PM7:

```powershell
python -m alembic downgrade 20260726_0007
```

Downgrade này xóa PM8 redrive/backup-validation evidence và alert types, nhưng
giữ PM1–PM7 business/operations tables. PM8-only redrive-cycle attempts bị xóa;
unfinished non-alert redrive trở lại `dead_lettered` với PM7-compatible attempt
history. Backup trước khi downgrade, rồi revalidate revision, API/worker
readiness, dead-letter và PM1–PM7 invariants trước khi mở traffic.

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

## PM8 Incident Index

PM8 giữ nguyên worker/job catalog và bổ sung procedure tại
[failure recovery](failure_recovery.md), [backup/restore](backup_restore.md) và
[secret rotation](secret_rotation.md).

| Tình huống | Phát hiện | Hành động đầu tiên | Recovery gate |
|---|---|---|---|
| API unavailable | liveness timeout/fail | Kiểm tra process, safe log và PostgreSQL; restart API | Login, protected read, readiness pass; worker không duplicate |
| Worker unavailable | heartbeat missing/stale | Kiểm tra database, lease và process; start đúng một worker | heartbeat ready, lease recovered, backlog drain |
| PostgreSQL unavailable | readiness 503/degraded, worker safe error | Dừng test mutation, kiểm tra container/disk/credential | reconnect, revision/count/pending work giữ nguyên |
| Stuck job | running quá lease | Không sửa SQL; kiểm tra worker/lease | retry/dead-letter đúng policy, không duplicate business effect |
| Outbox backlog | pending/oldest age vượt threshold | Dừng fixture, kiểm tra worker/recipient/catalog | pending và age giảm trong measured window |
| Dead letter | dead-letter count > 0 | Sửa nguyên nhân, dùng audited redrive | processed; notification không duplicate |
| Analytics failure | failed execution/stale age | Giữ last-valid; kiểm tra source/temp permission | isolated full publish, no partial promotion |
| Failed backup | dump/checksum/restore fail | Không dùng archive; kiểm tra disk/tool/permission | backup mới restore-validate hoàn toàn |
| Restore validation fail | revision/count/integrity mismatch | Không chuyển traffic; drop restore DB | rerun bằng archive/database mới |
| Secret rotation | auth/readiness fail | Giữ old key trong previous slot hoặc rollback env | login/access/refresh/logout pass |
| Notification backlog | outbox/inbox tăng bất thường | Kiểm tra attempt, recipient và retry storm | drain, dedup và owner isolation pass |
| Disk warning | host/container disk monitor | Dừng extended artifact generation | database/attachment write và backup smoke pass |
| Attachment issue | integrity count khác 0 | Không xóa; đối chiếu metadata/backup/checksum | missing/mismatch bằng 0, download pass |

Operational alert evaluation là action explicit, không phải job thứ năm:

```powershell
python -m src.operations.cli evaluate-alerts --actor-username admin.demo
```

Alert deduplicate theo type/entity/cycle và tạo raised/recovered notification qua
outbox. Khi PostgreSQL hoặc worker down, in-app alert không thể đến ngay; health
probe và incident contact path vẫn là detection boundary.

## PM8 Outbox Redrive

Sau khi event `dead_lettered` và nguyên nhân đã được sửa:

```powershell
python -m src.operations.cli retry-outbox <EVENT_UUID> `
  --idempotency-key "redrive-<EVENT_UUID>-01" `
  --actor-username admin.demo
```

Action khóa event, ghi append-only request + audit, mở một bounded attempt cycle
mới và không deliver trong API/CLI process. Replay cùng key trả cùng intent; key
khác khi event không còn dead-letter bị reject. Delivery attempt cũ không bị sửa.

Không mở pilot nếu [checklist](internal_pilot_checklist.md) còn gate bắt buộc chưa
có current-revision evidence. PM7 historical result không thay PM8 evidence.

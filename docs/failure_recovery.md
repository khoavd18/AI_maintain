# PM8–PM9 Failure And Recovery Drills

## Guardrails Chung

Chỉ chạy trên isolated `_test` database và temporary analytics/output paths.
Extended/destructive drill cần `PM8_ALLOW_DESTRUCTIVE_TESTS=true`. Ghi timestamp,
process/container identity, backlog/lease trước-sau và cleanup evidence. Không
kill developer data hoặc canonical output.

## Worker Termination Trong Job

1. Tạo manual execution bằng stable idempotency key trên `_test`.
2. Cho worker A claim; ghi execution ID, attempt và lease expiry.
3. Terminate worker A sau claim.
4. Xác nhận execution vẫn `running`, không có partial business effect.
5. Sau lease expiry, chạy worker B `--once`.
6. Xác nhận recovery count tăng; execution retry-scheduled hoặc dead-letter đúng
   max attempts; chạy tiếp sau `available_after`.
7. Xác nhận unique domain boundaries ngăn duplicate work order/SLA event.

Không rút ngắn lease trong developer database. Test tự động có thể truyền
timestamp tương lai vào repository trên database `_test`.

Checkpoint đã test deterministic lease recovery nhưng chưa kill live worker ở
đúng instruction boundary của một business mutation.

## Worker Termination Trong Outbox

1. Tạo allow-listed event, worker A claim nhưng chưa deliver.
2. Terminate A.
3. Sau outbox lease, worker B recover.
4. Xác nhận append-only failed attempt `lease_expired`, backoff và claim lại.
5. Deliver; notification unique theo recipient/dedup key.

## PostgreSQL Interruption

1. Ghi revision/counts/backlog và đảm bảo API/worker dùng test database.
2. `docker compose stop postgres`.
3. `/health/live` có thể còn alive; `/health/ready` phải fail/degrade an toàn,
   không trả stack/credential. Worker log chỉ có safe error.
4. `docker compose start postgres`; chờ `pg_isready`.
5. API/worker phải reconnect nhờ `pool_pre_ping`; pending work còn nguyên.
6. Xác nhận revision/counts/backlog và chạy worker `--once`.

## API Interruption

Terminate API trong khi worker đang chạy. Heartbeat/job/outbox phải tiếp tục.
Khởi động API lại không được tạo execution vì API lifespan không có scheduler.

## Analytics Publication Failure

Chạy với temporary target đã có last-valid file; inject controlled rename failure.
Target cũ phải được restore, staging bị cleanup, execution failure persisted và
operator có thể retry sau khi sửa nguyên nhân. Không trỏ drill vào
`data/processed`.

## Outbox Backlog/Dead Letter

- Pause worker, tạo bounded fixture events, ghi pending count/oldest age.
- Resume worker và đo drain time.
- Unsupported fixture event trên `_test` tạo retry theo 30/60/120/240 giây rồi
  dead-letter ở attempt 5.
- Sửa nguyên nhân; dùng protected retry:

```powershell
python -m src.operations.cli retry-outbox <EVENT_UUID> `
  --idempotency-key "pm8-redrive-<EVENT_UUID>-01"
```

Concurrent key khác bị conflict sau khi event rời dead-letter; replay cùng key trả
cùng result. Không update delivery attempt history và không infinite replay.

## Cleanup

Stop API/worker/frontend; xóa test fixtures bằng isolated fixture/reset, drop
restore database, xóa temporary report/dump/log/output và xác nhận canonical data
hash không đổi.

Structured JSON log dùng Unicode escape ASCII-safe. Windows redirected output
không được phát raw traceback/local path khi PostgreSQL unavailable.

## PM9 Evidence Boundary

PM9 thêm testable safety helpers và rehearsal procedures nhưng current
workstation không phải intended pilot host. Trạng thái không được suy ra từ
unit test:

| Drill | Prior/local evidence | PM9 live result |
|---|---|---|
| Job lease recovery | PM9 real PostgreSQL connection termination trong blocked completion, lease recovery và một execution row đã pass trên disposable PostgreSQL 16 `_test` | Live worker-process kill trong scheduled execution chưa chạy |
| Outbox lease/delivery recovery | PM9 real PostgreSQL connection termination, lease recovery, failed+succeeded attempts và đúng một notification đã pass | Live worker-process kill giữa claim và delivery chưa chạy |
| Business transaction atomicity | PM9 connection termination sau flush xác nhận ticket và required outbox cùng rollback | Supporting-process kill đúng service mutation boundary chưa chạy |
| PostgreSQL interruption | `73 passed, 239 deselected` trên disposable local PostgreSQL 16 `_test`; PM8 restart evidence vẫn historical | PM9 pilot Compose/pilot host chưa chạy |
| Backup failure | Local disposable `_test`: valid `pg_dump` exit `0`, invalid-database exit `2`, last-good index unchanged và không còn partial artifact | Controlled real `pg_dump` failure trên approved host/service account chưa chạy |
| Disk warning | PM9 injected warning/critical/dedup/recovery tests | Không có host/durable in-app disk alert rehearsal |
| Secret rotation | PM8 synthetic current/previous key tests | Real pilot signing/database rotation và rollback chưa chạy |
| Attachment recovery | PM9 authorized non-empty API upload/archive/restore/download test pass trên original `_test` metadata | Paired PostgreSQL dump + metadata/bytes restore chưa chạy |
| Release rollback | Contract metadata tests | PM9→PM8→PM9 rehearsal chưa chạy |

Quyết định vẫn là:

```text
NO-GO / NOT YET VERIFIED
```

## Exact Worker-Termination Acceptance

Mỗi scenario phải dùng isolated records, capture execution/event/lease ID trước
kill và không dùng developer data.

### Scheduled job

- worker A claim controlled execution;
- terminate đúng lúc execution đang `running`;
- heartbeat trở thành stale/stopping theo observed process state;
- lease expire và worker B recover;
- history thể hiện interruption/recovery;
- unique domain key ngăn duplicate work order/SLA/notification.

### Outbox

- worker A claim allow-listed event nhưng chưa deliver;
- terminate A;
- append-only `lease_expired` attempt còn nguyên;
- event available sau backoff;
- worker B xử lý một lần;
- đúng một intended notification/effect.

### Business transaction

- terminate supporting process tại controlled transaction boundary;
- transaction commit toàn bộ hoặc rollback toàn bộ;
- không partial inventory movement, ticket/work-order mutation;
- không orphan outbox và không business mutation thiếu required outbox.

Ba PM9 test đã gọi `pg_terminate_backend` trên đúng một uniquely named connection
trong disposable `_test` database và pass. Chúng chứng minh PostgreSQL
connection-loss boundaries nêu trên. Chúng không terminate OS worker process,
không quan sát heartbeat của live worker A/B và không thay thế ba live-process
scenario trong section này.

Không đánh dấu live worker-process gate pass nếu chỉ dựa trên connection
termination hoặc repository timestamp coordination.

## Disk Warning Drill

Không tạo large filler file. Injected provider phải cover:

1. healthy → warning;
2. repeated warning không raise duplicate;
3. warning → critical;
4. repeated critical theo bounded escalation policy;
5. critical/warning → healthy recovery.

Report chỉ chứa aggregate capacity percentage/state/action code, không local
path. Current PM9 helper là in-memory synthetic state machine; nó chưa ghi
durable alert/outbox. Vì vậy test pass không thay thế external host monitor và
incident-path rehearsal.

## Release Failure

Nếu migration/startup/health/authenticated smoke fail:

1. không mở traffic;
2. stop application writers;
3. giữ volumes và protected evidence, không `down -v`;
4. xác minh last-good backup;
5. application rollback về exact PM8 commit/tag ở revision
   `20260726_0008`;
6. restore chỉ khi compatibility/integrity yêu cầu và owner approve;
7. re-run auth/RBAC/worker/outbox/data checks;
8. sau approved evidence retention, xóa đúng các raw artifact paths được tạo bởi
   rehearsal và xác nhận từng path; không dùng generic recursive cleanup.

Xem [pilot deployment](pilot_deployment.md),
[release rehearsal](pilot_release_rehearsal.md),
[backup schedule](pilot_backup_schedule.md) và
[attachment recovery](pilot_attachment_recovery.md).

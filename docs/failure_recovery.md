# PM8 Failure And Recovery Drills

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

# Internal Pilot Reliability Validation

## Phạm Vi

Product Milestone 8 xác định operating envelope cho internal pilot của PM1–PM7.
Đây là validation và hardening có giới hạn, không phải chứng nhận production
readiness. PostgreSQL vẫn là transactional authority; FastAPI vẫn là
authorization boundary; `src/operations/worker.py` vẫn là worker duy nhất và chỉ
thực thi bốn job đã có.

PM8 không thêm business domain, external notification, queue/cache mới, cloud,
Kubernetes, SSO/MFA hoặc real-time processing.

## Reliability Inventory Trước PM8

Đã có transaction/constraint PostgreSQL, optimistic version, append-only trigger,
idempotency, `FOR UPDATE SKIP LOCKED`, lease, retry/dead-letter, atomic analytics
publication, owner-isolated notification và structured safe logging.

Khoảng trống đã xác nhận:

- SQLAlchemy dùng pool mặc định 5 + overflow 10 + wait 30 giây nhưng chưa cấu hình
  rõ; PostgreSQL chỉ có connect timeout 5 giây, chưa có statement/lock/idle
  transaction timeout.
- Chưa có authenticated load harness, soak/recovery profile hoặc capacity result.
- Backup/restore chỉ có lệnh runbook, chưa có checksum/manifest/restore validator.
- JWT chỉ verify một signing key.
- Chưa có operator redrive an toàn cho outbox dead letter.
- Chưa có alert cycle cho heartbeat, backlog, dead letter, analytics và backup.
- Attachment storage chưa có read-only metadata/byte reconciler.

## PM8 Controls

- Connection pool values được cấu hình tường minh nhưng giữ nguyên giá trị
  SQLAlchemy trước đó: size `5`, overflow `10`, pool wait `30s`.
- Thêm safety bounds: statement `30s`, lock `5s`, idle transaction `60s`. Đây là
  bounded-failure hardening vì trước PM8 các query/lock không có application
  timeout; không phải tuning theo throughput.
- API metrics là process-local, bounded 10.000 samples và không có path/user labels.
- Operational metrics thêm pool use, lease counts, retries, notifications, active
  alerts và backup-validation age.
- Dead-letter outbox redrive cần Administrator + caller-stable idempotency key,
  khóa row, tạo append-only intent và audit trong cùng transaction. Mỗi redrive có
  tối đa 5 delivery attempts mới; không có infinite replay.
- Operational alert evaluation là action API/CLI explicit. Nó không trở thành job
  thứ năm. Raised/recovered events đi qua transactional outbox và chỉ gửi in-app
  cho Administrator.
- Một previous JWT key có thể verify tạm thời; token mới luôn ký bằng current key.
- Backup drill restore vào database riêng kết thúc `_restore`, so khớp revision,
  critical row counts/integrity và luôn drop database restore trong `finally`.
- Attachment assessment chỉ đọc, không xóa file và chỉ trả aggregate counts.

## Metrics An Toàn

`GET /operations/metrics` không trả credential, payload, exception hoặc local
path. Process-local request metrics không tổng hợp nhiều API process; đây là giới
hạn internal pilot, không phải centralized observability.

## Executed Evidence

Checkpoint 2026-07-26 đã rerun bounded baseline/stress, focused PM8 và PM4–PM7
regression, full backend/frontend/static/build, clean/populated migration
rollback, API/worker/database interruption, protected redrive, alert recovery và
isolated backup/restore smoke trên disposable `_test` stack.

Exact measurements, backup checksum, pass/fail details và historical-vs-current
boundary nằm trong [PM8 release note](releases/product_milestone_8.md). Raw load
report, log, dump, manifest và frontend build output nằm ngoài canonical data và
được xóa sau validation. PM7 result hoặc PM8 report cũ không được tự động coi là
current checkpoint evidence.

## Unverified Risks

- Một API node, một polling worker và một PostgreSQL instance không có HA.
- Không có automated PITR, failover, centralized metrics/logging hoặc external
  alert delivery.
- Database-down alert không thể được persist trong chính PostgreSQL lúc database
  đang unavailable. Health probe phải phát hiện; alert cycle được đánh giá sau
  recovery.
- Local attachment bytes cần backup riêng và chưa có malware scanning.
- Operating limits chỉ áp dụng đúng test environment/profile đã ghi; không ngoại
  suy sang production.
- Soak, load-to-first-failure, mutation-bearing load, exact live mutation kill,
  disk-warning drill, real pilot-secret rotation và representative non-empty
  attachment restore chưa chạy.

Xem [load test plan](load_test_plan.md), [failure recovery](failure_recovery.md),
[backup/restore](backup_restore.md) và
[internal-pilot checklist](internal_pilot_checklist.md).

# PM9 Pilot Backup Schedule

## Boundary

PM9 hỗ trợ operator/OS-level schedule cho logical PostgreSQL backup. Module
`src.reliability.backup_schedule` không phải scheduler, không chạy trong API
startup và không thêm job thứ năm vào PM7 worker.

Backup scheduling, service account, destination và retention approval trên pilot
host chưa được cấu hình hay thực thi. PM8 manual backup/isolated restore là prior
evidence, không phải PM9 scheduled-backup evidence.

```text
Engineering implementation: COMPLETE
Local rehearsal: PARTIAL — local publication/failure boundary only
Real-company schedule and restore: BLOCKED — EXTERNAL DEPENDENCY
Overall: NO-GO / WAITING FOR PILOT SPONSOR
```

## Policy Record Cần Owner Điền

| Field | Current status |
|---|---|
| Company backup owner | `BLOCKED_EXTERNAL_DEPENDENCY`; future pilot sponsor phải assign |
| Service account/operator role | Unverified |
| Approved schedule | Unconfigured |
| Protected backup root | Unverified; không ghi absolute path vào Git |
| Retention | Candidate example ghi keep-count `7`; chưa được owner phê duyệt hoặc thực thi |
| Backup overdue threshold | 604.800 giây trong manifest |
| Restore database | Phải tách biệt và kết thúc `_restore`; integration test source riêng phải kết thúc `_test` |
| Attachment pairing | Bắt buộc nếu active metadata không rỗng |
| Incident channel | Unconfigured |

Exact frequency phải do owner chọn sao cho validation không vượt overdue
threshold. Repository không tự tạo Windows Task Scheduler task, cron entry hoặc
systemd timer.

## Scheduled Command

Populated `DATABASE_URL` và backup root chỉ tồn tại ở protected runtime
configuration:

```powershell
$env:PM9_ALLOW_SCHEDULED_BACKUP = "true"
python -m src.reliability.backup_schedule `
  --backup-root "<approved-outside-repository-root>" `
  --target-label "pilot" `
  --retention-keep-count 7 `
  --docker-container "<approved-postgresql-container>"
```

Nếu `pg_dump` có trên host, bỏ `--docker-container`. Target label chỉ là opaque
lowercase identifier, không dùng database name hay customer information.

Nếu được opt-in và thực thi với real `pg_dump`, command được thiết kế để:

- từ chối backup root trong repository;
- không đưa password vào generated command/report;
- stream dump vào partial path; sau khi tính checksum, publish artifact và
  metadata pair với tên immutable;
- thay thế nguyên tử chỉ con trỏ `latest-validated-backup.json` sau khi pair đã
  được đồng bộ và xác thực;
- verify artifact ngay sau publication;
- không publish invalid partial artifact;
- báo `restore_validated=false` cho đến khi separate restore drill pass.

Retention keep-count được validate và ghi vào report. Current command không tự
xóa archive cũ; pruning chỉ được thực hiện bởi approved operator sau khi xác
định last-good pairs. Không được diễn giải keep-count là retention đã được
enforce.

## Restore Validation

Scheduled dump chưa đủ để đóng backup gate. Theo định kỳ và trước release:

1. chọn một checksum-valid artifact pair;
2. restore vào database riêng kết thúc `_restore`;
3. so revision, row counts và integrity;
4. chạy restored FastAPI liveness/readiness;
5. ghép attachment archive nếu metadata không rỗng;
6. ghi successful validation record;
7. drop đúng restore database đã tạo trong `finally` và xác nhận nó không còn.

Chi tiết tại [backup/restore](backup_restore.md) và
[attachment recovery](pilot_attachment_recovery.md).

## Controlled Failure Drill

Các case hợp lệ: invalid PostgreSQL connection, unavailable isolated
destination, permission denial trong test directory hoặc checksum mismatch của
fixture. Không sửa hay làm hỏng real backup.

Expected:

- result `failed`, không có last-good replacement;
- exact partial test artifact không còn;
- failed run không được ghi là restore-valid;
- operator giữ safe error privately, không đưa credential/path vào release
  record;
- overdue alert state chỉ recover sau một backup/restore validation thật sự
  thành công.

Controlled-writer tests đã cover write failure, checksum mismatch, exact partial
test artifact removal, last-good preservation và selection logic.

Trên disposable PostgreSQL 16 database có hậu tố `_test`, một local operator
drill đã gọi real `pg_dump`: scheduled dump hợp lệ trả exit `0`, sau đó target
database không tồn tại trả exit `2`. Failed run không đổi validated-index,
không để lại partial artifact và không thay immutable artifact/metadata pair
trước đó. Toàn bộ temporary dump, metadata, index và directory đã được xóa ngay
sau kiểm tra.

Đây chỉ là local workstation boundary evidence. Nó không chạy dưới intended
pilot service account, không xác thực OS schedule, không restore database và
không đóng pilot-host backup/failure gate. Durable in-app disk/backup schedule
integration vẫn chưa chạy.

## OS-Level Schedule Checklist

- [ ] Host và service account được owner phê duyệt.
- [ ] Secret injection không xuất hiện trong task definition/log.
- [ ] Working directory và executable version được pin.
- [ ] Root containment/permission được kiểm tra.
- [ ] Overlap policy được xác định; không chạy concurrent backup không kiểm soát.
- [ ] Exit code khác 0 đi vào approved incident path.
- [ ] Last-good pair không bị replace khi run fail.
- [ ] Retention/pruning có dry-run selection và owner review.
- [ ] Restore drill chạy trên separate database.
- [ ] Attachment bytes được backup theo cặp khi cần.
- [ ] Raw artifacts/logs không commit.

Xem [operational ownership](operational_ownership.md) và
[operations runbook](operations_runbook.md).

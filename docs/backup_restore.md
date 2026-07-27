# PostgreSQL Backup And Restore Drill

## Boundary

Đây là logical backup/restore drill bằng `pg_dump`/`pg_restore`, không phải
automated backup policy, HA, PITR hoặc disaster-recovery certification. Dump
chứa PostgreSQL schema/data; attachment bytes không nằm trong dump.

## Safety

- Source và restore database phải khác nhau.
- Restore database bắt buộc kết thúc `_restore`.
- Output directory bắt buộc nằm ngoài repository.
- Archive filename do tool tạo, không lấy database name làm filesystem path.
- Drill cần `PM8_ALLOW_DESTRUCTIVE_TESTS=true`.
- Password truyền qua environment/`PGPASSWORD`, không xuất hiện trong command,
  manifest, log hoặc process argument do module tạo.
- Restore database được drop trong `finally`; source database không bị drop,
  clean hoặc restore đè.

## Chạy Với Docker PostgreSQL

```powershell
$env:DATABASE_URL = "<source-postgresql-url>"
$env:PM8_ALLOW_DESTRUCTIVE_TESTS = "true"
python -m src.reliability.backup_restore `
  --restore-database maintenance_pm8_restore `
  --output-dir "$env:TEMP\maintenance-pm8-backup" `
  --docker-container maintenance_postgres
```

Không dùng developer/demo database làm destructive test source. Với validation
milestone, dùng database có tên kết thúc `_test`.

## Drill Tự Động Xác Nhận

1. Custom-format dump với `--no-owner --no-privileges`.
2. SHA-256 và JSON manifest versioned.
3. Alembic revision nguồn.
4. Row counts cho users/roles, assets, tickets/SLA/escalation, work orders/logs,
   inventory position/movement, jobs/executions, outbox/attempts, notifications
   và audit.
5. Restore vào database riêng.
6. Revision và row counts giống nguồn.
7. Không có negative inventory hoặc orphan job/outbox/notification owner.
8. FastAPI lifespan, liveness và database readiness smoke chạy trực tiếp với
   restore URL thành công; worker readiness có thể degraded vì restore DB không
   chạy worker.
9. Mặc định ghi append-only `backup_restore` validation record vào source khi
   toàn bộ pass; dùng `--no-record-validation` cho smoke không được phép mutate
   source evidence.
10. Drop restore database kể cả khi validation lỗi.

Manifest không chứa password hoặc URL có credential. Backup archive/manifest là
runtime artifact; bảo vệ theo policy công ty và không commit.

## Attachment Bytes

Backup attachment root riêng bằng host-approved file backup, giữ permission và
relative generated keys. Sau restore metadata:

```powershell
python -m src.reliability.attachments
```

Chỉ coi attachment restore thành công khi missing/checksum mismatch/invalid key
bằng 0. Orphan bytes cần điều tra; PM8 không tự xóa.

## Failure

Nếu dump/checksum/restore/revision/count/integrity/smoke thất bại:

- coi backup validation là failed;
- không chuyển traffic sang restore;
- giữ safe command stderr trong private incident record, không đưa credential;
- kiểm tra disk, PostgreSQL version, quyền và migration;
- chạy lại bằng output/database restore mới sau khi sửa nguyên nhân;
- không cập nhật `last validated backup` thủ công.

## PM9 Scheduled Publication Boundary

PM9 bổ sung `src.reliability.backup_schedule` để một approved OS-level schedule
gọi đúng một bounded backup command. Module không phải scheduler và không thêm
job thứ năm.

```powershell
$env:PM9_ALLOW_SCHEDULED_BACKUP = "true"
python -m src.reliability.backup_schedule `
  --backup-root "<approved-outside-repository-root>" `
  --target-label "pilot" `
  --retention-keep-count 7 `
  --docker-container "<approved-postgresql-container>"
```

Khi command thật sự chạy, publication path được thiết kế để:

- ghi output của `pg_dump` vào partial artifact rồi `os.replace`;
- tạo và verify SHA-256 metadata;
- giữ last-good khi writer/checksum fail;
- không ghi credential/path vào summary;
- luôn báo `restore_validated=false` trước separate restore drill.

Current command validate/record keep-count nhưng không tự prune archive cũ.
Operator phải review last-good selection và organizational retention policy
trước deletion. Exact schedule, service account, backup root và pruning chưa
được cấu hình trên intended host. Xem
[pilot backup schedule](pilot_backup_schedule.md).

## PM9 Paired Attachment Recovery

Một database backup có active attachment metadata chỉ được coi là recovery
candidate khi có paired filesystem archive cùng rehearsal point. PM9 bounded
helpers:

- archive generated relative keys dưới contained root;
- reject traversal, symlink, duplicate/invalid entry và bounds violation;
- checksum từng non-empty fixture;
- inspect missing, mismatch, orphan metadata/file;
- restore vào empty isolated destination.

Sau restore database kết thúc `_restore`, chạy aggregate assessment và authorized
download. Expected invalid/missing/mismatch/orphan đều bằng 0. Raw bytes,
storage keys và absolute paths không vào release note.

Checkpoint PostgreSQL-marked selection đạt `73 passed, 239 deselected` trên
disposable PostgreSQL 16 `_test`. Test generated non-empty PDF đã upload qua
authorized API, archive/restore bytes, download `200` cho Administrator và
`403` cho Helpdesk. Test dùng original `_test` metadata; nó không dump/restore
PostgreSQL và không đóng representative paired drill. PM8 empty-metadata
assessment cũng không đóng gate này. Xem
[attachment recovery](pilot_attachment_recovery.md).

## PM9 Failure Evidence

Controlled-writer tests cover write failure/checksum mismatch, removal của
partial test artifact và last-good preservation. Local disposable `_test`
evidence cũng đã chạy valid `pg_dump` rồi invalid-database `pg_dump` mà không
thay last-good hoặc để lại partial. Chưa có controlled failure dưới intended
service account, scheduled execution hoặc PM9 separate restore trên intended
host.

Backup/restore decision PM9 hiện là:

```text
NO-GO / NOT YET VERIFIED
```

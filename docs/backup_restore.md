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

# Testing Guide

## Nguyên Tắc

- Unit tests không cần external production infrastructure.
- PostgreSQL behavior như row lock, JSONB, trigger, transaction và concurrency
  phải test trên PostgreSQL, không thay bằng SQLite.
- Integration database name bắt buộc kết thúc bằng `_test`.
- Destructive PostgreSQL suites chạy tuần tự vì dùng shared truncate fixture.
- Tests không được ghi vào developer/demo database hoặc canonical analytics
  outputs.

## Setup Test Database

```powershell
docker compose up -d postgres
python -m src.database.create_test_database
$env:TEST_DATABASE_URL = "postgresql+psycopg://maintenance:maintenance@localhost:5432/maintenance_copilot_test"
```

`.env` có thể giữ `TEST_DATABASE_URL`; `tests/conftest.py` từ chối tên database
không kết thúc `_test`.

## Backend

Full suite:

```powershell
python -m pytest
```

PostgreSQL-only:

```powershell
python -m pytest -m postgres
```

PM7 focused:

```powershell
python -m pytest `
  tests/test_background_operations.py `
  tests/test_postgres_background_operations.py
```

Regression areas:

```powershell
python -m pytest tests/test_maintenance_management.py
python -m pytest tests/test_ticket_operations.py
python -m pytest tests/test_inventory_management.py
python -m pytest tests/test_authentication.py
python -m pytest tests/test_database_load.py
```

Tên file có thể được mở rộng theo repository; full suite là authority.

## Frontend

```powershell
npm --prefix frontend run test
npm --prefix frontend run lint
npm --prefix frontend run build
```

Focused PM7:

```powershell
npm --prefix frontend run test -- operations-ui.test.tsx
```

Tests phải cover notification unread/actions, operator job state/manual trigger,
retry visibility và unauthorized state. Next.js build kiểm tra server/client
boundary và static route compilation.

## Migration

Trên isolated test database:

```powershell
python -m alembic downgrade base
python -m alembic upgrade head
python -m alembic downgrade 20260723_0006
python -m alembic upgrade 20260726_0007
python -m alembic current
python -m alembic check
```

Backup dữ liệu cần giữ trước downgrade. PM7 downgrade xóa operational history.

## Static Checks

```powershell
python -m ruff check .
git diff --check
```

Documentation link check phải xác nhận mọi local Markdown target tồn tại và
fragment nội bộ hợp lệ nếu checker hỗ trợ. Secret scan tối thiểu tìm private
keys, committed token/password patterns, live connection strings ngoài local
example và suspicious high-entropy values. Unsafe-path scan tìm hard-coded
absolute path, `file://`, traversal và storage-key exposure.

## Worker Smoke

Sau migration, với bốn job disabled:

```powershell
python -m src.operations.worker --once --worker-id verification-worker
python -m src.operations.cli status
```

Expected: worker startup/readiness thành công, không tạo business execution ngoài
explicit fixture. Trong iteration heartbeat là `ready`; sau khi `--once` kết thúc,
worker ghi `stopping` để health endpoint không báo false-ready process.

Representative job test phải dùng isolated `_test` database hoặc temporary
analytics output. Không enable analytics job trỏ vào canonical
`data/processed` trong test.

## Canonical Analytics Protection

Trước và sau analytics compatibility test:

1. hash tất cả `data/processed/*.csv`;
2. cấu hình `ANALYTICS_PROCESSED_DIR` vào temporary directory;
3. chạy snapshot/job;
4. xác nhận row contracts;
5. xác nhận canonical hashes không đổi;
6. xóa temporary directory.

## Cleanup

Sau verification:

- dừng worker/API/frontend process;
- xóa temporary database/snapshot/log/build artifact không thuộc expected
  ignored output;
- xóa test heartbeat/execution/outbox/notification records;
- dừng Docker services nếu chúng được khởi động chỉ cho verification;
- chạy `git status --short` và `git diff --check`.

Chỉ ghi kết quả `passed` trong release note khi command thực sự đã chạy ở current
revision.

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
$env:TEST_DATABASE_URL = "postgresql+psycopg://<test_user>:<test_password>@localhost:5432/<database_name>_test"
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
npm --prefix frontend run typecheck
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

## PM8 Focused Tests

```powershell
python -m pytest `
  tests/test_reliability_validation.py `
  tests/test_postgres_reliability.py `
  tests/test_database_load.py `
  tests/test_storage_configuration.py `
  tests/test_background_operations.py `
  tests/test_postgres_background_operations.py
```

PostgreSQL suite chạy tuần tự trên database `_test`; không dùng SQLite cho
pool/lock/lease/outbox behavior.

```powershell
$env:PM8_TEST_PASSWORD = "<isolated-test-user-password>"
python -m src.reliability.load_harness `
  --profile baseline --username admin.test `
  --output-dir "$env:TEMP\pm8-reliability"
```

Soak/mutation/destructive drill cần lần lượt
`PM8_ALLOW_EXTENDED_TESTS=true`, `PM8_ALLOW_MUTATIONS=true` và
`PM8_ALLOW_DESTRUCTIVE_TESTS=true`.

Migration PM8:

```powershell
python -m alembic downgrade base
python -m alembic upgrade head
python -m alembic downgrade 20260726_0007
python -m alembic upgrade 20260726_0008
python -m alembic current
python -m alembic check
```

Raw report/dump/log/restore DB phải cleanup. Xem [backup](backup_restore.md),
[recovery](failure_recovery.md) và [checklist](internal_pilot_checklist.md).

## PM9 Focused Tests

Pure/configuration-focused batch:

```powershell
python -m pytest `
  tests/test_pilot_contract.py `
  tests/test_deployment_rehearsal.py `
  tests/test_pm9_post_start_validation.py `
  tests/test_backup_schedule.py `
  tests/test_pm9_load_harness.py `
  tests/test_pm9_drills.py `
  tests/test_pm9_mutation_rehearsal.py `
  tests/test_pm9_secret_rotation.py `
  tests/test_storage_configuration.py `
  tests/test_api_health.py
```

PostgreSQL attachment recovery test phải dùng `TEST_DATABASE_URL` có database
name kết thúc `_test`:

```powershell
python -m pytest -m postgres `
  tests/test_asset_management.py `
  tests/test_pm9_postgres_interruption.py
```

Không chạy PostgreSQL-marked suite nếu URL trỏ vào developer/demo database.

Static contract placeholder check:

```powershell
python -m src.reliability.pilot_contract --skip-environment
```

Expected current result là non-zero cùng
`NO-GO / NOT YET VERIFIED`, vì ownership, limitation acceptance, release
checkpoint, intended host và critical evidence vẫn chưa có. Đây là successful
safety behavior, không phải failed test.

## PM9 Evidence Đã Ghi Trong Implementation Session

Tại thời điểm cập nhật tài liệu ngày 2026-07-26:

- storage/release configuration và API health: `11 passed`;
- pilot contract: `9 passed`;
- deployment rehearsal + backup schedule: `8 passed`;
- PM9 load safety cùng adjacent PM8 reliability tests: `24 passed`;
- PM9 drill helpers cùng adjacent PM8 reliability tests: `19 passed`;
- mutation rehearsal + synthetic secret rotation: `9 passed`;
- deployment/manifest/Compose reconciliation batch: `22 passed`; Ruff, Compose
  config và Make dry-runs pass;
- authenticated post-start validator và deployment integration: `16 passed`
  focused unit tests với mocked HTTP transport; không contact live PM9 stack;
- full PostgreSQL-marked selection trên disposable local PostgreSQL 16 database
  kết thúc `_test`: `73 passed, 239 deselected`;
- ba exact connection-termination tests trong selection trên đã pass; chúng gọi
  `pg_terminate_backend` nhưng không kill live worker process;
- authorized non-empty attachment API/archive test trong selection trên đã
  pass; nó không restore paired PostgreSQL dump + metadata/bytes;
- adjacent load/authentication regression run: `17 passed, 9 skipped`, một
  existing Starlette TestClient deprecation warning;
- mutation và secret CLI `--help`: pass;
- documentation link check sau PM9 docs: `1 passed`;
- focused Ruff cho các nhóm PM9 đã chạy và pass;
- static checked-in contract command đã chạy, trả expected blockers và
  `NO-GO / NOT YET VERIFIED`.

Final verification trên settled worktree ghi thêm:

- PM9-focused selection: `103 passed, 3 skipped` khi không inject
  `TEST_DATABASE_URL`; ba PostgreSQL interruption tests bị skip trong run này
  đều pass trong full database-enabled run;
- full backend với fresh disposable PostgreSQL 16 database kết thúc `_test`:
  `374 passed`, một existing Starlette TestClient deprecation warning;
- full frontend: `112 passed` trên 17 files; ESLint pass; Next.js production
  build tạo 32 pages và `.next` được xóa;
- Ruff `check .`: pass; focused format check cho 19 PM9 Python files: pass;
- Alembic có một head `20260726_0008`; `current`, `check` và clean
  base-to-head trên temporary `_test` database: pass;
- `docker compose ... config --quiet`: pass;
- manifest-only technical validator: expected exit `2` với generic
  `NO-GO / NOT YET VERIFIED`;
- full checked-in three-gate contract: expected exit `2` với exact
  `NO-GO / WAITING FOR PILOT SPONSOR`; release-identity validation vẫn fail
  closed khi chưa có final local tag/observations;
- deployment manifest semantic JSON SHA-256:
  `06bdd63dc28313ca32e5edd862fe019d421460e832dd3c6ccfda7d2d8583e9dc`.

Design-readiness classification follow-up ngày 2026-07-27 chạy riêng và ghi:

- revised decision/deployment contract tests: `47 passed`;
- full backend khi `TEST_DATABASE_URL` unset: `303 passed, 73 skipped`, cùng một
  existing Starlette TestClient deprecation warning; 73 PostgreSQL-marked skips
  không thay thế database-enabled result `374 passed` ở trên;
- full frontend: `112 passed` trên 17 files; ESLint pass; Next.js build 32 pages
  rồi `.next` được xóa;
- Ruff repository-wide, format check cho 3 changed Python files,
  documentation-link test (`1 passed`), JSON parse, manifest digest và
  `git diff --check`: pass;
- manifest-only/full checked-in contract commands đều exit `2` đúng với generic
  technical decision và sponsor-waiting decision tương ứng.

Các focused count không được cộng cơ học thành full-backend result và không thay
PM8 checkpoint counts. `73 passed, 239 deselected` là PostgreSQL-marked
selection riêng. Connection termination không đóng live worker-process gate;
attachment API/archive không đóng paired database/filesystem restore gate.

Chưa chạy/ghi host-dependent evidence:

- Docker pilot deployment và health;
- live authenticated RBAC/jobs/notifications/analytics deployment smoke;
- soak, mutation load, step capacity và live worker-process termination;
- PM9 restore, durable disk alert, real secret rotation và paired PostgreSQL
  dump + attachment drill. Local disposable `_test` valid/invalid-database
  `pg_dump` boundary đã chạy nhưng không phải intended-host/service-account
  evidence.

Final checkpoint phải cập nhật [PM9 release note](releases/product_milestone_9.md)
chỉ bằng command thật sự đã chạy.

## PM9 Host-Dependent Commands

Các command dưới đây không thuộc default regression và cần approved isolated
host/fixture:

- deployment execution: `PM9_ALLOW_DEPLOYMENT_REHEARSAL=true`;
- authenticated post-start deployment: thêm
  `PM9_ALLOW_POST_START_VALIDATION=true`,
  `PM9_APPROVED_DATA_ATTESTED=true`, opaque
  `PM9_APPROVED_DATA_EVIDENCE_ID`, bốn protected `PM9_SMOKE_*` credential
  variables và `--authenticated-post-start`;
- authenticated post-start mặc định cần HTTPS; isolated loopback HTTP test mới
  được phép thêm `PM9_ALLOW_HTTP_TEST_SMOKE=true`;
- empty-data deployment: thêm `PM9_ALLOW_EMPTY_TEST_DATA=true` và database
  kết thúc `_test`;
- scheduled backup: `PM9_ALLOW_SCHEDULED_BACKUP=true`;
- soak: `PM8_ALLOW_EXTENDED_TESTS=true`;
- mutation: `PM8_ALLOW_MUTATIONS=true`;
- closed mutation rehearsal: `PM9_ALLOW_MUTATION_REHEARSAL=true`;
- capacity: `PM9_ALLOW_CAPACITY_TESTS=true`;
- synthetic signing rotation: `PM9_ALLOW_SYNTHETIC_SECRET_ROTATION=true`;
- destructive restore drills: `PM8_ALLOW_DESTRUCTIVE_TESTS=true`.

Opt-in không phải host approval. Operator vẫn phải xác nhận resource safety,
owners, exact fixture-specific removal steps và raw evidence directory ngoài
repository.

## PM9 Documentation And Artifact Check

Final safe verification tối thiểu:

```powershell
python -m ruff check .
git diff --check
```

Ngoài ra kiểm tra local Markdown links, secret/high-entropy patterns,
credential-bearing URL, absolute/traversal path, backup/archive/log/load report,
`.next`, restored database và canonical-data drift. Không báo cleanup pass bằng
một câu chung: phải ghi riêng trạng thái process, container, volume, test rows,
fixture bytes, archive và report paths được tạo bởi run.

Xem [pilot load results](pilot_load_results.md),
[pilot deployment](pilot_deployment.md) và
[pilot checklist](internal_pilot_checklist.md).

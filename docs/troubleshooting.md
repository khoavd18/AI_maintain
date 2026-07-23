# Xử Lý Sự Cố

## PostgreSQL Không Chạy

Triệu chứng:

- Uvicorn fail startup với thông báo primary storage unavailable;
- API không tự chuyển sang CSV;
- frontend/Streamlit không kết nối được API.

Kiểm tra:

```powershell
docker compose up -d postgres
docker compose ps
docker compose logs postgres
```

Container phải ở trạng thái `healthy`. Kiểm tra `.env`:

```dotenv
STORAGE_BACKEND=postgresql
DATABASE_URL=postgresql+psycopg://maintenance:maintenance@localhost:5432/maintenance_copilot
```

Không đặt `STORAGE_BACKEND=csv` để che lỗi PostgreSQL trong normal product mode. CSV mode chỉ dành cho explicit fixtures/tests.

## Database Chưa Chạy Migration

Triệu chứng: startup báo schema chưa initialized hoặc thiếu `alembic_version`.

```powershell
python -m alembic current
python -m alembic upgrade head
python -m alembic check
```

API không tự tạo table. Mọi schema change phải qua Alembic.

## Legacy Experimental Database Xung Đột Migration

Một Docker volume từ phase cũ có thể chứa unversioned tables `assets`, `sensor_readings`, `risk_scores`, v.v. Khi chạy initial canonical migration, Alembic báo `relation "assets" already exists`.

Không stamp schema cũ thành head vì columns và constraints không khớp. Chọn một trong hai cách có chủ đích:

1. Tạo database mới, cập nhật `DATABASE_URL`, rồi chạy migration và import.
2. Backup dữ liệu cần giữ, sau đó drop/recreate database cũ ngoài ứng dụng.

Ví dụ tạo database mới trong local Docker:

```powershell
docker exec maintenance_postgres psql -U maintenance -d postgres -c "CREATE DATABASE maintenance_copilot_product"
$env:DATABASE_URL = "postgresql+psycopg://maintenance:maintenance@localhost:5432/maintenance_copilot_product"
python -m alembic upgrade head
python -m src.ingestion.load_data --dry-run
python -m src.ingestion.load_data
```

Old optional PostgreSQL schema không phải transactional source of truth trước milestone này; canonical CSV seed là nguồn reset được kiểm tra.

## CSV Import Bị Từ Chối

`python -m src.ingestion.load_data` từ chối database có bất kỳ transactional row nào. Đây là protection, không phải lỗi importer.

Kiểm tra trước:

```powershell
python -m src.ingestion.load_data --dry-run
```

Chỉ khi chủ động reset demo về canonical 27/42/86:

```powershell
python -m src.ingestion.load_data --replace
```

`--replace` xóa và import lại ba transactional tables trong cùng database transaction. Nó không xóa processed analytics hoặc Qdrant collection.

## Import Vi Phạm Constraint

Triệu chứng: importer báo uniqueness, foreign-key hoặc check-constraint violation và rollback.

Chạy validation độc lập:

```powershell
python -m src.ingestion.validation --input-dir data/raw
```

Không sửa riêng ID trong một file. Regenerate canonical seed nếu dữ liệu synthetic bị thay đổi ngoài contract:

```powershell
python -m src.data_generation.generate_data
python -m src.ingestion.validation
```

Sau đó dry-run/import lại. Failed import không để partial rows.

## Analytics Chưa Phản Ánh Ticket Hoặc Log Mới

Đây là expected behavior. PostgreSQL write không tự chạy Risk Score/KPI.

1. Export validated snapshot:

```powershell
python -m src.database.export_snapshot --replace
```

2. Chạy canonical batch từ snapshot:

```powershell
python -m src.features.build_features --input-dir data/analytics_input
python -m src.models.anomaly_detection
python -m src.risk.risk_scoring
python -m src.features.build_features --input-dir data/analytics_input --analysis maintenance
```

3. Refresh dashboard/frontend.

Không đổi Risk Score trên UI để giả lập batch refresh.

## Analytics Snapshot Export Bị Từ Chối

Nếu `data/analytics_input` đã tồn tại, dùng `--replace` có chủ đích. Export cần hai pass-through files trong `data/raw`:

- `sensor_readings.csv`;
- `documents.csv`.

Nếu thiếu, chạy generator. Snapshot chỉ được publish sau khi full CSV validator pass.

Nếu snapshot báo `expected ... from maintenance interval`, bảo đảm đang chạy exporter canonical thay vì tự dump table. PostgreSQL có thể giữ plan-derived next date; `src.database.export_snapshot` project ngày đó về fixed-interval contract trong staging rồi mới validation, không sửa transactional rows.

## Processed Analytics CSV Bị Thiếu Hoặc Stale

Triệu chứng:

- `/summary`, risk hoặc maintenance report trả `503`;
- health có `analytics_available=false`;
- transactional asset/ticket/log storage vẫn có thể healthy.

Chạy lại snapshot và batch theo phần trên. Latest dates của features, anomaly, risk, preventive và KPI phải đồng nhất.

## Stale Update Trả 409

PostgreSQL dùng optimistic version cho assets và tickets. Hai write đồng thời có thể làm request sau nhận `409`.

- reload ticket hoặc asset detail;
- kiểm tra trạng thái mới nhất;
- gửi lại quyết định có chủ đích.

Không retry blind một write có side effect.

## Asset Lifecycle Hoặc Operational Status Trả 409

Kiểm tra hai state riêng:

- `planned -> active|inactive`;
- `active -> inactive|retired`;
- `inactive -> active|retired`;
- `retired -> inactive` để review trước khi active lại;
- archive/restore phải dùng endpoint riêng và `expected_version` mới nhất;
- inactive/retired/archived giữ `out_of_service`; retired/archived không nhận ticket mới.

Reload rich profile trước khi thao tác. Không sửa trực tiếp legacy `status` để né lifecycle rule.

## Không Archive Được Location

- Location cha còn child đang active: archive/reassign child trước.
- Assigned assets không bị xóa và không chặn archive leaf; asset vẫn giữ location reference/history.
- Location archived không nhận asset mới. Chọn active location khác rồi update profile bằng current version.
- Cycle hoặc self-parent trả `409`; sửa parent chain thay vì can thiệp SQL trực tiếp.

## Attachment Upload Hoặc Download Lỗi

Backend chỉ chấp nhận PDF/PNG/JPG/JPEG khi extension, MIME và signature khớp, file không rỗng và không vượt `ATTACHMENT_MAX_SIZE_BYTES`. Tên chứa `/`, `\`, NUL hoặc traversal bị từ chối.

```dotenv
ATTACHMENT_STORAGE_BACKEND=local
ATTACHMENT_STORAGE_ROOT=data/attachments
ATTACHMENT_MAX_SIZE_BYTES=10485760
```

- Root phải writable bởi API process và không được public web server serve trực tiếp.
- Download `403`: user thiếu `attachments:read`; UI visibility không thay FastAPI permission.
- Download `503` checksum mismatch/missing bytes: giữ metadata/audit, phục hồi file từ backup hoặc upload lại qua workflow; không sửa checksum trong database để che lỗi.
- Delete response có `storage_cleanup_pending=true`: metadata đã soft-delete nhưng physical cleanup lỗi; local pilot cần operator xử lý file/reconcile thủ công.
- API không có inline preview cho file và không bao giờ trả storage key/local path.

Local storage chỉ phù hợp một API node. Chưa có S3 implementation, malware scanner hoặc attachment backup automation.

## QR Lookup Không Mở Được Asset

- `401`: QR route vẫn yêu cầu login; QR không phải auth token.
- `403`: user thiếu `assets:read`.
- `404`: token không hợp lệ hoặc không còn khớp asset.
- `410`: asset đã archived; Property Manager phải xác minh rồi restore explicit nếu phù hợp.
- URL sai host: đặt `FRONTEND_BASE_URL=http://localhost:3000`, restart API và tải lại QR preview. Token/SVG vẫn deterministic cho cùng asset ID.

QR payload chỉ nên có `/scan/assets/{opaque UUID}`. Nếu thấy credential, user data hoặc database URL, dừng sử dụng label và coi đó là contract/security defect.

## Ticket Không Resolve Được

Canonical sequence là:

```text
Mới tạo -> Đang xử lý -> tạo maintenance log -> Đã xử lý
```

Ticket phải có linked log trước khi resolve. `resolved_at` phải có timezone, không trước `created_at`, không trước maintenance date và không nằm trong tương lai.

## Maintenance Log Bị Từ Chối

Kiểm tra:

- ticket đang `Đang xử lý`;
- `asset_id` khớp ticket;
- maintenance date không trước ticket hoặc latest asset maintenance;
- next date bằng maintenance date cộng asset interval;
- `follow_up_required=false` chỉ với `Đã xử lý`;
- corrective log dùng technician đang được gán.

Composite foreign key cũng chặn ticket/log relationship sai ở database level.

## Test Database

Integration tests chỉ chạy với database name kết thúc bằng `_test`.

```powershell
python -m src.database.create_test_database
$env:TEST_DATABASE_URL = "postgresql+psycopg://maintenance:maintenance@localhost:5432/maintenance_copilot_test"
python -m pytest -m postgres
```

Fixture migrate và truncate test database. Không trỏ `TEST_DATABASE_URL` vào demo/developer database.

## API Không Khởi Động Vì Security Configuration

Ngoài `development`/`test`, API từ chối signing secret dưới 32 ký tự và cookie không có `Secure=true`:

```dotenv
APP_ENVIRONMENT=pilot
TOKEN_SIGNING_SECRET=<inject-random-secret-outside-git>
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
```

Pilot phải chạy HTTPS. Không ghi secret thật vào `.env.example`, command history, log hoặc source control. `SameSite=None` chỉ hợp lệ cùng `Secure=true`.

## Không Đăng Nhập Được

- Unknown user, wrong password và inactive account đều cố ý trả generic `Thông tin đăng nhập không hợp lệ.`; kiểm tra user bằng administrator UI/CLI thay vì dựa vào response để enumerate account.
- Username/email được trim + lowercase trước lookup.
- Basic limiter chặn tạm sau số lần thất bại cấu hình; chờ hết `LOGIN_RATE_LIMIT_WINDOW_SECONDS`. Limiter local hiện chỉ theo một API process.
- Không có default account. Tạo admin explicit:

```powershell
python -m src.security.cli create-admin --username admin.local --display-name "Quản trị viên local"
```

Demo roles chỉ seed khi `APP_ENVIRONMENT=development` bằng `python -m src.security.cli seed-demo-users`. Cả hai command prompt password nếu temporary environment variable không được cung cấp và không in password.

## Refresh Hoặc Logout Trả 401/403

- Browser phải gửi cookies với `credentials: include` và frontend origin phải nằm chính xác trong `CORS_ALLOWED_ORIGINS`.
- Refresh/logout cần `X-CSRF-Token` khớp readable CSRF cookie; `NEXT_PUBLIC_CSRF_COOKIE_NAME` phải khớp `CSRF_COOKIE_NAME`.
- Refresh token bị rotate sau mỗi lần dùng. Reuse token cũ, logout, password change, role change hoặc account deactivation sẽ làm session không còn hợp lệ.
- Access token chỉ ở frontend memory nên reload cần refresh session; không sửa bằng cách ghi token vào `localStorage`.
- Xóa cookies local cũ rồi login lại khi đổi cookie name/path giữa các lần chạy.

## Trả 403 Dù UI Có Hoặc Không Có Button

FastAPI là authorization boundary. Kiểm tra permission từ `GET /auth/me` và role matrix trong [architecture](architecture.md). Technician còn bị giới hạn theo `technician_id`; helpdesk không được assign/resolve/ghi maintenance log. Không thêm bypass route để sửa lỗi UI.

## Audit Log Không Sửa Hoặc Xóa Được

Đây là behavior có chủ đích. Application chỉ có paginated read endpoint, còn PostgreSQL trigger từ chối `UPDATE`/`DELETE`. Successful workflow event phải commit cùng business mutation. Database administrator vẫn là trust boundary; backup/retention hoặc external tamper-evident archive chưa được triển khai.

## Dashboard Không Kết Nối Được API

Khởi động PostgreSQL/migration trước, rồi API:

```powershell
python -m uvicorn src.api.main:app --reload --port 8000
```

Streamlit chỉ kiểm tra public `/health`; protected workflows đã bị vô hiệu hóa:

```powershell
$env:API_BASE_URL = "http://localhost:8000"
python -m streamlit run src/dashboard/app.py
```

Next.js `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_CSRF_COOKIE_NAME=maintenance_csrf
```

Nếu write timeout hoặc mất kết nối, kiểm tra list trước khi gửi lại vì response có thể bị mất sau khi transaction đã commit.

## Maintenance Plan Hoặc Work Order Table Chưa Có

Triệu chứng: API startup báo migration cũ, hoặc `/maintenance-plans`/`/work-orders` trả lỗi storage.

```powershell
python -m alembic current
python -m alembic upgrade head
python -m alembic check
```

Canonical head cho Product Milestone 4 là `20260720_0004`. API không tự `create_all`; không sửa table thủ công. Với database test, tên phải kết thúc `_test`.

## Không Có Preventive Plan Sau Canonical Import

Canonical CSV import cố ý chỉ giữ `27` assets, `42` tickets và `86` historical logs. Plan/template/work order là development seed riêng:

```powershell
python -m src.security.cli seed-demo-users
python -m src.maintenance_management.cli seed-development
```

Lệnh maintenance seed dùng existing `engineer.demo` và `technician.demo`; nó không tạo account hoặc password. `APP_ENVIRONMENT` phải là `development`/`test`.

## Generation Không Tạo Work Order

Chạy dry-run trước:

```powershell
python -m src.maintenance_management.cli generate --dry-run --as-of 2026-07-20
```

Đọc `reason` theo từng plan. Plan bị skip khi paused/archived/expired, `next_due_date` chưa đến release window, asset retired/archived, hoặc occurrence đã tồn tại. Catch-up bị giới hạn 366 ngày. Resume plan bỏ backlog trong thời gian pause theo policy.

Rerun real generation cho cùng as-of trả zero/skipped là behavior đúng. Unique `(preventive_plan_id, due_date)` ngăn duplicate dưới retry/concurrency.

## Plan Trả 422 Hoặc 409

- `interval_value` phải 1–366; unit chỉ `day/week/month/year`.
- `local_timezone` phải là IANA zone như `Asia/Ho_Chi_Minh`; không dùng offset tùy ý.
- `end_date` không trước `start_date`; raw RRULE không được hỗ trợ.
- Retired/archived asset không nhận active plan mới.
- Assignee phải là active technician; template phải active và tương thích asset type.
- `409` sau edit thường là optimistic stale version: reload detail rồi review thay đổi trước khi gửi lại.

## Work Order Không Chuyển Trạng Thái

Canonical flow: `planned -> assigned -> in_progress -> completed -> verified`; `on_hold` chỉ quay lại assigned/in-progress, cancellation/reopen dùng endpoint riêng.

- Chưa assign eligible technician thì không start.
- Technician chỉ execute assigned work order của chính họ.
- Required checklist chưa đủ hoặc safety-critical item `fail` thì completion bị chặn.
- Cancelled/verified work order không complete; verified record chỉ đọc.
- Technician complete không được tự verify. Đăng nhập Chief Engineer/Property Manager khác actor để review và verify.
- Stale `expected_version` trả `409`; không retry mù vì có thể ghi đè quyết định mới.

Completion tạo đúng một MaintenanceLog. Gửi lại request cũ không được tạo log thứ hai. Reopen trước verification giữ linked append-only log; current internal-pilot chưa có full amendment/countersign workflow.

## Ticket Không Tự Resolve Sau Work Order

Đây là behavior chủ đích. Tạo, complete hoặc verify corrective work order không đổi ticket. Authorized actor phải mở ticket, review maintenance evidence và gọi existing resolve action explicit. Ticket vẫn yêu cầu linked maintenance log theo rule hiện có.

## Work-Order Evidence Bị Từ Chối

Chỉ nhận PDF/PNG/JPG/JPEG có extension, claimed MIME và signature khớp, dưới configured size. Filename traversal, executable hoặc body rỗng trả `422`. Download yêu cầu permission/resource scope và kiểm tra SHA-256; mismatch trả `503`. Evidence của verified WO không thêm/xóa được. Bytes nằm trong private attachment root, không serve trực tiếp.

## Qdrant Không Chạy

Qdrant chỉ ảnh hưởng Copilot retrieval; analytics và transactional workflow không phụ thuộc Qdrant.

```powershell
docker compose up -d qdrant
python -m src.rag.index_documents
```

Kiểm tra `http://localhost:6333/collections`. Khi Qdrant unavailable, Copilot trả safe fallback và không dùng unrelated chunk.

Nếu Windows reserve port `6333`, chọn host port khác nhưng giữ container port qua Compose:

```powershell
$env:QDRANT_HTTP_PORT = "6461"
$env:QDRANT_URL = "http://localhost:6461"
docker compose up -d qdrant
python -m src.rag.index_documents
```

## Collection Thiếu, Trống Hoặc Sai Dimension

Re-index canonical documents:

```powershell
python -m src.rag.index_documents
```

Indexer replace collection để loại stale chunks. Nếu đổi embedding model, phải re-index toàn bộ collection; không trộn vector dimensions.

## sentence-transformers Chưa Cài

```powershell
python -m pip install -e ".[rag]"
```

Không thêm paid API fallback. Khi local embedding dependency thiếu, Copilot phải trả trạng thái unavailable an toàn.

## Backup Và Reset

Backup local transactional data:

```powershell
docker exec maintenance_postgres pg_dump -U maintenance -d maintenance_copilot -Fc -f /tmp/maintenance_copilot.dump
docker cp maintenance_postgres:/tmp/maintenance_copilot.dump .\maintenance_copilot.dump
```

Canonical application reset sau khi schema đã được Alembic quản lý:

```powershell
python -m src.database.init_db --reset
python -m src.ingestion.load_data
python -m src.security.cli seed-demo-users
python -m src.maintenance_management.cli seed-development
```

`--reset` và `--replace` là destructive với transactional demo data, gồm plans/templates/work orders/evidence metadata. Backup database và private attachment root trước nếu cần giữ workflow đã nhập. Không dùng Docker volume deletion như routine reset.

## Warnings Đã Review

`StarletteDeprecationWarning` từ current FastAPI test client là test-only warning đã biết; không thay đổi runtime API contract. Qdrant client được pin cùng minor line với local Qdrant server. Không upgrade dependency tree ngoài một dependency-focused task.

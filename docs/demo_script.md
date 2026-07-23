# Kịch Bản Demo Product 15–18 Phút

Kịch bản dùng PostgreSQL làm transactional source of truth cho asset, ticket/SLA, work order và inventory; CSV làm synthetic seed + batch analytics contract. Đây là internal pilot demo, không phải production deployment, procurement suite hoặc complete CMMS.

## Chuẩn Bị Trước Demo

### 1. Cài dependency và cấu hình

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,rag,postgres]"
Copy-Item .env.example .env
```

Giữ normal mode:

```dotenv
STORAGE_BACKEND=postgresql
DATABASE_URL=postgresql+psycopg://maintenance:maintenance@localhost:5432/maintenance_copilot
APP_ENVIRONMENT=development
ATTACHMENT_STORAGE_BACKEND=local
ATTACHMENT_STORAGE_ROOT=data/attachments
FRONTEND_BASE_URL=http://localhost:3000
```

Không commit password hoặc signing secret. Local development dùng process-ephemeral signing secret; pilot/non-local phải inject secret ngẫu nhiên và chạy HTTPS với `AUTH_COOKIE_SECURE=true`.

### 2. Khởi động infrastructure

```powershell
docker compose up -d postgres qdrant
docker compose ps
```

PostgreSQL phải `healthy`. Qdrant chỉ cần cho Copilot.

### 3. Generate và validate canonical data

```powershell
python -m src.data_generation.generate_data
python -m src.ingestion.validation
```

Expected seed counts:

- 27 assets;
- 42 tickets;
- 86 maintenance logs;
- 77.760 sensor readings;
- 6 documents.

### 4. Migrate và import PostgreSQL

```powershell
python -m alembic upgrade head
python -m alembic current
python -m src.ingestion.load_data --dry-run
python -m src.ingestion.load_data
```

Nếu database đã có demo data và cần reset có chủ đích, thay command cuối bằng:

```powershell
python -m src.ingestion.load_data --replace
```

Không dùng `--replace` khi cần giữ ticket/log từ buổi demo trước.

### 4.1. Bootstrap identity rõ ràng

Tạo administrator đầu tiên bằng password prompt:

```powershell
python -m src.security.cli create-admin --username admin.local --display-name "Quản trị viên local"
```

Tạo năm role demo bằng một password do người chạy nhập, chỉ trong development:

```powershell
python -m src.security.cli seed-demo-users
```

Expected usernames: `admin.demo`, `manager.demo`, `engineer.demo`, `technician.demo`, `helpdesk.demo`, `storekeeper.demo`. Không có default password và application startup không tự tạo user.

### 4.2. Seed preventive maintenance explicit

Lệnh dùng hai user đã tồn tại, không tạo password/account và idempotent:

```powershell
python -m src.maintenance_management.cli seed-development
python -m src.maintenance_management.cli generate --dry-run --as-of 2026-07-20
```

Chọn `--as-of` phù hợp ngày demo. Dry-run không write. Có thể bỏ seed và tạo template/plan trực tiếp trên UI để kể đầy đủ workflow.

### 4.3. Seed ticket/SLA reference data

Lệnh idempotent tạo category, source, support group, default Vietnamese business calendar và SLA policy. Actor phải tồn tại và có quyền quản lý SLA:

```powershell
python -m src.ticket_management.cli seed-defaults --actor-username admin.demo
```

### 4.4. Seed inventory explicit

Sau khi có demo users và work orders:

```powershell
python -m src.inventory_management.cli seed-development
python -m src.inventory_management.cli seed-development
```

Lần đầu tạo 6 categories, 3 UOM, 5 stock locations, 8 spare parts, opening balances và selected requirements/reservations. Lần hai phải báo zero cho master/requirement/reservation mới và không tăng movement count. Seed đi qua named services, không PATCH balance.

### 5. Tạo analytics snapshot và chạy batch

```powershell
python -m src.database.export_snapshot --replace
python -m src.features.build_features --input-dir data/analytics_input
python -m src.models.anomaly_detection
python -m src.risk.risk_scoring
python -m src.features.build_features --input-dir data/analytics_input --analysis maintenance
```

### 6. Index Vietnamese SOP/checklist

```powershell
python -m src.rag.index_documents
```

### 7. Khởi động FastAPI và frontend

Terminal 1:

```powershell
python -m uvicorn src.api.main:app --reload --port 8000
```

Terminal 2, Next.js manager workspace:

```powershell
Set-Location frontend
Copy-Item .env.example .env.local -ErrorAction SilentlyContinue
npm install
npm run dev
```

Mở `http://localhost:3000`.

Streamlit không dùng cho protected demo workflow. Nó chỉ còn là legacy development status page gọi public `/health`.

## Ticket Intake, SLA Và Escalation Workflow

### A. Helpdesk intake

1. Đăng nhập `helpdesk.demo`, mở `/tickets`, chọn queue **Chưa phân công**.
2. Mở `/tickets/new`, chọn `GENERATOR_002`, category/source, impact `high` và urgency `immediate`.
3. Chỉ priority preview `critical` đến từ FastAPI; browser không có matrix riêng.
4. Điền reporter contact cho demo, route đến Engineering và assign `technician.demo`.
5. Submit rồi mở detail; chỉ SLA first-response/resolution, policy snapshot và Vietnamese labels.

### B. Technician execution và communication

1. Đăng nhập `technician.demo`, mở queue **Phân công cho tôi**.
2. Mở ticket vừa tạo; reporter PII phải được redact.
3. Chọn **Ghi nhận phản hồi**, sau đó **Bắt đầu**.
4. Thêm internal comment; thử **Đặt chờ** với reason, kiểm tra resolution SLA chuyển `paused`, rồi **Tiếp tục**.
5. Mở Copilot với asset/ticket context và xem checklist có source.
6. Tạo hoặc mở corrective work order, thực hiện checklist/evidence và ghi maintenance result.
7. Quay lại ticket và resolve explicit sau khi linked maintenance log tồn tại.

### C. Manager oversight

1. Đăng nhập `manager.demo`, mở queues **Khẩn cấp**, **Sắp đến hạn** và **Vi phạm SLA**.
2. Mở ticket, xác nhận reporter PII hiển thị theo permission, timeline chứa intake/response/pause/resume/comment.
3. Đóng ticket đã resolved hoặc reopen với reason để chỉ SLA occurrence mới.
4. Mở `/admin/sla`: chỉ business calendar, policy targets và cảnh báo snapshot.
5. Mở `/admin/escalations`: chạy **Dry run**, sau đó execute nếu có candidate. Chạy lại để chứng minh không tạo duplicate.

CLI tương đương:

```powershell
python -m src.ticket_management.cli evaluate-escalations --dry-run --actor-username manager.demo
python -m src.ticket_management.cli evaluate-escalations --actor-username manager.demo
```

**Nói:** SLA state derive từ timestamps và policy/calendar snapshot. Escalation chỉ ghi operational event, không gửi email/SMS, không tự đổi ticket và không chạy background worker.

## Preventive Plan Và Work Order Workflow

### A. Chief Engineer tạo preventive flow

1. Đăng nhập `engineer.demo`.
2. Mở `/maintenance/checklists`, tạo checklist máy phát có ít nhất một required item và một safety-critical `pass_fail` item.
3. Tạo version mới và chỉ ra version cũ vẫn đọc được.
4. Mở `/maintenance/plans/new`, chọn `GENERATOR_002`, interval tháng, `Asia/Ho_Chi_Minh`, lead/grace period, checklist vừa tạo và `technician.demo`.
5. Mở plan detail, xem occurrence 180 ngày và warning rằng schedule change không sửa work order lịch sử.
6. Chạy **Dry run**, sau đó **Generate**. Mở generated WO và ghi lại `work_order_number`.

**Nói:** Due date là local business date. Month-end giữ anchor và clamp khi cần; execution timestamps là UTC. Generation chỉ chạy do actor explicit, không có startup scheduler.

### B. Technician thực thi trên mobile width

1. Đăng nhập `technician.demo`, mở `/work-orders` và lọc assigned technician.
2. Mở WO trên viewport khoảng 390 px; xác nhận không có horizontal overflow.
3. Chọn **Bắt đầu**, hoàn tất required checklist; thử đặt safety-critical item là `Không đạt` để thấy completion bị chặn, sau đó chỉ sửa thành `Đạt` khi phù hợp với demo.
4. Upload một PDF/JPEG nhỏ ở category before/after evidence, tải lại và kiểm tra filename/checksum metadata.
5. Nhập inspection result, action, historical `parts_replaced` text, labor, follow-up và completion summary; chọn **Hoàn tất và tạo log**.
6. Xác nhận maintenance log ID xuất hiện đúng một lần và technician không thấy/không được phép tự verify.

### C. Chief Engineer xác minh

1. Đăng nhập lại `engineer.demo`, mở completed WO.
2. Review checklist, evidence, completion summary và timeline.
3. Chọn **Xác minh kỹ thuật**.
4. Xác nhận status `verified`, verifier khác technician, linked MaintenanceLog giữ nguyên và asset maintenance dates được cập nhật.
5. Mở Audit log bằng role có quyền để xem generated/started/checklist/completed/verified/asset-date events.

### D. Corrective ticket flow

1. Từ `GENERATOR_002`, tạo ticket hoặc mở ticket đang `Đang xử lý`.
2. Trong ticket detail chọn **Tạo WO**, assign technician và mở linked corrective work order.
3. Technician execute/complete; Chief Engineer verify.
4. Quay lại ticket: status vẫn chưa tự đổi. Authorized actor resolve ticket bằng existing ticket action sau khi review evidence.

**Điểm cần chứng minh:** ticket, work order và maintenance log là ba entity khác nhau; creating/completing/verifying WO không ẩn business transition.

### E. Helpdesk restrictions

Đăng nhập `helpdesk.demo`: xem limited WO status; thử mở create plan, submit checklist hoặc verify phải bị UI chặn và FastAPI trả `403` nếu gọi trực tiếp.

### F. Generation safety

Chạy cùng command hai lần:

```powershell
python -m src.maintenance_management.cli generate --as-of 2026-07-20
python -m src.maintenance_management.cli generate --as-of 2026-07-20
```

Lần hai phải báo skipped/zero generated cho occurrence đã có. Automated PostgreSQL test còn chạy concurrent calls để chứng minh unique `(plan_id, due_date)` và sequence work-order number.

## Inventory Và Work-Order Parts Workflow

### A. Storekeeper kiểm tra stock

1. Đăng nhập `storekeeper.demo`.
2. Mở **Kho vật tư**: xem active parts, low/out-of-stock và work orders waiting for parts.
3. Mở **Tồn theo kho**: chỉ ra ba cột on-hand, reserved và available.
4. Mở **Biến động kho**: mỗi event có movement number, reference, actor và resulting balance.
5. Mở **Nhập kho**, ghi một receipt với business reference mới; upload evidence tùy chọn.

**Nói:** Client gửi named command + stable `Idempotency-Key`; backend lock position và append movement. Không có generic balance edit.

### B. Requirement, reservation và issue

1. Chief Engineer mở generated work order, tab **Vật tư cho công việc**.
2. Xem planned requirement hoặc thêm requirement; quantity stock chưa đổi.
3. Reserve một phần/toàn phần; on-hand giữ nguyên, available giảm.
4. Storekeeper mở cùng work order, issue reserved stock cho technician.
5. Quan sát on-hand giảm và issue/movement xuất hiện; ticket/work-order status không tự đổi.

### C. Technician consumption và return

1. Đăng nhập technician được gán và mở work order.
2. Trong tab **Xuất dùng**, ghi quantity thực dùng. Consumption không trừ stock lần hai.
3. Đăng nhập Storekeeper, return phần outstanding chưa dùng.
4. Nếu còn shortage/unresolved issued stock, completion chỉ hiện warning. Không có hidden issue/consume/release.

### D. Negative checks

- Technician khác không đọc/consume inventory của work order.
- Helpdesk không adjustment hoặc receipt.
- Transfer quá available và return quá outstanding bị từ chối, không partial write.
- Reuse idempotency key với payload khác trả conflict.

## 0:00–0:45 — Bài Toán Và Architecture

**Nói:** Đội facility phải ghép asset master, ticket, preventive schedule, operational readings và SOP. Hệ thống này là AI decision-support layer: PostgreSQL giữ transactions, batch analytics ưu tiên asset, FastAPI phục vụ hai frontend, Qdrant retrieve tài liệu. Con người vẫn chịu trách nhiệm quyết định và an toàn.

**Chỉ:** Architecture diagram trong [architecture.md](architecture.md).

## 0:45–1:30 — Overview

1. Mở `/login`, đăng nhập `manager.demo` bằng password vừa seed.
2. Chỉ current user/role trong authenticated shell.
3. Mở Overview và chỉ KPI cards, risk distribution, maintenance status.
4. Nhấn mạnh KPI/Risk là latest completed batch, không phải real-time IoT.
5. Chọn top risky asset `GENERATOR_002`.

**Nói:** Score hỗ trợ prioritization; không phải xác suất hỏng hoặc dự đoán thời điểm hỏng.

## 1:30–4:00 — Asset Lifecycle Và Field QR

### A. Chief Engineer

1. Đăng nhập `engineer.demo`, mở `/assets` và nhấn **Đăng ký asset**.
2. Tạo `DEMO_GENERATOR_001`, chọn location, technical identity, warranty, criticality và maintenance interval.
3. Mở detail, tải một PDF synthetic technical manual; chỉ metadata/checksum xuất hiện, không có local path.
4. Đổi operational status theo transition hợp lệ.
5. Mở QR tab, chỉ opaque lookup URL, tải/in label rồi mở `/scan/assets/{lookupToken}` ở viewport gần 390 px.

### B. Property Manager

1. Đăng nhập `manager.demo`, xem profile/history của asset vừa tạo.
2. Archive với lý do rõ ràng; xác nhận profile, attachment metadata và history vẫn còn, còn ticket-create bị chặn.
3. Restore explicit về `active` hoặc `inactive`; history có cả archive và restore actor/timestamp.

### C. Technician Và Helpdesk

1. Technician scan QR sau login: thấy identity, operational status, open tickets và action được phép; không có archive/profile-edit.
2. Helpdesk mở asset: chỉ đọc và có maintenance ticket entry point; không sửa technical/lifecycle/attachment.
3. Direct API attempt vượt permission phải trả `403`; UI hiding chỉ là UX.

**Nói:** Lifecycle và operational status là hai state khác nhau. QR chỉ nhận diện, không cấp quyền. Attachment bytes dùng safe local storage cho single-node pilot; đây chưa phải object storage production.

## 4:00–5:00 — Asset Detail Và Risk Explanation

1. Mở `GENERATOR_002`.
2. Chỉ measured facts: asset type, criticality, location, maintenance dates, recent anomaly.
3. Chỉ analytics explanation: contributing factors và recommended action.
4. Tách rõ facts khỏi recommendation.

**Nói:** Asset profile hiện đọc từ PostgreSQL. Risk/anomaly vẫn là snapshot từ batch gần nhất.

## 5:00–7:30 — Risk-To-Action Transaction

1. Nhấn **Create inspection ticket**.
2. Giữ prefilled asset/risk context, chọn priority và technician.
3. Lưu; chỉ ticket mới có status `Mới tạo`.
4. Mở Ticket workspace, chuyển sang `Đang xử lý` và cập nhật assignment/note.
5. Thêm maintenance result:
   - inspection result;
   - actions taken;
   - optional parts text;
   - maintenance result;
   - follow-up requirement;
   - next maintenance date.
6. Nếu result hoàn tất, chuyển ticket sang `Đã xử lý`; nếu cần theo dõi, giữ `Đang xử lý`.

**Nói:** Log insert và asset maintenance-date synchronization commit trong một PostgreSQL transaction. Ticket resolution vẫn là bước explicit của người dùng. UI không fake AI recalculation.

**Chỉ thông báo:** “Maintenance data has been recorded. Risk and KPI results will update in the next analytics batch.”

### Role checks trong workflow

1. Đăng nhập `helpdesk.demo`: intake và route ticket, nhưng maintenance execution/result và resolve controls không xuất hiện; direct API attempt trả `403`.
2. Đăng nhập `manager.demo`: assign ticket cho `TECH_002` và chuyển đúng status transition.
3. Đăng nhập `technician.demo`: chỉ thấy ticket được giao và tạo maintenance log; không có control assign/priority, direct API attempt bị từ chối.
4. Đăng nhập `admin.demo`: mở `/admin/users` và `/admin/audit`.
5. Trong audit view, filter resource `ticket` để chỉ actor, assignment, status và maintenance-log events; không hiển thị password/token/raw sensitive JSON.

## 7:30–9:00 — Copilot Có Nguồn

1. Từ asset hoặc ticket, mở Copilot.
2. Hỏi:

```text
Vì sao GENERATOR_002 đang rủi ro cao?
```

3. Chỉ structured context lấy từ PostgreSQL + latest analytics.
4. Chỉ checklist được retrieve, source title, document type, version và safety notice.
5. Hỏi thêm:

```text
Checklist kiểm tra ắc quy và khởi động máy phát là gì?
```

**Nói:** Qdrant retrieve chunk liên quan; deterministic composer không tự chẩn đoán. Technician phải xác minh hiện trường và ưu tiên manual/quy trình an toàn.

## 9:00–10:30 — Inventory Từ Requirement Đến Usage

**Thao tác:** Mở work order có requirement; chỉ ra reserve, issue, consumption và return là bốn record/action khác nhau. Mở movement timeline và low-stock view.

**Nói:** Reservation giảm available nhưng không giảm on-hand. Issue tạo physical movement; consumption chỉ xác nhận usage; return hoàn outstanding stock. Completion không tự tạo inventory action.

## 10:30–11:30 — Batch Refresh Có Chủ Đích

Không cần chạy trong demo ngắn; giải thích flow:

```text
PostgreSQL -> validated snapshot -> features -> anomaly -> risk -> reports
```

Nếu trình diễn refresh thật:

```powershell
python -m src.database.export_snapshot --replace
python -m src.features.build_features --input-dir data/analytics_input
python -m src.models.anomaly_detection
python -m src.risk.risk_scoring
python -m src.features.build_features --input-dir data/analytics_input --analysis maintenance
```

Sau đó refresh UI. Không có background scheduler trong milestone này.

## Safe Fallback Optional

```powershell
docker compose stop qdrant
```

Hỏi lại Copilot. Expected: safe fallback, zero sources, nhưng assets/tickets/logs/analytics pages vẫn hoạt động. Khởi động lại:

```powershell
docker compose start qdrant
```

## API Spot Checks

```powershell
Invoke-RestMethod http://localhost:8000/health
$loginBody = @{ identifier = "manager.demo"; password = "<DEMO_PASSWORD>" } | ConvertTo-Json
$login = Invoke-RestMethod http://localhost:8000/auth/login -Method Post `
  -ContentType "application/json" -Body $loginBody -SessionVariable BrowserSession
$headers = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod http://localhost:8000/auth/me -Headers $headers
Invoke-RestMethod "http://localhost:8000/assets/catalog?page=1&page_size=5" -Headers $headers
Invoke-RestMethod http://localhost:8000/assets/GENERATOR_002/profile -Headers $headers
Invoke-RestMethod http://localhost:8000/assets/GENERATOR_002/qr -Headers $headers
Invoke-RestMethod http://localhost:8000/assets/GENERATOR_002/history -Headers $headers
Invoke-RestMethod http://localhost:8000/assets/GENERATOR_002/details -Headers $headers
Invoke-RestMethod "http://localhost:8000/tickets?asset_id=GENERATOR_002" -Headers $headers
Invoke-RestMethod "http://localhost:8000/maintenance-plans?page_size=5" -Headers $headers
Invoke-RestMethod "http://localhost:8000/work-orders?page_size=5" -Headers $headers
Invoke-RestMethod "http://localhost:8000/work-orders/metrics?as_of_date=2026-07-20" -Headers $headers
```

OpenAPI vẫn có toàn bộ existing endpoints tại `http://localhost:8000/docs`.

## Điểm Kết Luận

- PostgreSQL cung cấp FK, transactions, unique sequences và optimistic conflicts cho focused workflow.
- Asset lifecycle, hierarchy, attachment metadata và audit là PostgreSQL-backed; local attachment bytes được checksum khi download.
- QR dùng opaque deterministic token và protected lookup, không chứa secret hoặc thay thế authorization.
- CSV vẫn phù hợp cho deterministic synthetic seed và batch model artifacts.
- FastAPI giữ business contract và enforce identity/permission trước service; Next.js không biết storage implementation.
- Local auth dùng memory access token, rotating HttpOnly refresh session, CSRF binding và immediate revocation checks.
- PostgreSQL audit append-only ghi cùng transaction với successful ticket/log mutation.
- Plan, work order, ticket và MaintenanceLog được tách; checklist version được snapshot và generation retry không tạo duplicate.
- Part, requirement, reservation, issue, consumption, return và movement được tách; server là nguồn quantity authoritative.
- Inventory dùng row locks, idempotency, immutable history và atomic transfer; không có procurement hoặc accounting.
- Completion và independent verification là hai action khác nhau; ticket resolution và analytics refresh vẫn explicit.
- RAG chỉ cung cấp source-grounded guidance; không thay thế technician.
- Remaining gaps gồm production scheduler/worker, notifications, SSO/MFA, distributed rate limiting, signing-key rotation, backup automation, observability và deployment hardening.

## Dừng Demo

```powershell
docker compose stop
```

Không xóa PostgreSQL volume nếu muốn giữ plans/work orders/tickets/logs/inventory. Canonical reset dùng explicit import `--replace`, sau đó chạy lại explicit PM4-PM6 seeds; không dùng routine volume deletion.

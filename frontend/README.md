# Next.js Maintenance Dashboard

Frontend manager-facing cho AI Maintenance Copilot. Ứng dụng dùng FastAPI làm serving boundary, TanStack Query để quản lý server state và Zod để kiểm tra response contract tại runtime.

Đây là frontend local/internal-pilot trên dữ liệu synthetic theo batch. Nó có focused asset lifecycle và maintenance decision workflow, không phải CMMS hoàn chỉnh và không được mô tả là production-ready.

## Cấu hình

```powershell
cd frontend
Copy-Item .env.example .env.local
```

Giá trị bắt buộc:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_CSRF_COOKIE_NAME=maintenance_csrf
```

Client loại bỏ trailing slash và chỉ chấp nhận URL `http` hoặc `https`. CSRF cookie name phải khớp backend. `.env.local` bị Git ignore; hai biến public chỉ là endpoint/cookie identifier, không chứa secret.

FastAPI mặc định cho phép browser origins `http://localhost:3000` và `http://127.0.0.1:3000`. Có thể đổi danh sách explicit bằng `CORS_ALLOWED_ORIGINS` ở backend; wildcard không được chấp nhận.

## Authentication Flow

- `/login` gửi identifier/password trực tiếp tới FastAPI qua HTTPS ngoài local.
- Access token ngắn hạn chỉ nằm trong module memory; không ghi `localStorage`, `sessionStorage` hoặc persistent Query cache.
- Refresh token nằm trong `HttpOnly` cookie nên JavaScript không đọc được. CSRF cookie được đọc để gửi `X-CSRF-Token` cho refresh/logout.
- `AuthProvider` restore session bằng một refresh request khi app khởi động. API client attach Bearer token tập trung và chỉ refresh/retry **một lần** cho eligible `401`.
- Refresh failure, inactive account hoặc revoked session xóa auth memory + TanStack Query cache rồi redirect về `/login?returnTo=...` với return path được validate nội bộ.
- `403` chuyển tới `/forbidden` hoặc hiển thị message rõ ràng. Permission-aware controls là UX; FastAPI vẫn enforce mọi action.

Current user, role label và logout nằm trong application shell. Permission codes lấy từ `/auth/me`; frontend không duy trì role matrix riêng.

## Chạy local

Terminal 1, từ repository root:

```powershell
docker compose up -d postgres
python -m alembic upgrade head
python -m src.ingestion.load_data --dry-run
python -m src.ingestion.load_data
python -m src.security.cli create-admin --username admin.local --display-name "Quản trị viên local"
python -m uvicorn src.api.main:app --reload --port 8000
```

Nếu PostgreSQL đã có canonical demo data, bỏ hai lệnh import. Normal runtime không fallback sang CSV khi database unavailable.

Lệnh admin prompt password hai lần và không in password. Demo roles chỉ được tạo explicit trong development bằng `python -m src.security.cli seed-demo-users`; không có default account ở startup.

Để dùng Copilot, khởi động Qdrant và index sáu tài liệu synthetic trước khi chạy API:

```powershell
docker compose up -d qdrant
python -m src.rag.index_documents
```

Các route analytics vẫn dùng được khi Qdrant dừng; chỉ retrieval của Copilot chuyển sang safe fallback.

Terminal 2:

```powershell
cd frontend
npm install
npm run dev
```

Mở `http://localhost:3000`.

## Routes đã kết nối

| Route | Nguồn dữ liệu | Trạng thái |
|---|---|---|
| `/` | assets, tickets, analytics KPI + PostgreSQL WO metrics | Live reads, risk action và operational work-order summary |
| `/assets` | paginated PostgreSQL catalog + latest batch signals | Create, filters, archived view và contextual ticket action |
| `/assets/[assetId]` | rich profile + existing analytics context | Edit, status/lifecycle, attachments, QR, history và ticket workflow |
| `/scan/assets/[lookupToken]` | authenticated opaque QR lookup | Mobile summary, open tickets, create ticket/Copilot theo permission |
| `/tickets` | tickets, related asset/log context | Live create, assign, transition, maintenance result và resolve |
| `/maintenance/plans` | preventive plans + generation reports | Filter, dry-run/generate và permission-aware lifecycle |
| `/maintenance/plans/new` | assets, templates, technicians, plan options | Controlled recurrence form, không có raw RRULE |
| `/maintenance/plans/[planId]` | plan, occurrences, generated work orders | Schedule update warning, pause/resume/archive và optimistic version |
| `/maintenance/checklists` | immutable template versions/items | Create/version/archive, safety/numeric validation |
| `/work-orders` | paginated PostgreSQL work orders + metrics | Full filters, responsive cards/table và manual create |
| `/work-orders/[workOrderId]` | WO/checklist/history/evidence | Assign, execute, complete, verify/cancel/reopen theo permission |
| `/work-orders/calendar` | bounded occurrence + WO projection | Date/asset/technician filters; không kéo-thả hoặc tạo source lịch thứ hai |
| `/anomalies` | anomalies và recurring issues | Live read-only |
| `/copilot` | `POST /copilot/ask`, assets và tickets | Live RAG, ID-only context handoff, sources và safe fallback |
| `/admin/users` | users + role options | Administrator create/update/activate/deactivate |
| `/admin/audit` | paginated audit events | Administrator/Property Manager read-only filters |
| `/login` | auth login/refresh | Public login surface |
| `/forbidden` | local authorization state | Friendly denied page |

Maintenance workflow giữ đúng ba endpoint FastAPI hiện có:

- `POST /tickets` tạo ticket ở trạng thái canonical `Mới tạo`;
- `PATCH /tickets/{ticket_id}` cập nhật assignment/priority/note và transition `Mới tạo -> Đang xử lý -> Đã xử lý`;
- `POST /maintenance/logs` ghi kết quả hiện trường trước khi resolve.

Form validate request trước khi gửi và validate response thành công trước khi xác nhận persistence. `ticket_id` và `asset_id` trên maintenance form được lấy từ ticket đang chọn, `follow_up_required` được suy ra từ `maintenance_result`, còn `next_maintenance_date` được tính theo `maintenance_interval_days` của asset. Risk/KPI không được sửa ở client và chỉ đổi sau lần chạy batch analytics tiếp theo.

Preventive/work-order workflow dùng additive endpoints:

- Plan form chỉ nhận interval day/week/month/year, IANA timezone, lead/grace, checklist version và assignee mặc định.
- Plan detail preview occurrence có date range giới hạn; dry-run không write, real generation hiển thị generated/skipped report.
- Ticket detail tạo corrective WO với source linkage; không có client-side ticket auto-resolution.
- Technician chỉ thấy execution controls khi có permission; backend tiếp tục kiểm tra assigned ownership.
- Checklist save cho phép tiến độ từng bước; completion chặn sớm required/safety failure và backend validate lại.
- Completion gửi một outcome request. Backend tạo exactly-one MaintenanceLog; frontend không POST duplicate log.
- Verification là action riêng cho reviewer khác; UI không giả lập asset date, risk hoặc KPI update.
- `409` hiển thị stale conflict và nút tải trạng thái mới; cancellation/reopen yêu cầu confirmation.

Asset management dùng additive endpoints cho catalog/profile create/update, operational/lifecycle transitions, archive/restore, locations, attachments, QR và history. Mọi update gửi `expected_version`; `409` hiển thị stale conflict và yêu cầu reload. Asset form cảnh báo khi đóng/reload với thay đổi chưa lưu. Retired/archived asset không hiện action tạo ticket.

Attachment UI chỉ chấp nhận PDF/PNG/JPG/JPEG tối đa 10 MB để feedback sớm; FastAPI vẫn kiểm tra signature/MIME/size, generated storage key, authorization và checksum. UI không inline-preview file. QR label chỉ chứa opaque lookup URL, in bằng isolated print CSS và route scan vẫn đi qua authentication.

## Data Layer

- `src/lib/api/config.ts`: kiểm tra API base URL.
- `src/lib/api/client.ts`: timeout, HTTP/network/write error mapping và request/response validation.
- `src/lib/api/auth-session.ts`: in-memory access token, deduplicated refresh handler và expired-session handler.
- `src/lib/api/schemas.ts`: Zod schemas bám theo FastAPI response contract.
- `src/lib/api/maintenance-schemas.ts`: explicit plan/template/work-order contracts và client coherence validation.
- `src/lib/api/query-keys.ts`: stable query keys và filter serialization.
- `src/lib/api/endpoints.ts`: toàn bộ maintenance, asset lifecycle, attachment/QR/history và Copilot calls.
- `src/lib/api/maintenance-endpoints.ts`: typed PM4 list/action/generation/evidence calls.
- `src/hooks/use-api-queries.ts`: reusable TanStack Query hooks.
- `src/hooks/use-api-mutations.ts`: confirmed-server write mutations và `useAskCopilot`; chat response không được lưu trong Query cache.
- `src/components/auth-provider.tsx`: session restore, login/logout, route guard và permission helpers.
- `src/lib/auth.ts`: permission constants và safe return-path validation; không có duplicate role matrix.
- `src/lib/copilot.ts`: suggested questions theo asset type, safe answer parser và user-facing retrieval states.
- `src/lib/adapters.ts`: chuyển API records sang display models.
- `src/lib/formatters.ts`: date, timestamp, percentage, duration và business labels.

Batch analytics có stale time 5 phút, không polling và không refetch khi focus. Health có stale time 30 giây. UI hiển thị `API`, `Analytics` và `RAG` thành ba trạng thái riêng; Qdrant unavailable không làm API bị gắn nhãn offline.

Sau write thành công, client chỉ invalidate/refetch các query liên quan:

- ticket create/update: ticket lists, asset list và asset detail tương ứng;
- maintenance log: maintenance-log lists, asset list và asset detail tương ứng;
- plan/template mutations: planning lists/detail/occurrence và schedule projection;
- work-order mutations: WO list/detail/calendar/metrics; completion/verification còn refresh linked asset/log data;
- risk, KPI, anomaly và health không bị invalidate vì write không tự chạy analytics.

Nếu API xác nhận write nhưng refetch thất bại, form giữ trạng thái thành công và yêu cầu refresh view, không khuyến khích gửi lại. Với timeout hoặc mất kết nối giữa write, trạng thái được đánh dấu ambiguous; kiểm tra ticket/log list trước khi thử lại để tránh duplicate.

## Copilot Live Workflow

Copilot có thể mở từ priority asset ở Overview, asset detail, ticket detail hoặc navigation độc lập. URL chỉ mang stable IDs:

```text
/copilot?asset=GENERATOR_002&ticket=TCK-000041
```

Frontend tải lại asset/ticket từ FastAPI và chỉ gửi các field backend chấp nhận: `question`, optional `asset_id`, `top_k`, optional `document_type` và optional `failure_category`. Asset type, risk explanation, maintenance status, ticket description và technician được hiển thị như local context; chúng không được nhét vào URL hoặc thêm vào request trái contract.

Response được Zod validate trước khi hiển thị. UI tách:

- dữ liệu thiết bị thực tế và analytics explanation;
- hướng dẫn được truy xuất từ SOP/checklist;
- toàn bộ sources với title, document type, version, asset type và metadata mở rộng;
- safety notice và giới hạn khuyến nghị.

Answer/source content được render thành text và list an toàn, không dùng `dangerouslySetInnerHTML`, không hiển thị chunk ID hoặc vector score. Enter gửi, Shift+Enter xuống dòng, giới hạn câu hỏi là 1.000 ký tự và duplicate submit bị khóa khi request đang chạy.

History tối đa tám lượt chỉ tồn tại trong React state của page hiện tại. Reload hoặc rời page sẽ xóa history; không có persistence ở browser, FastAPI hoặc database. Mỗi lượt giữ response, sources và safety notice riêng.

Các response `empty`, `low_relevance`, `unsupported_asset_type`, `unrelated`, `missing_asset_context` và `unavailable` là confirmed safe fallback, không phải fabricated answer. Timeout/network/503 giữ nguyên câu hỏi để retry; invalid asset hiển thị lỗi riêng. Khi Qdrant unavailable, các route Overview, Assets, Tickets và Anomalies vẫn hoạt động.

## Transaction Và Reset Demo

PostgreSQL là transactional source of truth cho asset/location/attachment metadata, ticket, preventive plan, checklist template, work order, maintenance log, users, refresh sessions và audit. Attachment bytes dùng private local storage qua abstraction. Backend có FK, atomic database transactions, generated sequences, optimistic conflict handling, RBAC và transaction-coupled audit, nhưng chưa có production scheduler, SSO/MFA, distributed throttling hoặc operations hardening.

Frontend mutation tests vẫn mock HTTP; backend có dedicated PostgreSQL integration tests. Để khôi phục canonical transactional data và analytics sau một demo có write, chạy từ repository root:

```powershell
python -m src.data_generation.generate_data
python -m src.ingestion.validation
python -m src.ingestion.load_data --replace
python -m src.maintenance_management.cli seed-development
python -m src.database.export_snapshot --replace
python -m src.features.build_features --input-dir data/analytics_input
python -m src.models.anomaly_detection
python -m src.risk.risk_scoring
python -m src.features.build_features --input-dir data/analytics_input --analysis maintenance
```

`--replace` là destructive với transactional demo data, gồm PM4 plans/templates/work orders; chỉ dùng khi chủ động reset. Seed maintenance là explicit và idempotent, không tạo user hoặc password.

## Mock Boundary

Tất cả production routes, gồm `/copilot`, độc lập với `src/lib/mock-data.ts`. File mock chỉ còn là visual fixture không được import vào live screen; test `src/test/mock-boundary.test.ts` bảo vệ boundary này.

## Kiểm tra

```powershell
npm run lint
npm test
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
npm run build
```

Frontend tests mock HTTP responses và kiểm tra login/session, guards, role-aware actions, asset lifecycle, recurrence/date validation, plan rendering/generation controls, technician WO execution, stale conflict, checklist completion guard, attachment/QR, admin/audit và existing risk-to-ticket flow. Browser smoke test vẫn cần FastAPI để xác nhận cookie, CORS credentials, file download/print và dữ liệu hiện tại.

## Security Limitations

Đây là local/internal-pilot UI, chưa có SSO, MFA, password recovery, centralized session management hoặc browser-level penetration test. Attachment storage hiện single-node local, chưa có malware scanner/S3/object backup. QR chưa có camera/browser compatibility matrix và không hỗ trợ offline. Non-local usage bắt buộc HTTPS và backend `Secure` cookie. In-memory access token giảm persistence nhưng XSS trong origin vẫn có thể sử dụng active session; tiếp tục cần CSP, dependency scanning và security review trước deployment thực tế.

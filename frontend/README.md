# Next.js Maintenance Dashboard

Frontend manager-facing cho AI Maintenance Copilot. Ứng dụng dùng FastAPI làm serving boundary, TanStack Query để quản lý server state và Zod để kiểm tra response contract tại runtime.

Đây là frontend portfolio MVP trên dữ liệu synthetic theo batch, không phải CMMS hoàn chỉnh và không được mô tả là production-ready.

## Cấu hình

```powershell
cd frontend
Copy-Item .env.example .env.local
```

Giá trị bắt buộc:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Client loại bỏ trailing slash và chỉ chấp nhận URL `http` hoặc `https`. `.env.local` bị Git ignore; biến public này chỉ chứa địa chỉ API, không chứa secret.

FastAPI mặc định cho phép browser origins `http://localhost:3000` và `http://127.0.0.1:3000`. Có thể đổi danh sách explicit bằng `CORS_ALLOWED_ORIGINS` ở backend; wildcard không được chấp nhận.

## Chạy local

Terminal 1, từ repository root:

```powershell
python -m uvicorn src.api.main:app --reload --port 8000
```

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
| `/` | assets, tickets, preventive, maintenance KPI | Live read-only |
| `/assets` | enriched asset overview | Live read-only |
| `/assets/[assetId]` | consolidated asset details | Live read-only, dynamic ID |
| `/tickets` | tickets và related asset context | Live read-only |
| `/anomalies` | anomalies và recurring issues | Live read-only |
| `/copilot` | response fixture minh họa | Mock cho tới Copilot frontend milestone |

Ticket assignment, status transition, maintenance result và resolution controls được hiển thị disabled hoặc ghi rõ chưa kết nối. Frontend Milestone 2 không gọi `POST /tickets`, `PATCH /tickets/{ticket_id}` hoặc `POST /maintenance/logs`.

## Data Layer

- `src/lib/api/config.ts`: kiểm tra API base URL.
- `src/lib/api/client.ts`: timeout, HTTP/network error mapping và JSON validation.
- `src/lib/api/schemas.ts`: Zod schemas bám theo FastAPI response contract.
- `src/lib/api/query-keys.ts`: stable query keys và filter serialization.
- `src/lib/api/endpoints.ts`: toàn bộ read calls.
- `src/hooks/use-api-queries.ts`: reusable TanStack Query hooks.
- `src/lib/adapters.ts`: chuyển API records sang display models.
- `src/lib/formatters.ts`: date, timestamp, percentage, duration và business labels.

Batch analytics có stale time 5 phút, không polling và không refetch khi focus. Health có stale time 30 giây. UI giữ main API status, RAG status và synthetic-data label tách biệt.

## Mock Boundary

Các live routes không import `src/lib/mock-data.ts`. Mock content chỉ còn phục vụ Copilot screen và visual fixtures chưa kết nối; test `src/test/mock-boundary.test.ts` bảo vệ boundary này.

## Kiểm tra

```powershell
npm run lint
npm test
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
npm run build
```

Frontend tests mock HTTP responses và không yêu cầu Python API. Browser smoke test vẫn cần FastAPI để xác nhận CORS và dữ liệu portfolio hiện tại.

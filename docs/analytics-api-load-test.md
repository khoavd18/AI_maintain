# Stage 10 — Authenticated Analytics API Load Test

## Contract đo

Runner `python -m data_platform.api_benchmark` dùng `httpx.AsyncClient`, login qua
`POST /auth/login`, lấy access token thật và gửi Bearer token cho toàn bộ request.
API chạy hai Uvicorn workers trong service `stage10-api`; analytics query PostgreSQL
thật, không cache dummy response và không bypass authentication.

Workload cuối:

- pipeline ở trạng thái idle;
- date range `2024-01-01..2024-12-31`;
- site `00020000-0000-0000-0000-000000000001`;
- limit 25;
- round-robin public health và sáu authenticated domain capabilities;
- 4 request/client: 100 request ở 25 clients và 200 request ở 50 clients.

Credential được sinh ngẫu nhiên trong memory, chỉ truyền qua environment đến CLI
bootstrap/runner và không được in hoặc ghi artifact. Username benchmark không có
mật khẩu mặc định trong repository.

## Kết quả

| Clients | Requests | Duration | RPS | p50 | p95 | p99 | Max | Success/error |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 25 | 100 | 3,314 s | 30,1753 | 1.651,3 ms | 2.814,8 ms | 3.090,8 ms | 3.092,7 ms | 100 / 0 |
| 50 | 200 | 8,441 s | 23,6934 | 4.237,3 ms | 7.588,9 ms | 7.889,8 ms | 8.003,8 ms | 200 / 0 |

HTTP status distribution là `200` cho 100% request. Cả 87/87 và 171/171
analytics responses tương ứng là JSON list không rỗng.

| Clients | PG connections before/max/after | API container before | API container after |
|---:|---|---|---|
| 25 | 16 / 27 / 16 | 0,54%; 355,9 MiB; 38 PIDs | 0,51%; 380,9 MiB; 61 PIDs |
| 50 | 16 / 30 / 16 | 0,45%; 380,9 MiB; 61 PIDs | 0,62%; 405,9 MiB; 86 PIDs |

CPU là snapshot `docker stats` trước/sau, không phải time-series maximum. PostgreSQL
connection monitor lấy sample 100 ms; không có sample error trong run cuối.

## Reliability fixes từ diagnostic runs

Các run chẩn đoán trước artifact cuối không được dùng làm benchmark result:

1. image đầu thiếu package `data_platform`, làm API không import được; Dockerfile
   được sửa để package declared trong `pyproject.toml` thực sự có trong image;
2. PostgreSQL không bind parameter trực tiếp trong `SET LOCAL`; adapter chuyển sang
   parameterized `set_config(..., true)`;
3. workload global 50-client đã chạm `max_connections` và timeout. Adapter được
   thêm backpressure 8 analytical queries/worker, monitor không làm mất artifact
   khi sample connection tạm thất bại;
4. run cuối dùng explicit site scope, là workload bounded thực tế và tận dụng các
   measured site/date indexes. Không tăng PostgreSQL `max_connections`, không nới
   statement timeout 30 giây và không giảm số client.

Site scope quan trọng: serial global inventory aggregate phải scan 1,5 triệu
movements (~1,85 s trên máy này), còn site-scoped call đo ~84 ms khi idle. Kết quả
cuối không được diễn giải thành global-query capacity hay production SLA.

## Reproduce

```powershell
$env:DATA_PLATFORM_DB_NAME = 'maintenance_copilot_benchmark_scale'
docker compose -f docker-compose.scale.yml build stage10-api
docker compose -f docker-compose.scale.yml up -d --wait stage10-api

# Sinh password ngẫu nhiên ngoài repository, bootstrap một user explicit,
# đặt STAGE10_BENCHMARK_PASSWORD chỉ trong process hiện tại.
.\.venv\Scripts\python.exe -m data_platform.api_benchmark `
  --base-url http://127.0.0.1:18082 `
  --username <explicit-benchmark-admin> `
  --requests-per-client 4 `
  --site-id 00020000-0000-0000-0000-000000000001 `
  --pipeline-state idle `
  --output data/scale/stage10-api-benchmark.json
```

Raw artifact SHA-256:
`17e6dd96066e619a934cfe773d762306921332a7d6affd8f5b482c07b98774a8`.

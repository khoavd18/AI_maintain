# Internal Pilot Secret Rotation

## Secrets Và Configuration

- `DATABASE_URL`: username/password từ environment; pilot không chấp nhận
  `maintenance:maintenance`, missing components hoặc literal `replace_with_*`
  placeholders.
- `TOKEN_SIGNING_SECRET`: current HS256 key, tối thiểu 32 ký tự.
- `TOKEN_SIGNING_PREVIOUS_SECRET`: optional, chỉ dùng trong grace period.
- Refresh/CSRF secrets được tạo ngẫu nhiên theo session; PostgreSQL chỉ lưu hash.
- Cookie names, attachment root và frontend API origin là configuration, không
  phải secret. `NEXT_PUBLIC_*` luôn public.

Không ghi secret vào Git, command history, ticket, notification, audit, health,
metrics hoặc log. Không log hash của low-entropy password/secret.

## JWT Signing Rotation

1. Sinh current key mới bằng approved random generator ngoài repository.
2. Deploy đồng thời:
   - `TOKEN_SIGNING_SECRET=<new>`;
   - `TOKEN_SIGNING_PREVIOUS_SECRET=<old>`.
3. Restart API processes có kiểm soát; token mới ký bằng key mới, access token cũ
   vẫn verify bằng đúng một previous key.
4. Smoke login, protected read, refresh và logout.
5. Chờ ít nhất `ACCESS_TOKEN_LIFETIME_MINUTES` kể từ khi process cuối dùng old key
   dừng phát token.
6. Xóa `TOKEN_SIGNING_PREVIOUS_SECRET`, restart và smoke lại.

Không chain nhiều old keys. Refresh token không phụ thuộc JWT signing key; refresh
rotation phát access token mới. Nếu nghi lộ key, bỏ grace period, rotate ngay và
thu hồi refresh sessions theo incident decision.

PM8 checkpoint chỉ verify implementation bằng test keys. Real pilot signing-key
rotation chưa được thực hiện và vẫn là go/no gate mở.

## Database Credential Rotation

1. Tạo/alter credential trong PostgreSQL theo operator policy.
2. Cập nhật `DATABASE_URL` qua protected environment injection.
3. Restart worker rồi API từng process; xác nhận readiness/reconnect.
4. Thu hồi old credential sau khi không còn connection cũ.
5. Chạy authentication/RBAC, worker heartbeat và pending-work smoke.

Không sửa `.env.example` thành giá trị thật. Local `.env` phải có filesystem
permission phù hợp và không commit.

## Refresh/CSRF

Không có shared refresh-session secret để rotate: mỗi refresh/CSRF value là random
và chỉ hash được persist. Password change, account disable, logout và refresh
rotation tiếp tục revoke session. Cookie-name change làm client cookie cũ không
được đọc; xử lý như forced re-login và cập nhật backend/frontend config đồng bộ.

## Attachment/Frontend Configuration

Đổi attachment root chỉ sau khi copy/verify checksum toàn bộ bytes và giữ generated
relative keys. Không đặt credential trong `NEXT_PUBLIC_API_BASE_URL`; frontend
build artifact có thể công khai mọi `NEXT_PUBLIC_*`.

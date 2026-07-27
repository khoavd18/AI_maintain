# PM9 Pilot Secret Rotation And Rollback

## Current Status

Real pilot secrets, owner approval và real rotation evidence không có trong
repository hoặc current environment. Không có secret value nào được tạo, đọc ra
hay ghi vào tài liệu PM9.

PM8 đã test current/one-previous signing-key behavior bằng synthetic keys. PM9
có opt-in `src.reliability.secret_rotation` để tạo ephemeral keys và kiểm tra
overlap, previous-key removal, within-window rollback, forward restore,
simulated post-window removal, refresh/CSRF mechanics và report redaction.
Focused deployment/contract tests cũng kiểm tra placeholder, weak/missing
secret. Đó không phải real pilot rotation.

Focused PM9 mutation/secret batch đạt `9 passed`; secret tests xác nhận report
không chứa generated secret, JWT hoặc refresh/CSRF token material. Không có real
process restart, database credential hay elapsed overlap-window evidence.

```text
NO-GO / NOT YET VERIFIED
```

## Required Approval

Trước rehearsal cần:

- security contact, release owner, rollback owner và incident coordinator đã
  assign;
- approved maintenance window và support coverage;
- protected secret distribution method;
- current/previous key custody và database credential operator;
- explicit maximum overlap window;
- session-impact communication;
- rollback decision point và evidence directory ngoài repository.

Không ghi secret, hash của low-entropy secret, database URL, token, cookie,
Authorization header hoặc personal contact vào evidence.

## Access-Token Signing Rotation

1. Ghi current release/health, active session count ở aggregate level và
   readiness; không ghi token.
2. Tạo new key bằng approved generator ngoài repository.
3. Cấu hình:
   - `TOKEN_SIGNING_SECRET=<new>`;
   - `TOKEN_SIGNING_PREVIOUS_SECRET=<old>`.
4. Restart API có kiểm soát; worker không cần signing key để bypass service
   authorization và không được cấp bypass mới.
5. Xác nhận token mới chỉ ký bởi current key.
6. Xác nhận unexpired token ký bởi previous key chỉ còn valid trong overlap.
7. Smoke login, protected read, refresh, CSRF-protected logout và revoked session.
8. Chờ ít nhất access-token lifetime kể từ process cuối cùng phát old-key token,
   hoặc dùng shorter incident path nếu key bị nghi lộ.
9. Xóa previous key, restart và xác nhận old-key token fail, current token/session
   behavior đúng.
10. Ghi redacted result, cleanup synthetic tokens và đóng window.

Chỉ hỗ trợ đúng một previous key; không chain nhiều old keys.

## Rollback Trong Overlap Window

Nếu new key gây authentication failure trong approved window:

1. dừng rollout;
2. đặt old key trở lại current slot;
3. chỉ giữ new key ở previous slot nếu security contact cho phép;
4. restart API;
5. smoke login/access/refresh/logout và readiness;
6. ghi nguyên nhân/impact không chứa secret;
7. quyết định lại rotation sau khi sửa.

Rollback sau khi previous key đã bị loại bỏ không được giả định giữ session cũ.
Nếu nghi compromise, không kéo dài overlap chỉ để giữ session; revoke refresh
sessions theo incident decision.

## Database Credential Rotation

1. Backup và xác nhận rollback point.
2. Tạo/alter pilot database credential theo PostgreSQL operator policy.
3. Cập nhật protected `DATABASE_URL`; đồng bộ API, worker, migration và backup
   operator configuration.
4. Restart worker rồi API từng process.
5. Xác nhận readiness, worker heartbeat, pending work, auth/RBAC và representative
   transaction.
6. Kiểm tra không còn old connection, rồi revoke old credential.
7. Nếu fail trong window, restore old credential/config và chạy lại smoke.

Không sửa `.env.pilot.example` thành giá trị thật. Frontend public API origin
phải đồng bộ khi endpoint thay đổi, nhưng không được chứa credential.

## Session, CSRF Và Frontend Impact

- Refresh/CSRF values là per-session random values; PostgreSQL chỉ giữ hash.
- Signing-key rotation không tự revoke refresh session; refresh phát access token
  bằng current key.
- Cookie-name hoặc origin change có thể buộc re-login và phải được ghi trong user
  communication.
- `AUTH_COOKIE_SECURE=true` cần HTTPS ngoài local.
- Build-time `NEXT_PUBLIC_*` là public và không phải secret channel.

## Required Evidence

| Check | Current PM9 result |
|---|---|
| Missing/placeholder pilot secret blocks startup/contract | Covered by focused synthetic tests |
| Current/previous signing semantics | Prior PM8 evidence; PM9 synthetic tool implemented |
| Previous-key removal | PM9 synthetic path implemented; no PM9 pilot run |
| Simulated rollback transition | PM9 synthetic path implemented; no process restart or elapsed window |
| Explicit real rollback-window rehearsal | Not executed |
| Database credential rotation | Not executed |
| Frontend/backend synchronization | Not executed |
| Active-session impact | Not measured |
| Log/health redaction with real pilot config | Not executed |

Real gate chỉ pass khi approved pilot values được dùng mà không xuất hiện trong
report, logs hoặc health. Xem [security boundary](security.md),
[existing rotation design](secret_rotation.md) và
[release rehearsal](pilot_release_rehearsal.md).

Synthetic command, sau khi tests/output directory được review:

```powershell
$env:PM9_ALLOW_SYNTHETIC_SECRET_ROTATION = "true"
python -m src.reliability.secret_rotation `
  --output-dir "<outside-repository-report-directory>"
```

Report cố ý ghi `real_pilot_rotation_gate_passed=false` và
`real_time_overlap_window_elapsed=false`.

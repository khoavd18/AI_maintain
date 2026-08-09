# RBAC Matrix

## Nguyên Tắc

`src/security/permissions.py` là nguồn role/permission canonical. FastAPI dependency kiểm tra coarse permission; service tiếp tục kiểm tra lifecycle, ticket ownership và separation of duties. Next.js chỉ dùng permission codes từ `/auth/me` để ẩn hoặc hiện controls, không phải security boundary.

## Ticket Và SLA

| Capability | Administrator | Property Manager | Chief Engineer | Technician | Helpdesk | Storekeeper |
|---|---:|---:|---:|---:|---:|---:|
| Đọc ticket/queue | Có | Có | Có | Ticket được gán | Có | Read-only context |
| Intake ticket | Có | Có | Có | Không | Có | Không |
| Assign/group routing | Có | Có | Có | Không | Có | Không |
| Acknowledge | Có | Có | Có | Ticket được gán | Có | Không |
| Start/hold/resume | Có | Có | Có | Ticket được gán | Không | Không |
| Đổi impact/urgency | Có | Có | Có | Ticket được gán | Có | Không |
| Resolve | Có | Có | Có | Ticket được gán | Không | Không |
| Close | Có | Có | Không | Không | Không | Không |
| Reopen | Có | Có | Có | Không | Không | Không |
| Cancel | Có | Có | Không | Không | Không | Không |
| Internal comment | Có | Có | Có | Ticket được gán | Có | Không |
| Requester-visible comment | Có | Có | Không | Không | Có | Không |
| Reporter PII | Có | Có | Không | Không | Có | Không |
| Đọc SLA configuration | Có | Có | Có | Không | Có | Không |
| Quản lý calendar/policy | Có | Có | Không | Không | Không | Không |
| Escalation dry-run | Có | Có | Có | Không | Có | Không |
| Escalation execute | Có | Có | Không | Không | Có | Không |

Administrator có toàn bộ permission codes. Bảng thể hiện behavior chính; exact list luôn lấy từ `GET /users/roles`.

## Notifications Và Background Operations

| Capability | Administrator | Property Manager | Chief Engineer | Technician | Helpdesk | Storekeeper |
|---|---:|---:|---:|---:|---:|---:|
| Đọc/mutate personal notification | Có | Có | Có | Có | Có | Có |
| Đọc job/execution/outbox/metrics | Có | Không | Không | Không | Không | Không |
| Enable/disable supported job | Có | Không | Không | Không | Không | Không |
| Manual trigger/retry | Có | Không | Không | Không | Không | Không |

Notification permission không cho đọc inbox của user khác. Administrator operator
permission cũng không tạo generic cross-user notification read API. Enable job
snapshot Administrator làm run-as actor, nhưng worker vẫn gọi canonical business
service và chịu permission/resource rules.

## Work-Order Separation

- Property Manager và Chief Engineer có thể tạo/link corrective work order theo permission hiện có.
- Technician chỉ execute assigned ticket/work order.
- Work-order completion tạo maintenance outcome riêng; verification cần authorized reviewer khác actor thực hiện.
- Không role nào được auto-resolve ticket qua work-order action. Ticket resolution là named action riêng.

## Inventory

| Capability | Administrator | Property Manager | Chief Engineer | Technician | Helpdesk | Storekeeper |
|---|---:|---:|---:|---:|---:|---:|
| Đọc inventory/report | Có | Có | Có | Assigned WO only | Limited availability | Có |
| Quản lý part master | Có | Không | Không | Không | Không | Có |
| Quản lý stock location | Có | Không | Không | Không | Không | Có |
| Opening balance/receipt | Có | Không | Không | Không | Không | Có |
| Thêm WO requirement | Có | Không | Có | Không | Không | Không |
| Reserve/release/expire/replace | Có | Không | Có | Không | Không | Có |
| Issue | Có | Không | Không | Không | Không | Có |
| Explicit consumption | Có | Không | Không | Assigned WO | Không | Không |
| Return | Có | Không | Không | Không | Không | Có |
| Transfer/adjust/damaged | Có | Không | Không | Không | Không | Có |
| Đọc inventory evidence | Có | Có | Có | Assigned WO only | Không | Có |
| Upload/delete inventory evidence | Có | Không | Không | Không | Không | Có |

Service enforce assigned-work-order ownership cho Technician ngay cả khi actor có coarse `work_order_parts:read` hoặc `inventory:consume`. Helpdesk không được đọc unit-cost metadata. Frontend controls chỉ phản ánh permission; FastAPI vẫn trả `403` cho request không hợp lệ.

Không role nào được PATCH balance, sửa/xóa movement hoặc tự động tạo purchase order. Storekeeper không có quyền complete/verify work order hoặc thay ticket lifecycle chỉ vì đã issue/return stock.

## PII Và Communication

- Role thiếu `ticket_pii:read` nhận contact fields là `null`.
- Internal comments chỉ trả cho actor có internal-comment permission.
- Requester-visible comments có thể dùng làm phối hợp, nhưng PM7 chỉ tạo internal
  in-app notification và không gửi email/SMS/push.
- Audit chỉ giữ safe actor/action/resource metadata; reporter contact và secret bị loại.

## Authorization Failures

- Thiếu permission: HTTP `403`.
- Technician truy cập ticket không thuộc ownership: HTTP `403`.
- Technician truy cập inventory/evidence của work order không được gán: HTTP `403`.
- Stale `expected_version`: HTTP `409`.
- Invalid transition hoặc relationship: HTTP `409`.
- Invalid request shape/value: HTTP `400` hoặc `422` tùy validation boundary.

Role matrix này phù hợp local/internal pilot, chưa phải enterprise IAM. Không có multi-tenancy, SSO, MFA hoặc external identity provider.

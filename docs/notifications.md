# In-App Notifications

## Phạm Vi

PM7 cung cấp notification inbox bên trong authenticated Next.js application.
Notification hỗ trợ nhận biết sự kiện vận hành; nó không phải email, SMS, push,
customer messaging hoặc bằng chứng rằng người nhận đã thực hiện hành động.

## Recipient Rules

Worker chỉ resolve active users từ existing identity/RBAC model:

| Event | Người nhận |
|---|---|
| Critical ticket | Administrator, Property Manager, Chief Engineer |
| Ticket assigned | Assigned user |
| Ticket held/resumed | Assigned user và Chief Engineer |
| SLA warning/breach/escalation | Assigned user, Administrator, Property Manager, Chief Engineer |
| Work order assigned | Assigned user |
| Work order completed | Property Manager và Chief Engineer |
| Inventory issue completed | Issued-to user và Storekeeper |
| Preventive work orders generated | Chief Engineer |
| Stock below reorder point | Administrator, Chief Engineer, Storekeeper |
| Analytics refresh dead-lettered | Administrator và Property Manager |

Một user khớp nhiều rule chỉ nhận một notification cho cùng outbox event.
Inactive users bị loại. Ticket requester không được tự động nhận internal event
vì repository chưa có confirmed external-customer communication policy.

## Privacy Và Content

- Notification chỉ chứa title/body tiếng Việt và structured fields đã
  allow-list.
- Không chứa password, token, cookie, Authorization header, reporter email/phone,
  attachment bytes hoặc local storage path.
- Outbox payload tối đa 16 KiB; notification body tối đa 1.000 ký tự.
- Related entity chỉ chứa type và opaque/business ID cần để điều hướng.
- Operator outbox API không trả event payload.

## Ownership Và State

Mỗi notification thuộc đúng một `recipient_user_id`. FastAPI luôn lấy owner từ
authenticated user; client không được gửi user ID để đọc hoặc mutate inbox
người khác.

Các action:

- `read`: đặt `read_at`;
- `unread`: xóa `read_at`;
- `dismiss`: đặt `dismissed_at`;
- `read-all`: đánh dấu tất cả notification chưa dismiss của current user.

Mutation dùng `expected_version`; stale client nhận conflict. Dismiss không xóa
row hoặc delivery history. List có stable order mới nhất trước, pagination,
`unread_only` và severity filter.

## Deduplication

Unique `(recipient_user_id, deduplication_key)` ngăn worker retry tạo duplicate.
Deduplication key được derive từ outbox event và recipient. Low-stock alert còn
có persistent recovery cycle để cùng một shortage không lặp liên tục.

## API

```text
GET  /notifications
GET  /notifications/unread-count
POST /notifications/{notification_id}/read
POST /notifications/{notification_id}/unread
POST /notifications/{notification_id}/dismiss
POST /notifications/read-all
```

Tất cả role nội bộ hiện có `notifications:read`; server vẫn là authorization
boundary. Chi tiết request/response tại [API contract](api_contract.md).

## Next.js

- Bell trong authenticated shell hiển thị unread count.
- Sheet hiển thị notification gần nhất và action read/unread/dismiss.
- `/notifications` có filter, pagination, loading/empty/error state.
- Related links chỉ xuất hiện khi frontend biết user có permission phù hợp;
  FastAPI vẫn kiểm tra quyền ở destination route.
- `/admin/jobs` dành cho Administrator và tách khỏi personal inbox.

## Giới Hạn

PM7 chưa có notification preference, digest, acknowledgement, retention policy,
external delivery, delivery receipt hoặc distributed push. Operator phải dựa
vào job/outbox metrics và runbook để theo dõi backlog.

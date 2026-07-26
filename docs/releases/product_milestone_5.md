# Product Milestone 5: Ticket Operations Và SLA

## Trạng Thái Release

Product Milestone 5 đã triển khai bounded context quản lý ticket, SLA và
communication cho AI Maintenance Copilot. Release này là nền tảng cho
internal pilot, chưa phải chứng nhận production readiness, security hoặc SLA
performance.

PM1-PM6 đã được triển khai. PM7 chưa bắt đầu.

## Mục Tiêu

PM5 chuyển ticket từ lifecycle compatibility ba trạng thái sang workflow vận
hành rõ ràng, có phân công, business priority, SLA snapshot, timeline và audit.
Mục tiêu là giúp Helpdesk, Manager, Chief Engineer và Technician phối hợp xử lý
sự cố mà vẫn giữ:

- quyết định cuối cùng thuộc về con người;
- ticket lifecycle độc lập với work-order lifecycle;
- legacy `/tickets` contract cho các client hiện hữu;
- một canonical service và PostgreSQL repository, không đặt business rules
  trong route hoặc frontend.

Canonical implementation:

- domain và priority matrix: `src/ticket_management/domain.py`;
- business-calendar math: `src/ticket_management/sla.py`;
- named actions và business rules: `src/ticket_management/service.py`;
- transaction repository: `src/repositories/postgres_tickets.py`;
- typed FastAPI boundary: `src/ticket_management/routes.py` và
  `src/ticket_management/schemas.py`.

## Migration Và Schema

Migration [20260723_0005](../../migrations/versions/20260723_0005_add_ticket_intake_sla_and_escalation.py)
nâng schema từ `20260720_0004` và bổ sung:

- support groups, ticket categories, subcategories và intake sources;
- versioned business calendars, working periods và holidays;
- SLA policies và priority-specific targets;
- per-ticket SLA state với policy/calendar snapshot;
- append-only ticket comments, SLA events và escalation events;
- comment-to-attachment links;
- rich lifecycle, routing, priority, reporter và optimistic-concurrency fields
  trên `maintenance_tickets`.

Migration backfill legacy ticket theo quy tắc deterministic, thay constraint
phù hợp rich lifecycle và cài database trigger chặn `UPDATE`/`DELETE` trên
communication/SLA/escalation history.

## Ticket Lifecycle

Rich API dùng code-level states:

```text
open
  -> assigned
  -> in_progress
  -> waiting
  -> resolved
  -> closed
```

Các nhánh được kiểm soát gồm `cancelled` và `reopened`. Mỗi thay đổi dùng named
action: `assign`, `acknowledge`, `start`, `hold`, `resume`, `resolve`, `close`,
`reopen` hoặc `cancel`. Rich API không có generic status patch.

Các invariant chính:

- mọi mutation nhận `expected_version`; stale update trả conflict;
- `acknowledge` ghi first response nhưng không tự đổi lifecycle;
- `hold`, `reopen` và `cancel` bắt buộc có reason;
- ticket chỉ resolve từ `in_progress` sau khi có linked maintenance log;
- work-order create, complete hoặc verify không tự resolve/close ticket;
- Technician chỉ execute ticket được gán cho mình;
- reopen tạo SLA occurrence mới và không xóa event cũ.

Chi tiết state machine nằm trong
[Ticket Operations và SLA](../ticket_operations.md).

## Priority

Priority là kết quả backend-derived từ ma trận `impact x urgency`. Frontend chỉ
preview kết quả do server trả và không duy trì ma trận độc lập hoặc submit
priority tùy ý.

```text
critical + immediate -> critical
high + high          -> high
medium + medium      -> medium
low + low            -> low
```

Mọi thay đổi impact/urgency đều được tính lại tại service boundary và yêu cầu
reason/audit phù hợp.

## SLA Snapshot Và Business Calendar

Khi intake, hệ thống chọn SLA policy đang hiệu lực rồi snapshot:

- policy code/name và target theo priority;
- first-response và resolution target minutes;
- calendar version, IANA timezone, working periods và holidays;
- `pause_on_waiting` và `due_soon_percent`.

Sửa policy/calendar chỉ ảnh hưởng ticket tạo sau đó. Historical deadline không
bị recompute từ master data đã thay đổi.

Business calendar chỉ hỗ trợ same-day, timezone-aware, non-overlapping working
periods. SLA math bỏ qua non-working time và holidays theo snapshot.

Khi ticket vào `waiting`, pause phải có reason. Nếu policy cho phép pause,
service lưu remaining business minutes; `resume` tính deadline mới từ thời điểm
tiếp tục. Reopen tăng `occurrence_number` và mở resolution clock mới mà không
xóa occurrence trước.

## Escalation Và Append-Only History

Escalation chỉ được đánh giá qua explicit API/CLI service:

- dry-run không ghi dữ liệu;
- execute không gửi email/SMS và không tự đổi ticket status;
- uniqueness boundary
  `(ticket_id, rule_code, occurrence_number)` làm retry idempotent;
- ticket comments, SLA events và escalation events là append-only;
- database administrator vẫn là trust boundary cuối cùng.

Không có hidden scheduler, notification worker hoặc automatic transition trong
release này.

## PII Và RBAC

Reporter name, email và phone chỉ hiển thị cho actor có `ticket_pii:read`.
Actor khác nhận projection đã redacted. Audit payload không chứa reporter
contact, token, cookie, credential hoặc attachment body/path.

Phân quyền chính:

| Role | Quyền chính trong PM5 |
|---|---|
| Administrator | Toàn bộ ticket/SLA/reference administration |
| Property Manager | Assign, execute, resolve, close/reopen, SLA management |
| Chief Engineer | Assign/execute/resolve/reopen và technical coordination |
| Technician | Acknowledge/execute/resolve ticket được gán, internal comment |
| Helpdesk | Intake, route, acknowledge, communication, escalation evaluation |
| Storekeeper | Limited ticket identity/status và requester-visible update |

FastAPI là authorization boundary. Frontend visibility chỉ hỗ trợ usability.

## API Và Frontend

PM5 bổ sung additive endpoints cho:

- ticket options và priority preview;
- intake và chín server-driven queues;
- ticket detail/timeline;
- named lifecycle actions;
- comments;
- business calendars và SLA policies;
- SLA summary;
- escalation dry-run/execute.

Next.js surfaces:

- `/tickets`;
- `/tickets/new`;
- `/tickets/[ticketId]`;
- `/admin/sla`;
- `/admin/escalations`.

## Backward Compatibility

Legacy `GET|POST|PATCH /tickets` vẫn giữ Vietnamese display values, original
request/response fields và lifecycle projection hẹp. Projection này chỉ là
compatibility adapter; rich code-level lifecycle là canonical cho PM5.

Existing asset, analytics, maintenance, Copilot và work-order contracts không
bị đổi. Corrective work order có thể link ticket nhưng hai lifecycle vẫn độc
lập.

## Verification Ngày 2026-07-26

Các kiểm tra được chạy lại trên isolated PostgreSQL database kết thúc bằng
`_test`:

- Alembic có một head `20260723_0006`; clean base-to-head,
  PM4-to-PM5-to-PM6 upgrade, PM5/PM6 downgrade rehearsal và `alembic check`
  đều đạt;
- focused PM5 ticket/SLA: `28 passed`;
- PM4 compatibility: `10 passed`;
- authentication và database-load slice: `17 passed`;
- full backend: `224 passed`;
- focused PM5/PM6 frontend: `19 passed` trên 4 files;
- full frontend: `106 passed` trên 16 files;
- Ruff, ESLint và Next.js production build đều đạt;
- build tạo 30 frontend routes và live OpenAPI có 128 paths;
- live ticket `TCK-000043` đi qua intake, assign, acknowledge, start, hold,
  resume và comment; kết quả là `in_progress`, priority `critical`, SLA
  occurrence 1, 7 SLA events và 1 comment;
- assigned-to-me queue trả đúng ticket;
- database-role probe từ chối update/delete ticket comment và SLA event;
- PostgreSQL restart giữ nguyên ticket state/version và API phục hồi
  `health=ok`.

Đây là local verification trên synthetic data, không phải bằng chứng SLA
performance, production availability hoặc business impact.

## Rollback

Downgrade `20260723_0005 -> 20260720_0004` đã được rehearsal trên isolated
database. Nếu database đang ở PM6, phải downgrade PM6 trước.

Downgrade PM5 làm mất rich SLA, comment, escalation và reference tables, đồng
thời project ticket về legacy-compatible state. Trước rollback trên dữ liệu có
giá trị phải:

1. dừng write traffic;
2. tạo và kiểm tra PostgreSQL backup;
3. export dữ liệu lịch sử cần giữ;
4. xác nhận client chỉ còn dùng legacy contract;
5. chạy migration bằng operator được ủy quyền.

Downgrade không phải cơ chế correction dữ liệu hằng ngày.

## Rủi Ro Còn Lại

- SLA/escalation evaluation vẫn là explicit API/CLI, chưa có scheduler hoặc
  notification delivery.
- Login throttling là in-process; chưa có distributed gateway control.
- Reporter PII chưa có field-level encryption hoặc retention workflow.
- Audit/append-only triggers không bảo vệ trước database administrator.
- Legacy projection cố ý không thể biểu diễn đầy đủ rich lifecycle.
- Chưa có SSO, MFA, multi-tenancy, centralized observability hoặc production
  backup/failover automation.

## Boundary Sau Release

PM1-PM6 đã được triển khai. PM7 chưa bắt đầu. Procurement, suppliers,
accounting, valuation, lot/serial/barcode, cycle count, notifications,
deployment, multi-tenancy, SSO, MFA và generative LLM vẫn nằm ngoài completed
boundary.

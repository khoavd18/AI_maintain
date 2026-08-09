# Product Milestone 6: Spare-Parts Inventory

## Trạng Thái Release

Product Milestone 6 bổ sung bounded context stock control cho maintenance work
order. Release này hỗ trợ internal pilot và không phải warehouse-management,
procurement, accounting hoặc production-certified inventory platform.

PM1-PM6 đã được triển khai. PM7 chưa bắt đầu.

## Mục Tiêu Và Bounded Context

PM6 trả lời các câu hỏi vận hành:

- part nào có tại stock location nào;
- bao nhiêu quantity đang on-hand, reserved và available;
- work order cần, reserve, issue, consume hoặc return bao nhiêu;
- physical stock đã thay đổi bằng movement nào và do actor nào thực hiện;
- balance nào low-stock theo threshold deterministic.

Canonical implementation:

- enums và stock semantics: `src/inventory_management/domain.py`;
- named actions và transaction rules: `src/inventory_management/service.py`;
- PostgreSQL implementation: `src/repositories/postgres_inventory.py`;
- typed API: `src/inventory_management/routes.py` và
  `src/inventory_management/schemas.py`;
- explicit deterministic seed: `src/inventory_management/cli.py`.

## Migration Và Entities

Migration [20260723_0006](../../migrations/versions/20260723_0006_add_spare_parts_inventory.py)
nâng schema từ `20260723_0005` và tạo:

- `part_categories`;
- `units_of_measure`;
- `spare_parts`;
- `part_reorder_configurations`;
- `stock_locations`;
- `inventory_positions`;
- `inventory_operations`;
- `inventory_movements`;
- `work_order_part_requirements`;
- `stock_reservations`;
- `stock_reservation_events`;
- `work_order_part_issues`;
- `work_order_part_consumptions`;
- `work_order_part_returns`;
- `inventory_attachments`.

Schema sử dụng foreign keys, unique constraints, indexes, quantity checks,
optimistic version và append-only trigger cho physical movement, reservation
event, issue, consumption và return history.

## Stock-Balance Authority

PostgreSQL `inventory_positions` là current balance projection. Client không
được PATCH balance hoặc submit calculated stock state.

```text
available = on_hand - reserved
```

Named service action lock các row liên quan, validate invariant, ghi immutable
history, cập nhật position và ghi audit trong cùng transaction. Server từ chối:

- negative on-hand;
- negative available;
- reservation oversubscription;
- operation trên part/location không còn eligible;
- stale version;
- reuse idempotency key với payload khác.

Movement giữ resulting on-hand/reserved/available snapshot để hỗ trợ audit.
Correction dùng compensating movement, không sửa lịch sử.

## Requirement, Reservation, Issue Và Consumption

Các khái niệm được giữ riêng:

| Khái niệm | Ảnh hưởng stock |
|---|---|
| Work-order requirement | Chỉ ghi planned demand |
| Reservation | Tăng reserved, giảm available, giữ nguyên on-hand |
| Issue | Giảm on-hand và release reserved tương ứng |
| Consumption | Xác nhận phần issued thực dùng, không trừ stock lần hai |
| Return | Tăng on-hand bằng movement mới |

Issue có thể liên kết requirement/reservation và actor nhận vật tư. Technician
được gán chỉ consume quantity thuộc work order của mình. Return không thể vượt
outstanding issued quantity.

Historical `MaintenanceLog.parts_replaced` vẫn là mô tả bảo trì và không thay
thế inventory ledger.

## Return Và Atomic Transfer

Return chỉ nhận active destination và luôn tạo append-only return record cùng
inventory movement. Service lock issue và destination position, từ chối
quantity vượt phần đã issue nhưng chưa consume/return.

Transfer:

- lock source/destination theo thứ tự deterministic;
- ghi `transfer_out` và `transfer_in` dùng chung `transfer_group_id`;
- commit cả hai position/movement/audit hoặc rollback toàn bộ;
- không có trạng thái trung gian "đã ra nhưng chưa vào".

API biểu diễn transfer direction bằng `movement_type`; quantity là absolute
positive amount trong từng response record.

## Idempotency

Các stock-changing command yêu cầu caller-stable `Idempotency-Key`.
`inventory_operations` lưu operation type, request fingerprint và committed
result linkage.

- replay cùng key và cùng payload trả committed result;
- cùng key với payload khác trả conflict;
- receipt replay không tăng stock lần hai;
- transfer replay không tạo thêm movement pair;
- requirement/reservation/issue/consume/return tuân theo boundary tương ứng.

## Immutable Ledger Và Reservation History

`inventory_movements` là physical ledger append-only.
`stock_reservation_events` ghi `reserved`, `released`, `expired`, `replaced`,
`issued` hoặc `fulfilled` mà không sửa event cũ.

Issue, consumption và return cũng là append-only concepts. API không có
update/delete history route; PostgreSQL trigger từ chối mutation trực tiếp bằng
normal application database role. Database administrator vẫn là trust boundary.

## Attachments

Inventory evidence tái sử dụng `AttachmentStorage`:

- metadata trong PostgreSQL, bytes sau storage abstraction;
- allow-listed extension/MIME/signature và bounded size;
- generated storage key và SHA-256 checksum;
- authenticated download, `nosniff`, soft deletion và audit;
- không expose local path, storage key hoặc file body trong audit.

Current implementation dùng local single-node bytes storage, chưa phải object
storage production design.

## RBAC

Phân quyền chính:

| Role | Quyền chính trong PM6 |
|---|---|
| Administrator | Toàn bộ inventory administration/action |
| Property Manager | Read inventory metrics/balance/history |
| Chief Engineer | Read, requirement và reservation planning |
| Technician | Read assigned work-order parts và explicit consumption |
| Helpdesk | Limited part availability read, không stock mutation |
| Storekeeper | Part/location master, receive, reserve, issue, return, transfer, adjustment và evidence |

FastAPI enforce permission trước service; service tiếp tục kiểm tra work-order
ownership, lifecycle và stock eligibility.

## API Và Frontend

PM6 bổ sung additive API cho:

- part category, UOM, part và stock-location master data;
- balance, low-stock, movement, reservation và metrics views;
- opening balance, receipt, transfer và adjustment named actions;
- work-order requirement/reservation/issue/consumption/return;
- protected inventory evidence.

Next.js surfaces:

- `/inventory`;
- `/inventory/parts` và `/inventory/parts/[partId]`;
- `/inventory/stock`;
- `/inventory/low-stock`;
- `/inventory/movements`;
- `/inventory/reservations`;
- `/inventory/receiving`;
- `/inventory/transfers`;
- `/inventory/adjustments`;
- `/inventory/settings`;
- work-order parts panel trong `/work-orders/[workOrderId]`.

## Work-Order Integration

Work order, requirement, reservation, issue, consumption, return và maintenance
log vẫn là các concepts riêng.

Current completion policy là `warning_only`: unresolved shortage hoặc issued
quantity chưa consume/return tạo warning cho authorized actor, nhưng completion
không tự issue, consume, return, release reservation hoặc resolve ticket.
Verification và ticket resolution vẫn là explicit human actions.

## Seed Behavior

`python -m src.inventory_management.cli seed-development` là explicit
development/test command. Seed dùng stable codes và idempotent lookups, không
chạy khi API startup.

Trên clean isolated database trong verification ngày 2026-07-26, seed tạo:

- 6 categories;
- 3 units of measure;
- 5 stock locations;
- 8 parts;
- 3 reorder configurations;
- 8 opening positions;
- 3 work-order requirements;
- 3 reservations.

Idempotent seed/replay behavior tiếp tục được kiểm tra trong automated suite.

## Analytics Isolation

Inventory transaction không trigger Risk Score, KPI hoặc RAG update. PostgreSQL
snapshot bridge chỉ project asset, ticket và maintenance-log contracts; sensor
readings/documents vẫn là generated batch inputs.

Temporary external snapshot sau live verification tạo:

- 3,240 feature rows;
- 3,240 anomaly rows;
- 3,240 risk rows;
- 27 preventive records;
- 26 recurring-issue records;
- 1 KPI record.

Feature, anomaly, risk và preventive hashes khớp canonical outputs. Recurring/KPI
khác vì live test tạo ticket thứ 43, chứng minh dữ liệu transactional chỉ ảnh
hưởng khi chạy batch explicit. Canonical analytics files không bị ghi hoặc thay
đổi. Inventory data không được đưa vào Qdrant.

## Verification Ngày 2026-07-26

Các kiểm tra được chạy lại trên isolated PostgreSQL database kết thúc bằng
`_test`:

- Alembic có một head `20260723_0006`; clean base-to-head,
  PM4-to-PM5-to-PM6 upgrade, PM6-to-PM5 downgrade rehearsal và
  `alembic check` đều đạt;
- focused PM6 domain/management: `14 passed`;
- focused PM5 regression: `28 passed`;
- PM4 work-order compatibility: `10 passed`;
- full backend: `224 passed`;
- focused PM5/PM6 frontend: `19 passed` trên 4 files;
- full frontend: `106 passed` trên 16 files;
- Ruff, ESLint và Next.js production build đều đạt;
- live OpenAPI có 128 paths; 15 representative Next.js routes trả `200`;
- authenticated Storekeeper receipt replay trả cùng movement và chỉ có 1
  receipt row; atomic transfer có đúng 2 movement cùng transfer group;
- unauthenticated inventory request trả `401`; Helpdesk receipt trả `403`;
- database-role probe từ chối update/delete inventory movement và reservation
  event;
- PostgreSQL restart giữ revision `0006`, 8 parts, 11 movements, 3
  reservations, 1 release receipt và 2 release transfer rows; API phục hồi
  `health=ok`.

Đây là local verification trên synthetic data, không phải chứng nhận stock
accuracy, production availability, security hoặc business impact.

## Rollback

Downgrade `20260723_0006 -> 20260723_0005` đã được rehearsal trên isolated
database. Migration này xóa toàn bộ PM6 master, balances, operations,
requirements, reservation, ledger và evidence metadata.

Trước rollback trên dữ liệu có giá trị phải:

1. dừng stock-changing traffic;
2. tạo và kiểm tra PostgreSQL backup;
3. export ledger/position/evidence metadata cần giữ;
4. đối soát private attachment bytes riêng;
5. xác nhận không còn client phụ thuộc PM6 routes;
6. chạy migration bằng operator được ủy quyền.

Không dùng downgrade để sửa chênh lệch stock; correction phải là named
compensating movement.

## Rủi Ro Còn Lại

- Chưa có procurement, supplier, valuation hoặc accounting integration.
- Không có lot/serial/expiry, barcode, cycle count hoặc demand forecasting.
- Low-stock/reorder chỉ là deterministic threshold, không phải optimization.
- Local attachment storage chưa có malware scan, object-store replication hoặc
  automatic reconciliation.
- Chưa có distributed lock/scheduler, notification delivery, production
  observability, backup/failover automation hoặc load qualification.
- Database administrator vẫn có thể vượt application-level append-only
  boundary.

## Boundary Sau Release

PM1-PM6 đã được triển khai. PM7 chưa bắt đầu. Procurement, suppliers,
accounting, valuation, lot/serial/barcode, cycle count, notifications,
deployment, multi-tenancy, SSO, MFA và generative LLM vẫn nằm ngoài completed
boundary.

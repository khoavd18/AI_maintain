# FastAPI Product Contract

## Conventions

- Legacy `GET /health` và PM7 `/health/live|ready|worker` là public; business routes cần Bearer access token.
- Rich product endpoints dùng English code values và trả Vietnamese `*_display` labels.
- Timestamps là timezone-aware ISO 8601; business due dates là local dates theo domain.
- Mutating rich endpoints dùng `expected_version` để chống stale write.
- Stock-changing endpoints yêu cầu caller-stable `Idempotency-Key`; replay cùng payload không tạo movement thứ hai.
- Error body theo FastAPI `{ "detail": "..." }`; frontend phân biệt `401`, `403`, `404`, `409`, `410`, `422` và `503`.
- Local `/docs` và `/openapi.json` chỉ bật trong development/test.

## Ticket Operations

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/ticketing/options` | Categories, subcategories, sources, groups, assignees, labels và priority matrix |
| `GET` | `/ticketing/priority-preview?impact=&urgency=` | Backend-authoritative priority preview |
| `POST` | `/tickets/intake` | Rich ticket intake và SLA snapshot |
| `GET` | `/ticket-queues/{queue_name}` | Server-filtered/sorted/paginated operational queue |
| `GET` | `/tickets/{ticket_id}` | Rich detail, SLA, timeline, comments, escalations và linked work orders |
| `POST` | `/tickets/{ticket_id}/assign` | Assignment/group routing |
| `POST` | `/tickets/{ticket_id}/acknowledge` | Record first response |
| `POST` | `/tickets/{ticket_id}/start` | Start execution |
| `POST` | `/tickets/{ticket_id}/hold` | Place on hold with reason |
| `POST` | `/tickets/{ticket_id}/resume` | Resume previous active status |
| `POST` | `/tickets/{ticket_id}/resolve` | Resolve after maintenance log exists |
| `POST` | `/tickets/{ticket_id}/close` | Close a resolved ticket |
| `POST` | `/tickets/{ticket_id}/reopen` | Reopen with reason and new SLA occurrence |
| `POST` | `/tickets/{ticket_id}/cancel` | Cancel active ticket with reason |
| `POST` | `/tickets/{ticket_id}/priority` | Change impact/urgency with reason; backend recalculates priority |
| `POST` | `/tickets/{ticket_id}/sla-policy` | Manual SLA policy override with reason |
| `GET|POST` | `/tickets/{ticket_id}/comments` | Read/add append-only communication |
| `GET|POST` | `/tickets/{ticket_id}/work-orders` | Read/create corrective work orders through maintenance service |

Queue filters: `asset_id`, `status`, `priority`, `category_id`, `support_group_id`, `assigned_user_id`, `search`, `page`, `page_size`.

## SLA Administration Và Escalation

| Method | Path | Purpose |
|---|---|---|
| `GET|POST` | `/ticketing/business-calendars` | List/create versioned calendars |
| `PATCH` | `/ticketing/business-calendars/{calendar_id}` | Replace validated periods/holidays with optimistic version |
| `GET|POST` | `/ticketing/sla-policies` | List/create effective-dated policies |
| `PATCH` | `/ticketing/sla-policies/{policy_id}` | Update policy/targets with optimistic version |
| `GET` | `/ticketing/sla-summary` | Derived active/waiting/critical/due-soon/breached counts |
| `POST` | `/ticketing/escalations/evaluate` | Dry-run or idempotent event creation |

Escalation execute không gửi external notification và không đổi ticket status.
PM7 worker có thể chuyển allow-listed escalation outbox event thành in-app
notification.

## PM7 Operations Và Notifications

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/notifications` | Personal inbox với unread/severity filters và pagination |
| `GET` | `/notifications/unread-count` | Current-user unread count |
| `POST` | `/notifications/{id}/read\|unread\|dismiss` | Versioned owner-only actions |
| `POST` | `/notifications/read-all` | Mark all current-user notifications read |
| `GET` | `/operations/jobs` | Closed four-job catalog |
| `PATCH` | `/operations/jobs/{job_key}` | Administrator enable/disable |
| `POST` | `/operations/jobs/{job_key}/trigger` | Persist idempotent manual execution |
| `GET` | `/operations/executions` | Filtered execution history |
| `POST` | `/operations/executions/{id}/retry` | Persist a new eligible retry |
| `GET` | `/operations/outbox` | Safe status view without payload |
| `GET` | `/operations/metrics` | Queue age/counts và last-success summary |

Trigger/retry yêu cầu `Idempotency-Key`; API không chạy job trong request.
Operator routes chỉ dành cho Administrator. Chi tiết schema và errors:
[PM7 API contract](api_contract.md).

## Legacy Compatibility

Existing `/tickets` list/create and `PATCH /tickets/{ticket_id}` remain unchanged for older clients. They expose the original narrow Vietnamese lifecycle and priority values. The adapter delegates storage/rules to PM5 service, but it must not be used to infer the complete rich timeline.

Existing asset, analytics, maintenance, work-order, identity and Copilot
contracts remain additive and unchanged through PM7. Full route schemas are
generated from Pydantic models in local OpenAPI.

## Spare-Part Master Và Stock

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/inventory/options` | Code + Vietnamese labels cho lifecycle, location, movement, state và attachment |
| `GET|POST` | `/part-categories` | List/create part categories |
| `GET|POST` | `/units-of-measure` | List/create UOM với precision 0–3 |
| `GET|POST` | `/parts` | Filtered/sorted/paginated catalogue và create |
| `GET|PATCH` | `/parts/{part_id}` | Detail/update với optimistic version |
| `GET` | `/parts/{part_id}/history` | Paginated immutable movement history |
| `POST` | `/parts/{part_id}/activate\|deactivate\|archive\|restore` | Named lifecycle actions |
| `POST` | `/parts/{part_id}/reorder-configurations` | Create/update effective thresholds theo location |
| `GET|POST` | `/stock-locations` | List/create locations tách biệt asset location |
| `PATCH` | `/stock-locations/{location_id}` | Versioned metadata update |
| `POST` | `/stock-locations/{location_id}/activate\|deactivate\|archive\|restore` | Named lifecycle actions |
| `GET` | `/inventory/balances` | On-hand/reserved/available + derived state |
| `GET` | `/inventory/low-stock` | Server-derived low/reorder/out-of-stock queue |
| `GET` | `/inventory/movements` | Filtered immutable ledger |
| `GET` | `/inventory/metrics` | Additive operational inventory metrics |

Part filters gồm search, category, lifecycle, compatible asset type, stock state, sort và pagination. Balance/movement filters gồm part/location/type/work order/date khi phù hợp. Helpdesk response redacts unit-cost metadata.

## Named Stock Actions

| Method | Path | Quantity effect |
|---|---|---|
| `POST` | `/inventory/opening-balances` | Tăng on-hand |
| `POST` | `/inventory/receipts` | Tăng on-hand |
| `POST` | `/inventory/transfers` | Giảm source và tăng destination atomically |
| `POST` | `/inventory/adjustments` | Tăng/giảm/damaged theo authorized reason |
| `POST` | `/work-orders/{work_order_id}/part-requirements` | Không đổi stock |
| `POST` | `/work-order-part-requirements/{requirement_id}/reservations` | Tăng reserved, giảm available |
| `POST` | `/stock-reservations/{reservation_id}/release\|expire` | Giảm reserved, tăng available |
| `POST` | `/stock-reservations/{reservation_id}/replace` | Đóng occurrence cũ và reserve occurrence mới atomically |
| `POST` | `/work-orders/{work_order_id}/part-issues` | Giảm on-hand; dùng reserved hợp lệ nếu có |
| `POST` | `/part-issues/{issue_id}/consumptions` | Quyết toán usage; không đổi stock lần hai |
| `POST` | `/part-issues/{issue_id}/returns` | Tăng on-hand, không vượt outstanding issue |
| `GET` | `/work-orders/{work_order_id}/parts` | Requirements, reservations, issues, returns, consumption, shortage, timeline |

Không có generic balance PATCH. Negative stock/available, duplicate idempotency payload, stale version, inactive location và invalid work-order relationship bị từ chối.

## Inventory Evidence

`GET|POST /inventory/movements/{movement_id}/attachments` và protected download/soft-delete endpoint tái sử dụng attachment validation. API không trả storage key/path hoặc file body trong audit.

## Receipt Example

```bash
curl -X POST http://localhost:8000/inventory/receipts \
  -H "Authorization: Bearer <STOREKEEPER_ACCESS_TOKEN>" \
  -H "Idempotency-Key: receipt-demo-20260723-001" \
  -H "Content-Type: application/json" \
  -d '{
    "part_id": "<PART_UUID>",
    "stock_location_id": "<STOCK_LOCATION_UUID>",
    "quantity": 4,
    "business_reference": "DEMO-RECEIPT-001",
    "reason": "Nhập bổ sung cho lịch bảo trì",
    "unit_cost_snapshot": 250000
  }'
```

Retry sau timeout phải giữ nguyên `Idempotency-Key` và payload. Không tạo key mới cho cùng một ý định nghiệp vụ chưa xác định kết quả.

## Minimal Rich Intake Example

```bash
curl -X POST http://localhost:8000/tickets/intake \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_id": "GENERATOR_002",
    "issue_description": "Điện áp không ổn định khi chạy thử.",
    "failure_category": "electrical_issue",
    "impact": "high",
    "urgency": "immediate",
    "category_id": "<CATEGORY_UUID>",
    "subcategory_id": "<SUBCATEGORY_UUID>",
    "intake_source_id": "<SOURCE_UUID>",
    "support_group_id": "<GROUP_UUID>",
    "assigned_user_id": "<USER_UUID>"
  }'
```

Lấy UUID options từ `GET /ticketing/options`; không hard-code reference IDs trong client.

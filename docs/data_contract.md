# Data Contract Canonical

## Nguyên Tắc Chung

- Column name, API field và technical identifier dùng tiếng Anh.
- Business value và user-facing explanation dùng tiếng Việt.
- Date dùng `YYYY-MM-DD`; timestamp dùng ISO 8601 có timezone.
- PostgreSQL là transactional source of truth cho assets, locations, attachment metadata, tickets, preventive plans, checklist templates, work orders và maintenance logs; file bytes nằm ngoài database.
- Generated/raw CSV là seed và batch interchange contract, không phải normal mutable runtime storage.
- Processed CSV là versioned-by-batch analytics serving contract.
- Qdrant chỉ lưu document chunks và metadata cho RAG retrieval.
- Risk Score dùng để prioritization, không phải failure probability hoặc exact failure-time prediction.

Synthetic seed mặc định hiện có 27 assets, 42 tickets, 86 maintenance logs, 77.760 hourly sensor readings và 6 Vietnamese SOP/checklist documents.

## Ownership Theo Storage

| Data | Primary runtime owner | CSV role |
|---|---|---|
| Asset master và maintenance dates | PostgreSQL `assets` | Synthetic seed, import, analytics snapshot |
| Location hierarchy | PostgreSQL `locations` | Deterministic nodes derived during import; không export riêng |
| Attachment metadata | PostgreSQL `asset_attachments` | Không có CSV analytics |
| Attachment bytes | Private `AttachmentStorage` root | Không lưu trong PostgreSQL hoặc analytics CSV |
| Tickets | PostgreSQL `maintenance_tickets` | Synthetic seed, import, analytics snapshot |
| Maintenance logs | PostgreSQL `maintenance_logs` | Synthetic seed, import, analytics snapshot |
| Preventive plans | PostgreSQL `preventive_maintenance_plans` | Development seed explicit; không thuộc canonical 27/42/86 import |
| Checklist template versions/items | PostgreSQL `checklist_templates`, `checklist_template_items` | Development seed explicit; work order giữ snapshot |
| Work orders/checklist execution | PostgreSQL `work_orders`, `work_order_checklist_items` | Transactional product data; không thay đổi historical CSV counts |
| Work-order evidence metadata/bytes | PostgreSQL `work_order_attachments` + private `AttachmentStorage` | Không export sang analytics CSV |
| User identities | PostgreSQL `users` | Không export sang analytics CSV |
| Refresh sessions | PostgreSQL `refresh_sessions` | Không có CSV; chỉ lưu token/CSRF hash |
| Security/business audit | PostgreSQL `audit_logs` | Không có CSV; paginated read qua API |
| Operational readings | Generated CSV | Batch analytics input |
| Feature/anomaly/risk/report outputs | Processed CSV | Canonical batch output |
| SOP/checklist chunks | Qdrant | Documents CSV là indexing source |

## Enum Mapping

PostgreSQL lưu internal English code. Repository trả Vietnamese display value và nhận lại đúng Vietnamese API value hiện có.

| Field | Internal code examples | API/CSV display examples |
|---|---|---|
| `asset_type` | `hvac`, `pump`, `generator` | `Máy lạnh`, `Máy bơm nước`, `Máy phát điện dự phòng` |
| `criticality` | `medium`, `high`, `critical` | `Trung bình`, `Cao`, `Rất quan trọng` |
| `lifecycle_status` | `planned`, `active`, `inactive`, `retired`, `archived` | `Đang lập kế hoạch`, `Đang hoạt động`, `Tạm ngừng`, `Đã ngừng sử dụng`, `Đã lưu trữ` |
| `operational_status` | `running`, `warning`, `fault`, `under_maintenance`, `out_of_service` | `Đang vận hành`, `Cảnh báo`, `Có lỗi`, `Đang bảo trì`, `Ngừng phục vụ` |
| Legacy Asset `status` projection | mapped từ `operational_status` | `Bình thường`, `Cảnh báo`, `Sự cố` |
| `asset_category` | `climate_control`, `water_system`, `power_system`, `other` | Vietnamese display label |
| `ownership_type` | `owned`, `leased`, `managed` | `Sở hữu`, `Thuê`, `Quản lý hộ` |
| Ticket `status` | `open`, `in_progress`, `resolved` | `Mới tạo`, `Đang xử lý`, `Đã xử lý` |
| `priority` | `low`, `medium`, `high`, `critical` | `Thấp`, `Trung bình`, `Cao`, `Khẩn cấp` |
| `failure_category` | `electrical_issue`, `sensor_issue` | `Lỗi điện`, `Lỗi cảm biến` |
| `maintenance_type` | `preventive`, `corrective`, `inspection`, `emergency` | Vietnamese maintenance type |
| `maintenance_result` | `resolved`, `partially_resolved`, `monitoring_required`, `vendor_required` | `Đã xử lý`, `Đã xử lý một phần`, `Cần theo dõi`, `Cần hỗ trợ chuyên môn` |
| Plan `status` | `active`, `paused`, `archived` | `Đang hoạt động`, `Tạm dừng`, `Đã lưu trữ` |
| `interval_unit` | `day`, `week`, `month`, `year` | `Ngày`, `Tuần`, `Tháng`, `Năm` |
| Work-order `status` | `planned`, `assigned`, `in_progress`, `on_hold`, `completed`, `verified`, `cancelled` | Vietnamese display label từ API options |
| Checklist `response_type` | `checkbox`, `pass_fail`, `numeric`, `text` | Vietnamese display label từ API options |

Canonical mappings nằm tại `src/config/value_mappings.py`. `vendor_required` chỉ có nghĩa cần hỗ trợ chuyên môn; không tạo vendor-management feature.

## Assets

PostgreSQL table: `assets`. Seed/snapshot file: `assets.csv`.

| Field | DB type | Required | API exposure | Rule |
|---|---|---:|---:|---|
| `asset_id` | varchar(50) | Có | Có | Primary key ổn định |
| `asset_name` | varchar(200) | Có | Có | Vietnamese display name |
| `asset_type` | varchar(40) | Có | Có, mapped | Chỉ focused `hvac`, `pump`, `generator` |
| `asset_category` | varchar(40) | Có | Rich profile | Stable code, default theo type khi import |
| `manufacturer`, `model` | varchar(200)/null | Không | Rich profile | Optional technical identity |
| `serial_number` | varchar(150)/null | Không | Rich profile | Trim + uppercase; unique khi có |
| `production_year` | integer/null | Không | Rich profile | 1900–2200 |
| `location_id` | UUID/null | Có với service write | Rich profile | FK `locations`; nullable ở DB chỉ để migrate legacy rows an toàn |
| `location` | varchar(200) | Có | Legacy + rich | Compatibility leaf label đồng bộ theo location assignment |
| `criticality` | varchar(20) | Có | Có, mapped | Named check constraint |
| `lifecycle_status` | varchar(20) | Có | Rich profile | `planned/active/inactive/retired/archived` |
| `operational_status` | varchar(30) | Có | Rich profile | Tách khỏi lifecycle; legacy `status` được project từ field này |
| `lifecycle_status_before_archive`, `operational_status_before_archive` | varchar/null | Có điều kiện | Rich profile | Chỉ dùng cho explicit restore |
| `installed_at` | timestamptz | Có | Rich profile | UTC; source cho compatibility installation date |
| `installation_date` | date | Có | Legacy + snapshot | Preserved analytics contract |
| `commissioned_at`, `retired_at`, `archived_at` | timestamptz/null | Không/điều kiện | Rich profile | Chronology và lifecycle controlled |
| `archive_reason` | text/null | Có khi archived | Rich profile | Không rỗng khi lifecycle archived |
| `ownership_type` | varchar(20) | Có | Rich profile | Stable enum code |
| `description` | text/null | Không | Rich profile | Tối đa 4.000 ký tự ở API |
| `warranty_start_date`, `warranty_end_date` | date/null | Không | Rich profile | End không trước start |
| `warranty_provider`, `warranty_reference` | varchar(200)/null | Không | Rich profile | Optional business reference |
| `last_maintenance_date` | date | Có | Có | Đồng bộ khi tạo maintenance log |
| `maintenance_interval_days` | integer | Có | Có | Lớn hơn 0 |
| `next_maintenance_date` | date | Có | Có | PostgreSQL: earliest active-plan due/fallback; snapshot: `last_maintenance_date + maintenance_interval_days` |
| `version` | integer | Có | Rich profile | `expected_version` bắt buộc cho mutation |
| `created_at`, `updated_at` | timestamptz | Có | Rich profile | UTC database/ORM timestamps |
| `created_by_user_id`, `updated_by_user_id` | UUID/null | Không với imported rows | Rich profile | FK actor cho user-created records |
| `qr_token` | UUID | Có | API field `qr_lookup_token` | Deterministic UUID5, unique; không phải credential |

`GET /assets` và analytics snapshot tiếp tục trả đúng legacy fields. Rich management contract dùng `/assets/catalog` và `/assets/{asset_id}/profile` với code/display siblings, location breadcrumb và version.

## Locations

PostgreSQL table: `locations`; không có mutable CSV source riêng.

| Field | Rule |
|---|---|
| `id` | UUID primary key |
| `code` | 2–50 ký tự, trim + uppercase, unique |
| `name` | Vietnamese display name |
| `location_type` | `building`, `floor`, `room`, `area`, `plant` |
| `parent_id` | Optional self-FK; không self-parent/cycle |
| `description` | Optional text |
| `is_active` | False nghĩa archived-in-place; assigned assets được giữ |
| `created_at`, `updated_at` | UTC timestamps |
| `created_by_user_id`, `updated_by_user_id` | Optional actor FK cho imported rows, required by service context for mutations |
| `version` | Optimistic concurrency |

API trả thêm computed `breadcrumb` và `asset_count`; hai field này không persist. Active parent/child rules được kiểm tra ở service.

## Asset Attachments

PostgreSQL table: `asset_attachments`; bytes nằm trong `AttachmentStorage`.

| Field | Rule |
|---|---|
| `id`, `asset_id` | UUID primary key + restricted asset FK |
| `category` | `asset_photo`, `technical_manual`, `warranty_document`, `commissioning_record`, `inspection_document`, `other` |
| `original_filename` | Display/download name, không bao giờ làm storage path |
| `storage_key` | Generated unique private key; không xuất API/audit |
| `media_type` | Chỉ `application/pdf`, `image/png`, `image/jpeg` sau signature validation |
| `size_bytes` | Dương và không vượt configured limit |
| `checksum` | 64-character SHA-256; verify lại khi download |
| `uploaded_by_user_id`, `created_at` | Required actor + UTC timestamp |
| `deleted_at`, `deleted_by_user_id` | Soft-delete metadata; active list bỏ record đã xóa |

Không có inline preview endpoint. Download dùng attachment disposition và authorization trên mọi request.

## Tickets

PostgreSQL table: `maintenance_tickets`. Seed/snapshot file: `maintenance_tickets.csv`.

| Field | DB type | Required | API exposure | Rule |
|---|---|---:|---:|---|
| `ticket_id` | varchar(50) | Có | Có | Primary key; runtime ID từ PostgreSQL sequence |
| `asset_id` | varchar(50) | Có | Có | FK đến `assets`, delete restricted |
| `issue_description` | text | Có | Có | 5–1.000 ký tự ở request schema |
| `priority` | varchar(20) | Có | Có, mapped | Bốn canonical priorities |
| `status` | varchar(20) | Có | Có, mapped | `open -> in_progress -> resolved` |
| `failure_category` | varchar(40) | Có | Có, mapped | Tám focused categories |
| `created_at` | timestamptz | Có | Có | Server tạo, timezone-safe |
| `resolved_at` | timestamptz/null | Có điều kiện | Có | Chỉ có khi status `resolved` |
| `technician_id` | varchar(50) | Có | Có | Technician được gán |
| `manager_note` | text/null | Không | Có | Ghi chú khi manager tạo ticket |
| `note` | text/null | Không | Có | Ghi chú update gần nhất |
| `version` | integer | Có | Không | Optimistic concurrency |
| `updated_at` | timestamptz | Có | Không | Storage metadata |

Constraints:

- `(ticket_id, asset_id)` unique để maintenance log có thể dùng composite FK;
- `resolved_at >= created_at`;
- unresolved status phải có `resolved_at = null`;
- resolved status phải có `resolved_at`;
- service chỉ cho phép cùng status hoặc transition tuyến tính;
- ticket phải có linked maintenance log trước khi resolve.

Indexes: `asset_id`, `status`, `created_at`. API không expose `version`, vì vậy request/response contract của frontend không đổi; stale write được trả HTTP `409`.

## Maintenance Logs

PostgreSQL table: `maintenance_logs`. Seed/snapshot file: `maintenance_logs.csv`.

| Field | DB type | Required | API exposure | Rule |
|---|---|---:|---:|---|
| `log_id` | varchar(50) | Có | Có | Primary key; runtime ID từ PostgreSQL sequence |
| `ticket_id` | varchar(50)/null | Có điều kiện | Có | Null cho historical preventive log |
| `work_order_id` | UUID/null | Không | Có qua work-order detail | Unique FK; historical/direct API logs giữ null |
| `asset_id` | varchar(50) | Có | Có | FK đến asset |
| `maintenance_date` | date | Có | Có | Không trước ticket hoặc latest asset maintenance |
| `maintenance_type` | varchar(30) | Có | Có, mapped | Runtime form tạo `corrective` |
| `technician_id` | varchar(50) | Có | Có | Kế thừa ticket trong current workflow |
| `inspection_result` | text | Có | Có | Field observation |
| `actions_taken` | text | Có | Có | Hành động thực tế |
| `parts_replaced` | text/null | Không | Có | Historical text, không phải inventory transaction |
| `technician_note` | text | Có | Có | Handover/follow-up note |
| `maintenance_result` | varchar(30) | Có | Có, mapped | Canonical result |
| `follow_up_required` | boolean | Có | Có | False chỉ khi result `resolved` |
| `next_maintenance_date` | date | Có | Có | PostgreSQL giữ operational next date; snapshot project `maintenance_date + maintenance_interval_days` |
| `created_at` | timestamptz | Có | Không | Storage metadata |
| `updated_at` | timestamptz | Có | Không | Storage metadata; log hiện append-only |

Composite FK `(ticket_id, asset_id) -> maintenance_tickets(ticket_id, asset_id)` và `(work_order_id, asset_id) -> work_orders(id, asset_id)` ngăn liên kết sai asset ở database level. Existing direct maintenance-log API vẫn lock asset/ticket, insert log và cập nhật maintenance dates như trước. Work-order completion dùng transaction riêng được mô tả dưới đây.

## Preventive Maintenance Plans

PostgreSQL table: `preventive_maintenance_plans`. Plan mô tả recurring intent, không phải executable job.

| Nhóm field | Fields | Contract |
|---|---|---|
| Identity | `id`, `plan_code`, `name`, `description`, `asset_id` | UUID PK; `plan_code` unique; asset FK delete restricted |
| Recurrence | `schedule_type`, `interval_value`, `interval_unit`, `recurrence_rule`, `start_date`, `end_date`, `local_timezone` | `schedule_type=interval`; N=1–366; unit chỉ day/week/month/year; `recurrence_rule` null trong current subset; timezone phải là IANA hợp lệ |
| Release/overdue | `lead_time_days`, `grace_period_days`, `next_due_date`, `last_generated_due_date` | 0–365 ngày; due dates là business dates; next due được service derive |
| Defaults | `estimated_duration_minutes`, `default_priority`, `default_assignee_user_id`, `checklist_template_id`, `instructions` | Assignee phải là active technician; template active và tương thích asset type |
| Lifecycle | `status`, `is_active`, `paused_at`, `archived_at`, `archive_reason` | Pause/archive không hard-delete; archived plan chỉ đọc; paused plan không generate |
| Concurrency/audit | creator/updater IDs, UTC timestamps, `version` | Mỗi mutation yêu cầu optimistic version và ghi audit cùng transaction |

Recurrence semantics:

- monthly/yearly giữ anchor ngày bắt đầu; nếu tháng không có ngày 29/30/31 thì clamp vào cuối tháng rồi quay lại anchor ở tháng sau;
- leap-day yearly recurrence clamp vào 28/02 ở năm không nhuận;
- expansion bị giới hạn 256 occurrence mỗi request và catch-up chỉ xét trailing 366 ngày;
- pause không tạo uncontrolled backlog; resume đặt lại `next_due_date` từ ngày resume;
- schedule update không viết lại work order đã generate;
- overdue là phép tính `as_of_date > due_date + grace_period_days`, không có writable overdue status.

## Checklist Template Versions

Tables: `checklist_templates`, `checklist_template_items`.

| Field | Contract |
|---|---|
| `id`, `code`, `version_number` | UUID PK; `(code, version_number)` unique; version mới tạo row mới |
| `name`, `asset_type`, `description`, `status` | Plain text, không nhận executable HTML; archived version vẫn đọc được |
| Item `sequence` | Unique trong template, liên tục từ 1, tối đa 100 items |
| Item `instruction`, `guidance` | Plain text có giới hạn độ dài |
| `response_type` | `checkbox`, `pass_fail`, `numeric`, `text`; N/A là result chỉ khi `allow_not_applicable=true` |
| `is_required`, `safety_critical` | Required item phải hoàn tất; safety-critical `fail` chặn completion |
| numeric fields | `expected_unit`, `minimum_value`, `maximum_value` chỉ dùng cho numeric; min không lớn hơn max |

Work order copy các item sang `work_order_checklist_items`; template version sau đó không thể thay đổi history của work order cũ.

## Work Orders

PostgreSQL table: `work_orders`. Một row là một executable maintenance job trên đúng một asset.

| Nhóm field | Fields | Contract |
|---|---|---|
| Identity | `id`, `work_order_number`, `title`, `description`, `work_order_type` | UUID PK; number sinh bằng PostgreSQL sequence và unique dưới concurrency |
| Source | `asset_id`, `preventive_plan_id`, `source_ticket_id` | Asset bắt buộc; plan/ticket optional; source relationship phải cùng asset |
| People/result | `assigned_to_user_id`, `created_by_user_id`, `verified_by_user_id`, `maintenance_log_id` | Assignee là active technician; verifier khác actor completion; one-to-one maintenance log |
| Planning | priority, UTC scheduled timestamps, `due_date`, `local_timezone`, `grace_period_days`, duration | Scheduled end không trước start; due date là local business date |
| Execution | `started_at`, `completed_at`, `verified_at`, `cancelled_at`, reasons/summary/safety/labor | UTC chronology phải phù hợp state; cancellation cần reason |
| State | `status`, `hold_reason` | Canonical state machine; overdue không lưu ở đây |
| Concurrency/audit | UTC create/update, `version` | Stale expected version trả HTTP 409; mọi transition audit trong transaction |

Canonical state machine:

```text
planned -> assigned -> in_progress -> completed -> verified
              |             |
              +-> on_hold <-+
planned/assigned -> cancelled
completed -> in_progress  (explicit authorized reopen)
```

- work order cần eligible assignee trước khi start;
- completion cần mandatory checklist và không có safety-critical fail;
- completion tạo/link đúng một `MaintenanceLog`; repeated request không tạo log trùng;
- verification cập nhật `last_maintenance_date` và compatibility `next_maintenance_date` transactionally;
- verify/cancel không tự resolve source ticket;
- verified work order và evidence của nó chỉ đọc trong current milestone.

## Work-Order Evidence

`work_order_attachments` lưu UUID, work-order/asset FK, category, generated storage key, filename, MIME, size, SHA-256, actor và soft-delete fields. API không trả storage key/path. Categories: `before_photo`, `after_photo`, `inspection_document`, `completion_document`, `safety_document`, `other`. MIME/signature/extension, configured size, checksum, authenticated resource scope và `nosniff` download dùng cùng security contract với asset attachment.

## User Identity Contract

`users` là local/internal-pilot identity store:

| Field | Rule |
|---|---|
| `id` | UUID primary key; API trả UUID, client không tự tạo |
| `username` | 3–100 ký tự, normalize lowercase + trim, unique |
| `email` | Optional, normalize lowercase + trim, unique khi có |
| `password_hash` | Argon2id encoded hash, không bao giờ xuất qua API/audit |
| `display_name` | 2–200 ký tự, dùng làm actor snapshot |
| `role` | Stable English code trong sáu role canonical |
| `technician_id` | Optional unique link cho technician resource scope |
| `is_active` | Inactive user không login/refresh/access được |
| `created_at`, `updated_at`, `last_login_at` | UTC timezone-aware timestamps |
| `version` | Optimistic concurrency và access-token invalidation |

API `UserResponse` bổ sung `role_display_name` tiếng Việt và sorted `permissions`; không chứa hash hoặc session token. User create yêu cầu password 12–256 ký tự. Username/email trùng sau normalize bị từ chối.

## Refresh Session Contract

| Field | Rule |
|---|---|
| `id` | UUID session identifier, được bind trong access token |
| `user_id` | Required FK tới `users`, cascade khi user bị xóa ở DB administration layer |
| `token_hash` | Unique SHA-256 hash của opaque refresh token; không lưu plaintext |
| `csrf_token_hash` | SHA-256 hash của CSRF binding token |
| `created_at`, `expires_at`, `revoked_at` | UTC; active khi chưa revoke và chưa hết hạn |
| `user_agent` | Optional, truncate 300 ký tự; không lưu Authorization/cookie |

Refresh cookie và CSRF cookie là HTTP transport state, không thuộc JSON response. Rotation tạo session mới và revoke session cũ atomically. Logout revoke đúng active session; password change/deactivation revoke toàn bộ sessions của user.

## Audit Log Contract

| Field | Rule |
|---|---|
| `id`, `occurred_at` | UUID + UTC timestamp |
| `actor_user_id` | Nullable FK cho failure không xác định được actor |
| `actor_display_name` | Snapshot để giữ ngữ cảnh hiển thị |
| `action` | Stable dotted code, ví dụ `auth.login_succeeded`, `ticket.status_changed` |
| `resource_type`, `resource_id` | Entity/action target, ID nullable khi chưa tồn tại |
| `request_id` | Correlation ID do middleware chấp nhận/tạo |
| `before_state`, `after_state` | Optional allow-listed JSON projection, không phải raw model/request |
| `metadata` | Optional safe bounded metadata |
| `outcome` | `success`, `failure` hoặc `denied` theo event |

Các event hiện có bao gồm login/session/user; asset/location/lifecycle/attachment; ticket/log; preventive plan create/update/schedule/pause/resume/archive/generation; checklist template create/version/archive; work-order generate/create/assign/start/hold/resume/checklist/complete/reopen/verify/cancel; evidence upload/delete; maintenance-log linkage và asset-date update. Application không cung cấp update/delete endpoint cho audit; database trigger chặn sửa/xóa. Audit projection loại password, hash, token, cookie, Authorization header, attachment storage key/path/body, raw checklist payload, secret và oversized text.

`GET /audit-logs` trả `{items, page, page_size, total, total_pages}` và hỗ trợ filter theo action, resource type, outcome, actor. Quyền đọc audit không cho quyền thay đổi event.

## Transactional Import Contract

`src/ingestion/load_data.py`:

- chạy full canonical CSV validation trước khi kết nối write;
- tạo deterministic `FACILITY-ROOT` và một location child cho mỗi legacy location, rồi import assets, tickets và maintenance logs;
- chuyển Vietnamese values sang internal codes;
- gán category theo asset type, lifecycle `active`, ownership `owned`, `installed_at` từ installation date và deterministic QR token;
- import toàn bộ ba table trong một transaction;
- không tự tạo plan/template/work order. `--replace` xóa PM4 transactional demo rows theo FK order trước khi khôi phục canonical 27/42/86; PM4 seed chạy bằng command riêng;
- đồng bộ ID sequences theo maximum imported `TCK-*` và `LOG-*`;
- từ chối database không rỗng nếu không có `--replace`;
- `--dry-run` không ghi dữ liệu;
- `--replace` là explicit canonical demo reset và vẫn atomic;
- duplicate, FK hoặc check-constraint error rollback toàn bộ import.

## Analytics Snapshot Contract

`src/database/export_snapshot.py` đọc assets, tickets và logs trong một PostgreSQL `REPEATABLE READ` transaction. Command ghép hai generated pass-through files:

- `sensor_readings.csv`;
- `documents.csv`.

Toàn bộ staging directory phải qua `validate_csv_dataset` trước khi replace `data/analytics_input/`. Processed analytics không đọc trực tiếp PostgreSQL trong milestone này. Exporter không thay đổi transactional rows: nó project asset/log next dates về fixed-interval contract trong staging để giữ validator và analytics formulas hiện có.

Asset snapshot cố ý chỉ có 10 legacy columns: ID/name/type/location/criticality/status, installation date, maintenance dates và interval. Plan-specific due dates, lifecycle, warranty, attachment và QR fields không đi vào formula. Retired/archived rows vẫn được giữ trong snapshot để bảo toàn reference/history; pipeline hiện chưa tự loại chúng. Đây là documented compatibility behavior, không phải quyết định production scheduling.

## Operational Readings

Primary source: generated `sensor_readings.csv`. Đây là batch input, không phải real-time stream.

| Field | Type | Rule |
|---|---|---|
| `reading_id` | string | Unique |
| `asset_id` | string | Phải tồn tại trong snapshot asset master |
| `timestamp` | zoned datetime | Unique với `asset_id` |
| `energy_kwh` | float | Không âm |
| `temperature` | float | Không âm trong synthetic contract |
| `vibration` | float | Không âm |
| `runtime_hours` | float | 0–24 |
| `status` | string | Vietnamese business value |

Không có anomaly label, future outcome hoặc raw risk score trong input.

## SOP Và Checklist Documents

Indexing source: generated `documents.csv`. Canonical RAG normalization tạo:

- `document_id`;
- `document_type`;
- `title`;
- `asset_type`;
- `failure_category`;
- `version`;
- `effective_date`;
- `source`;
- `content`.

Qdrant payload giữ document identity, chunk index và filter metadata. Asset/ticket/log không được persist trong Qdrant.

## Daily Feature Contract

`asset_daily_features.csv` có một row cho mỗi `(asset_id, feature_date)`. Nhóm field chính:

- asset profile: type, location, criticality;
- daily energy, runtime, temperature, vibration;
- rolling 7-day baselines và deltas;
- ticket counts 7/30 ngày, high-priority và unresolved counts;
- recurring issue và follow-up counts;
- last/next maintenance dates, days overdue;
- criticality score.

Calculations chỉ dùng event có timestamp không muộn hơn feature date.

## Anomaly Result Contract

`anomaly_results.csv` giữ backward-compatible API fields:

- `asset_id`, `date`, `asset_type`, `location`;
- measured metrics và deltas;
- `rule_based_score`, `isolation_forest_score`, `anomaly_score` trong 0–100;
- `is_anomaly`;
- Vietnamese `anomaly_type` và `anomaly_reasons`.

Không thay đổi thresholds hoặc model trong Product Milestone 1.

## Risk Result Contract

`risk_scores.csv` giữ:

- component scores 0–100;
- `final_risk_score`/`risk_score` 0–100;
- `risk_level_code` và Vietnamese `risk_level`;
- Vietnamese `main_reasons`/`contributing_factors`;
- Vietnamese `recommended_action`.

Risk formula và labels được định nghĩa tại [Analytics pipeline](analytics.md). Score không được diễn giải là xác suất hỏng.

## Maintenance Report Contracts

- `preventive_maintenance_status.csv`: due status, days until due, days overdue.
- `recurring_issues.csv`: deterministic group theo asset/failure category.
- `maintenance_kpis.csv`: một descriptive KPI snapshot cho latest batch date.

Transactional write không sửa ba files này. Chỉ snapshot + canonical batch tiếp theo mới cập nhật reports.

## API Compatibility

Tất cả legacy business endpoint paths, request fields, response fields, Vietnamese statuses và successful status codes được giữ. Chúng yêu cầu Bearer authentication và permission phù hợp; `GET /health` vẫn public. Rich asset/catalog/location/attachment/QR/history endpoints là additive và dùng explicit schemas; storage key/local path không xuất hiện trong response. Frontend không cần biết storage backend; HTTP `401`, `403`, `409`, `410`, `422` và `503` được map thành các error state riêng.

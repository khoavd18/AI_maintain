# Data Contract Tối Thiểu

## Nguyên Tắc Chung

- Column name, API field và technical identifier dùng tiếng Anh.
- Business value và nội dung hiển thị cho người dùng dùng tiếng Việt.
- Timestamp dùng ISO 8601; timestamp có timezone khi dữ liệu ở mức thời gian.
- Date dùng định dạng `YYYY-MM-DD`.
- CSV là primary contract của MVP; PostgreSQL không phải dependency bắt buộc.
- Dataset synthetic mặc định gồm 27 assets thuộc HVAC, pump và generator, cùng 120 ngày readings theo giờ.
- Raw inputs không chứa anomaly label, future outcome hoặc raw risk result.

## Assets

Primary source hiện tại: `data/raw/assets.csv`.

| Field | Type | Required | Ý nghĩa | Trạng thái hiện tại |
|---|---|---:|---|---|
| `asset_id` | string | Có | Định danh ổn định của thiết bị | Có |
| `asset_name` | string | Có | Tên hiển thị tiếng Việt | Có |
| `asset_type` | string | Có | Loại thiết bị bằng business value tiếng Việt | Có |
| `location` | string | Có | Vị trí thiết bị | Có |
| `criticality` | string | Có | Mức độ quan trọng | Có |
| `status` | string | Có | Trạng thái vận hành/nghiệp vụ | Có |
| `installation_date` | date | Có | Ngày lắp đặt, phải trước observation window | Có |
| `last_maintenance_date` | date | Có | Ngày maintenance log mới nhất trong toàn bộ generated history | Có |
| `maintenance_interval_days` | integer > 0 | Có | Chu kỳ preventive maintenance theo loại asset | Có |
| `next_maintenance_date` | date | Có | `last_maintenance_date + maintenance_interval_days` | Có |

Allowed `asset_type`: `Máy lạnh`, `Máy bơm nước`, `Máy phát điện dự phòng`.

Allowed `criticality`: `Trung bình`, `Cao`, `Rất quan trọng`. Allowed `status`: `Bình thường`, `Cảnh báo`.

## Tickets

Primary source hiện tại: `data/raw/maintenance_tickets.csv`.

| Field | Type | Required | Ý nghĩa |
|---|---|---:|---|
| `ticket_id` | string | Có | Định danh ticket |
| `asset_id` | string | Có | Asset liên quan |
| `issue_description` | string | Có | Mô tả sự cố tiếng Việt |
| `priority` | string | Có | Mức ưu tiên |
| `status` | string | Có | Trạng thái ticket |
| `failure_category` | string | Có | Nhóm sự cố dùng cho recurring issue analysis |
| `created_at` | datetime | Có | Thời điểm tạo |
| `resolved_at` | datetime/null | Có điều kiện | Có giá trị khi ticket đã xử lý |
| `technician_id` | string | Có | Định danh technician được gán |

Allowed `status`: `Mới tạo`, `Đang xử lý`, `Đã xử lý`. Chỉ ticket `Đã xử lý` có `resolved_at`; timestamp này không được sớm hơn `created_at`.

## Maintenance Logs

Primary source hiện tại: `data/raw/maintenance_logs.csv`.

| Field | Type | Required | Ý nghĩa | Trạng thái hiện tại |
|---|---|---:|---|---|
| `log_id` | string | Có | Định danh maintenance log | Có |
| `ticket_id` | string/null | Có điều kiện | Ticket nguồn khi log là corrective maintenance | Có |
| `asset_id` | string | Có | Asset được bảo trì | Có |
| `maintenance_date` | date | Có | Ngày thực hiện | Có |
| `maintenance_type` | string | Có | Preventive, corrective hoặc inspection bằng tiếng Việt | Có |
| `technician_id` | string | Có | Định danh người thực hiện | Có |
| `inspection_result` | string | Có | Kết quả kiểm tra bằng tiếng Việt | Có |
| `actions_taken` | string | Có | Hành động đã thực hiện | Có |
| `parts_replaced` | string/null | Không | Mô tả part đã thay, không phải inventory transaction | Có |
| `technician_note` | string | Có | Ghi chú bàn giao hoặc theo dõi | Có |
| `maintenance_result` | string | Có | Kết quả maintenance theo canonical enum | Có |
| `follow_up_required` | boolean | Có | Có khi result chưa xử lý hoàn toàn | Có |
| `next_maintenance_date` | date | Có | `maintenance_date + maintenance_interval_days` | Có |

Allowed `maintenance_result`:

- `Đã xử lý` (`resolved`);
- `Đã xử lý một phần` (`partially_resolved`);
- `Cần theo dõi` (`monitoring_required`);
- `Cần hỗ trợ chuyên môn` (`vendor_required`).

`follow_up_required = false` chỉ khi result là `Đã xử lý`; các result còn lại yêu cầu follow-up. Tên code trong ngoặc dùng trong mapping nội bộ, còn CSV giữ business value tiếng Việt.

`parts_replaced` có thể được giữ như lịch sử hành động nhưng không được mở rộng thành spare-parts inventory.

## Operational Readings

Primary source hiện tại: `data/raw/sensor_readings.csv`. Đây là batch input, không phải real-time stream.

| Field | Type | Required | Ý nghĩa |
|---|---|---:|---|
| `reading_id` | string | Có | Định danh reading |
| `asset_id` | string | Có | Asset liên quan |
| `timestamp` | datetime | Có | Thời điểm đo |
| `energy_kwh` | number | Có | Điện năng tiêu thụ |
| `runtime_hours` | number | Có | Thời gian vận hành trong kỳ đo |
| `temperature` | number | Có | Nhiệt độ |
| `vibration` | number | Có điều kiện | Độ rung khi phù hợp với loại thiết bị |
| `status` | string | Có | Trạng thái reading |

Raw readings không chứa `pressure`, `anomaly_type`, `is_anomaly` hoặc future outcome. Controlled anomalies chỉ được thể hiện qua numeric pattern ở một nhóm nhỏ assets. Reading status không được dùng làm ground-truth anomaly label.

## SOP/Checklist Documents

Primary source hiện tại: `data/raw/documents.csv`.

Raw CSV giữ các tên cột legacy để không làm thay đổi optional PostgreSQL loader. `src/rag/document_loader.py` chuẩn hóa chúng thành contract canonical dùng cho RAG:

| Raw field | Canonical RAG field | Type | Required | Ý nghĩa |
|---|---|---|---:|---|
| `doc_id` | `document_id` | string | Có | Định danh ổn định của tài liệu |
| `title` | `title` | string | Có | Tiêu đề tiếng Việt |
| `doc_type` | `document_type` | string | Có | Checklist hoặc troubleshooting guide |
| `asset_type` | `asset_type` | string | Có | Một trong HVAC, pump hoặc generator bằng business value tiếng Việt |
| suy ra từ title/type | `failure_category` | string | Có điều kiện | Nhóm lỗi cho troubleshooting document; để trống với preventive checklist |
| `raw_text` | `content` | string | Có | Nội dung tiếng Việt có cấu trúc và cảnh báo an toàn |
| giá trị mặc định | `version` | string | Có | Phiên bản synthetic hiện tại là `1.0` |
| ngày của `created_at` | `effective_date` | date | Có | Ngày hiệu lực minh họa, hiện là `2026-01-01` |
| `source` | `source` | string | Có | Nguồn hiển thị/citation |
| `clean_text` | `clean_text` | string | Có | Nội dung normalized dùng cho compatibility |
| `created_at` | `created_at` | datetime | Có | Thời điểm tạo tài liệu synthetic |

Sáu tài liệu hiện tại gồm preventive inspection và failure troubleshooting cho từng loại: HVAC cooling failure, pump vibration/abnormal noise và generator startup failure. Nội dung là synthetic/illustrative, không thay thế manual của nhà sản xuất.

Mỗi indexed chunk phải có `document_id`, `title`, `document_type`, `asset_type`, `failure_category`, `version`, `effective_date` và `chunk_index`. Payload đồng thời giữ `doc_id`, `doc_type` và `text` để bảo toàn response compatibility.

## Daily Maintenance Features

Canonical producer: `src/features/build_features.py`.

Với mỗi `asset_id` và `feature_date`:

- `last_maintenance_date` là event gần nhất có `maintenance_date <= feature_date`;
- `next_maintenance_date` lấy từ chính event đó;
- `days_since_last_maintenance = feature_date - last_maintenance_date`;
- `days_overdue = max(0, feature_date - next_maintenance_date)`.
- `unresolved_ticket_count` chỉ tính ticket đang mở tại ngày feature;
- `recurring_issue_count` là số failure categories đã đạt 3 occurrences tại ngày feature;
- `follow_up_required_count` chỉ tính maintenance logs đã xảy ra đến ngày feature.

Mọi asset phải có ít nhất một maintenance event trước hoặc đúng ngày đầu observation window. Feature pipeline không dùng future maintenance event và không fallback sang `installation_date`.

## Anomaly Results

Canonical producer: `src/models/anomaly_detection.py`.

| Field | Type | Required | Ý nghĩa |
|---|---|---:|---|
| `asset_id` | string | Có | Asset được chấm điểm |
| `feature_date` | date | Có | Ngày feature canonical |
| `date` | date | Có | Ngày feature |
| `asset_type` | string | Có | Loại asset |
| `location` | string | Có | Vị trí |
| `rule_based_score` | number 0-100 | Có | Severity từ rule |
| `isolation_forest_score` | number 0-100 | Có | Relative outlier score |
| `anomaly_score` | number 0-100 | Có | Combined score |
| `is_anomaly` | boolean | Có | Cờ bất thường theo implementation canonical |
| `anomaly_type` | string | Có | Loại bất thường tiếng Việt |
| `anomalous_metrics` | string | Có | Metrics đóng góp vào rule signals hoặc `none` |
| `contributing_signals` | string | Có | Giải thích signal tiếng Việt |
| `anomaly_reasons` | string | Có | Giải thích tiếng Việt |

Các operational values và delta hiện có trong output để hỗ trợ inspection, nhưng không thay đổi minimum identity/explanation contract ở trên.

## Risk Results

Canonical producer: `src/risk/risk_scoring.py`.

| Field | Type | Required | Ý nghĩa |
|---|---|---:|---|
| `asset_id` | string | Có | Asset được chấm điểm |
| `feature_date` | date | Có | Ngày feature canonical |
| `date` | date | Có | Ngày risk score |
| `asset_name` | string | Có | Tên hiển thị |
| `asset_type` | string | Có | Loại asset |
| `location` | string | Có | Vị trí |
| `anomaly_score` | number 0-100 | Có | Input bất thường |
| `maintenance_overdue_score` | number 0-100 | Có | Thành phần quá hạn |
| `unresolved_ticket_score` | number 0-100 | Có | Thành phần ticket chưa xử lý |
| `recent_ticket_score` | number 0-100 | Có | Thành phần ticket gần đây |
| `recurring_issue_score` | number 0-100 | Có | Thành phần sự cố lặp lại |
| `criticality_score` | number 0-100 | Có | Thành phần criticality |
| `follow_up_score` | number 0-100 | Có | Thành phần maintenance cần follow-up |
| `runtime_score` | number 0-100 | Có | Thành phần runtime |
| `final_risk_score` | number 0-100 | Có | Điểm ưu tiên cuối cùng |
| `risk_score` | number 0-100 | Có | Alias canonical của `final_risk_score` |
| `risk_level_code` | string | Có | `low`, `medium`, `high`, `critical` |
| `risk_level` | string | Có | Mức rủi ro tiếng Việt |
| `contributing_factors` | string | Có | Alias canonical của explanation tiếng Việt |
| `main_reasons` | string | Có | Lý do chính tiếng Việt |
| `recommended_action` | string | Có | Hành động tham khảo tiếng Việt |

Risk result là decision-support output. Nó không phải failure probability đã hiệu chuẩn và không dự đoán exact failure time.

## Preventive Maintenance Status

Canonical producer: `src/features/build_features.py`. Output: `data/processed/preventive_maintenance_status.csv`.

| Field | Type | Required | Ý nghĩa |
|---|---|---:|---|
| `asset_id` | string | Có | Asset được phân loại |
| `as_of_date` | date | Có | Ngày cuối observation window |
| `last_maintenance_date` | date | Có | Maintenance event mới nhất |
| `next_maintenance_date` | date | Có | Ngày đến hạn kế tiếp |
| `days_until_due` | integer >= 0 | Có | Số ngày còn lại, bằng 0 nếu đã quá hạn |
| `days_overdue` | integer >= 0 | Có | Số ngày quá hạn, bằng 0 nếu chưa quá hạn |
| `maintenance_status` | string | Có | `not_due`, `due_soon`, `overdue` |
| `maintenance_status_display` | string | Có | Business value tiếng Việt |

## Recurring Issues

Canonical producer: `src/features/build_features.py`. Output: `data/processed/recurring_issues.csv`.

Mỗi hàng là một group `asset_id` + `failure_category`, gồm `occurrence_count`, `first_occurrence`, `last_occurrence`, `resolved_count`, `unresolved_count`, `recurrence_flag` và `recurrence_threshold`. Threshold canonical là 3 occurrences.

## Maintenance KPIs

Canonical producer: `src/features/build_features.py`. Output: `data/processed/maintenance_kpis.csv`. File gồm một batch snapshot với ticket totals/status, resolution rate/duration, preventive status counts, recurring issue count, follow-up count và latest High/Critical risk asset count. Không tính MTBF; resolution duration không được claim là MTTR.

Formula, threshold và KPI definitions đầy đủ: [Analytics pipeline](analytics.md).

## Compatibility Và Thay Đổi Contract

- Existing FastAPI risk, anomaly, context và Copilot fields tiếp tục được giữ. Manager endpoints dùng explicit response schemas và normalize CSV blank values thành JSON `null`.
- Future additions phải ưu tiên additive change và có test cho schema/behavior.
- Generator không tạo raw `risk_scores.csv`; khi save, generator xóa stale raw file cũ nếu tồn tại. Canonical risk result chỉ là `data/processed/risk_scores.csv` do `src/risk/risk_scoring.py` tạo.
- Mọi thay đổi data contract phải cập nhật file này, validation, tests và README trong cùng milestone.

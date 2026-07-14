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

| Field | Type | Required | Ý nghĩa |
|---|---|---:|---|
| `doc_id` | string | Có | Định danh tài liệu |
| `title` | string | Có | Tiêu đề tiếng Việt |
| `doc_type` | string | Có | SOP, checklist hoặc troubleshooting guide |
| `asset_type` | string | Có | Loại asset áp dụng |
| `source` | string | Có | Nguồn hiển thị/citation |
| `raw_text` | string | Có | Nội dung gốc để trace trước khi chuẩn hóa |
| `clean_text` | string | Có | Nội dung đã chuẩn hóa để chunk/embed |
| `created_at` | datetime | Có | Thời điểm tạo/cập nhật tài liệu |

Dataset hiện có SOP/checklist cho cả ba focused asset types. RAG loader dùng `clean_text`; `raw_text` được giữ để trace nội dung gốc.

## Daily Maintenance Features

Canonical producer: `src/features/build_features.py`.

Với mỗi `asset_id` và `feature_date`:

- `last_maintenance_date` là event gần nhất có `maintenance_date <= feature_date`;
- `next_maintenance_date` lấy từ chính event đó;
- `days_since_last_maintenance = feature_date - last_maintenance_date`;
- `days_overdue = max(0, feature_date - next_maintenance_date)`.

Mọi asset phải có ít nhất một maintenance event trước hoặc đúng ngày đầu observation window. Feature pipeline không dùng future maintenance event và không fallback sang `installation_date`.

## Anomaly Results

Canonical producer: `src/models/anomaly_detection.py`.

| Field | Type | Required | Ý nghĩa |
|---|---|---:|---|
| `asset_id` | string | Có | Asset được chấm điểm |
| `date` | date | Có | Ngày feature |
| `asset_type` | string | Có | Loại asset |
| `location` | string | Có | Vị trí |
| `rule_based_score` | number 0-100 | Có | Severity từ rule |
| `isolation_forest_score` | number 0-100 | Có | Relative outlier score |
| `anomaly_score` | number 0-100 | Có | Combined score |
| `is_anomaly` | boolean | Có | Cờ bất thường theo implementation canonical |
| `anomaly_type` | string | Có | Loại bất thường tiếng Việt |
| `anomaly_reasons` | string | Có | Giải thích tiếng Việt |

Các operational values và delta hiện có trong output để hỗ trợ inspection, nhưng không thay đổi minimum identity/explanation contract ở trên.

## Risk Results

Canonical producer: `src/risk/risk_scoring.py`.

| Field | Type | Required | Ý nghĩa |
|---|---|---:|---|
| `asset_id` | string | Có | Asset được chấm điểm |
| `date` | date | Có | Ngày risk score |
| `asset_name` | string | Có | Tên hiển thị |
| `asset_type` | string | Có | Loại asset |
| `location` | string | Có | Vị trí |
| `anomaly_score` | number 0-100 | Có | Input bất thường |
| `maintenance_overdue_score` | number 0-100 | Có | Thành phần quá hạn |
| `recent_ticket_score` | number 0-100 | Có | Thành phần ticket gần đây |
| `criticality_score` | number 0-100 | Có | Thành phần criticality |
| `runtime_score` | number 0-100 | Có | Thành phần runtime |
| `final_risk_score` | number 0-100 | Có | Điểm ưu tiên cuối cùng |
| `risk_level` | string | Có | Mức rủi ro tiếng Việt |
| `main_reasons` | string | Có | Lý do chính tiếng Việt |
| `recommended_action` | string | Có | Hành động tham khảo tiếng Việt |

Risk result là decision-support output. Nó không phải failure probability đã hiệu chuẩn và không dự đoán exact failure time.

## Compatibility Và Thay Đổi Contract

- Existing FastAPI field names không thay đổi trong Milestone 1.
- Future additions phải ưu tiên additive change và có test cho schema/behavior.
- Generator không tạo raw `risk_scores.csv`; khi save, generator xóa stale raw file cũ nếu tồn tại. Canonical risk result chỉ là `data/processed/risk_scores.csv` do `src/risk/risk_scoring.py` tạo.
- Mọi thay đổi data contract phải cập nhật file này, validation, tests và README trong cùng milestone.

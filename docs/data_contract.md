# Data Contract Tối Thiểu

## Nguyên Tắc Chung

- Column name, API field và technical identifier dùng tiếng Anh.
- Business value và nội dung hiển thị cho người dùng dùng tiếng Việt.
- Timestamp dùng ISO 8601; timestamp có timezone khi dữ liệu ở mức thời gian.
- Date dùng định dạng `YYYY-MM-DD`.
- CSV là primary contract của MVP; PostgreSQL không phải dependency bắt buộc.
- Field đánh dấu **Future gap** thuộc target MVP nhưng chưa tồn tại đầy đủ trong behavior hiện tại.

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
| `last_maintenance_date` | date | Có | Ngày bảo trì gần nhất đã xác nhận | Có |
| `next_maintenance_date` | date | Có trong target contract | Ngày bảo trì kế tiếp | **Future gap** trong asset CSV; hiện có ở maintenance log |

Các field hiện có nhưng không thuộc minimum contract: `floor`, `installation_date`, `maintenance_frequency_days`.

## Tickets

Primary source hiện tại: `data/raw/maintenance_tickets.csv`.

| Field | Type | Required | Ý nghĩa |
|---|---|---:|---|
| `ticket_id` | string | Có | Định danh ticket |
| `asset_id` | string | Có | Asset liên quan |
| `issue_description` | string | Có | Mô tả sự cố tiếng Việt |
| `priority` | string | Có | Mức ưu tiên |
| `status` | string | Có | Trạng thái ticket |
| `created_at` | datetime | Có | Thời điểm tạo |
| `resolved_at` | datetime/null | Có điều kiện | Có giá trị khi ticket đã xử lý |
| `technician_note` | string | Có | Ghi chú hoặc hành động đề xuất của technician |
| `failure_type` | string | Có | Nhóm sự cố dùng cho recurring issue analysis |

## Maintenance Logs

Primary source hiện tại: `data/raw/maintenance_logs.csv`.

| Field | Type | Required | Ý nghĩa | Trạng thái hiện tại |
|---|---|---:|---|---|
| `log_id` | string | Có | Định danh maintenance log | Có |
| `asset_id` | string | Có | Asset được bảo trì | Có |
| `maintenance_date` | date | Có | Ngày thực hiện | Có |
| `maintenance_type` | string | Có | Preventive, corrective hoặc inspection bằng tiếng Việt | Có |
| `technician_name` | string | Có | Người thực hiện | Có |
| `actions_taken` | string | Có | Hành động đã thực hiện | Có |
| `maintenance_result` | string | Có trong target contract | Kết quả sau bảo trì | **Future gap**; hiện dùng `note` chung |
| `next_maintenance_date` | date | Có | Ngày bảo trì kế tiếp | Có |

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

`pressure` và raw `anomaly_type` hiện có để tương thích dữ liệu, nhưng không phải minimum operational contract của revised MVP.

## SOP/Checklist Documents

Primary source hiện tại: `data/raw/documents.csv`.

| Field | Type | Required | Ý nghĩa |
|---|---|---:|---|
| `doc_id` | string | Có | Định danh tài liệu |
| `title` | string | Có | Tiêu đề tiếng Việt |
| `doc_type` | string | Có | SOP, checklist hoặc troubleshooting guide |
| `asset_type` | string | Có | Loại asset áp dụng |
| `source` | string | Có | Nguồn hiển thị/citation |
| `clean_text` | string | Có | Nội dung đã chuẩn hóa để chunk/embed |
| `created_at` | datetime | Có | Thời điểm tạo/cập nhật tài liệu |

`raw_text` hiện có và nên được giữ để trace nội dung gốc, dù RAG loader hiện dùng `clean_text`.

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
- Legacy raw `risk_scores.csv` do data generator tạo không phải canonical processed risk result.
- Mọi thay đổi data contract phải cập nhật file này, validation, tests và README trong cùng milestone.

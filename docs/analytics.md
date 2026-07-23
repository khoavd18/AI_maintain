# Analytics Pipeline Canonical

> Ticket, maintenance log và inventory được ghi vào PostgreSQL. Chỉ database-to-analytics snapshot tiếp theo mới đưa contract được hỗ trợ vào batch inputs; write endpoints không thay đổi feature, anomaly, risk, preventive, recurring hoặc KPI output ngay tại thời điểm lưu.

## Phạm Vi

Analytics chạy theo batch trên validated CSV snapshot gồm PostgreSQL transactions và generated operational data. Kết quả dùng để ưu tiên kiểm tra và hỗ trợ giải thích; không phải failure probability, không dự đoán thời điểm hỏng và không tự động quyết định maintenance action.

Production path chỉ sử dụng:

- feature và maintenance analytics: `src/features/build_features.py`;
- anomaly detection: `src/models/anomaly_detection.py`;
- risk scoring: `src/risk/risk_scoring.py`.

## Daily Features

Mỗi hàng đại diện một `asset_id` tại một `feature_date`. Pipeline tổng hợp energy, runtime, temperature và vibration theo ngày, rolling baseline 7 ngày, ticket counts 7/30 ngày và maintenance chronology.

Các signal nghiệp vụ bổ sung:

- `unresolved_ticket_count`: ticket đã tạo trước hoặc đúng ngày feature nhưng chưa có resolution trước cuối ngày đó;
- `recurring_issue_count`: số `failure_category` của asset đã đạt ít nhất 3 occurrences tính đến ngày feature;
- `follow_up_required_count`: số maintenance logs đến ngày feature có `follow_up_required = true`.

Mọi calculation chỉ dùng ticket và maintenance event có timestamp không muộn hơn feature date. `pressure = 0.0` chỉ là compatibility field cho API hiện tại, không phải raw sensor measurement hoặc model signal.

## Anomaly Detection

Canonical anomaly pipeline gồm hai thành phần deterministic:

1. Rules kiểm tra delta so với rolling baseline: energy tăng từ 50%, vibration tăng từ 0.15, runtime tăng từ 40%, hoặc temperature tăng từ 3°C.
2. Isolation Forest chạy riêng theo `asset_type`, dùng `random_state = 42`, `contamination = 0.06` và tạo relative outlier severity từ 0 đến 100.

```text
anomaly_score = 70% rule_based_score + 30% isolation_forest_score
is_anomaly = anomaly_score >= 60
```

Vì Isolation Forest đóng góp tối đa 30 điểm, model này không thể tự tạo final anomaly flag nếu không có rule signal. Rules kiểm soát điều kiện cần; Isolation Forest điều chỉnh severity và bổ sung explanation. Raw data không có anomaly label và pipeline không dùng future outcome làm input.

`anomalous_metrics` liệt kê metric vượt rule threshold. `contributing_signals` và `anomaly_reasons` giữ giải thích tiếng Việt. Score là severity phục vụ prioritization, không phải xác suất hỏng.

## Risk Scoring

Mỗi component được chuẩn hóa trong khoảng 0–100. Formula canonical:

```text
risk_score =
  20% anomaly_score
+ 25% maintenance_overdue_score
+ 20% unresolved_ticket_score
+ 10% recent_ticket_score
+  7.5% recurring_issue_score
+ 10% criticality_score
+  5% follow_up_score
+  2.5% runtime_score
```

Final score được clip về `[0, 100]`. Internal level code và display value:

| Score | Internal code | Vietnamese display |
|---:|---|---|
| 0–30 | `low` | `Thấp` |
| >30–60 | `medium` | `Trung bình` |
| >60–80 | `high` | `Cao` |
| >80–100 | `critical` | `Khẩn cấp` |

Các component thresholds:

- overdue: 0 ngày = 0; 1–7 = 30; 8–30 = 60; trên 30 = 100;
- unresolved tickets: 0 = 0; 1 = 50; 2 = 75; từ 3 = 100;
- recent tickets: 0 = 0; 1 = 30; 2–3 = 60; từ 4 = 80; cộng 20 nếu có high-priority ticket, tối đa 100;
- recurring categories: 0 = 0; 1 = 70; từ 2 = 100;
- follow-up logs: 0 = 0; 1 = 70; từ 2 = 100;
- criticality: source score 1–4 được đổi thành 25–100;
- runtime delta: đến 10% = 0; đến 25% = 30; đến 50% = 70; trên 50% = 100.

`risk_score`/`contributing_factors` là canonical aliases. `final_risk_score`/`main_reasons` tiếp tục được giữ để bảo toàn API contract hiện tại.

## Preventive Maintenance Status

Output: `data/processed/preventive_maintenance_status.csv`.

Status được tính tại ngày cuối observation window:

- `overdue`: `next_maintenance_date < as_of_date`;
- `due_soon`: còn từ 0 đến 14 ngày;
- `not_due`: còn trên 14 ngày.

`days_overdue` và `days_until_due` đều không âm. Internal code được giữ ổn định; `maintenance_status_display` cung cấp business value tiếng Việt.

## Recurring Issues

Output: `data/processed/recurring_issues.csv`.

Ticket được group theo `asset_id` và `failure_category`. `recurrence_flag = true` khi `occurrence_count >= 3`. Output giữ first/last occurrence cùng resolved/unresolved counts. Đây là phép group deterministic, không dùng LLM hoặc model.

## Maintenance KPIs

Output: `data/processed/maintenance_kpis.csv`, gồm một snapshot tại ngày cuối observation window.

| KPI | Định nghĩa |
|---|---|
| `total_tickets` | Tổng ticket trong observation window |
| `open_tickets` | Ticket không có status `Đã xử lý` |
| `resolved_tickets` | Ticket có status `Đã xử lý` và resolution timestamp hợp lệ |
| `ticket_resolution_rate_percent` | `resolved_tickets / total_tickets * 100` |
| `average_resolution_time_hours` | Trung bình `resolved_at - created_at` của resolved tickets |
| `median_resolution_time_hours` | Median của cùng duration |
| `overdue_asset_count` | Assets có preventive status `overdue` |
| `due_soon_asset_count` | Assets có preventive status `due_soon` |
| `recurring_issue_count` | Asset/category groups có `recurrence_flag = true` |
| `follow_up_required_maintenance_count` | Maintenance logs có follow-up flag |
| `high_critical_risk_asset_count` | Assets ở level `high` hoặc `critical` tại ngày risk mới nhất |

Average/median resolution time không được gọi là MTTR vì ticket data không bảo đảm mọi ticket là repair event. Pipeline không tính MTBF do không có failure-event contract đủ chặt.

## Product Milestone 4 Compatibility Bridge

Preventive plans và work orders là PostgreSQL transactional views, không thay formula analytics ở trên.

- Mỗi plan giữ `next_due_date` riêng. Transactional `assets.next_maintenance_date` là ngày sớm nhất của active plans sau verified maintenance; nếu không có active plan, service giữ legacy interval/log fallback.
- Work-order completion tạo một MaintenanceLog nhưng chưa đổi Risk Score/KPI processed CSV. Verification cập nhật transactional asset maintenance dates, nhưng analytics chỉ thấy dữ liệu sau `export_snapshot` và full batch run.
- Existing CSV validator yêu cầu fixed interval. Vì vậy `export_snapshot` tạo compatibility projection: asset `next_maintenance_date = last_maintenance_date + maintenance_interval_days`, và log `next_maintenance_date = maintenance_date + maintenance_interval_days`. PostgreSQL vẫn giữ nguyên plan-derived operational dates.
- Preventive plan/work-order calendar và work-order metrics là operational views từ PostgreSQL. Existing batch preventive/KPI formulas tiếp tục dùng legacy interval projection trong milestone này; không diễn giải hai view là cùng một scheduling metric.
- Work-order status/checklist/evidence không được thêm làm feature, anomaly hoặc risk input trong milestone này.

## Product Milestone 6 Inventory Boundary

Inventory là transactional operational domain và **không** được thêm vào current analytics snapshot/formulas:

- spare-part quantity, reservation, issue, consumption, return, low-stock state và unit cost không phải feature;
- work-order shortage không thay anomaly score, Risk Score, preventive status, recurring issue, maintenance KPI, ticket KPI hoặc SLA;
- receipt/reserve/issue/return/transfer/adjustment không trigger batch job;
- `MaintenanceLog.parts_replaced` vẫn là narrative legacy field, không được join với inventory ledger để suy ra cost hoặc model signal;
- inventory metrics từ PostgreSQL là operational report riêng, không phải `maintenance_kpis.csv`.

Future analytics chỉ được thêm khi có explicit data contract, data-quality ownership và evaluation; không được âm thầm thay formula hiện tại.

`GET /work-orders/metrics` là reporting transaction riêng, không thay `maintenance_kpis.csv`:

| Metric | Định nghĩa |
|---|---|
| `total_work_orders` | Số WO trong PostgreSQL query scope hiện tại |
| `by_status` | Count theo canonical WO status |
| `overdue_count` | Non-verified/non-cancelled WO khi `due_date + grace_period_days < as_of_date` |
| `upcoming_preventive_count` | Preventive WO non-terminal có due date trong `[as_of_date, as_of_date + 30 ngày]` |
| `completed_count` | WO ở `completed` hoặc `verified` |
| `verified_count` | WO ở `verified` |
| `completed_on_time_count` | Completed/verified WO có `completed_at` không sau due + grace |
| `technician_workload.open_count` | Assigned WO chưa verified/cancelled theo technician |

Các metric được gắn nhãn synthetic/internal-pilot. Completion percentage không được gọi là reliability/predictive accuracy; MTTR, MTBF, downtime và cost vẫn ngoài scope.

## Limitations

- Thresholds và weights là transparent demo heuristics, chưa được hiệu chuẩn bằng facility history thực tế.
- Isolation Forest chỉ cho biết mức khác biệt tương đối trong synthetic batch data.
- Recurrence threshold 3 là business rule của MVP, không phải industry standard.
- KPI phản ánh synthetic snapshot và không chứng minh ROI, reliability improvement hoặc production performance.
- Human manager và technician vẫn xác minh dữ liệu, an toàn, hiện trạng và quyết định cuối cùng.

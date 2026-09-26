# Đặc tả report Maintenance Analytics

## Ranh giới kiến trúc

Power BI là consumer cuối của Data Platform, tách khỏi operational frontend:

```text
OLTP PostgreSQL -> Airflow -> raw -> dbt staging -> dbt warehouse/marts -> Power BI
```

Report chỉ đọc. Nó không gọi API mutation, không cập nhật OLTP, không tạo luồng
real-time và không thay thế quyết định của facility manager/technician.

## Semantic model

| Table | Nguồn | Grain | Mục đích |
|---|---|---|---|
| `Date` | `analytics_warehouse.dim_date` | một ngày | lọc và trục thời gian |
| `Site` | `analytics_warehouse.dim_site` | một site | dimension dùng chung |
| `Daily Work Orders` | `analytics_marts.daily_site_work_orders` | site x ngày | KPI và xu hướng work order |
| `Site Reliability` | `analytics_marts.site_reliability` | một site | completion, repair, on-hold |
| `Ticket SLA` | `analytics_marts.ticket_sla` | site x priority | ticket và SLA |
| `Inventory Consumption` | `analytics_marts.inventory_consumption` | part x site | issue/return/net consumed |
| `Technician Workload` | projection từ `dim_technician` + `fact_work_order` | technician x site | workload tổng hợp |

Projection workload chỉ gồm `SELECT`, `LEFT JOIN` và `GROUP BY`; không tạo hay
sửa object trong database.

### Relationships

Tất cả relationship là many-to-one, single direction từ dimension sang fact:

- `Daily Work Orders[created_date]` -> `Date[date]`
- Các table domain có `site_id` -> `Site[site_id]`

Không nối trực tiếp hai mart với nhau. `Ticket SLA` và `Inventory Consumption`
không có date grain trong contract hiện tại, vì vậy date slicer chỉ xuất hiện ở
trang work-order và không được mô tả như bộ lọc toàn report.

### Measures

| Measure | Định nghĩa business |
|---|---|
| `Total Work Orders` | tổng work order ở grain site/ngày |
| `Completed Work Orders` | tổng status completed/verified từ mart |
| `Completion Rate` | completed / total, trả blank khi mẫu số bằng 0 |
| `Critical Work Orders` | tổng work order priority critical |
| `Unassigned Work Orders` | tổng work order chưa có technician |
| `Average Repair Hours` | total repair hours / số work order có duration |
| `Site Completion Rate` | completed / work order ở mart reliability |
| `On-Hold Hours` | tổng on-hold seconds / 3600 |
| `Tickets` | tổng ticket |
| `Unresolved Tickets` | ticket chưa resolved |
| `SLA Breaches` | ticket breach resolution SLA |
| `SLA Breach Rate` | breach / ticket |
| `Escalated Tickets` | ticket đã escalation |
| `First Response Met Rate` | first-response-met / ticket |
| `Issued Quantity` | tổng lượng issue |
| `Returned Quantity` | tổng lượng return |
| `Net Consumed Quantity` | issue trừ return |
| `Assigned Technician Work Orders` | tổng work order được gán theo technician/site |
| `Completed Technician Work Orders` | completed/verified theo technician/site |
| `In-Progress Technician Work Orders` | in-progress theo technician/site |
| `Technician Completion Rate` | completed / assigned |

Không có measure chi phí.

## Trang report

### 1. Tổng quan điều hành

- Slicer: site, khoảng ngày tạo work order.
- Cards: total, completed, completion rate, critical, unassigned.
- Line chart: total và completed theo tháng.
- Bar chart: total và completed theo site.

### 2. Độ tin cậy & khối lượng

- Slicer: site.
- Cards: work order reliability, completion rate, repair hours, on-hold hours.
- Charts: completion rate và repair hours theo site.
- Table: employee code, technician, role, assigned/completed/in-progress và
  completion rate.

### 3. SLA & phụ tùng

- Slicer: site.
- Cards: tickets, unresolved, SLA breach rate, escalated, first-response-met.
- Column chart: ticket/unresolved/breach theo priority.
- Bar chart: net consumed theo spare part.
- Table: part number/name cùng issued/returned/net consumed.

## Tiêu chí nghiệm thu

- PBIR validation không có error hoặc warning.
- Ba page có đúng thứ tự, tiêu đề tiếng Việt và visual có data binding.
- Project mở được bằng Power BI Desktop; refresh chỉ yêu cầu credential tương
  tác và không chứa secret trong file tracked.
- Cards/charts/tables render không blank với database demo đã populate.
- Site/date slicer lọc đúng domain được relationship hỗ trợ.
- Không có reference đến frontend, FastAPI, raw/staging hay maintenance cost.
- `build_project.py --check` và test cấu trúc pass.

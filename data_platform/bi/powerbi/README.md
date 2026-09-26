# Maintenance Analytics - Power BI demo

Đây là lớp BI độc lập của Data Platform. Dự án Power BI đọc dữ liệu batch đã
được dbt kiểm thử trong `analytics_marts` và một projection tổng hợp chỉ-đọc từ
`analytics_warehouse`; nó không gọi FastAPI và không nằm trong Next.js.

```text
PostgreSQL OLTP
  -> Airflow ingestion
  -> raw
  -> dbt staging
  -> dbt warehouse/marts
  -> Power BI report
```

## Nội dung demo

Dự án `MaintenanceAnalytics.pbip` có ba trang:

1. `Tổng quan điều hành`: khối lượng work order, tỷ lệ hoàn thành, work order
   critical/chưa phân công, xu hướng theo tháng và phân bổ theo site.
2. `Độ tin cậy & khối lượng`: thời gian sửa chữa, thời gian on-hold, độ tin cậy
   theo site và workload kỹ thuật viên.
3. `SLA & phụ tùng`: ticket, SLA breach/escalation và lượng phụ tùng issue,
   return, net consumed.

Chi phí bảo trì không được đưa vào report. Mart lịch sử `maintenance_cost` vẫn
tồn tại trong dbt nhưng reporting chi phí/kế toán nằm ngoài phạm vi MVP hiện
tại.

Power BI Desktop tạo **report nhiều trang**. Nếu cần một Power BI Service
dashboard, sau khi publish có thể pin các visual đã chọn từ report; dashboard
Service không phải là một phần của source PBIP này.

## Nguồn dữ liệu demo

Project được sinh mặc định cho nguồn hiện có:

```text
Server:   127.0.0.1:25432
Database: maintenance_copilot_benchmark_scale
User:     maintenance_scale
Mode:     Import
```

Không có mật khẩu trong PBIP, TMDL, script hay tài liệu. Khi refresh lần đầu,
Power BI Desktop sẽ yêu cầu PostgreSQL credential. Lấy mật khẩu từ biến môi
trường/quản lý secret của môi trường demo, không lưu nó vào repository.

Database `maintenance_copilot_benchmark_scale` được chọn vì đây là database
lịch sử hiện đang có đầy đủ marts để demo. Khi chuyển môi trường, sinh lại
project với server/database mới:

```powershell
python data_platform/bi/powerbi/build_project.py `
  --server "postgres.company.internal:5432" `
  --database "maintenance_analytics"
```

Script cố ý không có tham số mật khẩu.

## Mở và refresh

Yêu cầu: Power BI Desktop có PostgreSQL connector và local Docker Data Platform
đang chạy.

```powershell
python data_platform/bi/powerbi/build_project.py --check

npx -y @microsoft/powerbi-report-authoring-cli@latest `
  validate data_platform/bi/powerbi/MaintenanceAnalytics/MaintenanceAnalytics.Report `
  --pretty

npx -y @microsoft/powerbi-desktop-bridge-cli@latest `
  open "$(Resolve-Path data_platform/bi/powerbi/MaintenanceAnalytics/MaintenanceAnalytics.pbip)"
```

Trong Power BI Desktop:

1. Chọn `Transform data > Data source settings` nếu hộp thoại credential chưa
   tự mở.
2. Chọn PostgreSQL source `127.0.0.1:25432` và nhập database credential.
3. Chọn mức privacy phù hợp với môi trường nội bộ demo.
4. Nếu Desktop hỏi xác nhận native query cho `Technician Workload`, kiểm tra
   query chỉ có `SELECT ... GROUP BY` rồi chọn chạy.
5. Chọn `Refresh`, sau đó kiểm tra ba trang và các slicer site/date.

Không chạy refresh Power BI đồng thời với lúc Airflow/dbt đang thay thế mart.
Report là batch analytics: dữ liệu chỉ thay đổi sau lần refresh kế tiếp.

## Phát triển và kiểm tra

Không sửa tay đồng thời cả generator và output. Thay đổi source trong
`build_project.py`, sinh lại rồi validate:

```powershell
python data_platform/bi/powerbi/build_project.py
python data_platform/bi/powerbi/build_project.py --check

npx -y @microsoft/powerbi-report-authoring-cli@latest `
  validate data_platform/bi/powerbi/MaintenanceAnalytics/MaintenanceAnalytics.Report `
  --pretty

npx -y @microsoft/powerbi-report-authoring-cli@latest `
  preview-pages data_platform/bi/powerbi/MaintenanceAnalytics/MaintenanceAnalytics.Report `
  --pretty

npx -y @microsoft/powerbi-report-authoring-cli@latest `
  preview-visuals data_platform/bi/powerbi/MaintenanceAnalytics/MaintenanceAnalytics.Report `
  --with-derived --pretty
```

`--check` thất bại nếu output đã bị sửa tay hoặc thiếu file. File local do Power
BI tạo (`.pbi/localSettings.json`, `.pbi/cache.abf`) được ignore và không được
commit.

## Giới hạn bàn giao

- Đây là demo batch reporting, chưa phải cấu hình Power BI Service production.
- Chưa có gateway, refresh schedule, workspace RBAC, RLS hay deployment
  pipeline. Các phần đó cần thiết kế theo tenant của công ty trước khi publish.
- KPI mô tả dữ liệu lịch sử để con người ưu tiên và điều tra; chúng không tự
  quyết định công việc bảo trì.

Chi tiết contract, grain, relationship và measure nằm trong
[`report-spec.md`](report-spec.md).

# Phạm Vi MVP

## Bài Toán

Đội ngũ vận hành tòa nhà thường phải đối chiếu nhiều nguồn dữ liệu rời rạc: danh mục thiết bị, ticket sự cố, lịch bảo trì định kỳ, dữ liệu vận hành và tài liệu SOP/checklist. AI Maintenance Copilot tập hợp các tín hiệu đó thành một lớp hỗ trợ quyết định để trả lời ba câu hỏi:

1. Thiết bị nào cần được ưu tiên kiểm tra?
2. Vì sao thiết bị đó có mức rủi ro cao?
3. Kỹ thuật viên nên tham khảo SOP hoặc checklist nào?

Sản phẩm không thay thế CMMS/S-Maintain và không tự quyết định thay con người. Manager và technician chịu trách nhiệm xác minh hiện trường, lựa chọn hành động và ghi nhận kết quả cuối cùng.

## Người Dùng Mục Tiêu

| Người dùng | Nhu cầu chính |
|---|---|
| Facility Manager | Theo dõi tình trạng bảo trì tổng thể, nhận diện thiết bị rủi ro và sắp xếp thứ tự ưu tiên |
| Maintenance Supervisor | Xem nguyên nhân rủi ro, tình trạng quá hạn và lịch sử ticket trước khi phân công kiểm tra |
| Technician | Xem ngữ cảnh thiết bị và tìm SOP/checklist liên quan trước khi kiểm tra hiện trường |
| Storekeeper | Quản lý part/location master, kiểm soát receipt/reservation/issue/return/transfer/adjustment và đối chiếu movement history |
| Data/AI Reviewer | Kiểm tra data contract, batch analytics, API contract và tính giải thích của kết quả |

## Phạm Vi Được Chấp Nhận

### Dữ Liệu Nghiệp Vụ

- Hồ sơ asset: identity/technical data, hierarchical location, criticality, lifecycle/operational status, warranty, maintenance dates, safe attachments và authenticated opaque QR lookup.
- Ticket: rich intake, backend impact/urgency priority, explicit lifecycle, assignment, SLA snapshot, comments và escalation history.
- Maintenance log: ngày bảo trì, loại bảo trì, hành động đã thực hiện, kết quả và lịch kế tiếp.
- Preventive maintenance plan: recurring intent theo interval có kiểm soát, timezone, lead/grace period, checklist và assignee mặc định.
- Standalone work order: một công việc thực thi cụ thể, có source plan hoặc ticket, assignee, checklist snapshot, evidence, completion, verification và audit.
- Spare-part master, UOM, stock location, effective reorder thresholds, inventory position và immutable movement history.
- Work-order part requirement, reservation, issue, explicit consumption và unused-part return là các record riêng.
- Operational reading theo batch: điện năng, runtime, nhiệt độ và độ rung khi phù hợp với loại thiết bị.
- SOP/checklist tiếng Việt có metadata nguồn và loại thiết bị.

Synthetic demo scope được khóa ở ba loại asset: `Máy lạnh` (HVAC), `Máy bơm nước` (pump) và `Máy phát điện dự phòng` (generator). Dataset mặc định gồm 27 assets và 120 ngày operational readings theo giờ. Đây là quy mô demo, không phải sizing cho production.

### Analytics Và Ứng Dụng

- Tổng hợp feature hằng ngày ở cấp asset.
- Batch anomaly detection bằng rule-based signals và Isolation Forest.
- Explainable risk scoring và danh sách top risky assets.
- Theo dõi bảo trì sắp tới, quá hạn và số ngày quá hạn.
- Phân tích sự cố lặp lại từ ticket.
- Maintenance KPI ở mức mô tả, với định nghĩa rõ ràng.
- FastAPI làm serving boundary cho Streamlit và Copilot.
- RAG Copilot tìm SOP/checklist liên quan và hiển thị nguồn.
- Maintenance result có enum rõ ràng, liên kết ticket khi là corrective maintenance và cờ follow-up nhất quán.
- Asset lifecycle archive/restore không phá history, unified asset timeline và mobile web QR lookup có RBAC.
- Deterministic preventive work-order generation qua protected API/CLI; không chạy ngầm khi startup và retry không tạo occurrence trùng.
- Corrective work order tạo explicit từ ticket; create/complete/verify work order không tự resolve ticket.
- Checklist template được version hóa; work order giữ snapshot để lịch sử không đổi.
- Operational ticket queues, first-response/resolution SLA và idempotent escalation evaluation qua API/CLI explicit; không có notification delivery.
- Inventory overview, part catalogue, stock by location, low-stock queue, movement timeline và named stock actions.
- `available = on_hand - reserved`; concurrent reserve/issue/return/transfer/adjustment đi qua PostgreSQL transaction và không cho tồn âm.

## Trạng Thái Hiện Tại Và Future Milestones

Đã có trong repository:

- synthetic Vietnamese CSV data;
- data validation;
- daily feature engineering;
- canonical anomaly detection;
- canonical explainable risk scoring;
- preventive maintenance status, recurring issue và maintenance KPI processed outputs;
- PostgreSQL-primary FastAPI cho asset, ticket, preventive plan, checklist template, work order, maintenance-log và inventory transactions;
- Alembic migrations, validated CSV seed import, optimistic conflicts và analytics snapshot export;
- Next.js authenticated workflow, permission-aware views, user administration và audit read UI;
- Streamlit legacy development health/status page;
- local/internal-pilot authentication, RBAC và append-only PostgreSQL audit;
- auditable asset lifecycle, location hierarchy, safe local attachment storage và deterministic QR lookup;
- preventive-plan lifecycle, controlled recurrence, standalone work-order state machine, checklist execution, evidence và independent verification;
- rich ticket intake/priority, named lifecycle actions, business-calendar SLA snapshots, append-only communication/escalation và server-driven queues;
- spare-part/location lifecycle, immutable movement ledger, work-order reservation/issue/consumption/return và deterministic low-stock visibility;
- Qdrant-based SOP/checklist retrieval và deterministic Copilot response.

Các production concerns ngoài behavior hiện tại gồm notification delivery, production scheduler/worker, SSO/MFA, distributed throttling, key rotation, centralized observability/audit retention, deployment hardening và browser regression testing. Đây không phải current capabilities của internal pilot.

## Ngoài Phạm Vi

- Supplier, purchasing, purchase requisition, purchase order hoặc inventory optimization.
- Accounting, general ledger, stock valuation hoặc maintenance-cost reporting.
- Resident mobile application.
- Technician mobile application.
- Vendor và contract management.
- Complex approval workflow.
- Real-time IoT streaming, event processing hoặc live alerting.
- SSO, MFA, external identity provider hoặc enterprise IAM integration.
- Hidden startup generation, distributed scheduler, job queue hoặc production scheduling infrastructure. Work order chỉ được generate qua API/CLI explicit trong current milestone.
- Exact failure-time prediction hoặc cam kết thời điểm thiết bị sẽ hỏng.
- Thay thế CMMS/S-Maintain làm enterprise-wide system of record.
- Tự động đưa ra quyết định bảo trì cuối cùng mà không có con người xác nhận.

## Giả Định

- PostgreSQL là primary transactional source cho assets, locations, attachment metadata, tickets/SLA history, preventive plans, checklist templates, work orders, maintenance logs và inventory; attachment bytes ở private storage abstraction.
- CSV là synthetic seed, import/export và batch analytics contract; explicit CSV runtime chỉ dành cho isolated fixtures.
- Dữ liệu được xử lý theo batch; không có yêu cầu near-real-time hoặc real-time.
- Dữ liệu hiện tại là synthetic và chỉ phục vụ development, demo, test.
- PostgreSQL local là prerequisite của normal product demo; unavailable database không fallback sang mutable CSV.
- Qdrant chỉ phục vụ vector retrieval cho RAG Copilot.
- Risk score là heuristic prioritization score, không phải calibrated failure probability.
- User-facing business values và giải thích được giữ bằng tiếng Việt; code, module, column và API field giữ bằng tiếng Anh.
- Manager và technician luôn kiểm tra lại dữ liệu, điều kiện an toàn và hiện trạng thiết bị.
- PostgreSQL workflow có transaction, FK, sequence và optimistic conflict; analytics vẫn không tự refresh sau khi ghi ticket/log.
- Due date là business date theo IANA timezone của plan; execution timestamps là UTC. Catch-up chỉ xét cửa sổ tối đa 366 ngày và không tạo backlog trong thời gian plan bị pause.
- Completion tạo đúng một maintenance log; verification bởi actor khác mới cập nhật maintenance dates của asset. Ticket chỉ resolve qua action explicit.
- Ticket priority chỉ do backend impact/urgency matrix tính. SLA state derive từ snapshotted policy/calendar, timestamps và pause intervals; không có editable breach flag.
- Attachment bytes dùng private local single-node storage; PostgreSQL chỉ giữ metadata/checksum. QR chỉ là identifier và vẫn yêu cầu authentication.
- Inventory balance/state/reorder suggestion do backend derive. Reservation không phải issue; issue không mặc định là consumption; work-order completion không tạo hoặc giải phóng stock movement.
- `parts_replaced` trong MaintenanceLog chỉ là historical narrative; inventory movement là source of truth cho quantity.

## Tiêu Chí Thành Công

MVP được xem là coherent khi:

1. Một developer có thể migrate PostgreSQL, dry-run/import canonical CSV seed và xác nhận 27/42/86 transactional rows.
2. Snapshot bridge tạo full validated analytics input từ PostgreSQL transactions và generated batch files.
3. Pipeline canonical tạo được feature, anomaly result và risk result theo thứ tự xác định.
4. FastAPI phục vụ dữ liệu cho Streamlit/Next.js; frontend không đọc trực tiếp database hoặc CSV.
5. Manager có thể nhận diện top risky assets và đọc nguyên nhân/khuyến nghị bằng tiếng Việt.
6. Technician có thể tìm SOP/checklist liên quan và thấy nguồn tài liệu được sử dụng.
7. Chief Engineer có thể tạo checklist/plan, preview occurrence và generate đúng một work order cho mỗi `(plan, due_date)`.
8. Manager có thể tạo inspection/corrective work order từ ticket; technician được giao có thể start, ghi checklist/evidence, complete và tạo đúng một maintenance log.
9. Một actor được ủy quyền khác có thể verify work order; asset maintenance dates cập nhật transactionally nhưng linked ticket không tự resolve.
10. Concurrent IDs, duplicate occurrence, invalid FK, rollback và stale write có automated integration tests trên database `_test`.
11. UI thông báo rõ risk/KPI chỉ cập nhật trong batch tiếp theo.
12. Authorized user có thể đăng ký/update/archive/restore asset, quản lý attachment, mở QR mobile route và xem de-duplicated history; unauthorized actions bị FastAPI từ chối.
13. Helpdesk có thể intake/route ticket; technician xử lý ticket được gán; manager theo dõi queues/SLA, comments và escalation mà không có automatic status transition hoặc notification delivery.
14. Storekeeper có thể receipt/reserve/issue/return/transfer/adjust; technician được gán chỉ có thể xem stock context và ghi permitted consumption cho work order của mình.
15. Concurrent reservation không oversubscribe available stock; transfer commit hai movement hoặc rollback toàn bộ; history không bị sửa/xóa.
16. Current features và future work được phân biệt rõ; tests/lint pass và không claim accuracy, ROI hoặc production readiness khi chưa có bằng chứng.

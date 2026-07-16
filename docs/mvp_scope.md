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
| Data/AI Reviewer | Kiểm tra data contract, batch analytics, API contract và tính giải thích của kết quả |

## Phạm Vi Được Chấp Nhận

### Dữ Liệu Nghiệp Vụ

- Thông tin cơ bản của asset: ID, loại, vị trí, mức độ quan trọng, trạng thái, ngày bảo trì gần nhất và ngày bảo trì kế tiếp.
- Ticket: mô tả sự cố, mức ưu tiên, trạng thái, thời điểm tạo/hoàn tất và ghi chú kỹ thuật viên.
- Maintenance log: ngày bảo trì, loại bảo trì, hành động đã thực hiện, kết quả và lịch kế tiếp.
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

## Trạng Thái Hiện Tại Và Future Milestones

Đã có trong repository:

- synthetic Vietnamese CSV data;
- data validation;
- daily feature engineering;
- canonical anomaly detection;
- canonical explainable risk scoring;
- preventive maintenance status, recurring issue và maintenance KPI processed outputs;
- CSV-backed FastAPI cho asset, ticket, log reads cùng local single-user write workflow;
- Streamlit dashboard với năm views, gồm risk-to-action và Ticket workspace;
- Qdrant-based SOP/checklist retrieval và deterministic Copilot response.

Các production concerns ngoài behavior hiện tại gồm scheduler, authentication, audit logging, observability, deployment hardening và browser regression testing. Đây không phải current capabilities của portfolio MVP.

## Ngoài Phạm Vi

- Spare-parts inventory hoặc inventory optimization.
- QR code generation/scanning.
- Resident mobile application.
- Technician mobile application.
- Vendor và contract management.
- Complex approval workflow.
- Real-time IoT streaming, event processing hoặc live alerting.
- Enterprise authentication, authorization hoặc RBAC.
- Tự động tạo production work order.
- Exact failure-time prediction hoặc cam kết thời điểm thiết bị sẽ hỏng.
- Thay thế CMMS/S-Maintain làm system of record.
- Tự động đưa ra quyết định bảo trì cuối cùng mà không có con người xác nhận.

## Giả Định

- CSV là primary data source và serving contract của MVP.
- Dữ liệu được xử lý theo batch; không có yêu cầu near-real-time hoặc real-time.
- Dữ liệu hiện tại là synthetic và chỉ phục vụ development, demo, test.
- PostgreSQL là optional/experimental; không cần để chạy demo chính.
- Qdrant chỉ phục vụ vector retrieval cho RAG Copilot.
- Risk score là heuristic prioritization score, không phải calibrated failure probability.
- User-facing business values và giải thích được giữ bằng tiếng Việt; code, module, column và API field giữ bằng tiếng Anh.
- Manager và technician luôn kiểm tra lại dữ liệu, điều kiện an toàn và hiện trạng thiết bị.
- CSV write workflow không hỗ trợ concurrent users; analytics không tự refresh sau khi ghi ticket/log.

## Tiêu Chí Thành Công

MVP được xem là coherent khi:

1. Một developer có thể chạy data pipeline chính từ CSV mà không cần PostgreSQL.
2. Pipeline canonical tạo được feature, anomaly result và risk result theo thứ tự xác định.
3. FastAPI phục vụ dữ liệu cho Streamlit; dashboard không đọc trực tiếp processed CSV.
4. Manager có thể nhận diện top risky assets và đọc nguyên nhân/khuyến nghị bằng tiếng Việt.
5. Technician có thể tìm SOP/checklist liên quan và thấy nguồn tài liệu được sử dụng.
6. Manager có thể tạo inspection ticket và technician có thể ghi maintenance result qua FastAPI mà không đọc/ghi CSV từ Streamlit.
7. UI thông báo rõ risk/KPI chỉ cập nhật trong batch tiếp theo.
8. Current features và future work được phân biệt rõ trong README và docs.
9. Test và lint pass; không có claim về accuracy, ROI hoặc production readiness khi chưa có bằng chứng.

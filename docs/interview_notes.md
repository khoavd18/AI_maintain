# Ghi Chú Phỏng Vấn

## Vì Sao Chọn Bài Toán Bảo Trì?

Bảo trì có business workflow rõ: dữ liệu vận hành, ticket, lịch preventive và tài liệu kỹ thuật phải được tổng hợp để quyết định thiết bị nào cần kiểm tra trước. Bài toán cho phép trình bày data engineering, explainable ML, API, dashboard và RAG trong một flow có human-in-the-loop.

## Project Giải Quyết Vấn Đề Gì?

Project giúp Facility Manager ưu tiên assets cần chú ý và giúp technician tìm SOP/checklist liên quan. Input gồm asset master, hourly readings, tickets, maintenance logs và documents. Output gồm daily features, anomaly results, explainable risk scores, preventive/recurring/KPI reports, dashboard và source-grounded Copilot response.

## Vì Sao Đây Không Phải Full CMMS?

CMMS là system of record cho work orders, assignments, approvals, inventory, vendor và maintenance history. Project chỉ là decision-support layer đọc dữ liệu kiểu CMMS để phân tích và retrieve tài liệu. Nó không tự tạo production work order, không quản lý inventory và không thay con người quyết định.

## Vì Sao Dùng Synthetic Data?

Dữ liệu bảo trì thật thường nhạy cảm, khó chia sẻ và hiếm failure labels. Generator deterministic giúp demo và test reproducible với 27 assets, 77.760 readings, 42 tickets và 86 logs. Synthetic data không chứng minh model accuracy hoặc business impact; production phải validate lại bằng history thực tế.

## Đây Có Phải Predictive Maintenance Không?

Đây là batch predictive-maintenance decision support theo nghĩa phát hiện tín hiệu bất thường và ưu tiên risk trước inspection. Nó không dự đoán exact failure time và Risk Score không phải calibrated failure probability. Cách gọi chính xác nhất là explainable maintenance risk prioritization.

## Risk Score Được Tính Như Thế Nào?

```text
final_risk_score =
  20% anomaly_score
+ 25% maintenance_overdue_score
+ 20% unresolved_ticket_score
+ 10% recent_ticket_score
+  7.5% recurring_issue_score
+ 10% criticality_score
+  5% follow_up_score
+  2.5% runtime_score
```

Weights và component thresholds là transparent demo heuristics. Output có Vietnamese contributing factors và recommended action để manager hiểu vì sao asset được xếp hạng.

## Isolation Forest Đóng Góp Gì?

Isolation Forest phát hiện multivariate outliers tương đối trong cùng asset type. Model score đóng góp 30% anomaly score; rule score đóng góp 70%. Trong implementation hiện tại, model không thể tự tạo final anomaly flag nếu không có rule evidence, nên vai trò chính là bổ sung mức độ khác biệt và explanation.

## Vì Sao Kết Hợp Rules Và Machine Learning?

Rules encode các tín hiệu bảo trì dễ giải thích như energy spike, vibration hoặc runtime delta. Isolation Forest có thể nhận ra tổ hợp measurements khác baseline mà một rule đơn lẻ bỏ qua. Kết hợp hai cách giữ explanation rõ cho business user nhưng vẫn minh họa unsupervised ML khi không có labels.

## Vì Sao Dùng RAG Thay Vì Gửi Toàn Bộ Documents Cho ChatGPT?

RAG index documents thành chunks, filter theo metadata và chỉ đưa context liên quan vào answer composer. Cách này giữ source identity, giảm unrelated context, hỗ trợ collection lớn hơn và cho phép fallback khi không có evidence. MVP dùng local embeddings và deterministic composer, không gửi documents đến paid API.

## Làm Sao Ngăn Câu Trả Lời Không Liên Quan?

Asset được chọn cung cấp `asset_type` filter; có thêm optional `document_type` và `failure_category`. Retriever áp dụng relevance threshold `0.55` cho sentence-transformer. Empty, low-relevance, unsupported hoặc unavailable retrieval trả sources rỗng và safe fallback, không compose checklist từ unrelated chunks.

## Người Dùng Có Thể Tin Recommendation Không?

Recommendation có thể dùng để tham khảo và prioritization, không phải mệnh lệnh. Successful RAG answer phải có source, safety notice và giới hạn. Anomaly/risk không chứng minh failure; technician phải xác minh hiện trường, và manual nhà sản xuất cùng quy trình an toàn luôn ưu tiên.

## Vì Sao Dùng PostgreSQL Và Qdrant?

PostgreSQL được giữ như optional/experimental structured-storage adapter và có compatibility tests, nhưng không phục vụ main CSV-first demo. Qdrant là active vector store chỉ cho SOP/checklist retrieval. API health và manager dashboard không phụ thuộc Qdrant.

## Cần Gì Trước Production Deployment?

Cần integration với CMMS/BMS thực, data quality ownership, labeled evaluation, risk calibration, RAG evaluation, scheduler, authentication/RBAC, audit logging, observability, secrets management, backup/recovery, deployment automation, security review và field safety validation. Cũng cần thống nhất SLA và quyền quyết định với đội vận hành.

## Tôi Đã Trực Tiếp Thiết Kế Và Implement Gì?

Tôi thiết kế data contract và deterministic generator; xây feature, anomaly, risk và maintenance analytics; triển khai CSV-backed FastAPI và Streamlit workflows; xây document chunking, Qdrant retrieval, relevance/safety fallback; viết tests, smoke checks và documentation. Các quyết định chính là CSV-first, batch-first, explainable scoring và human-in-the-loop.

## Limitations Cần Nói Thẳng

- Dữ liệu và sáu documents đều synthetic.
- Không có labeled failure/retrieval evaluation dataset.
- Thresholds/weights chưa được hiệu chuẩn trên facility thực.
- API đọc CSV và không có scheduler, auth, audit hoặc observability.
- Copilot composer deterministic và extractive, không phải automatic diagnosis.
- Portfolio MVP không phải production-ready enterprise deployment.

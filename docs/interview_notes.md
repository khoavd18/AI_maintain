# Ghi Chú Phỏng Vấn

## Vì Sao Chọn Bài Toán Bảo Trì?

Bảo trì có business workflow rõ: dữ liệu vận hành, ticket, lịch preventive và tài liệu kỹ thuật phải được tổng hợp để quyết định thiết bị nào cần kiểm tra trước. Bài toán cho phép trình bày data engineering, explainable ML, API, dashboard và RAG trong một flow có human-in-the-loop.

## Project Giải Quyết Vấn Đề Gì?

Project giúp Facility Manager ưu tiên assets cần chú ý và giúp technician tìm SOP/checklist liên quan. Input gồm asset master, hourly readings, tickets, maintenance logs và documents. Output gồm daily features, anomaly results, explainable risk scores, preventive/recurring/KPI reports, dashboard và source-grounded Copilot response.

## Vì Sao Đây Không Phải Full CMMS?

CMMS là enterprise system rộng cho planning/work orders, approvals, inventory, purchasing, vendor, labor/cost và compliance. Project chỉ giữ focused asset/plan/work-order/ticket/log workflow trong PostgreSQL để đóng vòng decision support; nó không có inventory, purchasing, complex approvals, vendor management, notifications hoặc production scheduler và không thay con người quyết định.

## Asset Lifecycle Được Thiết Kế Như Thế Nào?

Asset có rich technical/warranty/location profile và hai state độc lập. `lifecycle_status` mô tả planned/active/inactive/retired/archived; `operational_status` mô tả running/warning/fault/under-maintenance/out-of-service. Service kiểm tra transition, retired/archived chặn ticket mới, còn archive/restore dùng optimistic version và audit thay vì hard delete. Legacy asset API và analytics vẫn nhận compatibility `status`, location leaf và installation date.

Location là adjacency hierarchy có breadcrumb, cycle prevention và archive-in-place. Unified history kết hợp allow-listed audit với imported ticket/log events, de-duplicate và paginate để trace actor/action mà không làm một event store mới.

## Vì Sao Tách Preventive Plan, Work Order, Ticket Và Maintenance Log?

- **PreventiveMaintenancePlan** là recurring intent: làm gì, cho asset nào, theo chu kỳ/timezone nào.
- **WorkOrder** là một executable job cho một due occurrence hoặc corrective ticket.
- **Ticket** là incident/service request và chỉ resolve qua human-authorized action.
- **MaintenanceLog** là durable outcome/history sau khi công việc được thực hiện.

Nếu gộp bốn khái niệm, schedule change có thể sửa history, ticket dễ bị đóng ngầm và khó chứng minh exactly-one maintenance result. Thiết kế hiện tại giữ FK rõ, checklist snapshot, state machine và audit riêng.

## Recurrence Và Generation Có An Toàn Không?

Current subset chỉ có every N day/week/month/year; raw RRULE bị từ chối. Due dates là business dates theo IANA timezone, execution timestamps là UTC. Ngày 29–31 clamp cuối tháng nhưng giữ original anchor; leap-day có test. Expansion max 256 occurrence và catch-up window 366 ngày; paused backlog bị bỏ khi resume.

Generation được gọi explicit qua API/CLI, không chạy lúc startup. Plan row lock, PostgreSQL sequence và unique `(preventive_plan_id, due_date)` làm retry/concurrent calls idempotent. Future scheduler phải gọi cùng service thay vì copy logic.

## Work-Order Completion Khác Verification Thế Nào?

Technician completion yêu cầu assigned ownership, mandatory checklist và không có safety-critical failure; transaction tạo/link đúng một MaintenanceLog. Verification là technical acceptance bởi actor được ủy quyền khác technician. Chỉ verification mới đồng bộ asset maintenance dates. Cả hai action không resolve source ticket và không refresh Risk Score/KPI ngay.

Canonical states: `planned -> assigned -> in_progress -> completed -> verified`, có `on_hold`, cancellation riêng và authorized reopen trước verification. Overdue là phép tính từ due date + grace period, không phải status editable.

## Checklist Versioning Giữ History Như Thế Nào?

Mỗi template dùng `(code, version_number)`; version mới tạo row mới. Khi tạo work order, service copy item sang work-order snapshot. Vì vậy archive hoặc version template sau này không đổi instruction, safety flag hay result của job lịch sử.

## Attachment Và QR Có An Toàn Không?

Attachment bytes không nằm trong PostgreSQL. Storage abstraction dùng local implementation cho pilot: extension + MIME + signature allow-list, size bound, random storage key, atomic write, SHA-256 verify khi download, authenticated endpoint và soft-delete audit. Original filename không bao giờ là path; storage key/path không xuất API/audit. Hạn chế còn lại là chưa có malware scan, S3, reconciler hoặc backup automation.

QR là deterministic opaque UUID lookup URL. Nó không chứa asset ID, user, secret hoặc auth token và không cấp quyền; protected lookup vẫn kiểm tra session/RBAC, archived asset trả `410`. Mobile route là responsive web, không phải native app.

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

## Frontend Chuyển Context Sang Copilot Như Thế Nào?

Overview, asset detail và ticket workspace chỉ truyền stable `asset`/`ticket` IDs trong URL. Copilot page tải record thật từ FastAPI, hiển thị risk, maintenance và ticket facts, rồi chỉ gửi `question`, optional `asset_id`, `top_k` và optional filters được endpoint chấp nhận. Cách này tránh serialize object lớn, tránh contract drift và giữ link có thể mở lại. Lịch sử tối đa tám lượt chỉ tồn tại trong page session, không phải chat database.

Frontend Zod-validate successful response, render answer/source như untrusted text và tách trạng thái API, analytics, RAG. Confirmed low-relevance/unsupported/unavailable response được trình bày như safe fallback; Qdrant failure không biến toàn bộ application thành offline.

## Vì Sao Dùng PostgreSQL Và Qdrant?

PostgreSQL là primary transactional store cho assets, tickets và maintenance logs. Nó cung cấp FK, check constraints, transactions, concurrent-safe ID sequences và optimistic conflicts. CSV vẫn là deterministic seed và batch analytics contract. Qdrant là vector store chỉ cho SOP/checklist retrieval; nó không lưu transactional records và failure của Qdrant không làm manager workflow ngừng hoạt động.

Asset/location/attachment metadata cũng cần PostgreSQL vì lifecycle, hierarchy, unique serial, actor/version và archive history là transactional invariants. Attachment bytes tách ra object-storage boundary vì file body không phù hợp relational row; Qdrant vẫn chỉ xử lý document chunks, không thay asset repository.

## Authentication Và Authorization Được Thiết Kế Thế Nào?

Đây là local/internal-pilot identity, không phải enterprise IAM. Password dùng Argon2id; access JWT sống ngắn và chỉ ở frontend memory; opaque refresh token nằm trong HttpOnly cookie, chỉ hash được lưu trong PostgreSQL và rotate mỗi lần refresh. FastAPI kiểm tra user/session/version cùng permission cho từng request. Role matrix chỉ định nghĩa một lần ở Python và frontend nhận permission codes từ API. Deactivate, đổi role/mật khẩu và logout thu hồi sessions ngay.

Frontend ẩn action để UI rõ hơn nhưng backend mới là security boundary. Technician còn bị resource scope theo `technician_id`; helpdesk chỉ cập nhật field giới hạn. Refresh/logout dùng CSRF binding, CORS/trusted hosts là explicit. Trade-off hiện tại là HS256 chưa có key rotation, rate limiter chỉ một process, chưa có SSO/MFA/recovery và cần HTTPS ngoài local.

## Audit Log Bảo Đảm Điều Gì?

Audit ghi actor, action, resource, request ID, outcome và safe before/after projection. Ticket/log audit commit trong cùng transaction với business write nên nếu audit insert lỗi thì mutation rollback. Table không có write API và PostgreSQL trigger chặn update/delete. Audit không lưu password/token/cookie/raw request và không phải approval workflow. Database administrator vẫn là trust boundary vì chưa có external tamper-evident sink.

## Cần Gì Trước Production Deployment?

Cần integration với CMMS/BMS thực, data quality ownership, labeled evaluation, risk calibration, RAG evaluation, scheduler, SSO/MFA hoặc enterprise IAM integration, distributed throttling, key rotation, centralized audit retention/observability, secrets management, backup/recovery, deployment automation, security review và field safety validation. Cũng cần thống nhất SLA và quyền quyết định với đội vận hành.

## Tôi Đã Trực Tiếp Thiết Kế Và Implement Gì?

Tôi thiết kế data contract và deterministic generator; xây feature, anomaly, risk và maintenance analytics; triển khai Alembic schema, PostgreSQL repositories/transactions, local auth/RBAC, rotating refresh sessions và transaction-coupled immutable audit; bổ sung controlled recurrence, idempotent preventive generation, standalone work-order state machine, checklist snapshots/evidence và independent verification; giữ legacy API/Next.js contracts ổn định; kết nối context tới Qdrant retrieval và viết concurrency/rollback/security tests.

## Limitations Cần Nói Thẳng

- Dữ liệu và sáu documents đều synthetic.
- Không có labeled failure/retrieval evaluation dataset.
- Thresholds/weights chưa được hiệu chuẩn trên facility thực.
- Local auth/audit chưa có SSO, MFA, recovery, distributed throttling, key rotation, external tamper-evident archive hoặc security review.
- Preventive generation đang là explicit API/CLI, chưa có production scheduler/worker, holiday calendar, notifications hoặc missed-run operations.
- Recurrence mới hỗ trợ bounded day/week/month/year; work-order reopen chưa có full maintenance-record amendment/countersign workflow.
- Transactional API chưa có backup automation hoặc centralized observability.
- Attachment storage là local single-node, chưa có malware scanning, S3-compatible backend hoặc file/DB reconciliation worker.
- QR chưa có offline mode, camera/browser compatibility matrix hoặc fleet label operations.
- Copilot composer deterministic và extractive, không phải automatic diagnosis.
- Portfolio MVP không phải production-ready enterprise deployment.

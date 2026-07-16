# Kịch Bản Demo 5–7 Phút

Kịch bản dùng primary CSV-first workflow và dữ liệu synthetic mặc định. PostgreSQL không cần cho demo. Các giá trị expected bên dưới được verify với seed mặc định; nếu thay seed hoặc parameters, hãy dùng giá trị đang hiển thị thay vì đọc thuộc lòng.

## Chuẩn Bị Trước Demo

Windows PowerShell, không cần `make`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,rag,postgres]"

python -m src.data_generation.generate_data
python -m src.ingestion.validation
python -m src.features.build_features
python -m src.models.anomaly_detection
python -m src.risk.risk_scoring
python -m src.features.build_features --analysis preventive
python -m src.features.build_features --analysis recurring
python -m src.features.build_features --analysis kpis

docker compose up -d qdrant
python -m src.rag.index_documents
```

Index lần hai phải vẫn báo 6 documents và 30 chunks:

```powershell
python -m src.rag.index_documents
```

Terminal 1:

```powershell
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

Terminal 2:

```powershell
$env:API_BASE_URL = "http://localhost:8000"
python -m streamlit run src/dashboard/app.py
```

## 0:00–0:45 — Bài Toán Và Phạm Vi

**Click:** mở dashboard, view `Tổng quan`.

**Nói:**

> Đội vận hành phải đối chiếu asset, ticket, lịch bảo trì, readings và SOP. Project này là AI decision-support layer theo batch để ưu tiên thiết bị và tìm checklist liên quan. Nó không thay thế CMMS, không xử lý real-time IoT và không tự quyết định bảo trì.

Chỉ ra dataset đã verify: 27 assets, 77.760 hourly readings, 42 tickets, 86 maintenance logs và ba loại thiết bị HVAC, pump, generator.

## 0:45–1:45 — Overview KPIs

**Click:** KPI cards, preventive/risk distributions và bảng ưu tiên.

**Expected snapshot `2026-04-30`:**

- 42 tickets: 24 resolved, 18 open;
- ticket resolution rate 57,14%;
- 2 assets quá hạn;
- 4 recurring asset/category groups;
- 2 assets ở mức `Cao` hoặc `Khẩn cấp`.

**Nói:** KPI chỉ mô tả synthetic snapshot. Không diễn giải resolution rate thành ROI, SLA hay production performance.

## 1:45–3:20 — GENERATOR_002

**Click:** view `Thiết bị và rủi ro`, chọn `GENERATOR_002`, bấm `Xem chi tiết`.

**Expected facts:**

- asset: `Máy phát điện dự phòng 002`, `Sân thượng phía Đông`;
- latest Risk Score: `63.89`, level `Cao`;
- preventive status: `Quá hạn`, 159 ngày;
- 2 unresolved electrical tickets: một `Mới tạo`, một `Đang xử lý`;
- 1 preventive maintenance log ngày `2025-07-25`;
- recommended action: lên lịch kiểm tra trong tuần, kiểm tra ắc quy, dầu, nước làm mát và chạy thử tải.

**Nói:**

> Risk Score kết hợp anomaly, overdue maintenance, unresolved/recent tickets, recurring issue, criticality, follow-up và runtime. Đây là transparent prioritization score, không phải xác suất failure.

Mở ticket và maintenance history để chứng minh score có trace về business events, không chỉ là model output.

## 3:20–4:30 — Risk-To-Action

**Click:** `Tạo ticket kiểm tra`. Chỉ rõ hai phần:

- facts được prefill từ batch: asset, Risk Level và contributing factors;
- recommendation có thể được manager chỉnh trước khi gán technician.

Tạo ticket, mở `Ticket workspace`, chuyển `Mới tạo -> Đang xử lý`, ghi inspection result/action/result. Nếu result là `Đã xử lý`, resolve ticket sau khi log đã lưu; nếu result cần follow-up, giữ ticket `Đang xử lý`.

**Nói:**

> Dashboard chỉ ghi raw ticket/log CSV qua FastAPI. Risk và KPI không đổi ngay; thông báo trên form nói rõ kết quả sẽ cập nhật ở analytics batch tiếp theo. Đây là local single-user demo, không phải CMMS transaction engine.

Sau demo có write, chạy lại `python -m src.data_generation.generate_data` nếu cần khôi phục synthetic dataset mặc định.

## 4:30–5:00 — Anomaly Context

**Click:** view `Bất thường và lỗi lặp lại`, filter `GENERATOR_002` nếu cần.

**Expected anomaly gần nhất:** ngày `2026-04-21`, score `95.62`, loại `Thời gian vận hành bất thường`; energy tăng 54,7% và runtime tăng 57,8% so với baseline 7 ngày.

**Nói:** rule-based signals tạo explanation; Isolation Forest bổ sung relative outlier evidence. Anomaly không chứng minh thiết bị đã hỏng.

## 5:00–6:15 — RAG Copilot

**Click:** từ asset hoặc ticket, bấm `Mở Copilot checklist`, sau đó mở view `Trợ lý bảo trì`. Dashboard đã prefill asset type, asset ID, ticket category/description và latest risk explanation. Hỏi:

```text
Máy phát điện không khởi động thì cần kiểm tra gì trước?
```

**Expected:**

- `retrieval_status=success`;
- filter `asset_type=Máy phát điện dự phòng`, failure category `Lỗi điện`;
- source `Hướng dẫn kiểm tra máy phát điện không khởi động`, version `1.0`, effective date `2026-01-01`;
- answer tách asset facts, checklist, sources, safety notice và recommendation limits.

**Nói:** Qdrant chỉ retrieve document chunks; deterministic composer không tạo diagnosis. Relevance gate loại unrelated chunks. Technician vẫn phải kiểm tra hiện trường và ưu tiên manual nhà sản xuất cùng quy trình an toàn tòa nhà.

## 6:15–6:40 — Safe Fallback (Optional)

Nếu muốn demo failure handling:

```powershell
docker compose stop qdrant
```

Hỏi lại. Expected: `retrieval_status=unavailable`, không có source/chunk giả và có safe fallback yêu cầu kiểm tra manual hoặc liên hệ kỹ thuật trưởng. `GET /health` và các workflow không phụ thuộc RAG vẫn hoạt động.

Khởi động lại khi cần:

```powershell
docker compose start qdrant
```

## 6:40–7:00 — Kết Luận

**Nói:**

> MVP trình bày một flow coherent từ synthetic data, validation, feature engineering, hybrid anomaly detection, explainable risk, maintenance reports, API/dashboard đến source-grounded RAG. Production vẫn cần real data integration, evaluation, scheduler, auth, audit, observability và deployment hardening.

## Câu Hỏi Interviewer Có Thể Hỏi

- Vì sao rules và Isolation Forest được dùng cùng nhau?
- Risk Score khác failure probability như thế nào?
- Làm sao tránh Copilot retrieve SOP sai loại thiết bị?
- Vì sao Qdrant failure không làm dashboard ngừng hoạt động?
- Nếu có dữ liệu CMMS thực tế, bạn sẽ evaluate anomaly, risk và RAG như thế nào?
- PostgreSQL đang đóng vai trò gì nếu API hiện CSV-backed?

## Dừng Demo

Dừng API và Streamlit bằng `Ctrl+C`, sau đó:

```powershell
docker compose stop qdrant
```

Không dùng `docker compose down -v` trừ khi chủ động muốn xóa local service volumes.

# Kịch Bản Demo Portfolio

Kịch bản này trình bày primary CSV-first workflow. PostgreSQL không cần thiết cho demo chính. Qdrant chỉ cần khi demo Maintenance Copilot.

## 1. Chuẩn Bị Environment

```bash
python -m pip install -e ".[dev,rag]"
```

Giải thích ngắn:

- `dev` cung cấp pytest và Ruff;
- `rag` cung cấp sentence-transformers cho local embeddings;
- không sử dụng paid API.

## 2. Generate Vietnamese Synthetic Data

```bash
make generate-data
```

Mở `data/raw` và giới thiệu:

- asset master;
- hourly sensor readings;
- maintenance tickets và logs;
- Vietnamese SOP/checklist documents.

Nhấn mạnh đây là synthetic batch data, không phải real-time IoT hoặc production data.

## 3. Build Daily Features

```bash
make build-features
```

Mở `data/processed/asset_daily_features.csv` và chỉ ra:

- rolling energy trend;
- temperature/vibration/runtime delta;
- ticket frequency;
- maintenance overdue days;
- criticality score.

Canonical implementation: `src/features/build_features.py`.

## 4. Detect Anomalies

```bash
make detect-anomalies
```

Mở `data/processed/anomaly_results.csv` và giải thích:

- rule-based signals tạo explanation cho known patterns;
- Isolation Forest bổ sung relative outlier score;
- output có Vietnamese `anomaly_type` và `anomaly_reasons`.

Canonical implementation: `src/models/anomaly_detection.py`.

## 5. Score Risk

```bash
make score-risk
```

Mở `data/processed/risk_scores.csv` và trình bày formula:

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

Nói rõ risk score dùng để prioritization; nó không dự đoán exact failure time.

Canonical implementation: `src/risk/risk_scoring.py`.

Tạo các analytics snapshots bổ sung:

```bash
python -m src.features.build_features --analysis preventive
python -m src.features.build_features --analysis recurring
python -m src.features.build_features --analysis kpis
```

Các snapshots này được phục vụ qua manager API và xuất hiện trong các dashboard workflow tương ứng.

## 6. Start Qdrant Và Index Documents

```bash
docker compose up -d qdrant
make index-documents
```

Giải thích RAG path:

```text
documents.csv -> chunks -> local embeddings -> Qdrant -> top-k retrieval
```

Với default source set, command báo 6 documents và 30 chunks. Chạy `make index-documents` lần thứ hai và xác nhận chunk count vẫn là 30: indexer luôn thay thế collection, không append duplicate hoặc giữ stale chunk.

Qdrant không cần cho risk/anomaly dashboard; nó chỉ hỗ trợ Copilot retrieval. Nếu embedding model chưa có trong cache, lần chạy đầu có thể cần tải model miễn phí.

## 7. Run FastAPI

Trong terminal thứ nhất:

```bash
make run-api
```

Mở:

- `http://localhost:8000/health`
- `http://localhost:8000/summary`
- `http://localhost:8000/maintenance/kpis`
- `http://localhost:8000/assets/GENERATOR_002/details`
- `http://localhost:8000/docs`

FastAPI đọc canonical processed CSVs qua service layer.

## 8. Run Streamlit

Trong terminal thứ hai:

```bash
make run-dashboard
```

Mở URL do Streamlit hiển thị. Dashboard gọi FastAPI qua `API_BASE_URL` và không đọc CSV trực tiếp.

## 9. Inspect Top Risky Asset

1. Mở `Tổng quan` và trình bày ticket KPI, overdue assets và distributions.
2. Xem bảng thiết bị cần ưu tiên.
3. Mở `Thiết bị và rủi ro`.
4. Chọn `GENERATOR_002` hoặc asset có Risk Score cao nhất.
5. Trình bày asset profile, preventive status, contributing factors và recommended action.
6. Mở risk history, recent tickets và maintenance logs.
7. Mở `Bất thường và lỗi lặp lại` để phân biệt anomaly signal với recurring ticket group.
8. Nhấn mạnh manager và technician quyết định hành động thực tế.

## 10. Ask Maintenance Copilot

Mở `Trợ lý bảo trì` và hỏi:

```text
Vì sao GENERATOR_002 đang rủi ro cao?
```

Sử dụng:

- `asset_id`: `GENERATOR_002`
- `top_k`: `5`

Trình bày:

- `Facts từ dữ liệu thiết bị`: structured risk/anomaly context;
- `Hướng dẫn được truy xuất`: checklist từ document đủ relevance;
- filter `asset_type=Máy phát điện dự phòng`;
- source `Hướng dẫn kiểm tra máy phát điện không khởi động`, version và effective date;
- safety notice và giới hạn của recommendation.

Ví dụ API tương đương:

```bash
curl -X POST http://localhost:8000/copilot/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Máy phát điện không khởi động thì tham khảo checklist nào?","asset_id":"GENERATOR_002","top_k":5}'
```

Response thành công phải có `retrieval_status=success`, ít nhất một source và các section tình trạng, checklist, nguồn, an toàn, giới hạn.

Nói rõ response dùng deterministic composer, không phải generative LLM. Technician phải kiểm tra hiện trường và SOP chính thức trước khi hành động.

## 11. Minh Họa Safe Fallback

Dừng riêng Qdrant rồi hỏi lại; không cần dừng API hoặc dashboard:

```bash
docker compose stop qdrant
```

Copilot phải hiển thị thông báo thân thiện, không có source/chunk giả và có câu:

```text
Không tìm thấy SOP hoặc checklist đủ liên quan trong kho tài liệu hiện có. Vui lòng kiểm tra tài liệu của nhà sản xuất hoặc liên hệ kỹ thuật trưởng.
```

Các trang manager vẫn sử dụng được và `GET /health` vẫn trả trạng thái của raw/analytics data, không phụ thuộc RAG. Khởi động lại Qdrant trước lần hỏi tiếp theo:

```bash
docker compose start qdrant
```

## 12. Kết Thúc Product Story

AI Maintenance Copilot là:

- một AI decision-support layer;
- batch analytics workflow;
- portfolio MVP tích hợp data engineering, ML scoring, API, dashboard và RAG;
- không phải CMMS replacement hoặc production-ready system.

## Optional PostgreSQL Experiment

Phần này không thuộc main demo. Chỉ chạy khi muốn minh họa SQLAlchemy schema và raw CSV loading:

```bash
docker compose up -d postgres
make init-db
make load-data
```

PostgreSQL path hiện không cấp dữ liệu cho FastAPI, Streamlit hoặc canonical analytics outputs.

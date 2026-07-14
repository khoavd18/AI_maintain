# AI Maintenance Copilot

Nền tảng decision-support cho bảo trì thiết bị, sử dụng Vietnamese synthetic data, batch anomaly detection, explainable risk scoring và RAG retrieval trên SOP/checklist.

> Trạng thái: portfolio MVP đang được hoàn thiện. Repository không được mô tả là production-ready và không thay thế CMMS/S-Maintain.

## Bài Toán

Facility Manager và technician thường phải tổng hợp thủ công thông tin từ asset register, ticket, maintenance log, operational readings và tài liệu hướng dẫn. AI Maintenance Copilot tạo một luồng thống nhất để:

- nhận diện asset có tín hiệu bất thường;
- xếp hạng thiết bị theo explainable risk score;
- giải thích nguyên nhân và hành động tham khảo bằng tiếng Việt;
- tìm SOP/checklist phù hợp và hiển thị nguồn cho technician.

Hệ thống là lớp hỗ trợ quyết định. Manager và technician chịu trách nhiệm xác minh dữ liệu, đánh giá điều kiện an toàn và đưa ra quyết định cuối cùng.

## Revised MVP Scope

MVP tập trung vào:

- thông tin asset cơ bản;
- ticket và maintenance history;
- preventive maintenance tracking;
- operational data theo batch;
- anomaly detection và risk prioritization;
- recurring issue analysis và maintenance KPI ở mức mô tả;
- RAG retrieval cho SOP/checklist.

Synthetic data foundation hiện tập trung vào 27 assets thuộc HVAC, pump và generator, với 120 ngày operational readings theo giờ.

Không thuộc phạm vi:

- spare-parts inventory;
- QR code;
- resident hoặc technician mobile app;
- vendor/contract management;
- complex approval workflow;
- real-time IoT streaming;
- enterprise authentication/authorization;
- automatic production work-order creation;
- exact failure-time prediction.

Chi tiết và tiêu chí thành công: [docs/mvp_scope.md](docs/mvp_scope.md).

## Current Features Và Future Work

Đã có implementation:

- deterministic Vietnamese synthetic data;
- CSV validation;
- daily asset-level feature engineering;
- rule-based signals kết hợp Isolation Forest scoring;
- explainable risk scoring và top risky assets;
- preventive maintenance status, recurring issue và maintenance KPI snapshots;
- CSV-backed FastAPI cho asset, ticket, maintenance, analytics và Copilot context;
- Streamlit manager dashboard với bốn workflow views;
- Qdrant-based SOP/checklist retrieval với metadata filters và relevance gate;
- deterministic Maintenance Copilot response có sources, safety notice và safe fallback.

Các production concerns như scheduler, authentication, audit logging, observability và deployment hardening không thuộc portfolio MVP hiện tại.

## Canonical Architecture

Primary architecture là **CSV-first** và **batch-first**.

```mermaid
flowchart LR
    Raw[Raw Vietnamese CSVs] --> Validation[CSV validation]
    Validation --> Features[Daily features<br/>src/features/build_features.py]
    Features --> Anomaly[Batch anomalies<br/>src/models/anomaly_detection.py]
    Anomaly --> Risk[Explainable risk<br/>src/risk/risk_scoring.py]
    Risk --> Processed[Processed CSVs]
    Processed --> API[FastAPI]
    API --> Dashboard[Streamlit]

    Docs[documents.csv] --> RAG[RAG indexing/retrieval]
    RAG --> Qdrant[(Qdrant)]
    Qdrant --> API

    Validation -. optional .-> Postgres[(PostgreSQL<br/>experimental)]
```

Canonical analytics implementations:

| Stage | Module | Output |
|---|---|---|
| Feature engineering | `src/features/build_features.py` | `data/processed/asset_daily_features.csv` |
| Anomaly detection | `src/models/anomaly_detection.py` | `data/processed/anomaly_results.csv` |
| Risk scoring | `src/risk/risk_scoring.py` | `data/processed/risk_scores.csv` |

FastAPI đọc processed CSV qua service layer. Streamlit gọi FastAPI và không đọc CSV trực tiếp.

PostgreSQL được giữ như optional/experimental structured-storage path. Nó không cần thiết để chạy main data pipeline, API, dashboard hoặc non-RAG pages. Xem [docs/architecture.md](docs/architecture.md).

## End-to-End User Story

1. Manager mở dashboard và xem maintenance risk summary.
2. Manager chọn top risky asset.
3. Hệ thống hiển thị risk reasons, recent anomalies và recommended action.
4. Technician kiểm tra thiết bị theo quy định an toàn và tham khảo SOP/checklist từ Copilot.
5. Technician ghi nhận action và maintenance result trong hệ thống nguồn.
6. Batch pipeline tiếp theo cập nhật features, anomalies và risk ranking.

Quy trình nghiệp vụ chi tiết: [docs/business_process.md](docs/business_process.md).

## Data Sources

Raw synthetic CSVs:

- `data/raw/assets.csv`
- `data/raw/sensor_readings.csv`
- `data/raw/maintenance_tickets.csv`
- `data/raw/maintenance_logs.csv`
- `data/raw/documents.csv`

Canonical processed outputs:

- `data/processed/asset_daily_features.csv`
- `data/processed/anomaly_results.csv`
- `data/processed/risk_scores.csv`
- `data/processed/preventive_maintenance_status.csv`
- `data/processed/recurring_issues.csv`
- `data/processed/maintenance_kpis.csv`

Default generation tạo 27 assets và 120 ngày hourly readings. Generator không tạo raw risk result hoặc raw anomaly label; analytics output chỉ được tạo bởi canonical processed pipelines. Đây là synthetic demo data, không phải production dataset hoặc bằng chứng model accuracy.

Minimum field definitions: [docs/data_contract.md](docs/data_contract.md).

## Vietnamese Data Design

Code, module, column và API field dùng tiếng Anh. Business values và nội dung hiển thị cho user dùng tiếng Việt.

Ví dụ:

- `asset_type`: `Máy lạnh`, `Máy bơm nước`, `Máy phát điện dự phòng`;
- `priority`: `Thấp`, `Trung bình`, `Cao`, `Khẩn cấp`;
- `risk_level`: `Thấp`, `Trung bình`, `Cao`, `Khẩn cấp`;
- `anomaly_type`: `Tăng điện năng bất thường`, `Độ rung tăng bất thường`.

## Feature Engineering

`src/features/build_features.py` tổng hợp daily asset-level features:

- energy, temperature, vibration và runtime aggregates;
- rolling 7-day baselines và delta signals;
- days since maintenance và days overdue;
- ticket counts trong 7/30 ngày;
- high-priority ticket counts;
- point-in-time unresolved ticket, recurring category và maintenance follow-up counts;
- asset age và criticality score.

Raw readings không còn chứa `pressure`. Feature pipeline tạm phát sinh `pressure = 0.0` để giữ compatibility với downstream anomaly/API contracts; đây không phải measurement mới.

## Anomaly Detection

`src/models/anomaly_detection.py` là implementation canonical. Nó kết hợp:

- rule-based signals để giải thích các pattern đã biết;
- Isolation Forest để bổ sung relative outlier score trong cùng asset type.

```text
anomaly_score = 70% rule_based_score + 30% isolation_forest_score
```

Trong implementation hiện tại, rule signals có vai trò chính trong quyết định `is_anomaly`; Isolation Forest chủ yếu điều chỉnh score và explanation. Đây là batch retrospective scoring, không phải real-time alerting.

Final flag dùng combined score threshold 60. Vì Isolation Forest chỉ đóng góp tối đa 30 điểm, nó không thể tự tạo final flag khi không có rule signal. Output bổ sung `anomalous_metrics` và Vietnamese contributing signals.

## Risk Scoring

`src/risk/risk_scoring.py` là implementation canonical.

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

Risk levels:

- `0-30`: `Thấp`
- `31-60`: `Trung bình`
- `61-80`: `Cao`
- `81-100`: `Khẩn cấp`

Risk score là heuristic prioritization score. Nó không phải calibrated failure probability và không dự đoán exact failure time.

Formula, component thresholds, preventive status, recurrence và KPI definitions: [docs/analytics.md](docs/analytics.md).

## FastAPI Contract

Existing endpoints được giữ nguyên:

- `GET /health`
- `GET /summary`
- `GET /assets/risk`
- `GET /assets/risk/top`
- `GET /assets/risk/{asset_id}`
- `GET /assets/anomalies`
- `GET /assets/anomalies/{asset_id}`
- `GET /assets/{asset_id}/context`
- `POST /copilot/ask`

Manager workflow endpoints:

- `GET /assets`
- `GET /assets/{asset_id}`
- `GET /assets/{asset_id}/details`
- `GET /maintenance/preventive`
- `GET /maintenance/recurring-issues`
- `GET /maintenance/kpis`
- `GET /tickets`
- `GET /maintenance/logs`

Các list endpoint hỗ trợ filters theo data contract. `/assets/{asset_id}/details` gom asset profile, latest risk, preventive status, risk history, anomaly, ticket, log và recurring issues mà không thay đổi RAG logic.

Ví dụ:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/summary
curl "http://localhost:8000/assets/risk/top?limit=5"
curl http://localhost:8000/assets/GENERATOR_002/details
curl "http://localhost:8000/maintenance/preventive?maintenance_status=overdue"
curl "http://localhost:8000/maintenance/recurring-issues?recurrence_flag=true"
curl http://localhost:8000/maintenance/kpis
```

Copilot request:

```bash
curl -X POST http://localhost:8000/copilot/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Vì sao GENERATOR_002 đang rủi ro cao?","asset_id":"GENERATOR_002","top_k":5}'
```

Request giữ `question`, optional `asset_id` và `top_k`; có thể thêm optional `document_type` hoặc `failure_category`. Response vẫn giữ `answer`, `asset_context`, `sources`, `retrieved_chunks` và bổ sung `retrieval_status`, `relevance_status`, `safety_notice`, `filters_applied`.

## Streamlit Dashboard

Current dashboard views:

- `Tổng quan`: KPI, ticket/risk/preventive distributions và top priorities;
- `Thiết bị và rủi ro`: asset filters, consolidated details, risk history, tickets và logs;
- `Bất thường và lỗi lặp lại`: anomaly signals và deterministic recurring groups;
- `Trợ lý bảo trì`: existing Copilot retrieval, sources và technician disclaimer.

Dashboard lấy dữ liệu qua `API_BASE_URL`, mặc định `http://localhost:8000`.

## RAG Maintenance Copilot

Current RAG workflow:

1. Đọc `data/raw/documents.csv`.
2. Chuẩn hóa legacy CSV fields thành `document_id`, `document_type`, `content`, `failure_category`, `version` và `effective_date`.
3. Chunk nội dung theo section marker và giữ đầy đủ source metadata cùng `chunk_index`.
4. Tạo local sentence-transformers embeddings với E5-style prefixes.
5. Thay thế toàn bộ Qdrant collection `maintenance_knowledge` và upsert stable chunk IDs.
6. Retrieve top-k chunks với `asset_type` filter; `document_type` và `failure_category` là optional filters.
7. Loại chunk dưới relevance threshold và chỉ compose answer khi còn nguồn đủ liên quan.
8. Kết hợp retrieved guidance với structured asset facts từ CSV-backed service.
9. Tạo deterministic Vietnamese response với năm phần: tình trạng, checklist, nguồn, an toàn và giới hạn.

Document coverage hiện tại:

| Asset type | Preventive document | Troubleshooting document |
|---|---|---|
| HVAC | Checklist kiểm tra định kỳ máy lạnh | Máy lạnh không làm mát |
| Pump | Checklist kiểm tra định kỳ máy bơm | Rung hoặc tiếng ồn bất thường |
| Generator | Checklist kiểm tra định kỳ máy phát | Không khởi động |

Default source set có 6 documents và tạo 30 chunks với cấu hình `max_chars=800`, `overlap=80`. `make index-documents` luôn rebuild collection, vì vậy chạy lại cùng input không tạo duplicate và tài liệu bị xóa/đổi không để stale chunk active.

Relevance threshold là retrieval gate, không phải xác suất đúng:

- deterministic `HashEmbeddingProvider` trong unit tests: `0.15`;
- local `SentenceTransformerEmbeddingProvider`: `0.55`.

Khi kết quả rỗng, dưới threshold, câu hỏi ngoài phạm vi hoặc Qdrant unavailable, Copilot trả safe fallback và không tạo checklist từ unrelated chunks. API health và ba dashboard workflow còn lại không phụ thuộc Qdrant.

Copilot không sử dụng paid API và hiện không có generative LLM. Đây không phải automatic diagnostic system. Anomaly/Risk Score không chứng minh failure; manager/technician phải xác minh thiết bị và ưu tiên manual nhà sản xuất cùng quy trình an toàn tòa nhà.

Ví dụ câu hỏi trong phạm vi:

- `Thiết bị này cần kiểm tra gì trước?` khi đã chọn asset;
- `Máy bơm rung bất thường thì kiểm tra những bước nào?`;
- `Máy phát điện không khởi động thì tham khảo checklist nào?`;
- `SOP bảo trì định kỳ cho HVAC là gì?`.

## Setup

Yêu cầu: Python 3.11+.

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,rag]"
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,rag]"
```

## Main Portfolio Demo

### 1. Chạy CSV Batch Pipeline

PostgreSQL không cần cho các command này:

```bash
make generate-data
make build-features
make detect-anomalies
make score-risk
python -m src.features.build_features --analysis preventive
python -m src.features.build_features --analysis recurring
python -m src.features.build_features --analysis kpis
```

### 2. Khởi Động Qdrant Và Index Documents

Qdrant chỉ cần cho Maintenance Copilot:

```bash
docker compose up -d qdrant
make index-documents
```

Index command báo `document_count`, `chunk_count`, collection, embedding implementation và vector dimensions. Chạy lại command là cách canonical để đồng bộ document set.

### 3. Chạy FastAPI

```bash
make run-api
```

Mở `http://localhost:8000/docs`.

### 4. Chạy Streamlit

Trong terminal thứ hai:

```bash
make run-dashboard
```

### 5. Demo Copilot

```bash
make rag-query QUESTION="Vì sao GENERATOR_002 đang rủi ro cao?" ASSET_ID=GENERATOR_002
```

Demo walkthrough đầy đủ: [docs/demo_script.md](docs/demo_script.md).

## Optional PostgreSQL Experiment

PostgreSQL không nằm trong primary runtime path. Chỉ chạy các bước sau khi muốn thử SQLAlchemy schema và raw CSV loading:

```bash
docker compose up -d postgres
make init-db
make load-data
```

Database path hiện không cấp dữ liệu cho FastAPI hoặc Streamlit.

## Verification

```bash
python -m pytest
python -m ruff check .
```

Test suite bao phủ data generation, validation, optional database loading, feature engineering, anomaly detection, risk scoring, API, dashboard client helpers và RAG components. Test hiện tại chưa chứng minh production readiness, model accuracy hoặc end-to-end live Qdrant/PostgreSQL behavior.

## Limitations

- Synthetic data chưa được kiểm chứng bằng maintenance history thực tế.
- Analytics thresholds và risk weights là transparent demo heuristics, chưa được hiệu chuẩn trên dữ liệu thực tế.
- Synthetic chronology chỉ mô phỏng quy trình đơn giản và chưa được đối chiếu với quy tắc lịch bảo trì thực tế của một cơ sở cụ thể.
- API hiện phục vụ processed CSV, không có scheduler hoặc cache invalidation strategy cho production.
- Isolation Forest và risk formula chưa được đánh giá trên labeled failure outcomes.
- Copilot có relevance threshold minh bạch nhưng chưa có labeled retrieval evaluation dataset hoặc hiệu chuẩn trên tài liệu thực tế.
- Sáu SOP/checklist là synthetic/illustrative và không thay thế tài liệu nhà sản xuất.
- Deterministic composer là extractive decision support, không phải diagnosis hoặc generative reasoning.
- Dashboard là manager-facing portfolio workflow, chưa có production caching, accessibility audit hoặc browser-level regression suite.
- Không có production auth, audit logging, observability hoặc deployment hardening.

## Legacy Modules

Repository tạm thời giữ các duplicate/compatibility modules để tránh xóa code trước cleanup milestone. Không mở rộng các module sau:

- `src/models/anomaly.py`
- `src/risk/scoring.py`
- `src/ingestion/documents.py`
- `src/ingestion/tickets.py`
- `src/data_generation/sample_data.py`
- root `app.py`

Danh sách đầy đủ và canonical replacement nằm trong [docs/architecture.md](docs/architecture.md).

## Repository Layout

```text
src/config/           Settings và Vietnamese value mappings
src/data_generation/  Synthetic maintenance data
src/ingestion/        CSV validation; optional database loading
src/database/         Optional/experimental SQLAlchemy path
src/features/         Canonical daily feature pipeline
src/models/           Canonical anomaly pipeline và legacy wrapper
src/risk/             Canonical risk pipeline và legacy helper
src/rag/              Document retrieval và Copilot composition
src/api/              CSV-backed FastAPI
src/dashboard/        Streamlit app và API client
tests/                Automated tests
docs/                 Scope, architecture, process, contracts và demo docs
```

## Supporting Documentation

- [MVP scope](docs/mvp_scope.md)
- [Business process](docs/business_process.md)
- [Data contract](docs/data_contract.md)
- [Canonical architecture](docs/architecture.md)
- [Analytics pipeline](docs/analytics.md)
- [Demo script](docs/demo_script.md)
- [Interview notes](docs/interview_notes.md)
- [Troubleshooting](docs/troubleshooting.md)
- [CV bullets](docs/cv_bullets.md)

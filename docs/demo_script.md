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
  35% anomaly_score
+ 20% maintenance_overdue_score
+ 20% recent_ticket_score
+ 15% criticality_score
+ 10% runtime_score
```

Nói rõ risk score dùng để prioritization; nó không dự đoán exact failure time.

Canonical implementation: `src/risk/risk_scoring.py`.

## 6. Start Qdrant Và Index Documents

```bash
docker compose up -d qdrant
make index-documents
```

Giải thích RAG path:

```text
documents.csv -> chunks -> local embeddings -> Qdrant -> top-k retrieval
```

Qdrant không cần cho risk/anomaly dashboard; nó chỉ hỗ trợ Copilot retrieval.

## 7. Run FastAPI

Trong terminal thứ nhất:

```bash
make run-api
```

Mở:

- `http://localhost:8000/health`
- `http://localhost:8000/summary`
- `http://localhost:8000/docs`

FastAPI đọc canonical processed CSVs qua service layer.

## 8. Run Streamlit

Trong terminal thứ hai:

```bash
make run-dashboard
```

Mở URL do Streamlit hiển thị. Dashboard gọi FastAPI qua `API_BASE_URL` và không đọc CSV trực tiếp.

## 9. Inspect Top Risky Asset

1. Mở `Overview`.
2. Xem summary metrics và `Top 10 Risky Assets`.
3. Mở `Asset Risk Monitoring`.
4. Chọn một asset có risk score cao.
5. Trình bày `main_reasons` và `recommended_action`.
6. Nhấn mạnh manager quyết định mức ưu tiên thực tế.

## 10. Ask Maintenance Copilot

Mở `Maintenance Copilot` và hỏi:

```text
Vì sao GENERATOR_002 đang rủi ro cao?
```

Sử dụng:

- `asset_id`: `GENERATOR_002`
- `top_k`: `5`

Trình bày:

- structured risk/anomaly context;
- Vietnamese response;
- SOP/checklist sources;
- retrieved chunks.

Nói rõ response hiện dùng deterministic composer, không phải generative LLM. Technician phải kiểm tra hiện trường và SOP chính thức trước khi hành động.

## 11. Kết Thúc Product Story

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

# Xử Lý Sự Cố

## Qdrant Không Chạy Hoặc Không Kết Nối Được

Dấu hiệu:

- `make index-documents` báo lỗi kết nối Qdrant.
- Copilot trả `retrieval_status=unavailable` và không có sources.
- Dashboard hiển thị safe fallback nhưng các trang manager vẫn hoạt động.

Cách xử lý:

```bash
docker compose up -d qdrant
```

Kiểm tra Qdrant:

```bash
curl http://localhost:6333
```

Không cần khởi động PostgreSQL. `GET /health` chỉ phản ánh raw/analytics availability và không phụ thuộc Qdrant.

## Collection Thiếu Hoặc Trống

Dấu hiệu:

- Copilot trả fallback vì collection chưa tồn tại hoặc không có active chunks.
- Qdrant đang chạy nhưng `sources` và `retrieved_chunks` rỗng.

Cách xử lý:

```bash
make index-documents
```

Default indexing report phải cho biết 6 documents, 30 chunks, collection `maintenance_knowledge`, embedding implementation và vector dimensions. Indexer luôn rebuild collection; chạy lại không tạo duplicate.

## Vector Dimension Không Khớp

Dấu hiệu:

- Copilot yêu cầu index lại kho tài liệu sau khi đổi embedding model.
- Index/search từ chối collection có vector size khác provider hiện tại.

Cách xử lý:

```bash
make index-documents
```

Không sửa vector size trực tiếp. Full rebuild là synchronization path canonical của MVP.

## sentence-transformers Chưa Được Cài Đặt

Dấu hiệu:

- `make index-documents` báo chưa cài `sentence-transformers`.
- `make rag-query` hoặc `/copilot/ask` không khởi tạo được embedding provider.

Cách xử lý:

```bash
python -m pip install -e ".[dev,rag]"
```

Default model là `intfloat/multilingual-e5-small`. Lần chạy đầu có thể tải model miễn phí. Unit tests dùng deterministic hash embeddings và không cần model download.

## Copilot Trả Safe Fallback

Dấu hiệu:

- `retrieval_status` là `empty`, `low_relevance`, `unrelated`, `unsupported_asset_type` hoặc `missing_asset_context`.
- Response không có sources và không tạo checklist chi tiết.

Cách xử lý:

- Chọn asset thuộc HVAC, pump hoặc generator.
- Đặt câu hỏi bảo trì cụ thể, ví dụ `Máy bơm rung bất thường thì kiểm tra những bước nào?`.
- Xác nhận `asset_type`, `document_type` và `failure_category` filters phù hợp.
- Chạy lại `make index-documents` nếu source documents vừa thay đổi.

Hỏi lại:

```bash
make rag-query QUESTION="Vì sao GENERATOR_002 đang rủi ro cao?" ASSET_ID=GENERATOR_002
```

Không hạ relevance threshold chỉ để buộc Copilot trả lời. Threshold `0.55` của sentence-transformer là safety gate MVP, chưa phải calibrated probability.

## Dashboard Không Kết Nối Được API

Dấu hiệu:

- Streamlit báo không kết nối được FastAPI.
- Các trang dashboard không tải được dữ liệu.

Cách xử lý:

Khởi động API trong terminal thứ nhất:

```bash
make run-api
```

Khởi động dashboard trong terminal thứ hai:

```bash
make run-dashboard
```

Nếu API dùng host hoặc port khác, cấu hình `API_BASE_URL`:

```bash
API_BASE_URL=http://localhost:8000 make run-dashboard
```

Windows PowerShell:

```powershell
$env:API_BASE_URL = "http://localhost:8000"
make run-dashboard
```

## Thiếu Processed CSV

Dấu hiệu:

- `/summary` báo thiếu hoặc stale processed data.
- Bảng risk/anomaly trống do thiếu file.

Cách xử lý:

Chạy lại pipeline:

```bash
make generate-data
make build-features
make detect-anomalies
make score-risk
```

Outputs cần có:

- `data/processed/asset_daily_features.csv`
- `data/processed/anomaly_results.csv`
- `data/processed/risk_scores.csv`

## Optional Database Load Bị Lỗi

Dấu hiệu:

- `make load-data` cannot connect to PostgreSQL.
- Database connection errors mention localhost port `5432`.

Cách xử lý:

```bash
make services-up
make init-db
make load-data
```

Để thử optional database path không cần PostgreSQL, scripts hỗ trợ SQLite URL:

```bash
python -m src.database.init_db --database-url sqlite:///maintenance_demo.db --drop-existing
python -m src.ingestion.load_data --database-url sqlite:///maintenance_demo.db --replace
```

## Chạy Lại Toàn Bộ Primary CSV Pipeline

Dùng khi raw hoặc processed files bị stale:

```bash
make generate-data
make build-features
make detect-anomalies
make score-risk
docker compose up -d qdrant
make index-documents
```

PostgreSQL là optional và không cần cho primary pipeline. Để thử experimental database path riêng:

```bash
docker compose up -d postgres
make init-db
make load-data
```

Sau đó chạy ứng dụng:

```bash
make run-api
make run-dashboard
```

## Ruff Hoặc Pytest Bị Lỗi

Chạy:

```bash
make lint
make test
```

Nếu lỗi liên quan optional RAG dependencies, cài:

```bash
python -m pip install -e ".[dev,rag]"
```

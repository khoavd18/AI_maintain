# Xử Lý Sự Cố

## Qdrant Không Chạy Hoặc Không Kết Nối Được

Dấu hiệu:

- `python -m src.rag.index_documents` báo lỗi kết nối Qdrant.
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
python -m src.rag.index_documents
```

Default indexing report phải cho biết 6 documents, 30 chunks, collection `maintenance_knowledge`, embedding implementation và vector dimensions. Indexer luôn rebuild collection; chạy lại không tạo duplicate.

## Vector Dimension Không Khớp

Dấu hiệu:

- Copilot yêu cầu index lại kho tài liệu sau khi đổi embedding model.
- Index/search từ chối collection có vector size khác provider hiện tại.

Cách xử lý:

```bash
python -m src.rag.index_documents
```

Không sửa vector size trực tiếp. Full rebuild là synchronization path canonical của MVP.

## sentence-transformers Chưa Được Cài Đặt

Dấu hiệu:

- `python -m src.rag.index_documents` báo chưa cài `sentence-transformers`.
- `python -m src.rag.query` hoặc `/copilot/ask` không khởi tạo được embedding provider.

Cách xử lý:

```bash
python -m pip install -e ".[dev,rag,postgres]"
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
- Chạy lại `python -m src.rag.index_documents` nếu source documents vừa thay đổi.

Hỏi lại:

```bash
python -m src.rag.query "Vì sao GENERATOR_002 đang rủi ro cao?" --asset-id GENERATOR_002
```

Không hạ relevance threshold chỉ để buộc Copilot trả lời. Threshold `0.55` của sentence-transformer là safety gate MVP, chưa phải calibrated probability.

## Dashboard Không Kết Nối Được API

Dấu hiệu:

- Streamlit báo không kết nối được FastAPI.
- Các trang dashboard không tải được dữ liệu.

Cách xử lý:

Khởi động API trong terminal thứ nhất:

```bash
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

Khởi động dashboard trong terminal thứ hai:

```bash
python -m streamlit run src/dashboard/app.py
```

Nếu API dùng host hoặc port khác, cấu hình `API_BASE_URL` trong PowerShell:

```powershell
$env:API_BASE_URL = "http://localhost:8000"
python -m streamlit run src/dashboard/app.py
```

## Thiếu Processed CSV

Dấu hiệu:

- `/summary` báo thiếu hoặc stale processed data.
- Bảng risk/anomaly trống do thiếu file.

Cách xử lý:

Chạy lại pipeline:

```bash
python -m src.data_generation.generate_data
python -m src.ingestion.validation
python -m src.features.build_features
python -m src.models.anomaly_detection
python -m src.risk.risk_scoring
python -m src.features.build_features --analysis maintenance
```

Outputs cần có:

- `data/processed/asset_daily_features.csv`
- `data/processed/anomaly_results.csv`
- `data/processed/risk_scores.csv`

## Optional Database Load Bị Lỗi

Dấu hiệu:

- `python -m src.ingestion.load_data --replace` không kết nối được PostgreSQL.
- Lỗi database connection nhắc đến localhost port `5432`.

Cách xử lý:

```bash
docker compose up -d postgres
python -m src.database.init_db
python -m src.ingestion.load_data --replace
```

Để thử optional database path không cần PostgreSQL, scripts hỗ trợ SQLite URL:

```bash
python -m src.database.init_db --database-url sqlite:///maintenance_demo.db --drop-existing
python -m src.ingestion.load_data --database-url sqlite:///maintenance_demo.db --replace
```

## Chạy Lại Toàn Bộ Primary CSV Pipeline

Dùng khi raw hoặc processed files bị stale:

```bash
python -m src.data_generation.generate_data
python -m src.ingestion.validation
python -m src.features.build_features
python -m src.models.anomaly_detection
python -m src.risk.risk_scoring
python -m src.features.build_features --analysis maintenance
docker compose up -d qdrant
python -m src.rag.index_documents
```

PostgreSQL là optional và không cần cho primary pipeline. Để thử experimental database path riêng:

```bash
docker compose up -d postgres
python -m src.database.init_db
python -m src.ingestion.load_data --replace
```

Sau đó chạy ứng dụng:

```bash
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
python -m streamlit run src/dashboard/app.py
```

## Ruff Hoặc Pytest Bị Lỗi

Chạy:

```bash
python -m ruff check .
python -m pytest
```

Nếu lỗi liên quan optional RAG dependencies, cài:

```bash
python -m pip install -e ".[dev,rag,postgres]"
```

## Warnings Đã Review

### Starlette/httpx Trong Test Suite

Cause: Starlette `1.3.x` ưu tiên package `httpx2`; khi package này chưa được cài, `fastapi.testclient` fallback sang `httpx` và phát `StarletteDeprecationWarning`.

Impact: warning chỉ xuất hiện khi import test client; không ảnh hưởng FastAPI runtime, API contract hoặc dashboard. Milestone 6 không thêm `httpx2` chỉ để làm sạch một warning test-only.

Future resolution: đánh giá `httpx2` khi FastAPI/Starlette dependency path ổn định, hoặc migrate test transport trong một dependency-upgrade task riêng.

### Qdrant Client/Server Version

Cause cũ: dependency range `<2.0` cài Qdrant client `1.18.x` trong khi Docker server là `1.10.1`.

Resolution: `pyproject.toml` pin client vào `>=1.10,<1.11`, cùng minor line với Docker image. Nếu virtual environment cũ vẫn báo warning, chạy:

```powershell
python -m pip install -e ".[dev,rag,postgres]" --upgrade
```

Không upgrade Qdrant server hoặc toàn bộ dependency tree chỉ để xóa warning.

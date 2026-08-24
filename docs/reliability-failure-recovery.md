# Stage 10 — Reliability and Failure Recovery

## Kịch bản đã chạy

| Run ID | Kết quả | Tasks | Retries | Watermark |
|---|---|---:|---:|---|
| `stage10_baseline_20260824T103700Z` | success | 19/19 | 0 | six domains → version 1 |
| `stage10_incremental_fault_20260824T105500Z` | success after recovery | 19/19 | 3 | version 1 → 2 đúng một lần |
| `stage10_empty_20260824T110200Z` | success | 19/19 | 0 | giữ version 2 |

## Fault có chủ đích

Fault injection chỉ dành cho isolated scale environment và được chọn bằng domain
explicit. Nó xảy ra sau khi batch `ticket_events` đã commit vào raw nhưng trước
atomic final watermark transaction.

Quan sát tại thời điểm fault:

- 9.000 late ticket events đã có raw batch identity/checksum bền vững;
- watermark của cả sáu domain vẫn ở version 1;
- pipeline audit ghi failed step `load_raw_ticket_events`;
- retry cùng batch không tạo raw duplicate; attempt thành công ghi
  `inserted_count=0` cho batch đã commit;
- final reconciliation khớp 900.000 ticket events và mọi domain khác;
- watermark transaction sau cùng advance cả sáu domain đúng một lần đến version 2.

Task `load_raw_ticket_events` thành công ở try 3. Một marker fault bền vững theo
batch ngăn cùng fault bị inject lại sau process retry.

## Sự cố phụ được phục hồi

Trong lần chạy fault đầu tiên, các extractor song song dùng chung temporary
directory. Status extraction attempt 1 bị race trước khi tạo object. Không có
object checksum/raw row/watermark nào được commit từ attempt đó.

Fix dùng temporary directory riêng theo domain. Status extraction thành công ở
attempt 2. Fault task đã retry trước khi persistent marker fix có hiệu lực và hết
attempt 2; task được clear bằng supported Airflow task API, không sửa metadata SQL.
Attempt 3 sau đó thành công và raw insert bằng 0 như mong đợi.

Đây là hai failure khác nhau và được ghi riêng; temp-directory race không được mô
tả như fault injection có chủ đích.

## Bằng chứng idempotency

Incremental final counts:

- statuses `3.300.000`;
- tickets `300.000`, events `900.000`;
- parts `25.000`;
- movements `1.500.000`;
- costs `1.100.000`;
- work orders vẫn `1.100.000`.

Empty run ngay sau đó có extracted/inserted count bằng 0 ở cả sáu domain, 0
retries, 19/19 tasks success và không đổi counts/watermarks. Raw unique,
staging/fact và tám integrity checks tiếp tục reconcile.

## Transaction boundary

Mỗi extractor tạo immutable batch ID/object key và SHA-256. Raw COPY dùng
idempotent key; object mismatch fail closed. Watermarks không được advance trong
từng loader. Chỉ task finalization, sau dbt tests và reconciliation, kiểm tra
expected version rồi update toàn bộ non-empty domain watermarks trong một
transaction.

Vì vậy một domain raw commit sớm không thể bị báo nhầm là complete run; audit giữ
trạng thái chưa hoàn tất cho đến terminal gate.

## Không dùng để test recovery

Run không kill PostgreSQL, không corrupt/delete volume, không truncate, không
reset watermark, không dùng `docker system prune` và không sửa Airflow metadata
bằng SQL. Không AWS/LLM/embedding call nào được thực hiện.

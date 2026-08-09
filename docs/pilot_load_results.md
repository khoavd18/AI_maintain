# PM9 Soak, Mutation And Capacity Results

## Current Result

Không có PM9 host workload nào đã chạy. Không có soak result, mutation result,
first observed degradation point hay capacity result để công bố.

```text
Engineering readiness: PASS
Local rehearsal: PARTIAL
Real-company pilot: BLOCKED — EXTERNAL DEPENDENCY
Overall: NO-GO / WAITING FOR PILOT SPONSOR
```

Workstation hiện tại không được xác nhận là pilot host và chỉ còn khoảng
0,92 GiB memory khả dụng tại lúc inspection. Vì vậy 900-second soak và opt-in
step load không được chạy trong phiên này.

The unexecuted profiles keep the local rehearsal gate `PARTIAL`; they do not
negate engineering readiness and cannot be replaced with fabricated demand or
results. Execution belongs to
[Pilot 01 — Company-Specific Deployment](pilot_01_company_specific_deployment.md)
after a sponsor approves the host, users, data, and drill authorization.

## Evidence Classification

| Evidence | Trạng thái | Được phép kết luận |
|---|---|---|
| PM8 stress: 8 authenticated users, 12 req/s, 45 giây, read-heavy, không có unexpected error | Historical PM8 checkpoint | Điểm cao nhất đã test trên PM8 workstation/profile |
| PM8 baseline và stress chi tiết | Historical; xem [PM8 release note](releases/product_milestone_8.md) | Không phải PM9 result, capacity limit hay SLA |
| PM9 harness safety/redaction/metric tests | Executed locally bằng deterministic fixtures/test doubles | Tooling tính metric và dừng an toàn theo test |
| PM9 4-user/3 req/s/900-second soak | Chưa chạy | Gate mở |
| PM9 mutation-bearing workload | Chưa chạy | Gate mở |
| PM9 4→20 req/s capacity steps | Chưa chạy | Chưa có degradation point |
| Pilot-host resource trend, pool pressure, worker lag | Chưa đo | Không được ngoại suy |

## Intended Soak Profile

```text
4 concurrent authenticated users
3 requests per second
900 seconds
```

Profile phải bao gồm asset/analytics, ticket, work-order, inventory,
notification và job-status reads. Trước/sau phải ghi:

- total/status codes, expected authorization failures và unexpected failures;
- p50, p95, p99, max, throughput và timeout;
- database pool checkout/timeout, connection growth;
- memory trend, CPU khi có provider tin cậy, process stability và log volume;
- worker heartbeat, lease, execution delay;
- pending/oldest outbox, dead letter và duplicate notification;
- table/runtime-disk growth theo fixture kỳ vọng.

Một run ngắn hơn 900 giây chỉ là rehearsal, không đóng soak gate.

Chạy trên approved isolated stack:

```powershell
$env:PM8_TEST_PASSWORD = "<isolated-test-user-password>"
$env:PM8_ALLOW_EXTENDED_TESTS = "true"
python -m src.reliability.load_harness `
  --profile soak `
  --username "<isolated-test-user>" `
  --output-dir "<outside-repository-report-directory>"
```

Credential chỉ đi qua environment; report phải nằm ngoài repository.

## Mutation-Bearing Profile

Fixture phải dùng unique namespace, isolated records và caller-stable
idempotency keys. Named actions được phép xem xét:

- ticket creation, assignment/permitted lifecycle và comment;
- permitted work-order actions;
- inventory receipt hoặc transfer;
- notification read/unread/dismiss;
- stable manual trigger của một trong bốn fixed jobs;
- bounded safe dead-letter redrive khi fixture đã tạo đúng trạng thái.

PM9 acceptance yêu cầu:

- replay cùng key trả committed result;
- optimistic conflict được quan sát như expected conflict;
- inventory `on_hand` và `available` không âm;
- không có duplicate ticket/work-order effect, outbox event hoặc notification;
- append-only history không bị sửa/xóa;
- outbox/notification drain được đo;
- mọi declared cleanup action được attempted, trả expected result; fixture
  counts trở về expected zero/baseline và canonical fingerprints không đổi.

`src.reliability.mutation_rehearsal` bổ sung closed action catalog cho các nhóm
trên. `MutationPlan` từ chối:

- database URL không phải `postgresql+psycopg` hoặc tên không kết thúc `_test`;
- namespace không thuộc `pm9-*`;
- mutating action thiếu namespace-scoped caller-stable key;
- plan thiếu replay, optimistic-concurrency probe, invariant hoặc cleanup;
- action ngoài catalog;
- hơn 40 workload hoặc 20 cleanup actions;
- credential-bearing target/report path trong repository.

Runner luôn fingerprint canonical data trước/sau và attempt từng declared
cleanup action trong `finally` sau successful authentication. Trước login,
runner yêu cầu `/health/live` attest đúng fingerprint của supplied `_test`
database; mismatch dừng trước mutation. Catalog bind từng operation label với
HTTP method và actual FastAPI route shape; optimistic-concurrency probe chỉ
chấp nhận đúng `409`, còn invariant read phải trả đúng `200`.

Report ghi `attempted_cleanup_actions`, `cleanup_actions_complete`,
`isolated_database_teardown_required`, `test_records_removed_claim=false` và
`api_database_attestation_verified`. Missing captured cleanup context là
failure; named cancel/archive/dismiss action không được diễn giải là đã xóa
append-only history, nên isolated database teardown vẫn bắt buộc. Declarative
plan từ JSON từ chối unknown/secret fields. Repository chưa có checked-in
representative live plan và không có PM9 mutation report.

`load_harness` có thể đọc tối đa 20 local request specs và chặn credential-bearing
target. Fixture PM9 phải tự cung cấp stable key; key ngẫu nhiên do generic
harness tạo không đủ để chứng minh idempotent replay. Không có representative
mutation fixture hoặc cleanup evidence trong repository hiện tại.

Ví dụ command chỉ được chạy sau khi fixture được review:

```powershell
$env:PM8_TEST_PASSWORD = "<isolated-test-user-password>"
$env:PM8_ALLOW_MUTATIONS = "true"
python -m src.reliability.load_harness `
  --profile stress `
  --username "<isolated-test-user>" `
  --mutation-fixture "<outside-repository-reviewed-fixture>" `
  --output-dir "<outside-repository-report-directory>"
```

Command trên chưa được chạy cho PM9.

Dedicated executor:

```powershell
$env:PM9_ALLOW_MUTATION_REHEARSAL = "true"
$env:TEST_DATABASE_URL = "<postgresql+psycopg-url-ending-_test>"
$env:PM9_TEST_PASSWORD = "<isolated-test-user-password>"
python -m src.reliability.mutation_rehearsal `
  --plan "<outside-repository-reviewed-plan.json>" `
  --username "<isolated-test-user>" `
  --output-dir "<outside-repository-report-directory>"
```

Opt-in không thay thế approved host, reviewed plan hay cleanup verification.
Focused mutation/secret test batch đã pass bằng synthetic HTTP transport; không
có live mutation-stack execution.

## Capacity-To-Degradation Profile

Profile checked-in có năm stage, mỗi stage 30 giây:

| Stage | Concurrent users | Target rate |
|---:|---:|---:|
| 1 | 4 | 4 req/s |
| 2 | 4 | 8 req/s |
| 3 | 8 | 12 req/s |
| 4 | 8 | 16 req/s |
| 5 | 10 | 20 req/s |

Chạy chỉ khi host được approve:

```powershell
$env:PM8_TEST_PASSWORD = "<isolated-test-user-password>"
$env:PM9_ALLOW_CAPACITY_TESTS = "true"
python -m src.reliability.load_harness `
  --step-load-profile capacity `
  --username "<isolated-test-user>" `
  --output-dir "<outside-repository-report-directory>"
```

Harness dùng bounded in-flight window, monotonic stage deadline, short shutdown
grace và cancellation signal. Nó quan sát safety trước, trong và sau stage;
operator cancellation, unhealthy readiness, non-ready worker, missing mandatory
API telemetry, runner failure, unexpected-error ceiling, p95 ceiling, repeated
timeout, unrecovered outbox growth, database pool timeout hoặc host CPU/memory
ceiling đều dừng việc tiếp tục stage/step tương ứng.

Code defaults hiện là unexpected error rate `2%`, p95 `2000ms`, repeated
timeout limit `2`, bất kỳ readiness unhealthy nào, không cho worker-stale hay
unrecovered outbox growth, và host CPU/memory `90%`. Missing mandatory API
telemetry làm evidence `inconclusive`; injected runner/transport được ghi là
synthetic/test-double và không đủ điều kiện thành host-capacity evidence.
Threshold là rehearsal safety limits, không phải SLA. Final evidence phải ghi
đúng threshold thực tế được process sử dụng.

## Result Template

Chỉ điền từ redacted raw evidence:

| Field | PM9 result |
|---|---|
| Executed host | Unverified |
| Profile/start/end | Not executed |
| Total/achieved rate | Not measured |
| Success/expected conflict/unexpected failure | Not measured |
| p50/p95/p99 | Not measured |
| Timeout/pool timeout | Not measured |
| CPU/memory trend | Not measured |
| Worker/outbox/dead letter | Not measured |
| Cleanup/invariants | Not verified |
| First degradation stage | Not observed |

Nếu cả năm stage pass, kết luận chỉ là “không quan sát degradation trong bounded
profile này”; không được gọi 20 req/s là capacity.

Xem [load-test plan PM8](load_test_plan.md),
[pilot environment](pilot_environment.md) và
[testing guide](testing.md).

# PM8 Load Test Plan

## Nguyên Tắc

Các giá trị dưới đây là **test assumptions**, không phải customer demand, SLA hoặc
capacity commitment. Profile mặc định đủ nhỏ cho developer workstation. Mutation
chỉ chạy với fixture riêng và `PM8_ALLOW_MUTATIONS=true`; soak/extended test cần
`PM8_ALLOW_EXTENDED_TESTS=true`.

Base URL phải là credential-free HTTP(S) origin. Fixture chỉ nhận local absolute
path bắt đầu bằng một `/`; absolute/network URL bị từ chối để bearer token không
thể rời test stack.

| Profile | Concurrent users | Request rate | Duration | Mutation share | Mục đích |
|---|---:|---:|---:|---:|---|
| Baseline | 4 | 4 req/s | 30s | 10% khi opt-in | Normal local pilot assumption |
| Stress | 8 | 12 req/s | 45s | 15% khi opt-in | Bounded higher-load observation |
| Recovery | 2 | 2 req/s | 30s | 5% khi opt-in | Quan sát trong component interruption |
| Soak | 4 | 3 req/s | 900s | 5% khi opt-in | Leak/growth/stuck lease/retry storm |

Analytics không tự trigger trong profile mặc định vì là batch daily và có chi phí
lớn. Stable manual trigger có thể thêm bằng mutation fixture trên database `_test`.

## Endpoint Mix

Harness luôn hỗ trợ:

- `/health/live`, `/health/ready`;
- asset/analytics reads;
- ticket, work-order và inventory reads;
- notification inbox/unread count;
- job execution listing và metrics;
- expected unauthenticated failure.

Mutation fixture có thể thêm named ticket lifecycle action, work-order action,
inventory receipt/transfer trên isolated records và stable manual job trigger.
Không dùng generic balance/status patch.

Ví dụ fixture:

```json
[
  {
    "method": "POST",
    "path": "/operations/jobs/sla_escalation/trigger",
    "expected_statuses": [200],
    "idempotency_key": "pm8-baseline-sla-01"
  }
]
```

## Chạy

API và worker phải trỏ tới database riêng. Password chỉ cung cấp qua environment:

```powershell
$env:PM8_TEST_PASSWORD = "<test-user-password>"
python -m src.reliability.load_harness `
  --profile baseline --username admin.test `
  --output-dir "$env:TEMP\pm8-reliability"
```

Mutation:

```powershell
$env:PM8_ALLOW_MUTATIONS = "true"
python -m src.reliability.load_harness `
  --profile stress --username admin.test `
  --mutation-fixture "$env:TEMP\pm8-mutations.json"
```

## Measurements

Summary JSON ghi total/success/expected authorization/unexpected failure, timeout,
connection/503 failures, p50/p95/p99/max latency, achieved throughput,
idempotent replays, execution status counts và outbox trước/sau.

Pass/fail phải được quyết định từ observed failures, bounded timeout, invariant
checks và backlog drain, không từ một SLA tự đặt. Stress profile chỉ ghi điểm cao
nhất đã chạy. Chỉ một test capacity-to-first-failure riêng mới được gọi là failure
limit; PM8 checkpoint chưa chạy test đó.

## Soak Review

So sánh đầu/cuối:

- process memory và log volume;
- database pool checked-out;
- active/expired leases;
- retry/dead-letter count;
- pending/oldest outbox;
- duplicate notification/business effect;
- table row growth theo expected input volume;
- attachment/runtime disk growth.

Raw report không thuộc canonical data path và không được commit.

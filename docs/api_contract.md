# API Contract

## Compatibility

FastAPI là serving và authorization boundary. PM7 chỉ thêm routes; existing
PM1-PM6 request/response fields, Vietnamese legacy values và lifecycle rules
không đổi. Full domain endpoint inventory nằm tại [FastAPI reference](api.md).

`GET /health` giữ nguyên legacy response. PM7 health routes là additive.

## Authentication

- `/health`, `/health/live`, `/health/ready` và `/health/worker` là public.
- Notification routes cần `notifications:read`.
- `/operations/*` cần `job_operations:read`; mutation cần thêm
  `job_operations:manage`.
- Current role matrix chỉ cấp operator permissions cho Administrator.
- Bearer access token và rotating HttpOnly refresh-cookie behavior không đổi.

## Health

| Method | Route | Contract |
|---|---|---|
| `GET` | `/health/live` | Process sống; `{"status":"alive"}` |
| `GET` | `/health/ready` | Database readiness và worker state; worker stale tạo trạng thái `degraded` |
| `GET` | `/health/worker` | Latest heartbeat; trả `503` khi missing/stale/not ready |

Readiness không trả credential, database URL, stack trace hoặc worker metadata
payload.

## Notifications

### List

```http
GET /notifications?unread_only=true&severity=warning&page=1&page_size=25
Authorization: Bearer <access-token>
```

Response:

```json
{
  "items": [
    {
      "id": "UUID",
      "notification_type": "ticket.assigned",
      "title": "Ticket được phân công",
      "body": "Ticket TCK-000043 của asset GENERATOR_002 đã được phân công cho bạn.",
      "structured_content": {
        "ticket_id": "TCK-000043",
        "asset_id": "GENERATOR_002"
      },
      "severity": "info",
      "related_entity_type": "ticket",
      "related_entity_id": "TCK-000043",
      "created_at": "2026-07-26T08:00:00Z",
      "read_at": null,
      "dismissed_at": null,
      "version": 1
    }
  ],
  "page": 1,
  "page_size": 25,
  "total": 1
}
```

`structured_content` chỉ chứa event fields allow-list; source outbox ID, payload,
recipient ID và internal lease không được expose.

### Count Và Actions

```text
GET  /notifications/unread-count
POST /notifications/{notification_id}/read
POST /notifications/{notification_id}/unread
POST /notifications/{notification_id}/dismiss
POST /notifications/read-all
```

Ba single-item actions nhận:

```json
{"expected_version": 1}
```

Unknown hoặc notification của user khác trả `404` để không tiết lộ existence.
Stale version trả `409`.

## Operator Jobs

### List Và Enable

```text
GET   /operations/jobs
PATCH /operations/jobs/{job_key}
```

PATCH body:

```json
{"enabled": true, "expected_version": 1}
```

Chỉ bốn server-controlled `job_key` hợp lệ. Enable snapshots current
Administrator làm run-as actor. API không nhận interval, cron, executable
configuration hoặc arbitrary function.

### Trigger Và Retry

```http
POST /operations/jobs/sla_escalation/trigger
Authorization: Bearer <administrator-token>
Idempotency-Key: pilot-sla-20260726-01
```

```http
POST /operations/executions/{execution_id}/retry
Authorization: Bearer <administrator-token>
Idempotency-Key: retry-execution-01
```

Response gồm persisted execution và `created`. Replay cùng key trả
`created=false`; key reuse với intent khác trả `409`. Trigger/retry không execute
trong API request và không bypass worker lease.

### History, Outbox Và Metrics

```text
GET /operations/executions?status=dead_lettered&job_key=analytics_refresh&page=1&page_size=25
GET /operations/outbox?status=dead_lettered&page=1&page_size=25
GET /operations/metrics
```

Outbox response cố ý không có payload/hash/idempotency key. Metrics gồm:

- pending, failed và dead-letter job counts;
- pending/dead-letter outbox counts;
- oldest pending outbox age;
- last successful run cho từng supported job.

## Error Mapping

| HTTP | Ý nghĩa |
|---:|---|
| `400` | Unsupported job/action hoặc invalid closed configuration |
| `401` | Chưa xác thực/session invalid |
| `403` | Thiếu permission |
| `404` | Resource không tồn tại hoặc notification không thuộc current user |
| `409` | Stale version, idempotency conflict hoặc invalid operation state |
| `422` | Request schema/header không hợp lệ |
| `503` | PostgreSQL/worker readiness không đạt |

API không trả raw worker exception hoặc stack trace. OpenAPI chỉ bật trong
development/test theo existing settings.

## PM8 Reliability Actions

PM8 thêm additive Administrator endpoints:

```text
POST /operations/outbox/{event_id}/retry
POST /operations/alerts/evaluate
```

Outbox retry yêu cầu `Idempotency-Key`, chỉ nhận dead-letter event và persist
bounded redrive intent/audit; worker hiện có mới deliver. Alert evaluation dùng
closed thresholds và tạo raised/recovered outbox event, không thêm scheduler/job.
`GET /operations/metrics` thêm safe pool/API/lease/alert/backup aggregates; fields
PM7 giữ nguyên.

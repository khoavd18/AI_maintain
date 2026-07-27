# PM9 Operational Ownership

## Authoritative Record

Machine-readable source: [operational ownership record](../deployment/operational_ownership.json).

Không có owner, contact, support coverage, incident channel hoặc escalation
approval nào được cung cấp. Placeholder cố ý làm contract fail.

```text
NO-GO / NOT YET VERIFIED
```

Chỉ ghi role và approved internal channel. Không commit private phone number,
personal email hoặc dữ liệu cá nhân.

## Required Assignments

| Record key | Trách nhiệm bắt buộc | Assignment | Approved channel | Status |
|---|---|---|---|---|
| `operational_owner` | Daily health/metrics/inbox review, service coordination | `PENDING_ASSIGNMENT` | `PENDING_APPROVED_INTERNAL_CHANNEL` | Unassigned |
| `backup_owner` | Schedule, last-good protection, retention và restore evidence | `PENDING_ASSIGNMENT` | `PENDING_APPROVED_INTERNAL_CHANNEL` | Unassigned |
| `release_owner` | Release inputs, deployment window và evidence approval | `PENDING_ASSIGNMENT` | `PENDING_APPROVED_INTERNAL_CHANNEL` | Unassigned |
| `rollback_owner` | Rollback decision, quiesce và traffic reopen | `PENDING_ASSIGNMENT` | `PENDING_APPROVED_INTERNAL_CHANNEL` | Unassigned |
| `incident_coordinator` | Severity, timeline, communication và closure | `PENDING_ASSIGNMENT` | `PENDING_APPROVED_INTERNAL_CHANNEL` | Unassigned |
| `security_contact` | Secret rotation, suspected compromise và security acceptance | `PENDING_ASSIGNMENT` | `PENDING_APPROVED_INTERNAL_CHANNEL` | Unassigned |
| `database_recovery_contact` | PostgreSQL backup/restore/integrity decision | `PENDING_ASSIGNMENT` | `PENDING_APPROVED_INTERNAL_CHANNEL` | Unassigned |
| `application_support_contact` | First response cho API/frontend/worker issues | `PENDING_ASSIGNMENT` | `PENDING_APPROVED_INTERNAL_CHANNEL` | Unassigned |
| `pilot_business_owner` | Pilot scope, business interruption và limitation acceptance | `PENDING_ASSIGNMENT` | `PENDING_APPROVED_INTERNAL_CHANNEL` | Unassigned |

Responsibility descriptions không phải assignment. Mỗi role cần evidence link
tới approved internal record trước khi đổi status thành `assigned`.

## Incident Communication

Current structured status:

- primary internal channel: `PENDING_APPROVED_INTERNAL_CHANNEL`;
- fallback internal channel: `PENDING_APPROVED_INTERNAL_CHANNEL`;
- status: `unconfigured`;
- audience: pilot operators và business owner;
- support hours/timezone/after-hours assumption: chưa được xác nhận;
- escalation path: chưa được cấu hình.

Expected escalation shape:

```text
application support contact
→ incident coordinator
→ pilot business owner
```

Đây chỉ là role sequence template. Không được đánh dấu configured trước khi
approved channels, coverage và evidence links có thật.

## Owner-Supplied Input Procedure

1. Chọn organizational role cho từng key; không mặc định một developer sở hữu
   mọi trách nhiệm.
2. Chọn approved internal channel không chứa private contact detail trong Git.
3. Ghi support hours, timezone và after-hours expectation.
4. Ghi primary/fallback incident channels và ít nhất hai escalation steps.
5. Liên kết approval record bằng safe repository-relative hoặc approved
   organizational evidence reference.
6. Review separation giữa release/rollback/database recovery ở mức phù hợp với
   pilot risk.
7. Chạy validator; không sửa release decision bằng tay.
8. Pilot business owner review [known limitations](known_limitations_acceptance.md).

## Operational Cadence Cần Xác Nhận

| Cadence | Required review | Owner key |
|---|---|---|
| Mỗi support window | API/worker readiness, dead letter, oldest outbox, in-app alerts | `operational_owner` |
| Theo approved schedule | Backup exit/result, checksum pair, overdue state | `backup_owner` |
| Trước/sau release | Manifest identity, backup, smoke, rollback point, cleanup | `release_owner`, `rollback_owner` |
| Khi incident | Scope/severity, safe timeline, recovery owner, communication | `incident_coordinator` |
| Khi rotate secret | Approval, window, session impact, rollback | `security_contact` |
| Khi restore | Source artifact, separate database, integrity, traffic decision | `database_recovery_contact` |
| Trước mở rộng pilot | Limitations, capacity evidence, business impact | `pilot_business_owner` |

Không có cadence nào ở bảng trên được coi là staffed cho đến khi ownership
record được owner điền và approve.

## Validation

```powershell
python -m src.reliability.pilot_contract --skip-environment
```

Static run ngày 2026-07-26 trả blocker cho cả chín assignment, incident path,
support coverage và escalation path. Đó là expected result của placeholder
record.

Ownership gate chỉ pass khi:

- mọi assignment `assigned` và có evidence link;
- incident communication `configured`;
- support coverage `confirmed`;
- escalation path `configured`;
- limitation owner roles và acceptance record khớp;
- release record được regenerate và deterministic decision không còn blocker.

Xem [operations runbook](operations_runbook.md),
[pilot checklist](internal_pilot_checklist.md) và
[PM9 release note](releases/product_milestone_9.md).

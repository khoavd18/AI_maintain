# PM9 Operational Ownership

## Authoritative Record

Machine-readable source: [operational ownership record](../deployment/operational_ownership.json).

The solo project developer holds technical stewardship for the repository and
local engineering procedures. No sponsoring company, company owner, approved
contact channel, support coverage, incident organization, or business approval
exists. The organizational contract therefore remains externally blocked.

```text
Engineering readiness: PASS
Real-company ownership: BLOCKED — EXTERNAL DEPENDENCY
Overall: NO-GO / WAITING FOR PILOT SPONSOR
```

Chỉ ghi role và approved internal channel. Không commit private phone number,
personal email hoặc dữ liệu cá nhân.

## Solo Technical Stewardship

The structured role label is `Solo project developer`. It applies only to:

| Technical responsibility | Current holder | Authority boundary |
|---|---|---|
| Release preparation owner | `Solo project developer` | Prepare/checkpoint repository artifacts; cannot approve a company deployment window |
| Rollback procedure owner | `Solo project developer` | Maintain and locally test the procedure; cannot decide company traffic or data recovery |
| Backup drill operator | `Solo project developer` | Run safe local `_test` drills; cannot own a company schedule or retention policy |
| Database recovery drill operator | `Solo project developer` | Validate isolated recovery tooling; cannot authorize recovery of company data |
| Development application support | `Solo project developer` | Diagnose the development system; not production support coverage |
| Security implementation contact | `Solo project developer` | Maintain security controls/tests; not company security acceptance or incident authority |

These assignments do not satisfy any company ownership gate.

## Required Assignments

| Record key | Trách nhiệm bắt buộc | Assignment | Approved channel | Status |
|---|---|---|---|---|
| `operational_owner` | Daily health/metrics/inbox review, service coordination | `PENDING_PILOT_SPONSOR_ASSIGNMENT` | `PENDING_SPONSOR_APPROVED_CHANNEL` | `BLOCKED_EXTERNAL_DEPENDENCY` |
| `backup_owner` | Company schedule, last-good protection, retention and restore evidence | `PENDING_PILOT_SPONSOR_ASSIGNMENT` | `PENDING_SPONSOR_APPROVED_CHANNEL` | `BLOCKED_EXTERNAL_DEPENDENCY` |
| `release_owner` | Company deployment window and evidence approval | `PENDING_PILOT_SPONSOR_ASSIGNMENT` | `PENDING_SPONSOR_APPROVED_CHANNEL` | `BLOCKED_EXTERNAL_DEPENDENCY` |
| `rollback_owner` | Rollback decision, quiesce and traffic reopen | `PENDING_PILOT_SPONSOR_ASSIGNMENT` | `PENDING_SPONSOR_APPROVED_CHANNEL` | `BLOCKED_EXTERNAL_DEPENDENCY` |
| `incident_coordinator` | Severity, timeline, communication and closure | `PENDING_PILOT_SPONSOR_ASSIGNMENT` | `PENDING_SPONSOR_APPROVED_CHANNEL` | `BLOCKED_EXTERNAL_DEPENDENCY` |
| `security_contact` | Company secret/incident authority and security acceptance | `PENDING_PILOT_SPONSOR_ASSIGNMENT` | `PENDING_SPONSOR_APPROVED_CHANNEL` | `BLOCKED_EXTERNAL_DEPENDENCY` |
| `database_recovery_contact` | Company PostgreSQL recovery/integrity decision | `PENDING_PILOT_SPONSOR_ASSIGNMENT` | `PENDING_SPONSOR_APPROVED_CHANNEL` | `BLOCKED_EXTERNAL_DEPENDENCY` |
| `application_support_contact` | Production-facing API/frontend/worker support | `PENDING_PILOT_SPONSOR_ASSIGNMENT` | `PENDING_SPONSOR_APPROVED_CHANNEL` | `BLOCKED_EXTERNAL_DEPENDENCY` |
| `pilot_business_owner` | Pilot scope, interruption and limitation acceptance | `PENDING_PILOT_SPONSOR_ASSIGNMENT` | `PENDING_SPONSOR_APPROVED_CHANNEL` | `BLOCKED_EXTERNAL_DEPENDENCY` |

One sponsored person may hold multiple compatible roles; nine different people
are not required. Responsibility descriptions and solo technical stewardship
are not company assignments. Each company role needs an approved channel and
evidence before status becomes `assigned`.

## Incident Communication

Current structured status:

- primary internal channel: `PENDING_SPONSOR_APPROVED_CHANNEL`;
- fallback internal channel: `PENDING_SPONSOR_APPROVED_CHANNEL`;
- status: `BLOCKED_EXTERNAL_DEPENDENCY`;
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

Static validation intentionally returns blockers for all nine company
assignments, the incident path, support coverage, and escalation path. That is
the expected result of an externally blocked record, not an engineering
implementation failure.

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

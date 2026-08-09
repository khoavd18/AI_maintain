# PM9 Known-Limitations Acceptance

## Current Status

Machine-readable source:
[known-limitations record](../deployment/known_limitations.json).

All 14 limitations are documented and understood by the
`Solo project developer` as engineering constraints. Their engineering status
is `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED`. This acknowledgement is not
company, business, security, or production acceptance.

Organizational acceptance remains `BLOCKED_EXTERNAL_DEPENDENCY`: there is no
sponsoring organization or pilot business owner, so the accepted count remains
`0/14`. No acceptance was inferred or fabricated.

```text
Engineering documentation: COMPLETE
Organizational acceptance: BLOCKED — EXTERNAL DEPENDENCY
Overall: NO-GO / WAITING FOR PILOT SPONSOR
```

## Acceptance Register

### Single API Instance

- Description: pilot chỉ chạy một API process.
- Consequence: API dừng trong restart hoặc process failure.
- Mitigation: giới hạn pilot, theo dõi readiness, restart theo runbook.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: sau API incident hoặc trước khi tăng pilot scope.

### Single Worker Instance

- Description: pilot chỉ chạy một PostgreSQL polling worker.
- Consequence: background work dừng đến khi worker phục hồi; durable lease giữ
  retry boundary.
- Mitigation: theo dõi heartbeat, lease, dead letter và recovery runbook.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: sau worker outage hoặc backlog vượt threshold.

### Single PostgreSQL Instance

- Description: pilot dùng một PostgreSQL instance.
- Consequence: mất PostgreSQL làm dừng transactional và background workflows.
- Mitigation: checksummed backup, separate restore và rehearsed rollback.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: sau database incident hoặc trước khi nhận customer data.

### No Automatic Failover

- Description: không có automatic failover cho API, worker hoặc PostgreSQL.
- Consequence: human recovery và downtime.
- Mitigation: assign owners, configure incident path, rehearse restart/rollback.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: khi availability requirement vượt internal-pilot scope.

### No Automated PITR

- Description: không có automated point-in-time recovery.
- Consequence: chỉ restore về validated backup gần nhất, có thể mất thay đổi sau
  backup.
- Mitigation: operator schedule, overdue alert và separate restore drill.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: khi xác định data-loss objective hoặc trước pilot expansion.

### Local Attachment Storage

- Description: attachment bytes nằm trên local storage của một host.
- Consequence: host loss có thể làm metadata và bytes không đồng bộ.
- Mitigation: paired PostgreSQL/filesystem backup, checksum và orphan checks.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: sau attachment recovery failure hoặc trước multi-host use.

### No Malware Scanning

- Description: pilot không malware-scan attachments.
- Consequence: MIME/signature/extension/size checks không phát hiện mọi nội dung
  độc hại.
- Mitigation: limited types, authorized download và approved pilot data.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: trước khi nhận file ngoài approved pilot group.

### In-App Alerts Only

- Description: notifications/alerts chỉ ở in-app inbox.
- Consequence: owner có thể bỏ lỡ alert khi không đăng nhập.
- Mitigation: confirmed support hours, incident channel và operator review
  cadence.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: sau missed alert hoặc coverage change.

### No Centralized Observability Or On-Call Platform

- Description: không có centralized observability/on-call platform.
- Consequence: investigation phụ thuộc safe local logs, health, metrics và
  host procedure.
- Mitigation: bounded logs, operator metric review và documented escalation.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: sau hard-to-detect incident hoặc trước coverage expansion.

### No Managed Secrets

- Description: pilot không dùng managed secret service.
- Consequence: distribution, rotation và rollback cần secure operator process.
- Mitigation: runtime injection only, no values in evidence và rehearsed
  rotation.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: sau rotation failure hoặc operating-model change.

### Single-Host Capacity Evidence

- Description: load evidence chỉ áp dụng cho workstation/host đã test.
- Consequence: không ngoại suy sang capacity, SLA hoặc host khác.
- Mitigation: record host/profile, opt-in soak/step load và automatic safety
  stop.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: khi host, configuration hoặc demand thay đổi.

### No Multi-Tenancy

- Description: product không hỗ trợ multi-tenancy.
- Consequence: một deployment không được dùng để cô lập nhiều independent
  customers.
- Mitigation: giới hạn một approved internal-pilot boundary.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: trước đề xuất deployment cho nhiều tổ chức.

### No SSO Or MFA

- Description: pilot dùng local identity, không SSO/MFA.
- Consequence: access control không tích hợp enterprise identity policy.
- Mitigation: bounded user group, current RBAC/session controls và explicit CLI
  bootstrap.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: trước khi tăng data sensitivity hoặc user scope.

### No Customer-Facing SLA

- Description: pilot không có customer-facing SLA.
- Consequence: rehearsal không cam kết uptime, latency hoặc recovery time.
- Mitigation: chỉ báo observed envelope và confirmed support assumptions.
- Engineering status: `DOCUMENTED_NOT_ORGANIZATIONALLY_ACCEPTED` / `Solo project developer`.
- Organizational owner/status: `PENDING_PILOT_SPONSOR_ASSIGNMENT` / `BLOCKED_EXTERNAL_DEPENDENCY`.
- Review trigger: trước mọi service commitment.

## Engineering Documentation Versus Organizational Acceptance

Engineering documentation confirms that each limitation has a description,
operational consequence, mitigation, and review trigger. It does not authorize
company risk acceptance or permit a real pilot to start.

## Acceptance Rule

Mỗi limitation chỉ được chuyển sang `accepted` khi có:

- non-placeholder owner role;
- pilot business owner hoặc delegated approved role;
- accepted UTC timestamp;
- evidence link;
- mitigation được kiểm tra là khả thi;
- review trigger còn phù hợp với pilot scope.

`rejected` giữ release blocked. `pending` cũng giữ critical gate blocked. Không
được chấp nhận limitation thay cho integrity, authorization, backup/restore hay
secret-rotation evidence.

## Completed Boundary Không Được Mở Rộng

PM9 không hoàn thành hay thêm HA, automated PITR, managed secrets, centralized
observability/on-call, external alerts, object storage, malware scanning,
multi-tenancy, SSO/MFA, Kubernetes hoặc cloud deployment. Đây là internal-pilot
rehearsal, không phải production readiness.

Các capability/business domain bị cấm như procurement, supplier, accounting,
real-time IoT, external delivery và arbitrary jobs vẫn ngoài phạm vi.

Xem [operational ownership](operational_ownership.md),
[pilot environment](pilot_environment.md) và
[pilot checklist](internal_pilot_checklist.md).

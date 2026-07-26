# Internal Pilot Go/No-Go Checklist

PM8 chỉ validate internal-pilot operating envelope; checklist này không chứng
minh production readiness.

## Release Gate

- [x] Reviewable PM8 commit sequence và annotated local
  `product-milestone-8` tag được ghi; tag cũ không bị di chuyển.
- [x] Clean base-to-head migration đạt `20260726_0008`.
- [x] PM8 downgrade về `20260726_0007` và re-upgrade thành công.
- [x] `alembic current` và `alembic check` đạt.
- [x] Full backend, frontend, Ruff, ESLint và production build đạt.
- [x] Secret/path/runtime-artifact/canonical-data checks đạt.

## Data And Recovery Gate

- [x] Backup mới hoàn tất, checksum/manifest có bằng chứng.
- [x] Restore vào database `_restore` riêng đạt revision, row counts và integrity.
- [x] Restored-database application/operations smoke đạt.
- [x] Attachment backup scope được xác nhận; empty-metadata integrity assessment
  không có missing/checksum/orphan finding.
- [ ] Representative non-empty attachment metadata và bytes được backup/restore,
  rồi checksum-validate.
- [x] PostgreSQL interruption/recovery giữ pending work và data.
- [x] Analytics publication failure giữ last-valid output.

## Operations Gate

- [x] Bốn fixed jobs được enable/disable có chủ đích; không có executable config.
- [x] Worker heartbeat healthy.
- [x] Không có unresolved job/outbox dead letter.
- [x] Outbox backlog dưới configured age threshold và drain đã đo.
- [x] Operational alert raise/dedup/recovery smoke đạt.
- [x] Authentication/RBAC smoke đạt.
- [x] Baseline/stress result có environment, assumptions và observed limits.
- [x] Không có stuck/expired lease hoặc retry storm.
- [ ] Bounded soak và capacity-to-first-failure được chạy.
- [ ] Intended pilot host được rehearsal với sanitized representative data.

## Ownership Gate

- [ ] Operational owner được xác định.
- [ ] Rollback owner được xác định.
- [ ] Incident contact path được xác định.
- [ ] Backup/restore operator được xác định.
- [ ] Known limitations được internal-pilot owner chấp nhận.
- [ ] Secret values khác development placeholders/defaults.
- [ ] Real pilot signing/database secret rotation được rehearsal.

## Decision

`GO` chỉ khi mọi gate bắt buộc có current-revision evidence và không có unresolved
integrity/dead-letter/backup issue. Nếu một gate chưa chạy, kết quả là `NO-GO /
NOT YET VERIFIED`, không suy luận từ PM7 historical results.

### PM8 Local Validation Decision - 2026-07-26

`NO-GO / NOT YET VERIFIED`.

Technical local gates passed for migration integrity, `257` backend and `112`
frontend tests, static/build checks, bounded baseline/stress load, database/API/
worker recovery, durable lease/outbox recovery, dead-letter redrive, alert
cycles, analytics atomic publication, and PostgreSQL backup/isolated restore.
The immutable local commit/tag record is now closed.

The pilot remains blocked on named operational/rollback/backup owners, incident
contact, limitation acceptance, non-default pilot secrets, the bounded soak, a
measured first-failure limit, a representative non-empty
attachment-byte restore, and intended pilot-host rehearsal. Real pilot secret
rotation also remains unexecuted. See the PM8 release note for exact
measurements. Closing commit/tag did not change the overall decision.

## Explicit Remaining Boundary

HA, automated PITR, managed secrets, centralized observability, distributed
throttling, object storage, malware scanning, external notifications,
multi-tenancy, SSO/MFA, Kubernetes và cloud deployment nằm ngoài completed
boundary.

PM9 chưa bắt đầu.

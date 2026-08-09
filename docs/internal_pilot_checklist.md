# Internal Pilot Go/No-Go Checklist

Checklist giữ PM8 checkpoint làm historical evidence và theo dõi các gate PM9
cho internal-pilot deployment rehearsal. Nó không chứng minh production
readiness.

## PM9 Three-Gate Classification

- [x] Engineering readiness: `PASS` — design, contracts, tooling, procedures,
  tests, and operational templates are present.
- [x] Local rehearsal: `PARTIAL` — executed local/static/synthetic evidence is
  recorded separately from unexecuted live profiles.
- [ ] Real-company pilot: `BLOCKED — EXTERNAL DEPENDENCY` — sponsor, approved
  host, company owners, users/data, secrets, and organizational acceptance are
  not available.

Overall external pilot decision: `NO-GO / WAITING FOR PILOT SPONSOR`.

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
- [x] Trên disposable PostgreSQL 16 `_test`, generated non-empty PDF upload trả
  `201`, archive/restore thành công, Administrator download `200` với matching
  bytes và Helpdesk nhận `403`; test dùng original metadata và không restore
  paired PostgreSQL dump.
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

## PM9 Deployment And Release Gate

- [x] Versioned manifest, ownership, limitation và draft release records tồn tại.
- [x] Static validator giữ placeholder/open critical gate ở trạng thái blocker.
- [x] Pilot mode từ chối CSV, development defaults, weak/missing secret và
  unverified release identity.
- [x] Closed Compose rehearsal có explicit execution/host approval và default
  fixed `stop` command, không có volume deletion; real rehearsal cleanup chưa
  chạy.
- [ ] Candidate commit/tag không còn placeholder và release record ở trạng thái
  final.
- [ ] Intended hoặc approved pilot-equivalent host được xác nhận.
- [ ] Clean full-stack deployment rehearsal được thực hiện trên host đó.
- [ ] Approved data restore/seed, schema revision và release identity được xác
  minh.
- [ ] Authentication/RBAC, exact four-job catalog, notifications và analytics
  deployment smoke được thực hiện.
- [ ] Application rollback về PM8 và PM9 redeploy được rehearsal.

## PM9 Load And Failure Gate

- [x] Bounded step-load profile 4/8/12/16/20 req/s có explicit opt-in,
  allow-listed report và automatic safety-stop tests.
- [x] Synthetic disk warning/critical/dedup/recovery state-machine tests chạy mà
  không fill real disk.
- [x] Temporary-file/checksum/last-good artifact helpers và non-empty attachment
  archive helpers được test bằng temporary fixtures.
- [x] Local disposable `_test` boundary đã chạy một valid `pg_dump` và một
  invalid-database `pg_dump`; đây không phải intended-host/service-account gate.
- [x] PostgreSQL-marked suite trên disposable PostgreSQL 16 `_test` đạt
  `73 passed, 239 deselected`.
- [x] Ba real PostgreSQL connection-termination tests đạt cho job completion,
  outbox delivery và ticket+outbox transaction atomicity.
- [ ] 4-user/3 req/s/900-second soak chạy đủ trên approved host.
- [ ] Mutation-bearing workload chạy với stable idempotency, invariants và
  fixture-specific cleanup actions được xác minh.
- [ ] First observed degradation point được đo, hoặc ghi rõ không quan sát trong
  bounded profile.
- [ ] Exact live worker termination trong scheduled job, outbox delivery và
  controlled transaction được rehearsal.
- [ ] Controlled real backup failure được phát hiện mà không ảnh hưởng last-good.
- [ ] Disk alert được rehearsal qua approved operational path; synthetic helper
  không tự đóng gate.
- [ ] Paired PostgreSQL metadata và representative non-empty attachment bytes
  được restore/download/checksum-validate.

## PM9 Human And Security Gate

- [x] Solo technical stewardship is recorded for release preparation, rollback
  procedure maintenance, backup/database drills, development support, and
  security implementation.
- [ ] Cả chín ownership/contact roles được assign bằng role và approved internal
  channel.
- [ ] Support hours, incident communication và escalation path được xác nhận.
- [ ] Mỗi critical known limitation có owner, acceptance, timestamp, evidence và
  review trigger.
- [ ] Pilot-grade signing/database secrets được provision mà không ghi vào Git.
- [ ] Real signing/database secret rotation và bounded rollback window được
  rehearsal.

## Decision

The engineering, local-rehearsal, and real-company gates are evaluated
separately. A real-company `GO` still requires current-revision evidence for
every mandatory gate and no unresolved integrity, authorization, or recovery
issue. Generic technical validators may return `NO-GO / NOT YET VERIFIED`;
PM9's overall external decision is `NO-GO / WAITING FOR PILOT SPONSOR`.

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

### PM9 Design-Readiness Closure - 2026-07-27

```text
PILOT-READY BY DESIGN
NOT PILOT-VERIFIED IN PRACTICE

Engineering readiness: PASS
Local rehearsal: PARTIAL
Real-company pilot: BLOCKED — EXTERNAL DEPENDENCY
Overall: NO-GO / WAITING FOR PILOT SPONSOR
```

PM9 tooling và focused synthetic/local tests không thay thế intended-host
evidence. Deployment, release/rollback, soak, mutation, degradation, exact
live worker-process termination, intended-host/service-account `pg_dump`
failure, durable disk-alert path, real pilot secret rotation và paired
PostgreSQL dump + representative attachment recovery vẫn chưa chạy. Local
valid/invalid-database `pg_dump`, connection-termination và authorized
attachment archive boundaries đã pass nhưng không đóng các broader gates.
Solo technical stewardship is acknowledged. Company ownership, incident path,
support coverage, and organizational limitation acceptance remain externally
blocked and were not fabricated.

Static contract validation returns expected blockers. The complete release
record maps those blockers to the externally waiting decision. Xem
[PM9 release note](releases/product_milestone_9.md),
[pilot deployment](pilot_deployment.md), [load results](pilot_load_results.md)
và [ownership](operational_ownership.md).

The next external workstream is
[Pilot 01 — Company-Specific Deployment](pilot_01_company_specific_deployment.md),
not PM10.

## Explicit Remaining Boundary

HA, automated PITR, managed secrets, centralized observability, distributed
throttling, object storage, malware scanning, external notifications,
multi-tenancy, SSO/MFA, Kubernetes và cloud deployment nằm ngoài completed
boundary.

PM9 là internal-pilot rehearsal milestone, không thêm business domain hoặc thay
đổi bốn-job worker architecture.

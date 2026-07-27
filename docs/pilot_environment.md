# PM9 Pilot Environment Record

## Mục Đích Và Trạng Thái

Tài liệu này ghi lại môi trường đã quan sát cho Product Milestone 9 (PM9) và
phân biệt nó với intended pilot host. PM9 là diễn tập cho internal pilot, không
phải chứng nhận production readiness.

Current three-gate classification:

```text
Engineering readiness: PASS
Local rehearsal: PARTIAL
Real-company pilot: BLOCKED — EXTERNAL DEPENDENCY
Overall: NO-GO / WAITING FOR PILOT SPONSOR
```

Không có tài liệu, biến môi trường hay approval record nào xác định workstation
đang dùng là intended pilot host. Vì vậy mọi kiểm tra phụ thuộc pilot host vẫn
chưa được xác minh. There is also no sponsoring organization, real pilot user,
representative company data, operational team, or company acceptance authority.
No missing external condition is treated as an application defect or fabricated.

## Snapshot Môi Trường Đã Quan Sát

Snapshot dưới đây được ghi ngày 2026-07-26 trong giai đoạn inspection. Tài
nguyên khả dụng là số đo tại một thời điểm và phải được đo lại trước mỗi lần
rehearsal.

| Thuộc tính | Quan sát | Cách diễn giải |
|---|---|---|
| Host | Windows 11 developer workstation | Không được xác nhận là intended pilot host |
| CPU | 16 logical CPU | Chỉ là host fact, không phải capacity evidence |
| Memory | 15,63 GiB tổng; khoảng 0,92 GiB khả dụng tại lúc inspection | Không đủ safety margin để chạy soak/capacity trong phiên này |
| Disk | Khoảng 11,33 GiB trống tại lúc inspection | Không chạy drill bằng filler file; phải đo lại trước deployment |
| Docker/Compose | Có sẵn | Không có project container PM9 đang chạy tại inspection |
| Required ports | Không phát hiện service dự án chiếm `3000`, `5432`, `6333`, `8000` tại inspection | Không thay thế preflight trên pilot host |
| Python | 3.11.9 | Phù hợp major/minor trong manifest |
| Node/npm | Node 22.20.0; npm 11.17.0 | Phù hợp Node version được ghi trong manifest |
| `psql` standalone | Không có | PostgreSQL client có thể chạy trong container; host rehearsal phải xác nhận cách vận hành |
| Pilot environment | Không có populated pilot-grade environment được phê duyệt | Local ignored `.env` là development-grade và không được dùng làm pilot evidence |
| Owners/incident path | Không có assignment đã phê duyệt | Gate tổ chức còn mở |
| Attachment fixture | Không có non-empty representative fixture sẵn có | Recovery gate còn mở |

Không ghi giá trị secret, credential, token, local absolute storage path hoặc dữ
liệu cá nhân vào tài liệu này.

Sau inspection, checkpoint đã dùng ephemeral generated PDF và disposable local
PostgreSQL 16 database kết thúc `_test`. PostgreSQL-marked selection đạt
`73 passed, 239 deselected`. Đây là test evidence trên workstation, không biến
host thành intended pilot host hoặc fixture thành pilot backup.

## Những Gì Có Thể Chạy An Toàn Tại Đây

- static validation cho deployment, ownership, limitation và release records;
- unit/focused tests cho contract, redaction, rehearsal planning, authenticated
  post-start validation, bounded load, synthetic disk capacity, temporary
  backup-artifact publication và attachment archive;
- real PostgreSQL connection-termination boundary tests và authorized
  non-empty attachment API/archive test trên disposable `_test`;
- local valid/invalid-database `pg_dump` publication-failure boundary trên
  disposable `_test`; không phải intended-host/service-account evidence;
- lint và documentation checks;
- rehearsal plan không khởi động container;
- kiểm tra cấu hình bằng placeholder-safe example.

Các việc sau không được coi là đã chạy chỉ vì tooling hoặc test double đã pass:

- clean full-stack deployment;
- authentication/RBAC, scheduled job, notification và analytics deployment smoke;
- 900-second soak;
- mutation-bearing workload;
- opt-in capacity-to-degradation test;
- live worker-process termination; ba PostgreSQL connection terminations đã pass
  nhưng không kill worker process;
- real PostgreSQL backup failure và restore trên intended environment;
- real pilot secret rotation;
- paired PostgreSQL metadata và non-empty attachment-byte restore;
- release/rollback rehearsal trên intended environment.

## Versioned Environment Contract

Nguồn cấu hình:

- [pilot manifest](../deployment/pilot_manifest.json);
- [pilot environment example](../.env.pilot.example);
- [pilot Compose file](../docker-compose.pilot.yml);
- [deployment procedure](pilot_deployment.md).

Populated environment phải nằm ngoài version control, có filesystem permission
phù hợp và thay toàn bộ `REPLACE_WITH_*`. Validator không trả lại giá trị biến.

Nhóm bắt buộc gồm:

- mode và release identity: `APP_ENVIRONMENT=pilot`,
  `STORAGE_BACKEND=postgresql`, `RELEASE_IDENTIFIER`,
  `RELEASE_GIT_COMMIT`, `RELEASE_GIT_TAG`,
  `RELEASE_ALEMBIC_REVISION`;
- PostgreSQL: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`,
  `DATABASE_URL`;
- authentication: `TOKEN_SIGNING_SECRET`, optional
  `TOKEN_SIGNING_PREVIOUS_SECRET`, cookie policy;
- network: bind addresses/ports, `NEXT_PUBLIC_API_BASE_URL`,
  `FRONTEND_BASE_URL`, `CORS_ALLOWED_ORIGINS`, `TRUSTED_HOSTS`;
- contained storage roots cho attachments, analytics và backup;
- explicit database pool/timeouts, worker polling/lease và operational alert
  thresholds;
- bốn job enable flags, mỗi flag phải được chọn có chủ đích;
- approved opaque host identifier và `PILOT_HOST_APPROVED=true` chỉ sau khi
  operator xác minh đúng host.

Pilot mode từ chối CSV storage, signing secret yếu/thiếu, development database
defaults và release identity chưa được xác minh. `NEXT_PUBLIC_*` là public build
configuration, không được chứa credential.

Runtime values trong checked-in manifest:

| Control | Candidate value |
|---|---:|
| Database pool / overflow / wait | `5` / `10` / `30s` |
| Connect / statement / lock / idle transaction | `5s` / `30s` / `5s` / `60s` |
| Worker poll / heartbeat / stale / outbox lease / batch | `2s` / `10s` / `60s` / `120s` / `20` |
| Outbox oldest-age alert | `300s` |
| Repeated job-failure alert | `3` |
| Analytics stale alert | `172800s` |
| Backup overdue alert | `604800s` |
| Disk warning / critical free percentage | `20%` / `10%` |

Các giá trị này là bounded candidate controls, không phải capacity tuning, SLA
hoặc customer demand.

## Service Và Storage Assumptions

Contract yêu cầu PostgreSQL 16, Qdrant 1.10.1, một API, một worker và một
frontend. Migration là one-shot service; nó không phải worker hay scheduler.
Các port mặc định trong manifest là PostgreSQL `5432`, Qdrant `6333`, API
`8000` và frontend `3000`, nhưng binding thực tế phải được host owner phê duyệt.

Persistent state phải được bảo vệ riêng:

- PostgreSQL transactional data và Qdrant RAG index trong named volumes;
- local attachment bytes và analytics input/output trong pre-created host binds
  dưới approved `PILOT_ALLOWED_DATA_ROOT`;
- validated backup artifacts dưới
  `PILOT_BACKUP_ROOT/postgresql`, ngoài repository và không phải Compose volume.

PostgreSQL dump không chứa attachment bytes. Recovery chỉ có ý nghĩa khi
metadata và filesystem snapshot được ghép cặp, checksum-validate và cùng thuộc
một rehearsal record.

## Input Còn Thiếu Từ Owner

- xác nhận intended/pilot-equivalent host và approved opaque host ID;
- host capacity, network/TLS termination và port policy được phê duyệt;
- populated pilot environment với real secrets nhưng không commit;
- approved pilot data/restore source;
- operational, backup, release, rollback, incident, security, database recovery,
  application support và business ownership;
- support hours, incident channels và escalation path;
- acceptance cho từng known limitation;
- approval để chạy soak, mutation, capacity, termination, rotation và recovery
  drills.

## Static Contract Check

Static review không đọc runtime environment:

```powershell
python -m src.reliability.pilot_contract --skip-environment
```

Lần chạy local ngày 2026-07-26 trả đúng
generic technical `NO-GO / NOT YET VERIFIED` và findings dạng blocker cho
release placeholder, ownership/incident path, limitation acceptance, rollback
và các critical gate chưa có evidence. The complete release record separately
classifies the external decision as `NO-GO / WAITING FOR PILOT SPONSOR`. Đây là
expected safety behavior, không phải pilot-host
rehearsal.

Xem thêm [ownership](operational_ownership.md),
[known-limitations acceptance](known_limitations_acceptance.md) và
[go/no-go checklist](internal_pilot_checklist.md).

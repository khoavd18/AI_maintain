# PM9 Internal-Pilot Deployment Rehearsal

## Trạng Thái Và Boundary

PM9 cung cấp một deployment contract và một closed Docker Compose rehearsal cho
internal pilot. Nó không tạo generic deployment platform, cloud/Kubernetes
stack, scheduler mới hay job thứ năm.

The deployment design, closed execution tooling, validation controls, and
runbook are complete. Deployment on an approved pilot host has not been
performed. Current classification:

```text
Engineering readiness: PASS
Local rehearsal: PARTIAL
Real-company pilot: BLOCKED — EXTERNAL DEPENDENCY
Overall: NO-GO / WAITING FOR PILOT SPONSOR
```

Pilot-ready by design means the deployment architecture and procedures are
available for a future sponsor. Pilot-verified in practice requires their actual
execution on an approved host with company owners, secrets, representative
data, and real users. This workstation provides only local evidence and is not
an approved pilot host.

Nguồn authoritative:

- [deployment manifest](../deployment/pilot_manifest.json);
- [pilot environment example](../.env.pilot.example);
- [pilot Compose file](../docker-compose.pilot.yml);
- [release record](../deployment/pilot_release_record.json);
- [environment record](pilot_environment.md).

## Topology Cố Định

| Service | Version contract | Vai trò | Runtime count |
|---|---|---|---:|
| PostgreSQL | 16 | Transactional authority | 1 |
| Qdrant | 1.10.1 | SOP/checklist retrieval only | 1 |
| Migration | Application 0.1.0 / Python 3.11 | Chạy `alembic upgrade head`, rồi kết thúc | one-shot |
| FastAPI | Application 0.1.0 / Python 3.11 | Authorization và business boundary | 1 |
| PM7 worker | Application 0.1.0 / Python 3.11 | PostgreSQL polling, lease/outbox | 1 |
| Next.js | Frontend 0.1.0 / Node 22.20.0 / Next.js 16.2.12 | Authenticated operational frontend | 1 |

Worker chỉ được thực thi bốn job:

- `preventive_generation`;
- `sla_escalation`;
- `analytics_refresh`;
- `inventory_reorder_detection`.

Mọi job trong checked-in manifest đang `enabled=false`. Operator phải chọn trạng
thái từng job sau authenticated smoke và không được cung cấp arbitrary command,
SQL, module, function hoặc workflow.

PostgreSQL và Qdrant dùng named volumes. Attachment và analytics directories là
pre-created host binds dưới approved `PILOT_ALLOWED_DATA_ROOT`. Backup artifacts
do operator quản lý dưới `PILOT_BACKUP_ROOT/postgresql`; chúng không nằm trong
Compose volume. Default cleanup dùng `down --remove-orphans` trên dedicated
`pm9-*` project; named volumes và host-bind data vẫn được giữ vì command không
có `--volumes`.

## Preflight Bắt Buộc

1. Xác nhận host trong [environment record](pilot_environment.md) là intended
   hoặc pilot-equivalent host và có approval chạy rehearsal.
2. Đo lại free memory/disk, xác nhận port/TLS/network policy và Docker/Compose.
3. Tạo populated environment file ngoài repository từ
   [`.env.pilot.example`](../.env.pilot.example); không in hoặc commit secret.
4. Thay release placeholder bằng full 40-character commit, exact intended tag
   và revision `20260726_0008`.
5. Chọn data mode:
   - `existing_approved`: chỉ dùng volume/data source đã được owner phê duyệt;
   - `empty_test`: database name phải kết thúc `_test` và cần explicit
     `PM9_ALLOW_EMPTY_TEST_DATA=true`.
6. Xác nhận backup gần nhất, attachment snapshot scope và rollback owner.
7. Chạy contract validation; blocker phải được xử lý, không override. Execute còn
   yêu cầu worktree hoàn toàn clean để Docker build context đúng exact tagged
   commit.
8. Xác nhận dedicated `pm9-*` Compose project chưa có container. Executor từ chối
   project name đang được dùng và không cleanup project mà invocation này chưa
   claim.
9. Chỉ tạo raw evidence trong protected directory ngoài repository.

Không dùng `metadata.create_all()`, không reset developer/demo database và không
tự sinh canonical data trong rehearsal.

## Plan Không Thay Đổi Runtime

Không có `--execute`, command chỉ parse protected dotenv, kiểm tra release
identity, Git identity và contract, rồi trả plan `not_executed`:

```powershell
python -m src.reliability.deployment_rehearsal `
  --environment-file "<protected-pilot-env>"
```

Plan liệt kê cả authenticated/RBAC, jobs, notifications và analytics để operator
thấy full gate. Execute mặc định chỉ tự động hóa startup, health và frontend
availability, ghi năm post-start gate là `not_executed` rồi fail overall.
`--authenticated-post-start` là opt-in mới để chạy closed API smoke cho năm gate
đó. Tooling này đã có focused unit tests với mocked HTTP transport nhưng chưa
được chạy trên live PM9 stack hoặc intended pilot host.

## Execute Trên Approved Host

Base execution cần hai independent approvals:

- process environment `PM9_ALLOW_DEPLOYMENT_REHEARSAL=true`;
- populated pilot environment có `PILOT_HOST_APPROVED=true`.

Authenticated post-start còn yêu cầu:

- process environment `PM9_ALLOW_POST_START_VALIDATION=true`;
- `PM9_APPROVED_DATA_ATTESTED=true` và một opaque
  `PM9_APPROVED_DATA_EVIDENCE_ID`;
- username/password của một operator và một restricted user được inject vào
  process environment qua `PM9_SMOKE_OPERATOR_USERNAME`,
  `PM9_SMOKE_OPERATOR_PASSWORD`, `PM9_SMOKE_RESTRICTED_USERNAME` và
  `PM9_SMOKE_RESTRICTED_PASSWORD`; không ghi các giá trị này vào command,
  environment file, evidence hoặc repository;
- HTTPS cho API origin. Chỉ isolated loopback test mới được phép dùng HTTP khi
  có thêm `PM9_ALLOW_HTTP_TEST_SMOKE=true`.

Ví dụ:

```powershell
$env:PM9_ALLOW_DEPLOYMENT_REHEARSAL = "true"
$env:PM9_ALLOW_POST_START_VALIDATION = "true"
$env:PM9_APPROVED_DATA_ATTESTED = "true"
$env:PM9_APPROVED_DATA_EVIDENCE_ID = "<opaque-approved-data-evidence-id>"
# Inject bốn PM9_SMOKE_* credential variables từ protected secret source.
python -m src.reliability.deployment_rehearsal `
  --environment-file "<protected-pilot-env>" `
  --evidence-dir "<protected-outside-repository-directory>" `
  --execute `
  --intended-host `
  --authenticated-post-start
```

Không dùng `--intended-host` nếu host không thật sự được xác nhận. Không dùng
`--leave-running` trong automated verification; mặc định tooling stop frontend,
worker, API, Qdrant và PostgreSQL sau rehearsal nhưng không xóa persistent
volumes. Post-start failure luôn cleanup dedicated project ngay cả khi caller
đã yêu cầu `--leave-running`.

Make target giữ post-start tắt mặc định. Chỉ opt in bằng exact value `true`:

```powershell
make pilot-rehearsal-execute `
  PILOT_ENV_FILE="<protected-pilot-env>" `
  PILOT_EVIDENCE_DIR="<protected-outside-repository-directory>" `
  PILOT_INTENDED_HOST=true `
  PILOT_AUTHENTICATED_POST_START=true
```

Credential và approval variables vẫn phải được inject vào process environment;
Make không nhận hoặc in secret arguments.

Closed automated sequence hiện tại:

```text
validate release/environment/manifest
→ verify exact tag and clean release worktree
→ validate Compose
→ refuse an existing Compose project collision
→ build pinned release images
→ start PostgreSQL and Qdrant
→ run Alembic migration container and wait for exit
→ run `alembic current` and match expected revision
→ start API, worker and frontend
→ validate running services
→ probe API liveness with release identity
→ probe API readiness with release identity
→ probe worker readiness
→ probe Qdrant readiness
→ probe frontend availability
→ nếu opt in: verify approved-data attestation and run closed authenticated
  post-start API validation
→ nếu không opt in: record approved-data/auth-RBAC/jobs/notifications/analytics
  as not executed and fail overall
→ stop services by default
→ write redacted evidence outside repository
```

Không có arbitrary Compose operation hoặc shell payload trong command surface.
Subprocess output không được đưa nguyên vào release record.

## Authenticated Post-Start Smoke Có Điều Kiện

Khi opt in, closed validator chỉ gọi allow-listed FastAPI read/auth endpoints.
Nó tạo/rotate/revoke hai authentication sessions nhưng không thực hiện business
mutation. Redacted evidence ngoài repository bao gồm:

- unauthenticated boundary trả `401`, release identity, API/database/worker
  readiness;
- operator login, refresh rotation, logout và protected identity;
- restricted-user login, positive permissions và negative RBAC boundaries;
- chính xác bốn scheduled jobs, manifest-declared enable states và dead-letter
  counts;
- non-empty asset, ticket, work-order và inventory reads từ approved data;
- latest batch analytics availability với non-empty summary;
- non-empty, owner-isolated notification reads và unread counts;
- bounded cleanup của cả hai sessions kể cả khi check trước đó fail.

Implementation và fail-closed/redaction behavior đã được unit-test. Chưa có
live deployed execution evidence. Validator cũng không tự động:

- restore/seed hoặc phê duyệt data source; attestation và opaque evidence ID là
  input bắt buộc trước khi Compose command chạy;
- manual job trigger, business execution hoặc idempotent replay;
- notification read/dismiss mutation;
- content-level Qdrant retrieval smoke;
- attachment download/recovery boundary.

Các bước còn lại cần operator-approved evidence riêng khi fixture/scope yêu cầu.
`passed` cho liveness/readiness hoặc unit tests không thay thế live post-start
execution. Nếu không truyền `--authenticated-post-start`, executor cố ý đặt năm
required validation steps là `not_executed` và overall `failed`.

## Approved Data

Rehearsal tool không tự quyết định restore hay seed. `existing_approved` vẫn cần
operator attestation; khi chạy authenticated post-start, attestation phải có
opaque evidence ID và runtime reads phải non-empty. Nguồn dữ liệu, checksum,
revision và approval vẫn phải được ghi trong protected evidence. `empty_test`
chỉ dành cho isolated rehearsal và không chứng minh representative pilot-data
compatibility.

Canonical demo reset và `load_data --replace` là destructive development action,
không thuộc deployment rehearsal.

## Health Và Release Identity

- `/health/live`: process alive, secret-free release identity;
- `/health/ready`: PostgreSQL readiness, revision và release identity;
- `/health/worker`: worker heartbeat/readiness qua FastAPI;
- frontend: HTTP availability; authenticated post-start hiện kiểm tra API, không
  thay thế browser-level smoke.

Manifest resolve commit từ exact Git tag target thay vì tự nhúng SHA của commit
chứa chính nó. Executor xác nhận HEAD có exact intended tag; full
`RELEASE_GIT_COMMIT` trong protected environment phải khớp observed HEAD.
`git status --porcelain=v2 --untracked-files=all` phải rỗng trước bất kỳ Compose
command nào để health identity không thể đại diện sai cho dirty build context.
Final release record chỉ được điền tag-target SHA sau khi tag đã tồn tại.
Expected commit/tag/revision phải khớp intended release ở nơi có thể xác định.
Health không trả secret, database URL hoặc local storage path.

Boundary này mới khóa provenance của source checkout. Application/frontend và
base-service image hiện vẫn được tham chiếu bằng tag, chưa ghi image digest sau
build/pull vào release evidence. Vì vậy không được xem tag container là immutable
artifact hoặc dùng nó làm bằng chứng rollback cho đến khi intended-host
rehearsal capture và đối chiếu digest.

## Cleanup Và Rollback

Nếu bất kỳ startup/probe step nào fail, không mở traffic. Mặc định chạy fixed
`docker compose down --remove-orphans` trên dedicated `pm9-*` project để không
để lại stopped container hoặc network. Named volumes và host-bind state vẫn
được giữ để operator điều tra theo approval; closed command không cho phép
`--volumes`. Checkpoint mới chỉ test command construction, chưa thực thi real
rehearsal cleanup. Focused tests xác nhận failure trong authenticated post-start
vẫn gọi cleanup, `--leave-running` không giữ một sequence thiếu post-start, và
cleanup failure buộc overall `failed`/exit `2`. Project collision được từ chối
trước build mà không chạy `down` trên project có sẵn. Đây vẫn chưa phải
intended-host cleanup evidence.

Rollback PM9 hiện là application rollback về PM8, vì PM9 candidate giữ schema
revision `20260726_0008`. Nếu dữ liệu hoặc schema không tương thích, dùng
validated restore; database downgrade không được mặc định cho phép. Quy trình
chi tiết nằm tại [release rehearsal](pilot_release_rehearsal.md) và
[failure recovery](failure_recovery.md).
Không có PM8 application/frontend image digest đã xác minh trong repository;
rollback vẫn chưa executable cho đến khi operator chuẩn bị và kiểm tra artifact
PM8 immutable trên intended environment.

## Evidence Status

| Evidence | Trạng thái |
|---|---|
| Manifest/Compose/rehearsal reconciliation | `22 passed`; Ruff, Compose config và Make dry-runs pass |
| Closed command construction, dotenv protection, opt-in, host approval, `_test` empty-data guard và exact fixed-stop construction | Covered by focused local tests; no real stop execution |
| Authenticated post-start implementation | `16 passed` focused deployment/post-start tests cover closed API checks, redaction, HTTPS/loopback guard, data attestation và failure cleanup; chưa chạy trên live PM9 stack |
| Static checked-in contract | Executed locally; generic technical blockers remain fail-closed |
| Docker pilot Compose deployment | Chưa chạy |
| Intended-host deployment | Chưa chạy |
| Authenticated/RBAC/jobs/notifications/analytics smoke | Tooling implemented/unit-tested; live execution chưa chạy |
| Approved data restore/seed | Chưa chạy |
| Cleanup after real deployment rehearsal | Chưa có execution để xác minh |

PM9 rehearsal không thiết lập production readiness.

The next external workstream is
[Pilot 01 — Company-Specific Deployment](pilot_01_company_specific_deployment.md).
It is not PM10 and must not start until a sponsor supplies the required company
environment and authority.

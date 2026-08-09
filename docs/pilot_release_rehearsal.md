# PM9 Release And Rollback Rehearsal

## Release Candidate

| Field | Current record |
|---|---|
| Release name | `product-milestone-9` |
| Implementation commits | `425a652`, `e6a5cd8`, `b1fd8c3` |
| Design-readiness checkpoint | Resolved by the final local annotated tag after this documentation commit |
| Tag recommendation | `product-milestone-9-pilot-ready-by-design` |
| Current base/tag | PM8 commit `ad4779e4e21322789e1e7b9d98b485127f1fa95f`, local tag `product-milestone-8` |
| Alembic revision | `20260726_0008` |
| PM9 migration | Không có trong candidate hiện tại |
| Rollback target | PM8 commit/tag ở cùng revision `20260726_0008` |
| Release record status | `design_complete_external_verification_blocked` |

The design-readiness tag is created only after final safe verification. It does
not move any existing tag, is not pushed, and must not be named
`product-milestone-9`, which could imply real-company pilot completion.

Manifest không tự nhúng SHA của commit chứa chính manifest đó. Contract dùng
`commit_resolution=exact_tag_target` để tránh self-reference không thể
checkpoint. Quy trình release provenance bắt buộc là:

1. commit candidate đã review với manifest hash ổn định;
2. for this design-only closure, create exact annotated tag
   `product-milestone-9-pilot-ready-by-design`; a future company deployment must
   use its separately approved release identity;
3. lấy full SHA bằng Git tag target và inject cùng giá trị vào
   `RELEASE_GIT_COMMIT` của protected environment;
4. executor xác nhận HEAD có exact tag và environment commit khớp full observed
   HEAD trước bất kỳ Compose command nào;
5. sau khi tag tồn tại, generate final release record với tag-target SHA và lưu
   record ở protected evidence hoặc follow-up evidence commit không di chuyển
   release tag.

Như vậy deployed source, runtime health identity và final evidence cùng trỏ tới
một tag target, trong khi tracked candidate không cần dự đoán SHA của chính nó.
Khi validate final record, operator phải truyền cả observed checkout SHA và
observed tag-target SHA độc lập qua `--actual-commit` và
`--actual-tag-target-commit`; validator yêu cầu hai full SHA khớp chính xác.
Observed tag, Alembic revision và protected environment cũng là input bắt buộc
cho final validation. Không được nhập giá trị dự đoán hoặc chỉ lặp lại manifest
mà chưa quan sát Git/runtime.

Current classification:

```text
PILOT-READY BY DESIGN
NOT PILOT-VERIFIED IN PRACTICE

Engineering readiness: PASS
Local rehearsal: PARTIAL
Real-company pilot: BLOCKED — EXTERNAL DEPENDENCY
Overall: NO-GO / WAITING FOR PILOT SPONSOR
```

## Phạm Vi Rehearsal

Release rehearsal phải dùng approved pilot database hoặc isolated database có
tên kết thúc `_test`. Không downgrade, overwrite hoặc restore đè developer/demo
database.

Sequence bắt buộc:

```text
freeze reviewed release inputs
→ validate manifest hash and release identity
→ quiesce API/worker
→ create and restore-validate PostgreSQL backup
→ pair attachment snapshot when metadata is non-empty
→ deploy PM9 candidate and run Alembic
→ verify revision, API, worker and frontend
→ run authenticated representative smoke
→ record rollback decision point
→ stop PM9 application
→ roll application back to PM8 at the same schema revision
→ re-run health/auth/RBAC/worker/data invariants
→ redeploy PM9 candidate
→ re-run the same smoke and cleanup
```

Mọi evidence phải là redacted summary ngoài repository trước khi được liên kết
trong [pilot release record](../deployment/pilot_release_record.json).

## Migration Decision

PM9 hiện không thêm migration. Application-only rollback về PM8 là đường ưu tiên
vì target và candidate cùng Alembic revision `20260726_0008`.

Không được tự suy luận rằng same-revision luôn tương thích. Trước rollback cần
kiểm tra PM9 có ghi dữ liệu mà PM8 không hiểu hay không. Nếu có data/schema
incompatibility, quiesce writers và restore một backup đã checksum/restore
validate. Checked-in manifest đặt:

- `database_downgrade_allowed=false`;
- rollback mode là application first, rồi validated restore khi cần;
- rollback rehearsal status là `unverified`.

PM8→PM7 downgrade vẫn là một procedure lịch sử riêng, có data-loss semantics cho
PM8-only operational evidence; nó không phải default PM9 rollback.

## Representative Smoke

Sau mỗi deploy, rollback và redeploy:

- exact release identifier/commit/tag/revision trên liveness/readiness;
- login, refresh, logout, current-user và expected unauthorized/forbidden paths;
- representative asset/ticket/work-order/inventory reads;
- bounded isolated named mutation với optimistic concurrency/idempotency;
- worker heartbeat, exact four-job catalog, stable manual trigger;
- outbox drain, unique in-app notification và owner isolation;
- latest-valid analytics availability;
- attachment metadata/byte authorization nếu fixture không rỗng;
- no negative inventory, orphan outbox, duplicate business effect hoặc
  unexpected dead letter.

Không dùng business records của developer hoặc canonical output path làm
fixture.

## Evidence Hiện Có

| Loại | Evidence |
|---|---|
| Prior PM8 | Clean base-to-head, PM7↔PM8 migration rehearsal, API/worker reconnect và isolated backup/restore đã được checkpoint trong [PM8 release note](releases/product_milestone_8.md) |
| PM9 local implementation | Release/manifest validators và reconciliation đạt focused `22 passed`; Ruff, Compose config và Make dry-runs pass |
| PM9 PostgreSQL boundary | Disposable local PostgreSQL 16 `_test`: `73 passed, 239 deselected`; ba connection-termination tests và authorized non-empty attachment API/archive test pass |
| PM9 intended environment | Chưa có deployment, application rollback, restore-based rollback hoặc PM9 redeploy evidence |
| Image provenance | Source checkout được khóa bằng exact tag/full SHA/clean worktree; image vẫn dùng mutable tag, chưa có PM9 digest hoặc verified PM8 rollback image digest |
| Frontend compatibility | PM8 production build là historical evidence; PM9 candidate build chưa được ghi là đã chạy |
| Authenticated workflow | Opt-in post-start validator đạt `16 passed` focused unit tests; chưa chạy trên PM9 deployed stack |

PM8 evidence không được đổi nhãn thành PM9 evidence.

## Gate Để Đóng Release Rehearsal

- intended host/pilot-equivalent host được owner phê duyệt;
- real populated environment và release commit/tag không còn placeholder;
- validated current backup và paired attachment snapshot;
- rollback owner, release owner và database recovery contact đã assign;
- full deploy→rollback→redeploy sequence có timestamp/evidence links;
- PM9 deployment image digest và PM8 rollback application/frontend image digest
  được capture, đối chiếu với release evidence;
- application and data invariants pass ở cả ba điểm;
- evidence ghi riêng trạng thái process, container, restore database, archive,
  fixture và raw log paths do rehearsal tạo; không dùng generic cleanup claim;
- release record được regenerate/review, không sửa tay thành `passed`.

Xem [deployment rehearsal](pilot_deployment.md),
[backup/restore](backup_restore.md), [attachment recovery](pilot_attachment_recovery.md)
và [operations runbook](operations_runbook.md).

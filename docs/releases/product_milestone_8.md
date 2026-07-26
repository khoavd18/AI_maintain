# Product Milestone 8: Internal Pilot Reliability Validation

## Status

Product Milestone 8 is implemented, reconciled, and locally checkpoint-verified
on 2026-07-26. The deployment decision remains:

```text
NO-GO / NOT YET VERIFIED
```

PM8 validates a bounded internal-pilot operating envelope. It does not establish
production readiness, a production SLA, a capacity limit, model accuracy, or
business impact.

## Objective And Boundary

PM8 hardens and validates the existing PM1–PM7 product through:

- bounded authenticated baseline, stress, recovery, and opt-in soak profiles;
- explicit PostgreSQL pool, statement, lock, and idle-transaction timeouts;
- durable lease/outbox recovery and audited dead-letter redrive;
- deduplicated operational alert raise/recovery cycles;
- PostgreSQL dump, checksum, isolated restore, integrity, and application smoke;
- one-previous-key JWT verification for a bounded signing-key rollover;
- pilot/production database-secret validation;
- read-only attachment metadata/byte integrity and orphan assessment;
- internal-pilot go/no-go and reliability/recovery runbooks.

PM8 adds no business domain, fifth worker job, arbitrary executable schedule,
second worker, in-memory authoritative queue, Redis, Kafka, RabbitMQ, Celery,
external notification delivery, procurement, multi-tenancy, SSO/MFA,
Kubernetes/cloud infrastructure, real-time processing, or generative LLM
functionality.

## Test Environment And Assumptions

Checkpoint verification used one Windows developer workstation, Python 3.11.9,
PostgreSQL 16 in one disposable Docker container, one local FastAPI process, and
one local PM7 worker. The database name ended in `_test`; generated logs,
reports, dumps, manifests, and frontend output stayed outside canonical data and
were removed after verification.

Profile values are test assumptions, not measured customer demand or service
targets. The default profiles contained no mutation fixture.

| Profile | Assumption | Checkpoint result |
|---|---|---|
| Baseline | 4 users, 4 req/s, 30 seconds | 121 requests; 120 HTTP 200 plus one expected HTTP 401; 4.065 req/s; p50 24.423 ms, p95 236.900 ms, p99 460.613 ms, max 491.153 ms; no unexpected failure, timeout, connection/database failure, dead letter, or remaining outbox backlog |
| Stress | 8 users, 12 req/s, 45 seconds | 541 requests; 540 HTTP 200 plus one expected HTTP 401; 12.039 req/s; p50 47.749 ms, p95 346.719 ms, p99 396.318 ms, max 472.518 ms; no unexpected failure, timeout, connection/database failure, dead letter, or remaining outbox backlog |
| Recovery | 2 users, 2 req/s, 30 seconds | Component interruption/recovery drills were executed; the HTTP recovery profile itself was not run |
| Soak | 4 users, 3 req/s, 900 seconds, explicit opt-in | Not executed |

Stress is the highest tested checkpoint point. It is not a discovered failure or
capacity limit and must not be extrapolated to the pilot host or production.

## Executed Checkpoint Evidence

| Check | Executed result |
|---|---|
| Focused PM8 | Migration, pool/query/lock behavior, lease/outbox recovery, redrive authorization/idempotency/concurrency, alert deduplication/recovery, checksum, secret, path, attachment, and canonical-protection checks passed |
| PM4–PM7/auth regression | Inventory, ticket/SLA, recurrence/work order, asset, authentication/RBAC, transactional workflow, worker/outbox, and notification regressions passed |
| Full backend | `257 passed`; one existing Starlette/httpx TestClient deprecation warning |
| Full frontend | `112 passed` in 17 files |
| Static/build | Ruff, ESLint, and Next.js production build passed; 32 pages generated |
| Migration | Exactly one head; clean base-to-head; PM7→PM8; empty and populated PM8→PM7 downgrade; PM8 re-upgrade; `alembic current`; `alembic check`; PM8 catalog constraint/trigger checks passed |
| Load profiles | Baseline and stress results above were rerun at the checkpoint |
| API/worker | API import, liveness/readiness, worker readiness, and reconnect smokes passed |
| Dead-letter redrive | Protected API created one redrive intent, same-key replay returned `created=false`, the existing worker processed it once, and no dead letter/backlog remained |
| Operational alerts | Explicit evaluation raised two cycles, duplicate evaluation did not duplicate, recovery produced two recovery events, and active PM8 alerts returned to zero |
| PostgreSQL interruption | Liveness stayed HTTP 200, readiness changed to HTTP 503, API/worker reconnected after restart, and revision plus representative user/job/heartbeat state persisted |
| Backup/restore | Custom dump, SHA-256, manifest, isolated `_restore`, revision/row-count/six-integrity checks, and restored FastAPI liveness/readiness passed; restore database was dropped |
| Attachment assessment | Test database had zero active attachment metadata; invalid, missing, unreadable, checksum-mismatch, and orphan counts were zero; no malware scan was claimed |
| Repository safety | Documentation links, high-confidence secret scan, unsafe-path scan, runtime-artifact scan, canonical-data drift check, and final `git diff --check` passed |

The checkpoint backup was 270,581 bytes with SHA-256
`0f6720d017f62fa756e058b7ecfa8db7ddce1627874bf32705439aa9330665b9`.
It restored revision `20260726_0008` with 6 users, 4 scheduled jobs, 5 outbox
events, 5 delivery attempts, 5 notifications, and 10 audit rows. Business-domain
tables in that post-test source were empty, so this smoke does not claim a
representative pilot-data restore.

The earlier PM8 report recorded a 294,474-byte backup with SHA-256
`1df721c14adb3a219c34a416bdc9de1b6767b75a202939bb8224166dd28596fa`.
That result remains historical rather than newly executed checkpoint evidence.
No backup archive is committed or assumed to remain available.

The earlier report also observed an approximately 42-second worker-loop recovery
gap. This checkpoint verified reconnect/readiness but did not instrument a new
exact worker-loop gap, so the 42-second value remains historical.

## Database And Recovery Findings

Pool capacity/wait remains the prior SQLAlchemy effective values—size `5`,
overflow `10`, wait `30s`—because the bounded profiles did not justify capacity
tuning. New safety limits are statement `30s`, lock `5s`, and idle transaction
`60s`. Focused PostgreSQL tests bounded pool exhaustion, statement cancellation,
lock wait, deliberate deadlock rollback, advisory-lock visibility, and
transaction isolation.

The populated rollback test found and corrected a checkpoint defect. PM8→PM7 now
removes PM8-only redrive-cycle attempts, preserves PM7-compatible cycle-zero
attempt history, returns unfinished non-alert redrives to dead-letter, and
removes redrive intent before deleting PM8 operational-alert events. Concurrent
same-key redrive returns one created intent and one replay.

Worker lease and outbox interruption recovery remain durable PostgreSQL state
transitions. Redrive never delivers inside the API/CLI process and never becomes
an unbounded automatic replay.

## Security, Alert, And Attachment Findings

New access tokens are signed only with the current key. At most one distinct
previous key can verify unexpired access tokens during a bounded grace period.
The real pilot rotation procedure was not executed.

Pilot/production settings reject missing database URL components, the development
credential pair, and the literal `replace_with_*` example placeholders. Secrets
remain environment-provided; PM8 does not add a managed secret platform.

Operational alert evaluation remains an explicit Administrator API/CLI action,
separate from the four-job catalog. It writes only alert state and allow-listed
outbox/in-app notification records; it performs no inventory mutation and cannot
persist a database-down alert while PostgreSQL itself is unavailable.

Attachment assessment is read-only, streams checksums, counts every unreferenced
file below the configured storage root, and returns aggregate counts without
paths. PostgreSQL backup still excludes attachment bytes.

## PM1–PM7 Compatibility

- Revisions `20260718_0001` through `20260726_0007` are unchanged.
- PostgreSQL remains transactional authority; CSV remains the explicit
  seed/snapshot/batch boundary; Qdrant remains RAG-only.
- FastAPI remains the authorization boundary and existing domain services remain
  canonical.
- The four fixed worker jobs and single `src/operations/worker.py` architecture
  are unchanged.
- Existing asset, ticket/SLA, preventive/work-order, inventory, analytics, RAG,
  audit, and in-app notification contracts remain intact.

## Configuration Evidence

PM8 documents and validates:

- `TOKEN_SIGNING_PREVIOUS_SECRET`;
- `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`,
  `DATABASE_POOL_TIMEOUT_SECONDS`;
- `DATABASE_STATEMENT_TIMEOUT_SECONDS`, `DATABASE_LOCK_TIMEOUT_SECONDS`,
  `DATABASE_IDLE_TRANSACTION_TIMEOUT_SECONDS`;
- `OPERATIONAL_OUTBOX_AGE_ALERT_SECONDS`,
  `OPERATIONAL_REPEATED_JOB_FAILURE_THRESHOLD`,
  `OPERATIONAL_ANALYTICS_STALE_SECONDS`,
  `OPERATIONAL_BACKUP_OVERDUE_SECONDS`.

## Checks Intentionally Not Executed

- 15-minute soak profile;
- load-to-first-failure/capacity-limit test;
- mutation-bearing load profile;
- exact live worker termination during a business mutation;
- disk-warning drill;
- real pilot-secret rotation;
- restore with representative non-empty attachment metadata and bytes.

These checks are not passed by inference from unit/integration tests or earlier
reports.

## Internal-Pilot Operating Limits And Open Gates

The checkpoint supports only the tested single-node, batch-first,
internal-pilot boundary. The following release gates remain open:

- named operational/rollback/backup owners;
- incident contact path;
- known-limitation acceptance;
- real non-placeholder pilot secrets;
- bounded soak and capacity-to-first-failure validation;
- representative attachment metadata-plus-byte backup/restore;
- rehearsal on the intended pilot host.

The immutable repository release record is closed by the reviewable PM8 commit
sequence and annotated local `product-milestone-8` tag. Closing that one gate
does not change the overall `NO-GO / NOT YET VERIFIED` decision.

## Rollback Considerations

Before rollback, quiesce API and worker processes and take a separately protected
backup. Downgrading to `20260726_0007` preserves PM1–PM7 tables but removes PM8
redrive requests, backup-validation records, operational alert events/states,
and PM8-only redrive-cycle attempt evidence. Unfinished non-alert redrives return
to dead-letter. Revalidate migration revision, API readiness, worker readiness,
dead-letter state, and PM1–PM7 invariants before restoring traffic.

## Remaining Risks And Milestone Boundary

Single API/worker/PostgreSQL/local attachment storage has no HA. Automated PITR,
managed secrets, centralized observability/on-call routing, distributed
throttling, object storage, malware scanning, external notifications,
multi-tenancy, SSO/MFA, Kubernetes, and cloud deployment remain outside PM8.

PM9 has not started. No PM9 branch, migration, dependency, capability, or
implementation was created by this checkpoint.

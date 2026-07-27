# Product Milestone 9: Internal Pilot Deployment Rehearsal And Ownership

## Status

Product Milestone 9 is an implementation candidate on 2026-07-26. It has not
been checkpointed, tagged, deployed to the intended pilot host or accepted by
operational/business owners.

Final decision:

```text
NO-GO / NOT YET VERIFIED
```

PM9 rehearses an internal pilot. It does not establish production readiness,
an SLA, a capacity guarantee, recovery objectives, model accuracy or business
impact.

## Objective And Product Boundary

PM9 adds deployment, release, load/recovery and organizational evidence tooling
around the PM1–PM8 system. It does not add a business domain or change:

- PostgreSQL transactional authority;
- FastAPI authorization/service boundary;
- CSV seed/snapshot/batch analytics boundary;
- Qdrant RAG-only boundary;
- one `src/operations/worker.py`;
- exactly four scheduled jobs;
- in-app-only notification delivery;
- existing ticket/work-order/inventory independence and append-only rules.

No Redis, Kafka, RabbitMQ, Celery, Kubernetes, cloud platform, HA cluster,
automatic PITR, object storage, malware scanning, SSO/MFA, multi-tenancy,
external alerts, procurement, supplier, accounting, IoT streaming or arbitrary
job execution was added.

## Repository Baseline

| Field | Observed state |
|---|---|
| Branch | `feat/pm9-pilot-deployment-rehearsal` |
| HEAD during implementation | `ad4779e4e21322789e1e7b9d98b485127f1fa95f` |
| Exact local tag at HEAD | `product-milestone-8` |
| PM8 migration head | `20260726_0008` |
| PM9 migration | None in current candidate |
| PM9 candidate commit | `PENDING_PM9_CHECKPOINT` |
| PM9 tag recommendation | `product-milestone-9`; not created |
| Deployment manifest canonical semantic-JSON SHA-256 | `68f7ad8cd51dd7da90a060675eba113c81c11418c91cddbccf8a8800fad14bcb` |
| Push | Not performed |

The PM9 worktree is intentionally dirty with implementation changes. Existing
PM1–PM8 migration history and tag were not rewritten.

## Environment Findings

Inspection used an unidentified Windows 11 developer workstation, not an
approved pilot host:

- 16 logical CPU;
- 15,63 GiB RAM with about 0,92 GiB available at inspection;
- about 11,33 GiB disk free at inspection;
- Docker/Compose available, with no project containers/required ports active at
  inspection;
- Python 3.11.9, Node 22.20.0 and npm 11.17.0;
- no standalone `psql`;
- ignored local `.env` was development-grade and not valid pilot evidence;
- no approved pilot secrets, ownership/incident assignments or existing
  representative attachment fixture.

Dynamic resource values must be measured again. The observed memory state was
not safe for soak/capacity execution.

Checkpoint PostgreSQL evidence used a disposable local PostgreSQL 16 database
whose name ended `_test`. This was not a full pilot Compose deployment and does
not identify the workstation as the intended pilot host.

## Implemented Deployment Contract

- separate [pilot Compose](../../docker-compose.pilot.yml), leaving development
  Compose intact;
- pinned Python/Node frontend image build paths;
- [pilot environment example](../../.env.pilot.example) with placeholders only;
- versioned [manifest](../../deployment/pilot_manifest.json) for release,
  versions, services, ports, volumes, contained paths, jobs, worker/retry,
  alerts, database timeouts, restore and rollback;
- secret-free application release identity on OpenAPI and liveness/readiness;
- pilot settings that reject CSV, development database defaults, weak/missing
  signing secret and unverified release identity;
- deterministic contract/decision validation and draft
  [release record](../../deployment/pilot_release_record.json);
- checkpointable commit provenance resolved from the exact release-tag target,
  with protected-environment/observed-HEAD equality and a post-tag final release
  record instead of a self-referential SHA inside the tagged manifest;
- structured [ownership](../../deployment/operational_ownership.json) and
  [known-limitations](../../deployment/known_limitations.json) records whose
  placeholders intentionally block GO.

No `metadata.create_all()` startup behavior or PM9 migration was added.

## Implemented Rehearsal Tooling

### Deployment

`src.reliability.deployment_rehearsal` provides plan-only default, protected
dotenv parsing, closed Compose operations, explicit execution and host approval,
`_test` empty-data protection, outside-repository evidence, release-aware health
probes and default service stop.

The automated execution currently covers Compose/build/start, migration wait,
`alembic current`, API liveness/readiness, worker readiness, Qdrant readiness
and frontend availability. Without an explicit opt-in it records approved-data,
authentication/RBAC, job, notification and analytics validation as
`not_executed` and fails overall.

The new opt-in `--authenticated-post-start` path requires approved-data
attestation plus an opaque evidence ID, separate operator/restricted-user
credentials and an independent execution guard. Its closed FastAPI checks cover
unauthenticated `401`, release/API/database/worker readiness, login/refresh/
logout, positive and negative RBAC, the exact four-job catalog and declared
enable/dead-letter state, non-empty asset/ticket/work-order/inventory reads,
batch analytics and non-empty owner-isolated notifications. It performs no
business mutation beyond creating/rotating/revoking authentication sessions,
requires HTTPS except for explicitly allowed loopback test HTTP, writes
redacted evidence outside the repository and cleans up the dedicated deployment
after failure.

This path is implemented and unit-tested with mocked HTTP transport. It has not
been executed against a live PM9 stack or the intended pilot host. It does not
restore/seed data, trigger a job, mutate notification state, run a content-level
Qdrant smoke or validate attachment recovery.

### Load And Mutation

- the profile schema rejects a single reliability duration above 900 seconds;
  the configured 900-second soak itself was not executed;
- opt-in 4/8/12/16/20 req/s step load records allow-listed metrics and stops on
  configured degradation/safety observations;
- closed `mutation_rehearsal` types require an isolated PostgreSQL URL ending
  `_test`, PM9 namespace, stable keys, idempotent replay, optimistic-concurrency
  probe, invariant actions, cleanup actions, canonical-data fingerprints and a
  bounded request count;
- generic load targets remain credential-free local paths and reports stay
  outside the repository.

No representative mutation plan was executed against a live PM9 stack.

### Failure, Backup, Disk And Attachments

- three PostgreSQL connection-termination boundary tests passed for job
  completion, outbox delivery and same-transaction ticket/outbox rollback on
  the disposable `_test` database;
- OS/operator-driven backup tooling can feed `pg_dump` output through a
  temporary artifact + checksum publication path and does not add a worker job;
- controlled-writer/checksum/last-good/retention-selection helper tests;
- injected disk warning/critical/dedup/recovery state machine without filling
  disk;
- bounded attachment ZIP archive/inspect/restore with containment, checksum,
  missing/mismatch/orphan detection;
- PostgreSQL-marked authorized non-empty attachment API/archive test passed.

Synthetic disk state is not a durable in-app alert/outbox integration. Scheduled
retention is not automatic deletion. Connection termination did not kill a live
worker process. The attachment test reused original database metadata and did
not restore a paired PostgreSQL dump.

### Secret Rotation

Synthetic signing-key rotation tooling covers current/previous overlap,
previous-key removal, within-window rollback, forward restore, simulated
post-window removal and secret/token-free reports. It explicitly reports that
real time did not elapse and real pilot secrets/database credential rotation
were not exercised.

## Evidence Classification

### Executed Local/Synthetic Evidence

Implementation handoff recorded:

- storage/release configuration and API health: `11 passed`;
- pilot contract: `9 passed`;
- deployment rehearsal and backup schedule: `8 passed`;
- PM9 load safety with adjacent PM8 reliability checks: `24 passed`;
- PM9 drill helpers with adjacent PM8 reliability checks: `19 passed`;
- mutation rehearsal and synthetic secret rotation: `9 passed`;
- adjacent load/authentication regression: `17 passed, 9 skipped`, with one
  existing Starlette TestClient deprecation warning;
- mutation and secret CLI `--help` checks passed;
- PM9 documentation link check: `1 passed`;
- corresponding focused Ruff batches passed;
- static contract command ran and returned expected blockers with
  `NO-GO / NOT YET VERIFIED`.

Final reconciliation additionally recorded:

- deployment/manifest reconciliation: `22 passed`; Ruff, Compose config, Make
  dry-runs and `git diff --check` passed;
- authenticated post-start and its deployment integration: `16 passed`
  focused local unit tests with mocked HTTP transport; no live stack was
  contacted;
- PostgreSQL-marked selection: `73 passed, 239 deselected` on a disposable
  local PostgreSQL 16 database whose name ended `_test`;
- three real `pg_terminate_backend` boundary tests passed: interrupted job
  completion recovered after lease expiry without duplicate execution;
  interrupted outbox delivery recovered with failed and succeeded append-only
  attempts and exactly one notification; and a ticket plus its required outbox
  event rolled back together after connection termination;
- one generated non-empty PDF uploaded through the normal authorized API with
  `201`; one attachment was archived and restored to temporary storage;
  Administrator download returned `200` with matching bytes and Helpdesk
  download returned `403`.

Final verification on the settled worktree additionally passed:

- PM9-focused selection: `103 passed, 3 skipped` without
  `TEST_DATABASE_URL`; those three PostgreSQL interruption tests all passed in
  the full database-enabled run;
- full backend: `374 passed` against a fresh disposable PostgreSQL 16 database
  ending `_test`, with one existing Starlette TestClient deprecation warning;
- full frontend: `112 passed` across 17 files; ESLint passed; Next.js production
  build generated 32 pages, then `.next` was removed;
- repository-wide Ruff check and focused format check for 19 PM9 Python files;
- one Alembic head `20260726_0008`, `current`, `check`, and a clean
  base-to-head migration on a temporary `_test` database;
- pilot Compose syntax validation;
- deterministic manifest/full/release-identity validators, each returning the
  expected nonzero blocking result and exact `NO-GO / NOT YET VERIFIED`.

The settled manifest semantic-JSON SHA-256 is
`68f7ad8cd51dd7da90a060675eba113c81c11418c91cddbccf8a8800fad14bcb`.

The three interruption tests terminated PostgreSQL connections, not a live
worker process. The attachment drill reused its original `_test` PostgreSQL
metadata; it did not restore a paired PostgreSQL dump plus attachment bytes.
These focused counts are not a full-suite or intended-host result.

### Prior PM8 Evidence Only

PM8 established a bounded workstation envelope:

```text
8 concurrent authenticated users
12 requests per second
45 seconds
read-heavy workload
no unexpected errors
```

PM8 also checkpointed full backend/frontend/static/build, migration,
PostgreSQL interruption, redrive/alert and isolated database backup/restore
results documented in the [PM8 release note](product_milestone_8.md).

Those results are historical. They are not PM9 pilot-host evidence, a capacity
limit or an SLA. PM8 attachment metadata was empty.

## PM9 Gate Results

| Gate | Result | Reason |
|---|---|---|
| Deployment manifest/static decision | Executed, intentionally blocking | Placeholder release/owners/acceptance and open critical gates |
| Intended-host deployment | Unverified | Current host not approved/identified |
| Approved data restore/seed | Unverified | Attestation/runtime-read tooling exists; no approved source or live execution |
| Authentication/RBAC deployed smoke | Unverified | Opt-in tooling implemented/unit-tested; not executed on a live PM9 stack |
| Exact four jobs/notifications/analytics deployed smoke | Unverified | Opt-in tooling implemented/unit-tested; not executed on a live PM9 stack |
| Release/rollback/redeploy | Unverified | No intended-environment execution |
| 900-second soak | Unverified | Unsafe current memory margin; no approved host |
| Mutation-bearing workload | Unverified | Tooling exists; no live representative plan/result |
| Capacity/degradation | Unverified | Opt-in test not run; no observed boundary |
| Worker/job/outbox/transaction termination | Partial boundary evidence; broader gate open | Three real connection-termination tests passed on disposable PostgreSQL 16 `_test`; no live worker-process kill |
| Scheduled backup/service account | Unverified | No OS schedule or pilot owner |
| Controlled backup failure | Local boundary passed; pilot gate open | Real valid `pg_dump` exit `0` followed by invalid-database exit `2` preserved the validated index and left no partial; not run on the intended host/service account |
| PM9 backup/restore | Unverified | No paired PostgreSQL dump plus attachment metadata/bytes restore |
| Disk warning/recovery | Unverified | Synthetic injected state only; no durable operational alert path rehearsal |
| Real pilot secret rotation | Unverified | Synthetic values only; no restart/database credential/elapsed window |
| Representative attachment restore | API/archive boundary passed; paired restore open | Authorized non-empty upload/archive/restore/download passed, but original `_test` metadata was reused and no paired PostgreSQL restore ran |
| Operational ownership | Unverified | Nine assignments remain placeholders |
| Incident path/support coverage | Unverified | Unconfigured/unconfirmed |
| Known-limitations acceptance | Unverified | All critical limitations pending |

## Load And Capacity Result

No PM9 request count, latency percentile, throughput, error rate, pool pressure,
memory trend, worker lag, outbox drain, mutation success, conflict rate or
degradation point was measured. See [pilot load results](../pilot_load_results.md).

## Backup, Disk And Attachment Result

No scheduled backup ran under an intended service account and no PM9 separate
PostgreSQL restore was performed. A local disposable `_test` drill invoked real
`pg_dump`: one valid scheduled dump passed, then an invalid database failed with
exit `2` while the last validated index and immutable pair remained unchanged
and no partial remained. Every temporary backup artifact was removed. This does
not close the pilot-host/service-account gate. Disk tests used injected values
only; no durable disk-alert path was exercised.

The authorized attachment boundary did pass: a generated PDF upload returned
`201`, one attachment was archived/restored to temporary storage,
Administrator download returned `200` with matching bytes and Helpdesk
download returned `403`. Because the drill reused the original `_test`
metadata, it is not evidence of a paired PostgreSQL dump plus metadata/bytes
restore.

See [pilot backup schedule](../pilot_backup_schedule.md) and
[attachment recovery](../pilot_attachment_recovery.md).

## Ownership And Acceptance

All required ownership roles are unassigned. Incident channels, escalation and
support coverage are unconfigured. Every limitation in the structured register
is pending. No names, contacts or approvals were invented.

See [operational ownership](../operational_ownership.md) and
[known-limitations acceptance](../known_limitations_acceptance.md).

## Release And Rollback

The candidate keeps schema `20260726_0008`. Preferred rollback is exact PM8
application rollback at the same revision. If PM9 data/schema compatibility
requires it, use a separately protected, restore-validated backup; the manifest
does not allow database downgrade by default.

No deploy→PM8 rollback→PM9 redeploy sequence ran. Candidate commit/tag remain
pending and the release record remains draft. See
[release rehearsal](../pilot_release_rehearsal.md).

The source-checkout protocol requires an exact tag, matching full SHA and clean
worktree, but current application/frontend and base-service image references
remain mutable tags. No verified PM8 application/frontend image digest is
recorded, so the rollback path is documented but not yet executable as an
immutable-artifact rehearsal.

## Cleanup Status

The attachment test explicitly removed the restored bytes, its metadata through
the API and the temporary test archive. PostgreSQL-marked checks used a
disposable database whose name ended `_test`; that isolation does not prove
intended-host or deployment cleanup.

The local real-`pg_dump` drill removed its dump, metadata, validated index and
temporary directory. No intended-host deployment, load profile,
release/rollback rehearsal or intended-service-account backup drill ran.
Therefore this checkpoint makes no generic host, process, container, volume or
deployment cleanup claim.

No commit, tag or push was performed by PM9 implementation.

## Changed-Path Categories

Current candidate changes are organized under:

- release/deployment: `Dockerfile`, `frontend/Dockerfile`,
  `docker-compose.pilot.yml`, `.env.pilot.example`, `deployment/`;
- release/settings/health: `src/release.py`, API/configuration/repository files;
- reliability: deployment, contract, load/mutation, backup, disk, secret and
  attachment tooling under `src/reliability/`;
- focused tests under `tests/`;
- this README and PM9/operator documentation under `docs/`.

Exact final changed paths must come from `git status --short` after concurrent
work is complete.

## Remaining Risks

- no evidence from intended pilot host or representative pilot data;
- no live execution of the implemented authenticated post-start validation;
- no completed owner/incident/support/acceptance model;
- no real pilot secrets or rotation;
- no sustained/mutation/capacity boundary;
- no live worker-process kill; connection-termination boundaries alone do not
  close that gate;
- no scheduled backup or failed-backup rehearsal under the intended service
  account; local real-`pg_dump` evidence does not establish that boundary;
- no durable disk-alert path or paired PostgreSQL dump plus non-empty attachment
  metadata/bytes recovery;
- no release/rollback/redeploy rehearsal;
- no recorded immutable image digest for the PM9 deployment or PM8
  application/frontend rollback artifact;
- single API/worker/PostgreSQL/local storage without HA or automatic PITR;
- in-app-only alerts and no centralized observability/on-call platform.

## Recommended Next Work

Do not start a feature milestone. Complete the PM9 execution/ownership closure
on an approved intended or pilot-equivalent host:

1. assign owners, channels, coverage and limitation acceptance;
2. provision protected real pilot configuration;
3. execute deploy/auth/RBAC/jobs/notifications/analytics rehearsal;
4. execute release rollback/redeploy;
5. run bounded soak, mutation and approved step load;
6. execute live worker-process termination, controlled failing `pg_dump` under
   the intended service account, durable disk-alert path, real pilot
   signing/database secret rotation and paired PostgreSQL dump plus attachment
   metadata/bytes restore;
7. run full regressions/static/build/migration/scans/cleanup;
8. regenerate/review release record and reevaluate the deterministic decision.

Until every mandatory gate has evidence, the decision remains exactly:

```text
NO-GO / NOT YET VERIFIED
```

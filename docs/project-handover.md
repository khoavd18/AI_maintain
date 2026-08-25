# Final Project Handover

## Status

Roadmap Stages 1-12 are complete at the working-tree level. Stage 12 is an
uncommitted final portfolio candidate on branch
`release/stage12-final-portfolio`, based on the approved Stage 11 checkpoint
`33ac82efbe5f37ed07d412ba2554fd94bde0b6f3`.

No Stage 12 commit, tag, push, or public release is included in this handover.
Those remain separate approval gates. There is no Stage 13.

## Checkpoint lineage

| Checkpoint | Commit | Scope |
|---|---|---|
| Stage 9 | `9d556946d33bb7340dc28feee33b2fb5cebc5c02` | 1.1M-work-order Data Platform integration and scale evidence |
| Stage 10 | `3de9e53d072097665c9ecf718ddd4c22d418b4e6` | Multi-domain scale, reliability, dbt, and concurrent analytics |
| Stage 11 | `33ac82efbe5f37ed07d412ba2554fd94bde0b6f3` | Analytics API connection/contention optimization and evidence |
| Stage 12 | uncommitted | Final README, architecture, runbooks, portfolio, manifest, verification |

Two protected local modifications are explicitly outside the Stage 9-12
release lineage:

- `src/llm/prompt_builder.py`;
- `tests/test_grounded_generation_repair.py`.

Their required hashes are recorded in [release-manifest.json](release-manifest.json).
They must remain unstaged and uncommitted unless separately reviewed.

## Implemented capabilities

### Operational maintenance and AI

- FastAPI authentication, RBAC, CSRF/session handling, audit, health, readiness,
  metrics, and safe structured logging.
- PostgreSQL-backed assets, locations, attachments, QR lookup, tickets, SLA,
  preventive plans, checklist versions, work orders, maintenance logs, spare
  parts, stock, reservations, movements, jobs, outbox, and notifications.
- Named lifecycle actions and complete repository transaction ownership with
  locks, idempotency, audit/outbox coupling, commit, and rollback.
- Closed four-job background-worker catalog with durable leases, retry/dead
  letter, heartbeat, and operator visibility.
- Next.js authenticated UI plus a legacy development-only Streamlit status
  surface.
- Batch anomaly/risk analytics and grounded document retrieval with relevance,
  citation, safety, and deterministic-fallback boundaries.

### Data Platform and analytics

- Isolated `analytics_source` compatibility views and independent Alembic
  history.
- Tuple-watermark incremental extraction with immutable/checksummed objects.
- Restartable chunk-level COPY/audit loading and raw-before-watermark contract.
- Stage 9 nine-task and Stage 10 nineteen-task Airflow DAGs.
- dbt staging, dimensions, facts, marts, generic tests, and singular integrity
  assertions.
- Controlled failure recovery, empty rerun, cross-layer reconciliation, and six
  atomic domain watermarks.
- Authenticated site-scoped Analytics API with an exact query catalogue,
  read-only transactions, bounded concurrency, pool observability, and a short
  authorization-safe cache.

## Important files

| Area | Canonical path |
|---|---|
| Recruiter overview | `README.md` |
| Architecture | `docs/architecture.md` |
| Demo | `docs/demo-runbook.md` |
| Operations | `docs/operations-runbook.md` |
| Portfolio | `docs/portfolio/project-summary.md` |
| Interview guide | `docs/portfolio/interview-guide.md` |
| Release checklist | `docs/final-release-checklist.md` |
| Machine manifest | `docs/release-manifest.json` |
| Final verifier | `scripts/verify_final_release.ps1` |
| Application migrations | `migrations/versions/` |
| Data Platform migrations | `data_platform/migrations/versions/` |
| Airflow DAGs | `data_platform/airflow/dags/` |
| dbt project | `data_platform/dbt/maintenance_analytics/` |
| Analytics adapter/API | `src/analytics/domain_adapter.py`, `src/api/routers/domain_analytics.py` |

## Verified evidence map

| Evidence | Source | Classification |
|---|---|---|
| Stage 9 counts/index/Airflow/dbt | `docs/benchmark-results-1m.json` | Historical local synthetic benchmark |
| Stage 10 domains/recovery/query/dbt/tests | `docs/benchmark-results-domain-scale.json` | Historical local synthetic benchmark |
| Stage 10 generated chunks/bytes/checksums | `docs/benchmark-manifest-domain-scale.json` | Historical manifest summary |
| Failure and retry protocol | `docs/reliability-failure-recovery.md` | Historical controlled-failure evidence |
| Stage 11 API samples/medians/connections | `docs/benchmark-results-api-stage11.json` | Historical authenticated load benchmark |
| Public final metrics | `docs/release-manifest.json` | Stage 12 aggregate mapped to source evidence |
| Current safe review | `scripts/verify_final_release.ps1 -Mode Offline` | Rerunnable without Docker |

Core verified metrics:

- 1,100,000 final work orders and 1,110,000 raw versions;
- 7,728,467 generated/copied Stage 10 rows across 145 chunks;
- seven final domain counts reconciled, eight integrity checks at zero;
- 19 Airflow tasks with baseline, controlled retry, and empty rerun evidence;
- 26 dbt models + 433 data tests, `459/459 PASS`;
- 2,052 historical Stage 10 validation checks;
- Stage 11 50-client p95 `-34.5143%`, RPS `+38.9827%`;
- 900 requests, zero errors/timeouts, 774/774 valid analytics payloads;
- maximum PostgreSQL connections reduced from 33 to 23.

All are synthetic project/lab metrics, not production-company outcomes.

## Reproduction options

### Offline review

```powershell
Set-Location D:\code\rag\ai_maintain_copilot
.\scripts\verify_final_release.ps1 -Mode Offline
```

This is the default handover path. It validates required documents, metrics,
evidence paths, links, JSON, security scans, lineage, protected hashes, and
tracked-artifact boundaries. Missing Docker/Airflow/dbt is reported as `SKIP`.

### Local application read-only review

```powershell
.\scripts\verify_final_release.ps1 -Mode LocalReadOnly
```

This adds non-mutating health probes only when the local service is already
available. It never starts or stops a container.

### Preserved scale read-only review

```powershell
.\scripts\verify_final_release.ps1 -Mode ScaleReadOnly
```

This adds non-mutating scale API/Docker observations only when available. Use
[operations-runbook.md](operations-runbook.md) for read-only watermark and
reconciliation SQL.

### Full regeneration

Full Stage 9/10 regeneration is intentionally not a normal handover step. It is
disk-, memory-, and time-intensive and must have a separate benchmark plan.
Historical artifacts already contain generation, COPY, Airflow, dbt, failure,
query, resource, and checksum evidence.

## Docker-unavailable fallback

Stage 12 is designed to complete with Docker unavailable. Compose files can be
parsed when the CLI exists, but runtime health, Airflow DagBag, dbt-in-container,
watermark, and database queries should be `SKIP` rather than triggering a
service start.

Use tracked machine evidence and static source inspection. Do not fabricate a
live state from historical records; label it explicitly as historical.

## Historical versus live state

- Stage 9-11 pipeline, dbt, load, connection, and container observations are
  historical evidence from their recorded runs.
- Stage 12 Offline checks are current filesystem/Git/tooling validation.
- A future live release must rerun the appropriate health, migration, security,
  backup/restore, and representative load gates in its target environment.
- Historical AWS RDS learning resources were torn down. There is no live RDS
  deployment or endpoint to hand over.

## Generated-data boundary

The following must remain ignored/untracked:

- `.env` and environment-specific secret files;
- `data/scale/`, `data/analytics_input/`, attachments, raw/processed generated
  CSVs, and manual benchmark outputs;
- dbt `target/`, `logs/`, and packages;
- Python/test/lint caches and local virtual environments;
- dumps, backups, partial files, restore SQL, load JSON, rehearsal logs, and
  pilot evidence.

Tracked JSON under `docs/` is the sanitized evidence summary, not the generated
dataset.

## Known limitations

- Local synthetic evidence only; no production SLA, uptime, adoption, business
  impact, or prevented-failure claim.
- No real-company data governance, owner acceptance, retention, consent, or
  classification program.
- No SSO/MFA, production workload identity, managed secrets, or private-cloud
  deployment.
- No multi-node HA, failover, production PITR objective, centralized monitoring,
  paging, or on-call validation.
- Stage 11 cache is process-local and TTL-only.
- External model quality and production mixed read/write capacity were not
  validated.

## Production recommendations

1. Establish domain ownership, data contracts, classification, lineage,
   retention, consent, and quality SLOs for real maintenance data.
2. Deploy inside private networking with least-privilege workload identities;
   keep databases and management surfaces non-public.
3. Use managed secrets and stable encryption keys with rotation and recovery
   ownership.
4. Design HA, PITR, backup immutability, tested RPO/RTO, and disaster recovery.
5. Add centralized metrics/logs/traces, alerts, dashboards, runbooks, and staffed
   incident escalation.
6. Add CI/CD and infrastructure as code with policy, migration, security,
   evidence, and rollback gates.
7. Introduce a distributed cache only when required by measurement, with tenant
   isolation and coherent invalidation.
8. Run production-scale mixed-workload load, soak, failure, and recovery tests
   before defining capacity or SLA.

## Release governance

The final checklist is [final-release-checklist.md](final-release-checklist.md).
A Stage 12 commit, optional tag, and push require explicit future approvals.
Do not combine them into this documentation stage.

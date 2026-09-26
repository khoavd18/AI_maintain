# Final Project Handover

## Status

Roadmap Stages 1-12 are complete. Stage 12 is committed at
`cfdfa21a384073740d41528f470029a9746fce46` on branch
`release/stage12-final-portfolio`, based on the approved Stage 11 checkpoint
`33ac82efbe5f37ed07d412ba2554fd94bde0b6f3`.

At the 2026-08-27 local review, no tag pointed at that Stage 12 commit and the
branch had no configured upstream. A remote push or public release was not
verified and must not be inferred from the local commit. There is no Stage 13.

## Checkpoint lineage

| Checkpoint | Commit | Scope |
|---|---|---|
| Stage 9 | `9d556946d33bb7340dc28feee33b2fb5cebc5c02` | 1.1M-work-order Data Platform integration and scale evidence |
| Stage 10 | `3de9e53d072097665c9ecf718ddd4c22d418b4e6` | Multi-domain scale, reliability, dbt, and concurrent analytics |
| Stage 11 | `33ac82efbe5f37ed07d412ba2554fd94bde0b6f3` | Analytics API connection/contention optimization and evidence |
| Stage 12 | `cfdfa21a384073740d41528f470029a9746fce46` | Final README, architecture, runbooks, portfolio, manifest, verification |

Two protected local modifications are explicitly outside the Stage 9-12
release lineage:

- `src/llm/prompt_builder.py`;
- `tests/test_grounded_generation_repair.py`.

Their required hashes are recorded in [release-manifest.json](release-manifest.json).
They must remain unstaged and uncommitted unless separately reviewed.
This is the historical hash-protected exception list, not an exhaustive account
of the current working tree.

## Post-Stage-12 Data Platform ownership checkpoint — 2026-08-27

This is an unnumbered, **uncommitted working-tree maintenance checkpoint** after
the committed Stage 12 portfolio record. It is not a Stage 13 and does not
change the Stage 9-12 lineage, benchmark JSON, release manifest, or historical
validation totals. Its changes require their own review and commit decision.

The multi-domain ingestion implementation is now organized by capability under
`data_platform/ingestion/domains/`: catalogue, input safety, extraction, raw
loading, source counts/integrity validation, reconciliation/watermark
finalization, durable run tracking, and CLI dispatch.
`data_platform/domain_pipeline.py` remains the historical facade for existing
imports and `python -m data_platform.domain_pipeline` commands. The Airflow DAG
ID, command surface, database schema, migration head, dbt project, and
documented transaction boundaries remain compatibility seams.

Current maintainer guidance is in
[Data Platform Code Ownership](data-platform-code-ownership.md). It records the
whole raw-load and all-domain watermark transactions, the safe procedure for
adding a domain, and five deferred correctness findings. Those findings were not
fixed or reclassified by the structural move. Validation for this checkpoint
must be reported from commands actually executed against the current tree; none
of the historical Stage 9-11 benchmark or test totals may be presented as a new
run.

### Validation executed for this checkpoint

The following checks were executed on 2026-08-27 against this uncommitted
structural-refactor tree:

| Check | Current result |
|---|---|
| Data Platform tests | `94 passed`, with the existing Starlette/httpx deprecation warning |
| Architecture boundaries | `19 passed` |
| Complete repository test suite | `1,410 passed, 87 skipped`, with the same existing warning |
| Ruff | `python -m ruff check .` passed |
| Python compilation | `data_platform` and `src/analytics` passed `compileall` |
| Scale Compose definition | `docker compose -f docker-compose.scale.yml config --quiet` passed |
| Historical CLI facade | `python -m data_platform.domain_pipeline --help` passed |
| Live Airflow import check | Existing `stage9-airflow-api-server` returned `[]` import errors |
| Documentation checks | Link and release-document selection passed; `git diff --check` passed |

The PostgreSQL data, Docker volumes, historical benchmark artifacts, DAG runs,
and dbt warehouse were not mutated. No DAG, dbt build, fixture regeneration, or
destructive PostgreSQL setup was run for this structural checkpoint. The 87
skips include environment-gated PostgreSQL integration tests and are not
presented as newly executed database validation.

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
- Historical Stage 10 evidence includes a controlled failure/retry run and an
  empty rerun, plus cross-layer reconciliation and six atomic domain watermarks.
  The current controlled-failure marker persistence limitation is documented in
  [Data Platform Code Ownership](data-platform-code-ownership.md#deferred-correctness-findings);
  recovery is not presented as a current unconditional guarantee.
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
| Scale Docker topology | `docker-compose.scale.yml` |
| Current multi-domain ingestion owner | `data_platform/ingestion/domains/` |
| Historical Stage 9 work-order ingestion | `data_platform/pipeline.py` |
| Data Platform ownership guide | `docs/data-platform-code-ownership.md` |
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
- seven final count keys reconciled (legacy Stage 9 `work_orders` plus six
  Stage 10 domains), eight integrity checks at zero;
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
Stage 12 is already committed locally. A future tag, push, or public release,
and any commit for the current uncommitted Data Platform checkpoint, remain
separate approval gates.

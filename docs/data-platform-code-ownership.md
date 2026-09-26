# Data Platform Code Ownership

## Purpose and status

This is the current maintainer handoff for the multi-domain batch ELT code.
Implementation ownership lives under `data_platform/ingestion/domains/`; the
historical Stage 10 evidence and its measured results are unchanged. This
structural refactor does not claim a new benchmark run, production readiness,
or resolution of the deferred correctness findings listed below.

The workflow remains batch-first and bounded to the existing six analytical
domains:

- work-order status history;
- tickets;
- ticket events;
- spare parts;
- inventory movements;
- work-order costs.

These are the six independently watermarked Stage 10 domains. The historical
seven-count evidence additionally includes the legacy Stage 9 `work_orders`
count; it does not represent a seventh Stage 10 watermark.

PostgreSQL remains the structured source and analytical store in the isolated
scale topology. Airflow orders the work, dbt owns transformations and data
tests, and FastAPI retains authentication and site-scoped serving. This package
does not replace the application worker, application repositories, or RAG.

## Supported authoring model and scope

The supported path is batch **ELT**:

1. Python performs bounded extraction, technical validation, immutable object
   publication, checksum verification, and source-shaped raw loading.
2. dbt staging owns typing, normalization, and latest-version selection.
3. dbt warehouse and marts own business transformations, analytical grains, and
   data tests.

Do not put business metric logic in `extraction.py` or `raw_loading.py`, and do
not create a parallel generic ETL framework, arbitrary DAG, or fifth application
worker job. If a real source requires transformation before raw storage, stop
and define a separately reviewed ETL data contract, lineage, replay behavior,
and transaction boundary; the current ELT package is not that authorization.

The dbt source directories, PostgreSQL schemas, Docker volume, and generated
artifact paths are mapped in
[Data Platform Integration](data-platform-integration.md#dbt-source-code-và-runtime-storage).

## Adjacent owners outside this package

`data_platform/ingestion/domains/` owns the current Stage 10 operational domain
ingestion path, not every historical or benchmark utility under
`data_platform/`:

| Path | Owns | Relationship to this package |
|---|---|---|
| `data_platform/pipeline.py` | Historical Stage 9 work-order ingestion and its nine-task CLI contract | Preserve separately; do not move its single-watermark rules into the Stage 10 package. |
| `data_platform/domain_generator.py` | Deterministic synthetic Stage 10 fixture generation | Benchmark/demo input only; not application truth or operational extraction. |
| `data_platform/domain_loader.py` | Synthetic fixture migration/bootstrap COPY and manifest replay | Historical CLI remains; source count/integrity functions are compatibility re-exports from `source_validation.py`. |
| `data_platform/migrations/` | Data Platform-owned source views, raw/audit relations, constraints, and indexes | Independent Alembic history; never use it to mutate application schema design. |
| `data_platform/object_store.py` | Local/S3 object-store adapters and checksum primitives | Used through the existing bounded storage seam; it does not own pipeline lifecycle. |
| `data_platform/orchestration/airflow_callbacks.py` | Metadata-only retry/failure callbacks | Delegates to the stable CLI; it does not own ingestion transactions. |
| `data_platform/airflow/dags/` | Existing Stage 9 and Stage 10 Airflow control flow | May import the closed catalogue and invoke CLIs; no row payloads in XCom. |
| `data_platform/dbt/maintenance_analytics/` | Staging, warehouse, marts, and dbt data tests | Owns analytical transformation after raw load. |
| `src/analytics/domain_adapter.py` and `src/api/routers/domain_analytics.py` | Authenticated, bounded analytical reads | Consumer boundary only; never an ingestion or transformation owner. |

## Current ownership map

| Module | Owns | Must not own |
|---|---|---|
| `catalog.py` | Closed `DomainSpec` catalogue: source view, raw table, ordered columns, identity column, and warehouse relation | Runtime discovery, caller-defined SQL, or lifecycle state |
| `safety.py` | Run-ID validation and bounded credential redaction for audit text | Database state, filesystem publication, or business transformations |
| `extraction.py` | Lower-watermark reads, deterministic batch identity, ordered source COPY, immutable object publication, and extraction-batch metadata | Raw mutation, dbt execution, or watermark advancement |
| `raw_loading.py` | Checksum validation, temporary COPY buffer, idempotent raw insert, and raw-load batch state | Warehouse transformation or final watermark advancement |
| `source_validation.py` | Read-only source counts and source-domain integrity gates | Raw/warehouse mutation, watermark advancement, or CLI parsing |
| `reconciliation.py` | Cross-layer count checks and the all-domain watermark-finalization transaction | Airflow scheduling, arbitrary query execution, or run CLI parsing |
| `run_tracking.py` | Durable start, retry, failure, completion, and read-only run-state projection | Extract/load implementation or dbt models |
| `cli.py` | Stable argument parsing and command dispatch | SQL, transaction logic, or duplicated workflow rules |
| `__init__.py` | Narrow package exports for callers | A second implementation or orchestration layer |

The dependency direction is:

```text
cli
|-- extraction -------> catalog, safety
|-- raw_loading ------> catalog, safety, extraction
|-- reconciliation ---> catalog, safety, source_validation
|-- run_tracking -----> catalog, safety
`-- source_validation -> shared settings and read-only database boundary

__init__ -> catalog
```

Capability modules may use `DataPlatformSettings`, the PostgreSQL connection
boundary, and the object-store port. They must not import the Airflow DAG. The
DAG may import the closed catalogue and invoke the stable CLI, but row payloads
must never pass through XCom.

## Historical facade

`data_platform/domain_pipeline.py` remains the compatibility facade. Preserve
it because historical runbooks, tests, callbacks, and Airflow shell commands
use:

```powershell
python -m data_platform.domain_pipeline <command> ...
```

The facade re-exports the established public and characterized private names
and delegates CLI execution to `data_platform.ingestion.domains.cli`. New
workflow implementation must go into the owning capability module, not back
into the facade. Do not change the command names, JSON output shape, DAG ID, or
task IDs as part of a structural cleanup.

The facade aliases preserve direct imports. Tests that replace an internal
collaborator must patch it in its owning capability module; facade aliases are
not a second dependency-injection layer.

Stage names in this facade, database records, Compose services, and historical
evidence are compatibility identifiers. They do not justify naming new generic
implementation modules `stage9` or `stage10`.

## Transaction and publication boundaries

These boundaries are part of the operational contract and must remain visible
in code and tests:

1. Extraction reads a committed lower tuple and publishes one immutable object.
   It then records extraction metadata. Object publication and the audit insert
   are separate systems and are not described as one atomic transaction.
2. `load_raw_domain` owns one PostgreSQL transaction containing the temporary
   COPY, idempotent raw insert, and extraction-batch status update. Do not split
   raw rows and their batch state across commits.
3. The explicit controlled-failure hook occurs only after the raw-load
   transaction has committed. It is test/recovery behavior, not a general
   workflow extension point.
4. `reconcile_run` reads source/raw/warehouse counts and records the observed
   counts. It does not advance a watermark.
5. `finalize_watermarks` owns one PostgreSQL transaction for all six domains. It
   locks all six run-batch rows. For each non-empty batch it locks the current
   watermark row, verifies the lower tuple, advances idempotently, and marks the
   batch `complete`. Empty batches do not lock or advance a watermark and remain
   `empty` with a completion timestamp. Partial domain finalization is not an
   allowed design.
6. `complete_run`, `fail_run`, and `retry_run` are separate durable run-state
   transactions. Airflow ordering remains part of the current completion gate;
   see the deferred proof limitation below.

Moving functions between files must not divide the raw-load transaction or the
all-domain finalization transaction. Any future repository abstraction must
represent each as one whole command.

## Adding a domain safely

Adding a domain is a data-contract change, not just a new catalogue entry.
Proceed in this order:

1. Define the business grain, stable identity, source availability timestamp,
   deterministic tie-breaker, allowed fields, data owner, retention, and
   reconciliation rule. Do not ingest reporter contact details or secrets.
2. Add a Data Platform Alembic revision for the source compatibility view, raw
   relation, constraints, indexes, and audit requirements. Do not modify the
   application schema through Data Platform migration history.
3. Add exactly one `DomainSpec` to `catalog.py`. Keep relation names closed and
   columns ordered; callers must never supply a relation or SQL fragment.
4. Extend source counts and domain integrity validation in
   `data_platform/ingestion/domains/source_validation.py`. If source, raw, and
   warehouse grains differ, encode and test the explicit reconciliation
   expression rather than comparing unrelated row counts.
5. Extend the closed raw and warehouse count projections in
   `data_platform/ingestion/domains/reconciliation.py`; adding only a catalogue
   entry is insufficient. Test the source/raw/warehouse grain mapping.
6. Add the dbt staging model, warehouse dimension/fact, optional mart, schema
   tests, and singular reconciliation tests. Keep staging as views and
   warehouse/marts as tables unless an approved, measured change says otherwise.
7. Add deterministic synthetic fixture generation/loading only when the domain
   needs local benchmark coverage. Fixture records are not application truth.
8. Confirm the generated Airflow extract/load tasks, dependency edges, retry
   callback, timeouts, and metadata-only XCom behavior.
9. Extend the authenticated allow-listed analytics catalogue only when a
   bounded consumer query is required. Keep parameter binding, site scope,
   date/row limits, read-only transactions, and cache authorization context.
10. Update this ownership guide, the integration mapping, and current validation
   evidence. Never rewrite the historical Stage 9-12 metrics: a seventh domain
   would change the current DAG, not the historical 19-task result.

## Safe validation

Start with non-mutating and focused checks from the repository root:

```powershell
.\.venv\Scripts\python.exe -m data_platform.domain_pipeline --help
.\.venv\Scripts\python.exe -m compileall -q data_platform
.\.venv\Scripts\python.exe -m ruff check data_platform tests\data_platform
.\.venv\Scripts\python.exe -m pytest tests\data_platform
docker compose -f docker-compose.scale.yml config --quiet
```

When Airflow is already available, validate imports without triggering a DAG:

```powershell
docker exec stage9-airflow-api-server `
  airflow dags list-import-errors --output json
```

Use `dbt parse` as the lightweight project check. The checked-in dbt profile
requires `DATA_PLATFORM_DB_PASSWORD`; a host shell does not automatically load
it from `.env`. Either inject the secret into the current process from an
approved local secret source, or, when the existing Airflow container is already
running, use its configured environment without printing the value:

```powershell
docker exec stage9-airflow-api-server `
  dbt parse `
  --project-dir /opt/maintenance-platform/data_platform/dbt/maintenance_analytics `
  --profiles-dir /opt/maintenance-platform/data_platform/dbt/profiles `
  --target scale --no-partial-parse
```

Do not hardcode or print the password. Run `dbt build`, PostgreSQL integration
tests, pipeline retries, or regeneration only against the dedicated isolated
scale/test database and only when that work is explicitly approved. The fresh
Compose default and preserved benchmark database names are distinguished in
[Data Platform Integration](data-platform-integration.md). Follow
[Operations and Reproduction Runbook](operations-runbook.md) for resource
safeguards.

For a structural refactor, characterize before and after:

- package exports and historical facade import identity;
- CLI commands, arguments, exit behavior, and JSON projections;
- closed domain catalogue contents and ordering;
- DAG ID, task IDs, dependencies, callbacks, retries, and timeouts;
- raw-load commit/rollback ordering and idempotent replay;
- all-domain watermark locks, monotonic advancement, empty batches, and rollback;
- deterministic fixture checksums and dbt relation/test contracts.

Do not run `down --volumes`, prune Docker, truncate preserved relations, reset a
watermark, or label Stage 9-11 evidence as a newly executed validation.

## Deferred correctness findings

The package extraction preserves existing behavior. The following findings are
known and intentionally deferred; this refactor does **not** claim they are
fixed:

1. The controlled-failure marker and run-state updates are followed by an
   exception raised inside the PostgreSQL connection context. The connection
   helper rolls that transaction back, so persistence of those marker updates
   is not currently guaranteed even though the preceding raw load is committed.
2. Extraction records an upper tuple before COPY, but the COPY query is bounded
   only by the lower tuple. Under PostgreSQL `READ COMMITTED`, rows committed
   during extraction can be copied beyond the recorded upper tuple. A future
   correction needs a characterized snapshot or explicit upper-bound design.
3. Watermark finalization and run completion do not have a database-level proof
   that reconciliation succeeded for that exact run. Current Airflow task
   ordering supplies the control-flow gate, but direct/out-of-order commands are
   not equivalently proven.
4. The S3 adapter publishes an object but the raw loader has no object-store
   `get` path after the local source file is deleted. S3-backed retry/load is
   therefore not an end-to-end supported claim.
5. Immutable object publication and insertion of its extraction-audit row have
   a crash window. A crash can leave an unreferenced object; there is no atomic
   cross-system commit or documented orphan-reconciliation process yet.

Each item requires a separately scoped contract, failure-injection tests, and
isolated PostgreSQL/object-store validation. Do not fold a partial correction
into an unrelated package move.

## Historical evidence boundary

The verified Stage 9-12 counts, timings, DAG sizes, dbt totals, load results,
and API performance remain historical evidence. Their canonical sources are
[Data Platform Integration](data-platform-integration.md),
[Stage 10 domain scale](stage10-domain-scale.md),
[Stage 11 API performance](stage11-api-performance.md), and the
[Stage 12 release manifest](release-manifest.json). This guide documents current
code ownership only and does not supersede or rerun those artifacts.

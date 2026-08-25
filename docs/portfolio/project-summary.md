# Portfolio Project Summary

## Recommended title

**AI Maintenance Copilot and Batch Analytics Data Platform**

Use the subtitle: *A local synthetic portfolio project combining maintenance
workflows, grounded RAG, Airflow, dbt, PostgreSQL, and measured API performance.*

## 30-second pitch

I built an end-to-end maintenance engineering project with two deliberately
bounded planes. The operational plane uses FastAPI, PostgreSQL, RBAC, durable
jobs, a Next.js UI, and grounded document retrieval for maintenance workflows.
The analytics plane uses tuple-watermark extraction, checksum-verified batch
artifacts, Airflow, dbt, and a read-only Analytics API. On a synthetic laptop
dataset of 7.7M+ generated rows, I validated failure recovery, 459/459 dbt
nodes, and an API optimization that reduced 50-client p95 by about 34.5% while
raising RPS by about 39%.

## 2-minute technical explanation

The application keeps transactional maintenance state in PostgreSQL: assets,
tickets, SLA state, preventive plans, work orders, maintenance logs, inventory,
jobs, audit, outbox, and notifications. FastAPI owns HTTP authentication and
authorization; application services own orchestration; repositories retain
sessions, row locks, idempotency, audit/outbox coupling, and commit/rollback.

For structured analytics, isolated `analytics_source` views feed incremental
extractors. A tuple watermark prevents timestamp-tie loss, each published batch
has a checksum, and raw rows plus chunk audit commit before any watermark
advance. Airflow coordinates six domain extract/load pairs, dbt run/test,
reconciliation, and atomic finalization. A controlled failure after raw
`ticket_events` commit resumed with zero duplicate insertion.

dbt models typed staging, dimensions, facts, and marts for work orders, status
duration, ticket SLA, inventory, costs, and reliability. Stage 10 produced 26
models and 433 tests, with all 459 build nodes passing. Structured metrics stay
in PostgreSQL/dbt. Manuals and SOPs use hybrid document retrieval and grounded
responses; Qdrant is not used as a substitute for relational analytics.

Finally, I profiled the authenticated Analytics API. Direct SQL was fast, but
two workers multiplied oversized app pools and direct query slots. A bounded
four-configuration experiment selected two workers, pool `6+0`, six analytics
slots, and a five-second authorization-safe process-local cache. The median
50-client p95 fell from 4,284.3778 ms to 2,805.6529 ms and RPS rose from 41.5979
to 57.8139, with zero errors/timeouts and maximum PostgreSQL connections reduced
from 33 to 23.

## Recruiter-friendly explanation

This project shows that I can connect product requirements to data engineering
and software engineering decisions. I built transactional APIs and UI flows,
designed reliable incremental pipelines, modeled analytical data, automated
quality checks, diagnosed performance using measurements, and packaged the
result with reproducible evidence and honest limitations.

The scale figures are deterministic project/lab results—not production-company
outcomes. That distinction is part of the engineering work: every public metric
maps to a tracked JSON report.

## Data Engineer interviewer explanation

The strongest Data Engineering signal is the incremental/recovery contract:

- isolated source views prevent analytics ownership from leaking into OLTP;
- tuple watermarks `(updated_at, entity_id)` avoid missing equal-timestamp rows;
- immutable objects and SHA-256 make extraction replayable;
- chunk audit and COPY support restart without reloading committed chunks;
- raw commit precedes finalization, so retries do not skip data;
- Airflow separates six domains and converges before dbt/reconciliation;
- dbt enforces grain, chronology, relationships, business semantics, and
  cross-layer count equality;
- machine evidence records generation, COPY, failure recovery, query plans,
  resource observations, and checksums.

The measured Stage 9 watermark index improved p50 by 24.33x and p95 by 13.41x.
Stage 10 generated and copied 7,728,467 rows across 145 chunks and verified all
seven final domain counts.

## Software Engineer interviewer explanation

The strongest Software Engineering signal is explicit ownership:

- FastAPI routes enforce authentication/RBAC and request contracts;
- application services orchestrate named capabilities;
- PostgreSQL repositories own complete transaction/locking families;
- audit and selected outbox events commit with business changes;
- background execution is a closed four-job catalog with leases and bounded
  retries, not arbitrary code execution;
- cache keys include every authorization and response-semantic field;
- configuration is validated and defaults fail closed outside the explicit
  scale environment;
- focused concurrency, site-isolation, authentication, and PostgreSQL tests
  protect the behavior.

Stage 11 is an example of production-style diagnosis: measure SQL, pool state,
endpoint latency, and connection fan-out; reject two weaker configurations;
then retain only the smallest proven change.

## AI/RAG differentiation

The assistant is evidence-bound rather than an autonomous maintenance agent.
Documents are validated, chunked with metadata, retrieved through dense/sparse
signals, filtered by relevance, and passed through response/citation
validation. Insufficient evidence, disabled providers, or generation errors
lead to deterministic fallback.

Structured counts, balances, SLA aggregates, and costs never rely on generative
answers. This makes the AI boundary explainable: SQL/dbt answers relational
questions; RAG supplies traceable unstructured evidence.

## Five engineering tradeoffs

1. **Batch over real-time:** reproducibility and auditability were more valuable
   than adding streaming infrastructure without a real latency requirement.
2. **Separate migrations:** application and Data Platform histories use
   independent heads/version tables to preserve ownership.
3. **Raw before watermark:** extra audit state and reconciliation complexity
   buys safe recovery after partial failure.
4. **Process-local TTL cache:** a five-second bounded cache improved repeated
   analytics without adding Redis; coherence across replicas remains a known
   gap.
5. **Synthetic scale:** deterministic data enables repeatable engineering tests
   without exposing company or personal data, but cannot prove production
   behavior.

## Measurable project/lab results

| Area | Evidence-backed result |
|---|---|
| Stage 9 | 1,100,000 unique work orders; 1.11M raw versions; 549,230 logs |
| Watermark query | 24.33x p50 and 13.41x p95 speedup after measured index |
| Stage 10 data | 145 chunks; 7,728,467 rows; 2,106,564,675 bytes |
| Airflow | 19 task instances; baseline, controlled retry, empty rerun passed |
| dbt | 26 models + 433 tests; `459/459 PASS` |
| Validation | 2,052 historical Stage 10 checks across backend/PostgreSQL/frontend/dbt |
| Failure recovery | Retry after raw commit inserted 0 duplicates |
| Analytics API | 50-client p95 -34.5143%; RPS +38.9827% |
| Connections | Maximum reduced from 33 to 23 |
| Correctness | 900 requests, 0 errors/timeouts, 774/774 valid analytics payloads |

## Limitations

- All scale/performance results are local synthetic laptop measurements.
- No real-company users, adoption, uptime, maintenance savings, or prevented
  failures were measured.
- No production cloud deployment, live RDS resource, HA/failover, or production
  on-call process exists.
- Process-local TTL caching is not coherent across replicas.
- External LLM quality, production data governance, and mixed read/write
  capacity need separate real-world validation.

## Production roadmap

Start with governed real-data ownership and a narrowly scoped pilot. Then add
private networking, least-privilege workload identities, managed secrets,
stable encryption keys, encrypted object storage, HA/PITR and restore drills,
monitoring/alerting, CI/CD, infrastructure as code, and representative load and
failure testing. Add a distributed cache only if measurements justify it and a
coherent invalidation contract is available.

## Evidence links

- [Canonical architecture](../architecture.md)
- [Stage 10 machine report](../benchmark-results-domain-scale.json)
- [Stage 11 machine report](../benchmark-results-api-stage11.json)
- [Release manifest](../release-manifest.json)
- [Demo runbook](../demo-runbook.md)
- [Interview guide](interview-guide.md)

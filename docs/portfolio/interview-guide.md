# Interview Guide

## Architecture walkthrough

Start with the two-plane boundary:

1. The operational plane owns maintenance transactions, authentication, audit,
   UI, background jobs, and unstructured document assistance.
2. The analytics plane owns isolated source views, tuple-watermark extraction,
   immutable batch artifacts, raw/audit state, dbt models/tests, and read-only
   analytics.
3. FastAPI connects them through authenticated projections. PostgreSQL/dbt
   answers structured questions; RAG answers unstructured evidence questions.
4. Repository transactions and Data Platform watermarks have independent
   ownership and migration histories.
5. Every scale/performance claim maps to tracked machine evidence.

Use [canonical architecture](../architecture.md) for diagrams and
[release manifest](../release-manifest.json) for metrics.

## Five strongest technical decisions

1. **Tuple watermark instead of timestamp only.** `(updated_at, entity_id)`
   prevents missed rows when many updates share a timestamp.
2. **Raw/audit commit before finalization.** Recovery can resume from committed
   chunks without skipping or duplicating data.
3. **Separate structured analytics and RAG.** Relational truth stays
   queryable/testable; documents remain evidence with citations.
4. **Complete transaction ownership.** Repositories retain sessions, locks,
   audit/outbox coupling, idempotency, commit, and rollback.
5. **Measure before optimizing.** Stage 11 ruled out slow SQL, rejected two
   candidates, and accepted the smallest configuration that met correctness and
   performance gates.

## Five important tradeoffs

1. Batch processing sacrifices real-time freshness for reproducibility and
   simpler failure recovery.
2. Synthetic data enables safe deterministic scale tests but cannot prove
   production data quality or workload behavior.
3. Two independent Alembic histories improve ownership but require explicit
   exclusion and verification contracts.
4. Process-local TTL caching avoids new infrastructure but lacks cross-replica
   coherence and strict read-after-write freshness.
5. Local Compose improves reproducibility but does not provide production HA,
   managed identity, secrets, monitoring, or operational ownership.

## Failure recovery explanation

Each domain reads its lower tuple watermark and publishes an immutable object
with SHA-256. COPY/upsert and chunk audit commit together. Airflow runs dbt and
reconciliation only after raw loads complete. Finalization locks current
watermarks and advances them atomically to greater upper tuples.

In the controlled Stage 10 test, failure was injected after raw `ticket_events`
commit. Retry detected the committed checksum/chunk, inserted zero duplicates,
completed transformation/reconciliation, and advanced six watermarks once to
version 2. An immediate empty rerun extracted/inserted zero rows and preserved
the versions.

## Structured data versus RAG explanation

Use SQL/dbt for counts, balances, SLA aggregates, costs, trends, and exact
filters because those answers require deterministic grain and arithmetic. Use
RAG for manuals, SOPs, checklists, and narrative maintenance evidence because
the answer must cite source passages. Qdrant stores document chunks only.

The assistant retrieves through dense/sparse signals, applies metadata and
relevance gates, builds bounded context, validates response structure and
citations, and falls back safely when evidence is missing. It does not replace
relational analytics or human maintenance decisions.

## API performance explanation

Original Stage 10 theoretical fan-out was 40 connections: two workers times
app pool `8+4`, plus two workers times eight direct analytics slots. Under
concurrency, even `/health` had multi-second latency. Direct SQL p50 was only
about 5-48 ms for representative endpoints, so a new index was not justified.

Four bounded configurations tested separate hypotheses. Pool `4+0` caused
errors/low throughput; one worker serialized too much work. The final design
kept two workers, used pool `6+0`, six direct slots, and a 5-second/256-entry
authorization-safe LRU cache. Median 50-client p95 fell 34.5143%, RPS rose
38.9827%, and max PostgreSQL connections fell from 33 to 23 with zero errors.

## Synthetic benchmark caveat

Always say "local synthetic project/lab metric." Do not say production traffic,
company impact, real users, uptime, SLA, prevented failures, or live RDS. A
single laptop, warm buffer cache, fixed site/date mix, and read-only requests do
not model production concurrency or mixed workloads.

## 20 likely interview questions and concise answers

### 1. Why did you split the project into two planes?

Transactional workflows and analytical pipelines have different consistency,
latency, and ownership needs. The split keeps OLTP mutations safe while making
batch analytics reproducible and independently testable.

### 2. Why use a tuple watermark?

Timestamp-only extraction can lose rows tied at the boundary. Ordering by
`(updated_at, entity_id)` makes the position total and replayable.

### 3. What prevents watermark advancement ahead of data?

Raw rows and chunk audit commit first. dbt and reconciliation must pass, then a
separate locked finalization advances only greater tuples atomically.

### 4. How is retry idempotent?

Artifacts and chunks have stable identities/checksums. Committed chunks are
recognized and skipped; raw uniqueness/upsert boundaries prevent duplicates.
The injected retry inserted zero duplicate ticket events.

### 5. Why Airflow instead of a custom scheduler?

Airflow provides explicit DAG state, retries, task isolation, and operator
visibility. The graph stays bounded and manual; the operational product worker
remains a separate closed job catalog.

### 6. What does dbt add beyond SQL scripts?

Dependency ordering, environment-aware materialization, documented models,
generic/singular tests, and reproducible build evidence. Stage 10 ran 26 models
and 433 tests as 459 successful nodes.

### 7. How do you validate data quality?

I test grain, duplicates, relationships, chronology, final status, ticket SLA
evidence, inventory signs/balances, cost arithmetic, marts, and layer counts.
Eight final integrity queries returned zero violations.

### 8. Why not embed all database rows into Qdrant?

It would weaken exact filtering, arithmetic, freshness, authorization, and
lineage. Relational analytics belongs in PostgreSQL/dbt; Qdrant is for
unstructured evidence retrieval.

### 9. How do you keep RAG grounded?

Approved documents, metadata, hybrid retrieval, relevance thresholds, bounded
context, response schema validation, claim/citation validation, and a
deterministic insufficient-evidence fallback.

### 10. Where is authorization enforced?

FastAPI dependencies and application services enforce RBAC. The frontend is not
a security boundary. Analytics cache keys also include user and site scope.

### 11. Who owns transactions?

Concrete PostgreSQL repositories own sessions, row locks, audit/outbox writes,
flush/commit, rollback, and exception mapping. Services own orchestration, not
partial commits.

### 12. Why two Alembic histories?

Application and analytics schemas have separate lifecycle owners. Independent
heads/version tables prevent one history from interpreting the other's
revision.

### 13. What was the Stage 11 bottleneck?

Connection and transaction queueing from worker/pool/direct-query fan-out, not
slow SQL. Endpoint and pool metrics plus direct SQL/EXPLAIN evidence supported
that conclusion.

### 14. Why not just increase PostgreSQL max connections?

That hides application fan-out and can increase contention/memory use. I reduced
theoretical API demand from 40 to 24 and preserved headroom instead.

### 15. Why use a five-second cache?

Repeated analytics requests benefited from short reuse without new
infrastructure. The TTL bounds staleness; identity/site/query/date/limit keys
protect semantics. It is disabled by default outside explicit scale Compose.

### 16. What configuration did you reject?

Pool `4+0` with two workers produced seven errors and very low 50-client RPS.
One worker also reduced throughput substantially. Both were stopped early based
on bounded experiment criteria.

### 17. How reproducible are the metrics?

Machine JSON records raw sample hashes, methodology, medians, errors, payload
validity, connections, and limitations. They are reproducible local evidence,
not a production capacity guarantee.

### 18. What would you change for production?

Real data governance, private networking, managed identities/secrets,
encryption-key management, HA/PITR, monitoring/on-call, CI/CD/IaC, coherent
cache invalidation, and representative mixed-workload tests.

### 19. What would you monitor first?

API/error latency, pool checked-out/overflow/timeouts, analytics slot wait,
PostgreSQL active/idle-in-transaction connections, pipeline age/failure,
watermark lag, reconciliation violations, and job/outbox backlog.

### 20. What are you most proud of?

The project makes boundaries and evidence visible: failure recovery is tested,
performance changes are measured, RAG does not replace SQL, and portfolio claims
are traceable to machine-readable reports with honest limitations.

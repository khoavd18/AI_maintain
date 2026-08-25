# Final 5-10 Minute Demo Runbook

This is the canonical mentor/interview demo. It is evidence-first and works
without Docker, credentials, external AI services, or regenerated data.

Target speaking time: approximately 8 minutes. Run the Offline verifier before
the meeting and keep the linked evidence documents open.

## Pre-demo check — 30 seconds

```powershell
Set-Location D:\code\rag\ai_maintain_copilot
.\scripts\verify_final_release.ps1 -Mode Offline
```

Explain: the project has a reproducible offline release gate. It validates
required documents, source metrics, links, manifest content, secrets, Git
lineage, and generated-artifact exclusions without starting infrastructure.

Expected safe output: final `PASS` summary with optional dependencies reported
as `SKIP` when unavailable.

Evidence/fallback: [release manifest](release-manifest.json). If PowerShell is
restricted, open the manifest and README instead; do not change execution
policy globally.

## 1. Problem and complete architecture — 45 seconds

```powershell
Get-Content README.md -TotalCount 90
```

Explain: maintenance operations span transactional workflows, structured
analytics, and unstructured manuals. The design uses two connected planes with
explicit ownership instead of forcing every problem into RAG.

Expected safe output: project statement and system Mermaid diagram.

Evidence/fallback: [canonical architecture](architecture.md), especially the
system context and component-responsibility table.

## 2. Operational maintenance application — 45 seconds

```powershell
Get-ChildItem src\asset_management,src\ticket_management,`
  src\maintenance_management,src\inventory_management -Directory
```

Explain: FastAPI and application services cover assets, tickets/SLA,
preventive plans, work orders/checklists, maintenance logs, inventory, durable
jobs, and notifications. PostgreSQL repositories retain locks, transaction,
audit, outbox, and idempotency ownership.

Expected safe output: the four domain packages. No data is read or mutated.

Evidence/fallback: [application services](application-services.md),
[transaction map](repository-transaction-map.md), and
[business process](business_process.md).

## 3. Structured data versus RAG — 40 seconds

```powershell
Select-String -Path docs\structured-data-vs-rag.md `
  -Pattern 'Structured|RAG|PostgreSQL|Qdrant' | Select-Object -First 12
```

Explain: counts, SLA aggregates, inventory balances, and cost variance stay in
PostgreSQL/dbt. Manuals, SOPs, checklists, and narrative evidence use hybrid
retrieval and grounded generation. Qdrant is not a relational analytics store.

Expected safe output: bounded decision rules and architecture references.

Evidence/fallback: [structured data versus RAG](structured-data-vs-rag.md) and
[RAG/LLM design](RAG_LLM_DESIGN.md).

## 4. Dataset scale — 40 seconds

```powershell
$release = Get-Content -Raw docs\release-manifest.json | ConvertFrom-Json
$release.dataset.stage10 | ConvertTo-Json -Depth 4
```

Explain: the synthetic Stage 10 run covered 145 chunks, 7,728,467 rows, and
2,106,564,675 bytes. Domain counts include 1.1M work orders, 3.3M status rows,
300K tickets, 900K ticket events, 25K spare parts, 1.5M movements, and 1.1M
cost rows.

Expected safe output: numeric JSON only, no credentials or raw rows.

Evidence/fallback: [Stage 10 machine report](benchmark-results-domain-scale.json)
and [manifest summary](benchmark-manifest-domain-scale.json).

## 5. Airflow pipeline — 40 seconds

```powershell
Select-String `
  data_platform\airflow\dags\maintenance_domain_scale_pipeline.py `
  -Pattern 'task_id=' | ForEach-Object Line
```

Explain: the Stage 10 DAG has 19 task instances—start/check, six extract/load
pairs, dbt run/test, reconciliation, atomic finalization, and completion. XCom
carries metadata rather than row payloads.

Expected safe output: static task IDs. The loop defines the six extract/load
pairs, so the source shows fewer literal lines than runtime task instances.

Evidence/fallback: [Stage 10 runbook](stage10-domain-scale.md) and the Airflow
section in [architecture](architecture.md).

## 6. dbt transformation and quality — 35 seconds

```powershell
$report = Get-Content -Raw docs\benchmark-results-domain-scale.json |
  ConvertFrom-Json
$report.dbt | ConvertTo-Json -Depth 3
```

Explain: 26 models and 433 data tests produced `459/459 PASS`. Tests cover
grains, chronology, relationships, SLA evidence, signed inventory semantics,
cost arithmetic, and cross-layer reconciliation.

Expected safe output: `build_total_nodes=459`, `passed=459`, and zero errors.

Evidence/fallback: [Stage 10 benchmark report](benchmark-results-domain-scale.md).

## 7. Failure recovery and idempotency — 45 seconds

```powershell
Select-String docs\reliability-failure-recovery.md `
  -Pattern 'ticket_events|duplicate|watermark|retry' |
  Select-Object -First 15
```

Explain: raw chunks and audit commit before watermark finalization. The
controlled failure happened after raw `ticket_events` commit; retry verified
the prior chunk and inserted zero duplicates. Six watermarks advanced once to
version 2. The empty rerun inserted zero rows and preserved them.

Expected safe output: the documented injected-failure and retry evidence.

Evidence/fallback: [failure recovery](reliability-failure-recovery.md).

## 8. Authenticated Analytics API — 35 seconds

```powershell
Select-String src\analytics\domain_adapter.py `
  -Pattern 'DomainAnalyticsQuery|read_only=True|statement_timeout' |
  Select-Object -First 12
```

Explain: clients choose one of six exact capabilities, not SQL. Calls are
parameterized, date/result bounded, read-only, and protected by
`analytics.read`; site/user scope participates in caching.

Expected safe output: closed query enum and safety controls.

Evidence/fallback: [Data Platform integration](data-platform-integration.md)
and [Stage 11 runbook](stage11-api-performance.md).

## 9. Stage 11 performance — 45 seconds

```powershell
$api = Get-Content -Raw docs\benchmark-results-api-stage11.json |
  ConvertFrom-Json
$api.median_comparison | Format-Table clients,baseline,final,change_percent
```

Explain: direct SQL was already fast; the bottleneck was connection fan-out and
queueing. The accepted `2 workers / pool 6+0 / 6 slots / 5s cache` configuration
reduced 50-client p95 by about 34.5%, increased RPS by about 39%, and reduced
maximum PostgreSQL connections from 33 to 23.

Expected safe output: the two median-comparison records. The historical run had
900 requests, zero errors/timeouts, and 774/774 non-empty analytics payloads.

Evidence/fallback: [load-test report](analytics-api-load-test-stage11.md).

## 10. Frontend and dashboard evidence — 35 seconds

```powershell
Get-ChildItem frontend\src\app -Directory | Select-Object Name
Get-ChildItem frontend\src\features -Directory | Select-Object Name
```

Explain: the Next.js UI is an authenticated API client for asset, ticket,
work-order, inventory, notification, and operator workflows. Recharts provides
visualization; the legacy Streamlit page is development-only and not a second
business-data authority.

Expected safe output: tracked route and feature directories.

Evidence/fallback: [API documentation](api.md), [dashboard analytics](analytics.md),
and the historical Stage 10 frontend evidence of 141 tests and a successful
build.

## 11. Security boundaries — 35 seconds

```powershell
Select-String README.md -Pattern 'Security boundaries' -Context 0,12
```

Explain: FastAPI RBAC is authoritative; tokens and secrets are excluded from
evidence; audit/outbox couples with business transactions; scale rows were not
sent to external AI services; the analytics cache includes authorization and
site scope.

Expected safe output: the release security boundary list.

Evidence/fallback: [security](security.md), [RBAC](rbac.md), and
[release manifest](release-manifest.json).

## 12. Limitations and production roadmap — 45 seconds

```powershell
$release = Get-Content -Raw docs\release-manifest.json | ConvertFrom-Json
$release.limitations
```

Explain honestly: results are synthetic laptop evidence, not production SLA or
business impact. Production evolution requires data governance, private
networking, least-privilege identities, managed secrets, stable encryption
keys, HA/PITR, monitoring/on-call, CI/CD/IaC, and representative load testing.

Expected safe output: explicit limitations, not marketing claims.

Evidence/fallback: [project handover](project-handover.md) and
[portfolio summary](portfolio/project-summary.md).

## Close — 20 seconds

Suggested closing statement:

> This project demonstrates end-to-end engineering judgment: transactional
> ownership, batch data reliability, measurable performance work, grounded AI
> boundaries, and honest release evidence. The next step is not another feature
> stage; it is a governed pilot and production-hardening program.

# CV and Profile Copy

All scale and performance numbers below are synthetic project/lab metrics, not
production company outcomes.

## Data Engineer — English ATS bullets

- Engineered a PostgreSQL/Airflow/dbt maintenance analytics platform that
  generated and copied 7.7M+ synthetic rows across work orders, status history,
  tickets, inventory, spare parts, and costs, with tuple-watermark incremental
  extraction and source-to-fact reconciliation.
- Designed restartable checksum-verified batch loading and a 19-task Airflow
  DAG; validated controlled failure recovery after raw commit with zero
  duplicate retry insertion and six atomically finalized watermarks.
- Built 26 dbt models and 433 data tests (`459/459` nodes passed) and measured a
  composite-query p95 reduction from 840.3066 ms to 23.7709 ms on a local
  synthetic benchmark.

## Software Engineer — English ATS bullets

- Built a FastAPI/PostgreSQL maintenance platform with RBAC, auditable
  asset/ticket/work-order/inventory workflows, durable background jobs,
  transactional outbox behavior, and an authenticated Next.js frontend.
- Implemented an authorization-safe bounded analytics cache and concurrency
  controls that reduced 50-client p95 by approximately 34.5%, increased RPS by
  approximately 39%, and reduced maximum database connections from 33 to 23 in
  a 900-request synthetic load test with zero errors.
- Separated structured PostgreSQL/dbt analytics from grounded document RAG,
  adding hybrid retrieval, relevance gates, citation validation, deterministic
  fallback, and reproducible offline release verification.

## Data Engineer — Vietnamese bullets

- Xây dựng Data Platform bảo trì bằng PostgreSQL, Airflow và dbt, xử lý hơn 7,7
  triệu dòng synthetic thuộc work order, lịch sử trạng thái, ticket, tồn kho và
  chi phí; áp dụng tuple watermark và đối soát source-to-fact.
- Thiết kế pipeline 19 task có artifact checksum, COPY theo chunk, retry sau raw
  commit không chèn trùng dữ liệu và finalize nguyên tử sáu watermark.
- Phát triển 26 dbt models và 433 data tests (`459/459 PASS`), đồng thời đo tối ưu
  composite-query p95 từ 840,3066 ms xuống 23,7709 ms trong local lab.

## LinkedIn / GitHub description

Built an end-to-end AI Maintenance Copilot and batch analytics Data Platform
using FastAPI, PostgreSQL, Airflow, dbt, Next.js, and grounded RAG. The local
synthetic lab covers 7.7M+ generated rows, failure-safe tuple-watermark
ingestion, 459/459 dbt nodes, authenticated site-scoped analytics, and a measured
API optimization that lowered 50-client p95 by ~34.5% while increasing RPS by
~39%. Evidence, limitations, and offline verification are tracked in the repo;
this is a portfolio benchmark, not a production deployment claim.

## Compact technology line

Python, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Airflow, dbt, pandas,
scikit-learn, Qdrant, Next.js, React, TypeScript, Docker Compose, pytest, Ruff

## Honest project title

**AI Maintenance Copilot and Batch Analytics Data Platform — Synthetic
Engineering Portfolio Project**

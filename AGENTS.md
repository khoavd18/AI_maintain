# Repository Guardrails

These rules apply to future agent work in this repository.

## Product Boundary

AI Maintenance Copilot is a batch analytics and AI decision-support layer with focused asset lifecycle, ticket, preventive-plan, work-order, and maintenance-log workflows. PostgreSQL is the transactional source of truth, but the product is not a complete CMMS, autonomous maintenance controller, or production-ready enterprise platform.

Human facility managers and technicians remain responsible for prioritization, safety checks, field inspection, maintenance execution, and final decisions. Never describe a score or recommendation as an automatic decision.

## Canonical Architecture

- Keep PostgreSQL primary for transactional assets, tickets, preventive plans, checklist templates, work orders, and maintenance logs.
- Use Alembic for every PostgreSQL schema change. Do not call `metadata.create_all()` in product startup or production-mode commands.
- Keep CSV for synthetic generation, explicit seed/import, database-to-analytics snapshots, canonical demo reset, and batch analytics contracts.
- At the snapshot boundary, preserve the validated legacy interval contract: project asset/log `next_maintenance_date` from `last_maintenance_date` or `maintenance_date` plus `maintenance_interval_days`. Keep real plan-derived dates in PostgreSQL plans/work orders; do not weaken legacy analytics validation.
- Keep analytics batch-first. PostgreSQL transactional writes must not trigger or imitate immediate Risk Score/KPI recalculation.
- Keep FastAPI as the serving boundary. Streamlit must consume FastAPI and must not read raw or processed CSV files directly.
- Select storage in the service/repository factory, never in route functions. Do not silently fall back from unavailable PostgreSQL to mutable CSV storage.
- Keep the CSV repository only as an explicit compatibility adapter for isolated tests and demo fixtures.
- Use Qdrant only for RAG document retrieval.
- Do not add real-time ingestion, streaming, or event-processing infrastructure.

## Preventive Maintenance And Work Orders

- Keep `src/maintenance_management/service.py` as the canonical business boundary, `src/maintenance_management/recurrence.py` as the only recurrence implementation, and `src/repositories/postgres_maintenance.py` as the PostgreSQL implementation. Routes and frontends must not manipulate SQLAlchemy models directly.
- Keep `PreventiveMaintenancePlan`, `WorkOrder`, `ChecklistTemplate`, `WorkOrderChecklistItem`, `MaintenanceLog`, and `Ticket` as separate concepts. Never merge them into a generic maintenance record.
- Support only bounded interval recurrence in days, weeks, months, and years. Due dates are local business dates under an explicit IANA timezone; execution timestamps are UTC. Overdue is derived from due date and grace period, never an editable state.
- Preserve the documented month-end anchor, leap-year behavior, 366-day catch-up bound, and paused-backlog skip policy. Schedule changes affect only ungenerated occurrences.
- Generate preventive work orders only through the explicit service invoked by protected API or CLI commands. Do not generate at application startup, add a hidden scheduler loop, or duplicate generation logic in a future scheduler.
- Keep work-order numbers and plan occurrences concurrency-safe and idempotent. A generated `(preventive_plan_id, due_date)` pair is unique.
- Keep checklist template versions immutable. Work orders execute a snapshot, so later versions or archived templates never alter history.
- Enforce the canonical work-order state machine in the service. Completion creates or links exactly one `MaintenanceLog`; independent verification by a different authorized actor updates asset maintenance dates. Verified records are immutable without a separately authorized future correction design.
- Never resolve a ticket merely because a work order was created, completed, or verified. Ticket resolution remains an explicit authorized human action.
- Aggregate the legacy asset `next_maintenance_date` as the earliest due date among active plans, with the documented legacy fallback. Never present one asset date as a replacement for plan-specific schedules.
- Reuse `AttachmentStorage` for work-order evidence and preserve MIME/signature/extension checks, size bounds, generated keys, checksums, authorized download, and soft deletion. Do not expose storage paths or file bodies in audit records.

## Asset Lifecycle And Files

- Keep `src/asset_management/service.py` as the canonical asset lifecycle boundary and `src/repositories/postgres_assets.py` as its PostgreSQL implementation. Do not move lifecycle or hierarchy rules into routes or the frontend.
- Keep lifecycle status separate from temporary operational status. Asset archive/restore must be explicit, versioned, audited, and non-destructive; do not add a normal asset hard-delete endpoint.
- Preserve the legacy analytics asset projection (`asset_type`, `location`, `criticality`, `status`, installation and maintenance dates) when extending the management profile.
- Keep locations hierarchical and archive-in-place. Reject self-parenting/cycles, and never delete assigned assets or their history when a location is archived.
- Store attachment metadata in PostgreSQL and bytes behind `AttachmentStorage`. Enforce allow-listed type/signature/extension, bounded size, generated storage keys, checksum validation, authorized download, and soft-delete audit. Never expose local paths.
- Asset QR codes may contain only the deterministic opaque lookup URL. QR lookup remains authenticated; QR is an identifier, not an authorization token. Keep the scan experience web-based and do not create a native mobile app.

## Canonical Analytics

Extend only these production paths:

- Feature engineering: `src/features/build_features.py`
- Anomaly detection: `src/models/anomaly_detection.py`
- Risk scoring: `src/risk/risk_scoring.py`
- Dashboard: `src/dashboard/app.py`
- RAG chunking: `src/rag/chunking.py`

Duplicate anomaly, risk, ingestion, sample-data, and dashboard wrappers were removed in the verified cleanup milestone. Do not recreate parallel implementations or compatibility entrypoints; extend only the canonical paths above.

## Scope Expansion Prohibited

Do not add or propose implementation work for the following areas unless the repository owner explicitly changes the MVP scope:

- spare-parts inventory or inventory optimization;
- resident mobile applications;
- technician mobile applications;
- vendor or contract management;
- real-time IoT streaming or live event processing;
- complex approval workflows;
- SSO, MFA, external identity providers, or enterprise IAM integration;
- hidden or distributed scheduling, job queues, or startup work-order generation;
- exact failure-time prediction.

Historical `parts_replaced` data may remain in maintenance logs, but it must not grow into an inventory subsystem.

## Identity And Audit

- Keep local/internal-pilot authentication in `src/security/`; do not create a second role or permission model in Python or TypeScript.
- Enforce authorization in FastAPI. Hidden frontend controls are usability behavior, never the security boundary.
- Keep access tokens in frontend memory and refresh tokens in revocable HttpOnly cookies. Never store authentication tokens in `localStorage`.
- Keep successful business audit records in the same PostgreSQL transaction as their mutation. Audit records are append-only and must exclude passwords, tokens, cookies, Authorization headers, and secrets.
- Do not create users automatically at application startup. Bootstrap administrators and demo identities only through explicit CLI commands.

## Compatibility And Claims

- Preserve existing API contracts unless a task explicitly authorizes a change.
- Prefer additive, tested data-contract changes.
- Keep code, module, column, and API field names in English.
- Keep user-facing business values and operational explanations in Vietnamese.
- Clearly separate current behavior from future work in documentation.
- Do not claim production readiness, model accuracy, ROI, prevented failures, or business impact without measured evidence.
- Describe risk as prioritization, not a calibrated failure probability or guaranteed prediction.

## Verification

For repository changes, run the tests relevant to the modified area, then run:

```bash
python -m pytest
python -m ruff check .
```

Keep the product demo reproducible with local Docker PostgreSQL, migrations, and canonical CSV seed import.
Use a dedicated database whose name ends in `_test` for PostgreSQL integration tests. Never run destructive test setup against the developer/demo database.

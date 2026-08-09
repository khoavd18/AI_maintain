# Changelog

All notable repository-level changes are documented here. Dates use the repository business timezone.

## Unreleased — 2026-07-28

### Added

- Provider-independent LLM boundary under `src/llm/`.
- Ollama and environment-configured OpenAI-compatible Chat Completions providers.
- Strict Pydantic grounded answer schema with claim-level source IDs.
- Grounded prompt builder, bounded context, prompt-injection screening, Vietnamese output check, and deterministic citation validator.
- Explicit selected-asset/question type mismatch handling.
- Additive Copilot provenance, evidence, structured-answer, provider, citation, and context-warning API fields.
- Per-authenticated-user Copilot request limiting for the single-instance pilot.
- Frontend generated/fallback/evidence/mismatch/citation states and source alias display.
- Provider smoke command and reproducible RAG/LLM evaluation dataset/runner.
- Development full-stack Compose services for migration, API, and frontend; worker remains an explicit profile.
- Isolated `_test` graduation workflow runner with database-fingerprint attestation and in-memory multi-role authentication.
- Runtime verification record covering PostgreSQL, Qdrant, Ollama, Docker, authenticated workflow, and dependency evidence.
- Project audit, RAG/LLM design/evaluation, security review, graduation demo, and company handover documentation.

### Changed

- `MaintenanceCopilot` now uses a real generative provider when explicitly enabled and all grounding gates pass.
- Existing deterministic response composition is retained for disabled, unavailable, timeout, malformed, invalid-citation, unsafe, mismatch, and insufficient-evidence cases.
- Copilot frontend timeout is aligned with the default bounded backend provider call.
- Python image runs as a non-root application user.
- Frontend Next.js and matching ESLint configuration were upgraded from 16.2.10 to current stable 16.2.12; safe transitive audit fixes were applied.
- Pilot Compose/manifest/environment contract includes explicit LLM and Copilot rate-limit settings; release manifest hash was updated consistently.
- README and canonical architecture/security documentation now describe the actual RAG-plus-LLM flow and limitations.
- Development Compose no longer uses project-global fixed container names, waits for a real Qdrant `/readyz` health check, and permits explicit `APP_ENVIRONMENT=test` verification.
- Provider responses are streamed under a pre-buffer byte limit; serialized context, Vietnamese-language density, unsafe asset context, missing chunk IDs, and top-level/claim citation consistency now fail closed.
- Required guidance arrays are represented as required JSON Schema fields, matching local Pydantic business validation.
- Copilot frontend timeout now covers the default two-attempt backend provider envelope.
- Next image optimization is globally disabled as a reachability reduction while the framework-owned Sharp advisory awaits a stable compatible fix.

### Security

- Retrieved documents are treated as untrusted data, never system instructions.
- Provider redirects are disabled; calls have timeout/retry/response-size bounds.
- API keys are secret values and never returned/logged.
- Generated citations cannot be accepted unless they match exact response-local source aliases.
- Aggregate source IDs must exactly equal the union of claim-level citations; safe asset facts and retrieved chunks are both treated as untrusted prompt data.
- LLM has no tools or business mutation path.

### Verification

- Initial baseline: 308 passed, 73 skipped backend; 112 passed frontend; Ruff/lint/typecheck/build/Compose/Alembic head passed.
- Focused new LLM/RAG/API tests: 40 passed.
- Copilot rate-limit/API tests: 24 passed; frontend API-client tests: 30 passed.
- Evaluation and PM9 manifest tests: 30 passed.
- Deterministic evaluation: six expected documents ranked first and two no-answer cases matched on the small synthetic fixture.
- PostgreSQL integration: 73 passed, 0 skipped against an isolated `_test` database; online base-to-head migration and QR backfill passed.
- Final backend suite with PostgreSQL: 420 passed, 0 failed, 0 skipped.
- Live Qdrant: 6 documents, 30 stable chunks, 384-dimensional cosine collection; repeated indexing stayed at 30 points.
- Real Ollama smoke passed with the environment-selected installed model `qwen2.5-coder:7b`.
- Configured-Qdrant evaluation measured Recall@1 0.833, Recall@3/5 1.0, MRR 0.917; real generation succeeded for representative HVAC, pump, and generator questions while inconsistent citations fell back safely.
- Full Compose runtime reached healthy PostgreSQL/Qdrant/API/worker/frontend with migration exit 0 and zero restarts.
- Authenticated multi-role graduation workflow passed through ticket, Copilot, stock reservation/issue, work-order verification, audit, metrics, and worker health.
- Frontend remained at 115 passing tests; lint, typecheck, 32-route production build, Compose contracts, Ruff, compilation, Alembic head, pip check, documentation links, and tracked diff checks passed.

Full command output and limitations are recorded in `docs/RUNTIME_VERIFICATION.md` and `docs/PROJECT_AUDIT.md`.

### Known Dependency Advisory

`npm audit --omit=dev` still reports three high advisories in Next 16.2.12's pinned PostCSS and optional Sharp tree. The registry reports 16.2.12 as current stable; `npm audit fix --force` proposes an unsafe Next 9.3.3 downgrade. The repository does not take that breaking downgrade. Track the next patched stable Next release and repeat lint/typecheck/test/build/audit before deployment.

# Security Review

Review date: 2026-07-28<br>
Scope: repository implementation and local verification, not an external penetration test or certification

## Executive Conclusion

The application has a credible internal-pilot security baseline: FastAPI authorization, a canonical role/permission model, Argon2 passwords, revocable rotated refresh sessions, CSRF checks, explicit browser origins/hosts, PostgreSQL transactions/audit, constrained uploads, durable closed background operations, and secret-free configuration templates. No broad authentication bypass, arbitrary scheduler execution surface, browser token persistence, or hardcoded production credential was identified in the bounded review.

The new LLM path fails closed for generation and cannot mutate business state. It improves prompt/context isolation and citation integrity but does not eliminate indirect prompt injection or semantic hallucination risk.

This system remains inappropriate for public internet production without organizational ownership, HTTPS/network controls, shared rate limiting, managed secrets, central observability, recovery evidence, malware scanning, and external security testing.

## Threat Model

Protected assets include:

- user credentials, access/refresh/CSRF tokens;
- reporter contact data and restricted comments;
- asset/ticket/work-order/inventory business state;
- append-only audit, SLA, stock, job, and outbox history;
- attachment bytes and storage paths;
- provider API key and LLM prompts/context;
- release and backup evidence.

Relevant actors are authenticated internal users with role-specific access, an operator/deployer, a database/host administrator, malicious document/question input, and unavailable/misbehaving external dependencies.

## Controls Confirmed

### Identity And Session

- Argon2 password hashes and dummy verification for unknown accounts.
- Generic invalid-login response and bounded identifier-based failed-login limiter.
- Short-lived signed access token kept only in frontend memory.
- Opaque refresh token stored only as a hash in PostgreSQL and sent in HttpOnly cookie.
- Refresh rotation revokes the old session under row lock.
- Bound readable CSRF cookie plus header for refresh/logout.
- Every protected request rechecks user active/version and refresh-session revocation.
- Pilot/production requires secure cookies, strong signing secret, PostgreSQL, valid release identity, and non-placeholder database credentials.

### Authorization And Object Scope

- `src/security/permissions.py` is the single Python role/permission source.
- Routes enforce permissions; hidden controls are not treated as authorization.
- Technician assignment/resource rules are also enforced in services.
- Notification reads are owner-isolated.
- Reporter PII and comment visibility have separate permissions.
- Copilot requires `copilot:use` and is limited per authenticated user.

### Data Integrity And Audit

- Named services own lifecycle transitions and transaction boundaries.
- Optimistic versions, unique constraints, row locks, idempotency keys, and non-negative stock checks are present.
- Audit/outbox records are committed with selected business mutations.
- Audit, inventory movement, reservation event, comment/SLA/escalation histories are append-only by design; corrections create new records.
- The background worker accepts only four server-defined operations and persists leases/retries/dead letters.

### Files

- Allow-listed PDF/PNG/JPEG type, extension, MIME, and signature checks.
- Bounded size, generated key, containment, checksum verification, authenticated download, soft deletion.
- Storage keys/paths and file bodies are not returned in audit data.

### Browser And API

- Explicit credentialed CORS origins; wildcard rejected.
- Trusted host allow-list.
- API documentation disabled outside development/test.
- Typed request/response validation in Pydantic and Zod.
- Backend answer text rendered as text; no dangerous HTML injection path in Copilot.
- Copilot provider call uses a longer operation-specific frontend timeout and safe retry state.

### LLM And RAG

- Generation off by default; model and endpoint are explicit configuration.
- Provider key stored as `SecretStr`, never returned.
- No tools or mutation capabilities.
- User, allow-listed asset context, and retrieved prompt-injection screening.
- Asset and retrieved content isolated as untrusted JSON data.
- Bounded serialized context, generated output, timeout, retry, and streamed provider-response bytes.
- Strict structured output, Vietnamese requirement, claim-level source coverage, and exact citation allow-list.
- Fixed fallback reasons without raw prompt/provider/connection text.
- Asset type mismatch rejected before retrieval.

## Findings Register

| ID | Severity | Finding | Status / mitigation |
|---|---|---|---|
| SEC-01 | High for public deployment | Login/Copilot rate limiting is process-local | Accepted only for one-instance pilot; use gateway/shared limiter before scale-out |
| SEC-02 | High for external provider | Provider data retention/residency is operator-dependent | Keep disabled until contract and approved endpoint/secret source exist |
| SEC-03 | High | No malware scanner for attachments | File controls reduce risk but do not replace scanning; required before untrusted public uploads |
| SEC-04 | High | No SSO/MFA/account recovery/managed identity | Explicitly outside internal-pilot MVP; required for broader enterprise use |
| SEC-05 | Medium | Regex injection screening is incomplete | System/data isolation, no tools, schema/citations, fallback, and human verification reduce impact |
| SEC-06 | Medium | Citations do not prove semantic entailment | Human/evaluation rubric required; do not claim hallucination elimination |
| SEC-07 | Medium | Local attachment storage and single PostgreSQL/API/worker | No HA/PITR/distributed transaction; keep pilot-only claim |
| SEC-08 | Medium | No central log/metric/alert collection or retention policy | Existing structured safe logs/metrics require external operations platform |
| SEC-09 | Medium | Reporter PII not field-encrypted and lacks retention workflow | RBAC/redaction exists; define data governance before production |
| SEC-10 | Medium | Local model/provider supply chain is not attested | Pin/approve model artifacts and provider versions for a real pilot |
| SEC-11 | Low | Upstream FastAPI TestClient deprecation warning | Track dependency migration; no current runtime security impact shown |
| SEC-12 | High | Next 16.2.12 owns vulnerable nested PostCSS 8.4.31 and optional Sharp 0.34.5 paths | No stable compatible Next release observed with PostCSS >=8.5.18 and Sharp >=0.35.0. Do not force the proposed Next 9 downgrade or unsupported overrides. Builds accept only trusted checked-in CSS and `images.unoptimized=true` disables the runtime optimizer, but vulnerable packages remain and deployment stays blocked pending upstream stable support |

## Secret Handling

- `.env` is ignored; example files contain placeholders only.
- Do not put `LLM_API_KEY`, database password, token signing secret, demo password, or smoke credentials in Compose command lines, reports, screenshots, or Git.
- Pilot environment must be a protected file or secret-injection mechanism.
- `LLM_BASE_URL` must not contain embedded credentials.
- Rotate provider keys according to provider policy; the application does not persist them.

## Logging And Privacy

The Copilot logs a fixed reason when generation falls back. It does not log question text, retrieved content, raw provider output, provider URL, API key, asset context, or reporter data. API request logs include method/path/status/duration/request ID, not Authorization/cookies.

If external tracing is later added, it must default to redacted metadata and require explicit governance before capturing prompts or completions.

## Verification Evidence

- Ruff and Python compilation passed for the changed security/LLM surfaces.
- Focused LLM/RAG/API tests cover injection, unsafe stored asset context, invalid citations, invalid output, Vietnamese density, serialized context bounds, streaming byte bounds, timeout/unavailable, mismatch, provider schemas, key header boundary, transient retry, and per-user `429`.
- Frontend tests confirm escaped output, fallback/mismatch states, citation aliases, and typed HTTP error handling.
- PM9 deployment manifest validation fails closed when Compose-required variables are not in the manifest; the synchronized contract tests pass.

Later runtime verification used a dedicated `_test` database and passed all 73 PostgreSQL integration tests, a real Ollama smoke, live-Qdrant injection screening, the full Docker stack, and the authenticated multi-role workflow. The complete record is [Runtime verification](RUNTIME_VERIFICATION.md).

## Deployment Gate

Before any real pilot:

1. Assign security/incident/support owners and approved contact path.
2. Use HTTPS, secure cookies, explicit CORS/hosts, network restriction, and protected secrets.
3. Approve provider/model/data retention or use approved local Ollama only.
4. Run the clean `_test` migration and all PostgreSQL tests.
5. Complete backup plus paired database/attachment restore rehearsal.
6. Add shared ingress rate limiting and centralized redacted logs/alerts if more than one API instance or public access is introduced.
7. Perform external application/security review and attachment-malware decision.
8. Record accepted known limitations; engineering documentation cannot grant organizational acceptance.

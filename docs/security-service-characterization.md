# Security service characterization

Characterization date: 2026-08-06. This document records the current security
behavior and the one safe decomposition completed after characterization. It
is a behavior map, not a security certification or a production-readiness
claim. The current worktree is the source of truth; existing API, database,
token, and audit behavior is treated as stable.

## Boundary and dependencies

`AuthService` in `src/security/service.py` remains the canonical local
authentication/user/audit application boundary. Pure identity normalization and
user/principal projection now live in `src/security/identity.py`, and the
historical exception type is owned by `src/security/errors.py`. AuthService
still owns SQLAlchemy session usage for security transactions, while
cryptographic primitives remain in `passwords.py` and `tokens.py`. FastAPI
dependencies and routes perform transport mapping and RBAC dependency wiring;
the service does not import FastAPI.

| Dependency | Current responsibility | Security implication |
|---|---|---|
| `sessionmaker[Session]` | User, refresh-session, and audit reads/writes | Session/transaction ownership remains in the current service during characterization. |
| `Settings` | Signing keys, token/session lifetimes, and rate-limit settings | Pilot restrictions are validated before service construction. |
| `passwords.py` | Argon2id hash, verification, dummy verification | Unknown identifiers receive dummy verification to reduce timing differences. |
| `tokens.py` | JWT access claims, opaque refresh/CSRF tokens, hashes | Claims, algorithms, key rotation, expiry, and token types are centralized. |
| `permissions.py` | Role-to-permission matrix | This is the only Python RBAC source. |
| `audit.py` | Safe metadata and bounded audit context | Passwords, tokens, cookies, and authorization values are filtered. |
| `LoginRateLimiter` | Process-local failed-login throttling | Limiter state is intentionally process-local for the internal pilot. |
| `identity.py` | Identifier normalization and pure user/principal projections | No persistence, token, password, or audit side effects. |
| `errors.py` | Shared security exception ownership | Preserves one `AuthenticationError` class identity across the facade and extracted code. |

## Public `AuthService` method map

The validation order below is part of the current behavior. “Audit” means an
`AuditLog` is added through `_append_audit` in the same transaction unless the
row explicitly says best effort.

| Method | Inputs / output | Validation order and repository calls | Exceptions and security side effects | Existing coverage / gap |
|---|---|---|---|---|
| `login` | Identifier, password, user-agent, request ID → `AuthResult` | Normalize identifier → fingerprint/rate-limit check → query `User` by normalized username/email → dummy verify for unknown user, otherwise verify hash and active state → on success update `last_login_at`, create refresh session/access token/CSRF token, append success audit. | Generic `AuthenticationError` for limiter, bad credentials, unknown, or inactive account; `StorageUnavailableError` for SQL failures. Failure audit is rejected and contains only identifier fingerprint; failure limiter records, success clears. | PostgreSQL generic-login, rate-limit, token-response tests. Missing direct audit-order assertion and direct inactive-account service test. |
| `authenticate_access` | Access token → `CurrentUser` | Decode and validate signature/claims with current then one previous key → read `User` and `RefreshSession` → require active user, matching user version/role, session ownership, unrevoked and unexpired session → build principal. | Invalid/malformed/expired token becomes generic `AuthenticationError`; SQL failures become `StorageUnavailableError`. No mutation or audit. | Protected-route and expired-token tests. Missing direct coverage for role/version/session mismatch and previous-key access authentication. |
| `refresh` | Refresh token, CSRF token, user-agent, request ID → `AuthResult` | Parse session UUID → transaction locks old session → constant-time refresh hash check → constant-time CSRF hash check → load user and validate active/unrevoked/unexpired state → revoke old session → create new session/tokens → append refresh audit. | Generic `AuthenticationError` for malformed, unknown, revoked, expired, inactive, or hash-mismatched refresh; `CsrfValidationError` for missing/bad CSRF; storage maps to `StorageUnavailableError`. Old session is revoked before the new result is committed. | Rotation, replay, concurrent single-winner, logout/password invalidation tests. Missing direct malformed/CSRF/expired refresh matrix and audit ordering assertion. |
| `logout` | Optional refresh and CSRF tokens, request ID → `None` | Missing token or malformed token returns silently → lock session → verify refresh hash → missing/bad CSRF raises → load owner → revoke only if currently active → append logout audit only on actual revocation. | Invalid/missing refresh is intentionally idempotent/silent; bad CSRF raises `CsrfValidationError`; SQL maps to `StorageUnavailableError`. No token is returned. | Route logout and session revocation coverage. Missing direct invalid-CSRF and already-revoked audit characterization. |
| `change_password` | Current principal, current/new password, request ID → `None` | Hash new password first → lock actor user → require existing active user and valid current password → update password → bulk revoke all active refresh sessions → append success audit. | Invalid current/inactive/missing user raises generic `AuthenticationError` after transaction; SQL maps to `StorageUnavailableError`. New hash is never returned; all sessions are revoked on success. | End-to-end password-change revocation and password helper tests. Missing direct assertion that invalid change does not revoke sessions or audit success. |
| `list_users` | None → ordered user response list | Read users ordered by username → map through `user_response_values`. | SQL maps to `StorageUnavailableError`; response excludes password hash. | Administrator user-management test. Missing direct stable ordering test. |
| `create_user` | Actor, request ID, identity/password/profile/role fields → user response | Delegates unchanged to `_insert_user` with actor. | Duplicate identifiers → `DuplicateUserError`; validation/storage errors as described for `_insert_user`. Audit is `user.created` in the same transaction. | Administrator API creation test. Missing direct role/technician invalid mapping matrix. |
| `bootstrap_user` | Explicit CLI identity/password/profile/role fields → user response | Delegates to `_insert_user` with `actor=None`, request ID `cli-bootstrap`, and forced active state. | Duplicate identifiers → `DuplicateUserError`; audit has no actor but remains in transaction. Explicit CLI path only; no startup auto-user creation. | CLI and auth fixtures use it. Missing direct bootstrap audit and inactive-input characterization. |
| `update_user` | Actor, target UUID, updates, request ID → user response | Transaction locks target → reject missing target/self-disable → capture safe before state → apply allow-listed role/technician/display/active fields → validate technician mapping → flush → if role/active changed revoke active sessions → append one or more ordered state-change audits → serialize user. | `UserNotFoundError`, `UserConflictError` for self-disable/stale/duplicate; SQL maps to `StorageUnavailableError`. Role/active changes invalidate sessions; audit includes safe state only. | Administrator deactivation/revocation and protected-resource tests. Missing direct role-change session revocation and multi-action audit ordering. |
| `list_audit_logs` | Page/filter parameters → page dictionary | Build optional action/resource/outcome/actor filters → count → order by occurred time then ID descending → offset/limit → bounded audit response mapping. | SQL maps to `StorageUnavailableError`; no sensitive raw payload is added. | Audit pagination/redaction API test. Missing direct all-filter/order characterization. |
| `record_authorization_denied` | Actor, required permission, request ID, resource type → `None` | Open transaction → append `authorization.denied` with required permission value and bounded path. | Any SQL/operational error is swallowed deliberately after authorization remains denied; best-effort audit only. | Protected insufficient-token/permission behavior indirectly covers denial. Missing direct failure-swallow and payload-bound test. |

## Private service helpers

| Helper | Responsibility and invariants |
|---|---|
| `_insert_user` | Normalizes username/email/technician ID, validates technician-role mapping, hashes password, inserts user, flushes, appends `user.created`, maps integrity/storage failures. This is the only user-create implementation for API and CLI. |
| `_create_session_result` | Generates opaque refresh and CSRF values, stores only hashes in `RefreshSession`, applies configured expiry/user-agent bound, creates access token with current user version/role, and returns `AuthResult` plus a principal. It runs inside the caller’s transaction. |
| `current_user_from_user` in `identity.py` | Maps persisted role and canonical permission matrix into immutable `CurrentUser`; no persistence or token side effects. |
| `_access_state_is_valid` | Requires active user, matching version/role, matching session owner, unrevoked session, and future expiry. |
| `_append_audit` | Creates an append-only `AuditLog` with bounded request/display IDs and `safe_metadata`; used inside the caller’s transaction. |
| `_safe_user_state` / `_user_update_actions` | Allow-listed non-secret state projection and deterministic audit action ordering for user updates. |
| `_validate_technician_mapping` | Requires `technician_id` for the technician role. |
| `_safe_user_agent` / `_identifier_fingerprint` | Bounds user-agent storage and hashes normalized login identifiers; neither stores credentials. |
| `_audit_response_values` | Maps audit rows without adding storage paths, passwords, tokens, or raw authorization data. |
| `_utc_now` | Produces UTC timestamps used for token/session/revocation state. |

## Public compatibility helpers in `service.py`

| Symbol | Current behavior | Coverage |
|---|---|---|
| `normalize_identifier` | Trim/casefold identifier; reject empty with generic authentication error. | `tests/test_security_characterization.py` direct coverage; historical service import preserved. |
| `normalize_optional_identifier` | Apply identifier normalization only when a value exists. | Direct characterization and existing user creation coverage. |
| `normalize_optional` | Trim arbitrary optional value and convert empty to `None`. | Direct characterization and existing update/user coverage. |
| `user_response_values` | Serialize persisted user or `CurrentUser` with canonical role label/permission values and no password hash. | Direct projection/redaction characterization and API response coverage. |
| `append_audit_event` | Append a workflow audit row inside an existing transaction; bounded actor/display/request fields and safe metadata. | Repository transaction tests; direct secret-filter characterization is missing. |
| `CurrentUser` | Frozen principal with value equality and `has(permission)`. | Many service fixtures; direct identity/equality/import characterization is missing. |

`AuthenticationError`, `CsrfValidationError`, `DuplicateUserError`,
`UserNotFoundError`, `UserConflictError`, and frozen `AuthResult` are historical
public imports used by routes, CLIs, tests, and callers. Their exception types,
messages, field names, equality, and serialization behavior are compatibility
surface.

## Supporting cryptographic behavior

`passwords.py` uses the module-level Argon2id `PasswordHasher`; password policy
is 12–256 characters. `verify_password` returns `False` for mismatches and
malformed hashes without exposing details. Unknown login identifiers run dummy
verification.

`tokens.py` issues HS256 access JWTs with issuer/audience, `sub`, `sid`, `role`,
`ver`, `jti`, `type=access`, `iat`, and `exp`. Decode requires all claims,
validates issuer/audience/signature/algorithm/type/expiry, and tries at most the
current and explicitly configured previous signing key. Refresh tokens contain
an opaque secret plus a session UUID; CSRF and refresh values are random and
only SHA-256 hashes are persisted. Hash comparison uses `hmac.compare_digest`.

`audit.py.safe_metadata` filters sensitive key fragments and keeps only bounded
scalar values. Security audit rows are append-only and successful security
mutations add them in the same database transaction as the mutation.

## Environment and transport boundary

`composition/security.py` is the cached outer builder. `security/dependencies.py`
maps bearer/authentication failures to HTTP 401, performs permission checks and
best-effort denial audit. `security/routes.py` owns cookies, CSRF headers,
request schemas, and status-code mapping. Pilot settings enforce PostgreSQL,
secure cookies, strong non-placeholder signing/database credentials, and
verified release identity; this phase must capture that validation order rather
than reorder it.

## Characterization stop condition

## Safe decomposition completed

The characterization established that the following pure cluster could move
without crossing a transaction or transport boundary:

| Module | Responsibilities | Dependencies/state | Public methods and compatibility | Invariants/tests |
|---|---|---|---|---|
| `src/security/identity.py` | Normalize login/profile identifiers; serialize `User`/`CurrentUser`; construct an immutable principal from a persisted user. | Depends on the canonical `User` model, `CurrentUser`, role/permission definitions, and `AuthenticationError`; owns no mutable state and performs no I/O. | `normalize_identifier`, `normalize_optional_identifier`, `normalize_optional`, `user_response_values`, and `current_user_from_user`. The first four remain imported from `src.security.service`; `CurrentUser` remains imported from both historical and direct modules. | Empty identifiers remain generic authentication failures; role permissions remain canonical; responses exclude password/session secrets. Direct coverage is in `tests/test_security_characterization.py`. |
| `src/security/errors.py` | Own the shared generic authentication exception. | No dependencies or mutable state. | `AuthenticationError` is imported by `service.py`, preserving `src.security.service.AuthenticationError` identity. | Error type and generic message behavior remain covered by existing auth tests and direct normalization characterization. |

The following modules were deliberately not extracted because their cohesion is
already represented by real modules or because moving them would cross a
transaction-sensitive boundary:

- `passwords.py` and `tokens.py` are already cohesive cryptographic modules;
  wrapper-only duplicates would add risk without moving ownership.
- `login`, `refresh`, `logout`, `change_password`, `create_user`, `bootstrap_user`,
  `update_user`, and audit orchestration remain in `AuthService` so session
  locking, revocation, token issuance, and same-transaction audit ordering stay
  visible and unchanged.
- `append_audit_event` remains the compatibility helper used by transaction-heavy
  repositories; no audit write path was duplicated or moved.

## Characterization tests and validation

New direct tests in `tests/test_security_characterization.py` cover the frozen
principal and both imports, normalization, principal/response projections,
required access-token claims, current/previous signing keys, invalid signature,
malformed/wrong-type/expired/missing-claim tokens, refresh/CSRF hash behavior,
Argon2 hash compatibility and plaintext exclusion, and secret metadata filtering.
The focused characterization suite passed `12 passed`; the relevant non-
PostgreSQL security suite passed `15 passed, 9 deselected, 1 warning`. Ruff,
compileall, and `git diff --check` passed. The full backend suite passed `402
passed, 73 skipped, 1 warning`; the isolated PostgreSQL workflow passed `73
passed, 402 deselected, 1 warning`. Alembic `current` and `heads` both report
`20260726_0008`, and `alembic check` reports `No new upgrade operations
detected.` The known warning is the existing Starlette/httpx TestClient
deprecation.

No password parameters, token claims, route contracts, environment validation,
audit semantics, database metadata, or transaction boundaries changed. No
frontend file was modified.

## Remaining security boundary and next phase

The remaining security god-file responsibilities are transactional
authentication/session/user administration and audit orchestration in
`AuthService`; its size alone is not sufficient justification for another
split. A future bounded phase may characterize one of those seams with direct
database tests covering validation order, lock ownership, rollback, audit
ordering, and refresh contention before moving implementation. The next single
safe phase is therefore deeper transactional security characterization, not a
token/password/session wrapper extraction.

# Security service characterization

Characterization date: 2026-08-06. This document records the current security
behavior and the one safe decomposition completed after characterization. It
is a behavior map, not a security certification or a production-readiness
claim. The current worktree is the source of truth; existing API, database,
token, and audit behavior is treated as stable.

The selected ORM-free persistence boundary is defined in
[`security-transaction-contract.md`](security-transaction-contract.md).
The refresh-specific operation contract and retained-in-`AuthService` decision
are defined in
[`security-refresh-rotation-contract.md`](security-refresh-rotation-contract.md).

## Boundary and dependencies

`AuthService` in `src/security/service.py` remains the canonical local
authentication/user/audit facade. Pure identity normalization and
user/principal projection live in `src/security/identity.py`; shared exception
ownership lives in `src/security/errors.py`; and the complete logout transaction
now lives in `src/security/session_service.py` behind the ORM-free
`SessionRevocationPort`. AuthService still owns the other security transaction
families and cryptographic primitives remain in `passwords.py` and `tokens.py`.
FastAPI dependencies and routes perform transport mapping and RBAC dependency
wiring; the service does not import FastAPI.

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
| `contracts.py` | ORM-free `SessionRevocationPort` application contract | Exposes only logout inputs/results; no SQLAlchemy, ORM, FastAPI, or response types. |
| `session_service.py` | Complete single-session logout/revocation transaction | Owns one injected session, lock, validation, revocation, audit, commit, rollback, and exception mapping. |
| `audit.py` | Shared security audit-row construction and safe metadata | Audit rows are appended to the caller-owned transaction; UUID generation timing remains unchanged. |

## Public `AuthService` method map

The validation order below is part of the current behavior. “Audit” means an
`AuditLog` is added through `_append_audit` in the same transaction unless the
row explicitly says best effort.

| Method | Inputs / output | Validation order and repository calls | Exceptions and security side effects | Existing coverage / gap |
|---|---|---|---|---|
| `login` | Identifier, password, user-agent, request ID → `AuthResult` | Normalize identifier → fingerprint/rate-limit check → query `User` by normalized username/email → dummy verify for unknown user, otherwise verify hash and active state → on success update `last_login_at`, create refresh session/access token/CSRF token, append success audit. | Generic `AuthenticationError` for limiter, bad credentials, unknown, or inactive account; `StorageUnavailableError` for SQL failures. Failure audit is rejected and contains only identifier fingerprint; failure limiter records, success clears. | Existing API/rate-limit tests plus PostgreSQL persistence, hash-only storage, success/failure audit, and inactive-account characterization. |
| `authenticate_access` | Access token → `CurrentUser` | Decode and validate signature/claims with current then one previous key → read `User` and `RefreshSession` → require active user, matching user version/role, session ownership, unrevoked and unexpired session → build principal. | Invalid/malformed/expired token becomes generic `AuthenticationError`; SQL failures become `StorageUnavailableError`. No mutation or audit. | Unit token tests plus PostgreSQL role/version/session/inactive mismatch characterization and protected-route coverage. |
| `refresh` | Refresh token, CSRF token, user-agent, request ID → `AuthResult` | Parse session UUID → transaction locks old session → constant-time refresh hash check → constant-time CSRF hash check → load user and validate active/unrevoked/unexpired state → revoke old session → create new session/tokens → append refresh audit. | Generic `AuthenticationError` for malformed, unknown, revoked, expired, inactive, or hash-mismatched refresh; `CsrfValidationError` for missing/bad CSRF; storage maps to `StorageUnavailableError`. Old session is revoked before the new result is committed. | The exact order, generation timing, absent replacement relationship, rollback, and retain decision are documented in [`security-refresh-rotation-contract.md`](security-refresh-rotation-contract.md). PostgreSQL rotation/replay, bad-CSRF, expired/revoked, invalidated-user, rollback, and concurrent single-winner tests protect it. |
| `logout` | Optional refresh and CSRF tokens, request ID → `None` | Historical facade delegates the complete operation to `SessionRevocationPort`; the component returns silently for missing/malformed/unknown values, locks the session, verifies hashes, loads the owner, and revokes only an active row. | Invalid/missing refresh is intentionally idempotent/silent; bad CSRF raises `CsrfValidationError`; SQL maps to `StorageUnavailableError`. No token is returned. | PostgreSQL active/repeated/unknown logout, cross-user isolation, one-session ownership, and audit-failure rollback characterization plus route coverage. |
| `change_password` | Current principal, current/new password, request ID → `None` | Hash new password first → lock actor user → require existing active user and valid current password → update password → bulk revoke all active refresh sessions → append success audit. | Invalid current/inactive/missing user raises generic `AuthenticationError` after transaction; SQL maps to `StorageUnavailableError`. New hash is never returned; all sessions are revoked on success. | PostgreSQL invalid non-mutation, revoke-all, audit, and old-access rejection characterization plus existing API coverage. |
| `list_users` | None → ordered user response list | Read users ordered by username → map through `user_response_values`. | SQL maps to `StorageUnavailableError`; response excludes password hash. | Administrator user-management test. Missing direct stable ordering test. |
| `create_user` | Actor, request ID, identity/password/profile/role fields → user response | Delegates unchanged to `_insert_user` with actor. | Duplicate identifiers → `DuplicateUserError`; validation/storage errors as described for `_insert_user`. Audit is `user.created` in the same transaction. | Administrator API creation test; duplicate and technician mapping remain existing service/API coverage. |
| `bootstrap_user` | Explicit CLI identity/password/profile/role fields → user response | Delegates to `_insert_user` with `actor=None`, request ID `cli-bootstrap`, and forced active state. | Duplicate identifiers → `DuplicateUserError`; audit has no actor but remains in transaction. Explicit CLI path only; no startup auto-user creation. | PostgreSQL bootstrap persistence/audit/plaintext characterization plus CLI and fixture coverage. |
| `update_user` | Actor, target UUID, updates, request ID → user response | Transaction locks target → reject missing target/self-disable → capture safe before state → apply allow-listed role/technician/display/active fields → validate technician mapping → flush → if role/active changed revoke active sessions → append one or more ordered state-change audits → serialize user. | `UserNotFoundError`, `UserConflictError` for self-disable/stale/duplicate; SQL maps to `StorageUnavailableError`. Role/active changes invalidate sessions; audit includes safe state only. | PostgreSQL post-issuance role-change/session invalidation plus existing administrator deactivation, RBAC, stale-write, and API coverage. Multi-action ordering remains a gap. |
| `list_audit_logs` | Page/filter parameters → page dictionary | Build optional action/resource/outcome/actor filters → count → order by occurred time then ID descending → offset/limit → bounded audit response mapping. | SQL maps to `StorageUnavailableError`; no sensitive raw payload is added. | Audit pagination/redaction API test. Missing direct all-filter/order characterization. |
| `record_authorization_denied` | Actor, required permission, request ID, resource type → `None` | Open transaction → append `authorization.denied` with required permission value and bounded path. | Any SQL/operational error is swallowed deliberately after authorization remains denied; best-effort audit only. | Protected insufficient-permission behavior covers denial indirectly; direct failure-swallow remains a gap. |

## Private service helpers

| Helper | Responsibility and invariants |
|---|---|
| `_insert_user` | Normalizes username/email/technician ID, validates technician-role mapping, hashes password, inserts user, flushes, appends `user.created`, maps integrity/storage failures. This is the only user-create implementation for API and CLI. |
| `_create_session_result` | Generates opaque refresh and CSRF values, stores only hashes in `RefreshSession`, applies configured expiry/user-agent bound, creates access token with current user version/role, and returns `AuthResult` plus a principal. It runs inside the caller’s transaction. |
| `current_user_from_user` in `identity.py` | Maps persisted role and canonical permission matrix into immutable `CurrentUser`; no persistence or token side effects. |
| `access_state_is_valid` in `session_state.py` | Purely checks user/session ownership, active state, role/version, revocation, and expiry for an already decoded access token. |
| `access_state_is_valid` in `session_state.py` | Requires active user, matching version/role, matching session owner, unrevoked session, and future expiry; performs no I/O or mutation. |
| `append_security_audit` in `audit.py` (`_append_audit` historical alias) | Creates an append-only `AuditLog` with bounded request/display IDs and `safe_metadata`; used inside the caller’s transaction. |
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
| `append_audit_event` | Append a workflow audit row inside an existing transaction; bounded actor/display/request fields and safe metadata. | Repository transaction tests; direct helper-level secret-filter characterization remains a gap. |
| `CurrentUser` | Frozen principal with value equality and `has(permission)`. | Direct identity/equality/import characterization plus broad service fixtures. |

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

## Database-backed behavior and transaction ownership

`AuthService` remains the transaction owner for its persistent security
families. `AuthService.logout` delegates the complete logout family to
`SessionRevocationService`, which owns the same injected factory and uses
`with self.session_factory() as session, session.begin()`. Every other
mutating method uses that same context directly in `AuthService`.
`src/composition/security.py` injects the cached
`sessionmaker[Session]` from `get_session_factory(settings.database_url)`;
FastAPI routes, dependencies, and the CLI do not open a second session for the
same operation. The context commits on normal exit, rolls back on an exception,
and closes the session. The pure `session_state.py` predicate and `identity.py`
projections never own sessions.

The persistent security tables are:

- `users`: normalized identity, Argon2id password hash, active state, role,
  optimistic version, and login timestamps;
- `refresh_sessions`: user-owned session UUID, SHA-256 refresh/CSRF hashes,
  creation/expiry/revocation timestamps, and bounded user agent;
- `audit_logs`: append-only security/workflow events, with optional actor and
  bounded safe metadata. The refresh token hash is unique; user/session and
  audit foreign keys enforce ownership/history rules.

| Operation | Reads/writes and validation order | Flush/commit, locks, rollback, and audit |
|---|---|---|
| `login` | Normalizes and rate-limits before opening the session; queries `users` by normalized username/email; unknown users receive dummy verification. Valid credentials require an active user, update `last_login_at`, add one `refresh_sessions` row through `_create_session_result`, then add `auth.login_succeeded`; invalid credentials add only `auth.login_failed`. | The login timestamp is explicitly flushed before token/session creation. Session and audit rows commit together; any SQLAlchemy error rolls back both. The refresh hash uniqueness constraint protects the stored representation. |
| `authenticate_access` | Decodes and validates the JWT before reading `users` and `refresh_sessions`; `access_state_is_valid` checks active state, user version/role, session ownership, revocation, and expiry. | Read-only session, no explicit transaction, writes, or audit. Invalid state leaves PostgreSQL unchanged. |
| `refresh` | Parses the session UUID, opens one transaction, locks the old `refresh_sessions` row with `FOR UPDATE`, compares refresh and CSRF hashes, loads the owner, and rejects inactive, revoked, or expired state. It then revokes the old row, adds a replacement row, and appends `auth.refreshed`. | Old revocation, replacement creation, token generation, and audit append commit together. Any validation or audit/storage error rolls back the whole sequence. There is no replacement-link column; the old/new relationship is represented by the audit metadata and session ownership. Sequential replay finds the revoked old row and cannot create another session. |
| `logout` | `SessionRevocationService` parses missing/malformed/unknown refresh tokens without mutation. A valid token locks its row, verifies the hash and CSRF value, loads the owner, and revokes only an active session. | Revocation and `auth.logout` append commit together. Repeating logout is a no-op without a second audit event; bad CSRF raises before mutation. |
| `change_password` | Hashes the proposed new password before opening the transaction, locks the actor `users` row, verifies active state/current password, updates the password, and bulk-revokes all active `refresh_sessions` rows for that user. | Password, session revocations, and `auth.password_changed` commit together. Invalid current credentials leave password, sessions, and success audit unchanged. |
| `create_user` / `bootstrap_user` | Normalize and validate identifiers/technician mapping, hash the password, add a `users` row, flush it, and append `user.created`. Bootstrap uses the explicit `cli-bootstrap` request ID, no actor, and forces active state. | User and audit commit atomically. Unique username/email/technician constraints map to `DuplicateUserError`; failures roll back both. No startup creation or idempotency key exists. |
| `update_user` | Locks the target user, rejects missing/self-disable cases, applies the allow-listed updates, validates role/technician mapping, and flushes. Role/active changes bulk-revoke active sessions, then one or more deterministic audit events are appended. | User changes, revocations, and audits share one transaction. Optimistic `User.version`, unique constraints, and final flush protect stale/duplicate writes; exceptions roll back the complete update. |
| `list_users` / `list_audit_logs` | Open a short-lived read session, order/filter rows, map safe projections, and do not mutate state. | No explicit commit or audit. SQL failures map to `StorageUnavailableError`. |
| `record_authorization_denied` | Opens one transaction and appends `authorization.denied` with only the required permission and bounded resource path. | Best-effort by current contract: SQL/operational failure is swallowed after authorization remains denied. This is the deliberate exception to successful mutation audit atomicity. |

There is no production cleanup operation for expired refresh sessions, no
generic security idempotency key, and no separate session repository beyond the
selected complete logout component.
Concurrency protection for refresh is the row lock plus revoked-state check;
the existing PostgreSQL suite also covers the two-thread single-winner refresh
behavior. User role/active changes and password changes invalidate sessions
through bulk updates rather than a separate revocation service.

## Database-backed characterization coverage

`tests/test_security_postgres_characterization.py` adds thirteen isolated
PostgreSQL tests covering session persistence and hash-only storage, successful
and failed/inactive login audit state, rotation and replay, bad-CSRF/expired/
revoked refresh behavior, cross-user CSRF isolation, inactive/password/role
refresh invalidation, replacement and audit rollback, concurrent single-winner
refresh, logout idempotency and cross-user isolation, password-driven
revoke-all, post-issuance role/version/session/inactive access validation,
bootstrap audit state, and one-session contract ownership.
`tests/test_security_transaction_contract.py` and
`tests/test_security_refresh_contract.py` verify that the extracted logout port
and the retained refresh entry point are ORM-free/application-facing.
Existing `tests/test_authentication.py` additionally protects concurrent refresh
single-winner behavior, API-level logout/password revocation, RBAC, rate
limiting, and audit rollback. The new tests assert database rows rather than
only DTOs and use the repository's `clean_postgres_database` fixture and fixed
`maintenance_copilot_test` database.

## Characterization stop condition

The database evidence establishes one complete transaction-family seam:
single-session logout now lives behind `SessionRevocationPort`; the pure access
state predicate remains in `session_state.py`. Login, refresh, password change,
user creation/update, and their audit orchestration remain complete
`AuthService` families. No portion of those sequences was split.

## Safe decomposition completed

The characterization established the following safe pure and complete-family
moves without creating a second transaction owner:

| Module | Responsibilities | Dependencies/state | Public methods and compatibility | Invariants/tests |
|---|---|---|---|---|
| `src/security/identity.py` | Normalize login/profile identifiers; serialize `User`/`CurrentUser`; construct an immutable principal from a persisted user. | Depends on the canonical `User` model, `CurrentUser`, role/permission definitions, and `AuthenticationError`; owns no mutable state and performs no I/O. | `normalize_identifier`, `normalize_optional_identifier`, `normalize_optional`, `user_response_values`, and `current_user_from_user`. The first four remain imported from `src.security.service`; `CurrentUser` remains imported from both historical and direct modules. | Empty identifiers remain generic authentication failures; role permissions remain canonical; responses exclude password/session secrets. Direct coverage is in `tests/test_security_characterization.py`. |
| `src/security/errors.py` | Own shared authentication and CSRF exception types. | No dependencies or mutable state. | `AuthenticationError` and `CsrfValidationError` remain imported by `src.security.service`, preserving historical identities. | Existing auth tests, contract tests, and direct normalization characterization. |
| `src/security/session_state.py` | Pure access-token/session-state validity predicate. | Depends only on the canonical `User`, `RefreshSession`, and decoded `AccessClaims` values; owns no session, transaction, or mutable state. | `access_state_is_valid`; `AuthService` calls it while retaining reads and session ownership. No historical public symbol was removed. | PostgreSQL mismatch, role/version, revocation, and inactive-state tests protect the predicate; no token or API contract changed. |
| `src/security/contracts.py` / `session_service.py` | ORM-free single-session revocation port and complete SQLAlchemy-backed implementation. | The port owns no persistence details; the implementation owns exactly one injected session/transaction and the complete logout sequence. | `SessionRevocationPort.logout`; `AuthService.logout` remains the compatibility facade. | Contract signature test plus PostgreSQL one-session/rollback test and existing API/logout coverage. |

The following modules were deliberately not extracted because their cohesion is
already represented by real modules or because moving them would cross a
transaction-sensitive boundary:

- `passwords.py` and `tokens.py` are already cohesive cryptographic modules;
  wrapper-only duplicates would add risk without moving ownership.
- `login`, `refresh`, `change_password`, `create_user`, `bootstrap_user`,
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
The focused characterization suite passed `12 passed`; the two application
contract tests passed `2 passed`; the combined contract/characterization run
passed `14 passed`; and the PostgreSQL characterization suite passed `13
passed`. The relevant non-PostgreSQL security suite passed `16 passed, 9
deselected, 1 warning`. Ruff, compileall, and `git diff --check` passed. The
full backend suite passed `404 passed, 86 skipped, 1 warning`; the isolated
PostgreSQL workflow passed `86 passed, 404 deselected, 1 warning`.
Alembic `current`
and `heads` both report `20260726_0008`, and `alembic check` reports `No new
upgrade operations detected.` The known warning is the existing Starlette/httpx
TestClient deprecation.

No password parameters, token claims, route contracts, environment validation,
or database metadata changed. The complete logout transaction moved behind
the selected contract while preserving its audit semantics and one-session
boundary. No frontend file was modified.

## Remaining security boundary and next phase

The remaining security god-file responsibilities are transactional
authentication/session/user administration and audit orchestration in
`AuthService`; its size alone is not sufficient justification for another
split. A future bounded phase may characterize one of those seams with direct
database tests covering validation order, lock ownership, rollback, audit
ordering, and refresh contention before moving implementation. The next single
safe phase is therefore deeper transactional security characterization, not a
token/password/session wrapper extraction.

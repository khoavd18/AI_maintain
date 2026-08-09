# Refresh-rotation transaction contract

Date: 2026-08-06. This is the behavior contract for the current
`AuthService.refresh` implementation. It records current behavior, not a
security redesign or a claim of production readiness.

## Boundary and decision

The public entry point is `AuthService.refresh`. It remains in
`src/security/service.py` for this phase. No `RefreshRotationPort` was added:
the smallest useful boundary would have to own the complete transaction and
the shared `_create_session_result` token/session factory, which is also used
by login. A port that delegated token generation back to `AuthService` would
split the atomic family; a port that duplicated it would create two sources of
truth.

The evidence-based decision is therefore:

```text
retain in AuthService
```

Refresh rotation is not safe to extract as a standalone component until the
shared login/refresh session-result factory has its own explicitly approved
contract. Logout remains safely extracted behind its existing complete-family
port.

## Exact operation sequence

The numbered boundaries below expose the requested contract checkpoints while
preserving the actual call order. Session lookup and row-lock acquisition are
one `session.get` call; user ownership/state checks are one conditional; and
replacement creation, token generation, and result construction are one shared
`_create_session_result` helper. The current effective order is parse → capture
time → open/lock → verify refresh hash → verify CSRF → load/validate user and
session → revoke old row → create replacement → append audit → context flush/
commit → return.

| # | Owner, inputs/outputs, reads/writes, lock and generation timing | Failure and persistent state |
|---:|---|---|
| 1. Request and presence | `security.routes.refresh` reads the configured refresh cookie and `X-CSRF-Token`; missing values become empty strings passed to `AuthService.refresh`. | No database access or lock. Missing refresh eventually maps to generic authentication failure; missing CSRF maps to `CsrfValidationError` after the refresh hash check. |
| 2. Token processing | `AuthService.refresh` calls `refresh_session_id(refresh_token)`, which splits the opaque value and returns a UUID; it does not persist or hash the raw value. | Malformed input raises generic `AuthenticationError` before a session/transaction opens; state is unchanged. |
| 3. Token type | There is no JWT decode or refresh-token `type` claim. The UUID prefix plus secret length of at least 32 is the complete opaque-token format check. | Wrong/malformed format uses the same generic authentication error; no lock, write, audit, or secret exposure. |
| 4. Time capture | `_utc_now()` runs after parsing and before session acquisition. Its UTC value is reused for expiry comparison, old revocation, and replacement `created_at`/expiry calculation. | No database write yet; the captured value is discarded on any failure. |
| 5. Session lookup | Inside `with self.session_factory() as session, session.begin()`, `session.get(RefreshSession, session_id, ...)` reads the token's session row. | Missing row raises generic `AuthenticationError`; the transaction rolls back with no audit or replacement. |
| 6. Row lock | The same `session.get(..., with_for_update=True)` acquires the PostgreSQL row lock and holds it through commit/rollback. | Lock contention serializes concurrent attempts; no second session or transaction is opened by refresh. |
| 7. Refresh hash | `token_hash_matches` hashes the presented refresh value and compares it constant-time with `old_session.token_hash`. | Mismatch raises generic `AuthenticationError`; raw refresh material is never persisted or logged. |
| 8. CSRF validation | Presence and constant-time comparison against `old_session.csrf_token_hash` occur after the refresh hash check and before user lookup. | Missing/mismatched CSRF raises `CsrfValidationError`; no old-session mutation, replacement, or audit is committed. |
| 9. Session ownership | Ownership is derived from the locked row's `user_id`; `refresh` has no separate principal argument and does not accept a caller-supplied owner. | A token can address only its own session row. Cross-user CSRF cannot rotate it; no ownership error is separately exposed. |
| 10. User lookup | `session.get(User, old_session.user_id)` loads the persisted owner in the same transaction. | Missing owner raises generic `AuthenticationError`; the locked session remains unchanged after rollback. |
| 11. User active state | The conditional requires `user.is_active`. | Inactive users receive generic `AuthenticationError`; no revocation, replacement, or audit persists. |
| 12. User role/version/security state | Refresh has no JWT role/version claims to compare. Role/password/security changes invalidate existing sessions through service-level revocation, which is then observed here. | A stale/revoked security state raises generic `AuthenticationError`; there is no direct refresh-time role/version write. |
| 13. Expiry validation | The same captured `now` is compared with `old_session.expires_at`; `expires_at <= now` is rejected. | Generic `AuthenticationError`; an expired row remains unrevoked and no replacement/audit is created. |
| 14. Revocation validation | The conditional requires `old_session.revoked_at is None`. | A revoked row raises generic `AuthenticationError`; persistent state is unchanged. |
| 15. Replay/replacement validation | Replay is the revoked-state check under the row lock. There is no separate replay table, nonce, or replacement-reference lookup. | A previously successful old token cannot be reused; exactly one replacement can be created for the old row. |
| 16. Old-session rotation marking | `old_session.revoked_at = now` mutates the locked ORM row in memory before replacement creation. | The mutation is uncommitted until flush/commit; any later failure rolls it back. |
| 17. Replacement-session creation | `_create_session_result(session, user, now, user_agent)` starts the shared login/refresh session-result factory and returns an `AuthResult` plus principal. | A replacement is not visible outside the transaction before commit; injected creation failure maps to `StorageUnavailableError` and rolls back old revocation. |
| 18. Replacement relationship | No `replaced_by`, `replacement_session_id`, or equivalent column exists and no relationship assignment is performed. | The old/new relationship is represented only by old revocation, shared user ownership, and audit metadata; no dangling relationship can exist. |
| 19. Refresh-token generation | The helper generates a new replacement UUID first, then calls `create_refresh_token(new_session_id)`. | The opaque plaintext exists only in the in-memory result; UUID/secret generation occurs before persistence and is not recoverable from storage. |
| 20. CSRF-token generation | The helper calls `create_csrf_token()` after refresh-token generation. | Plaintext CSRF exists only in the in-memory result; failed transactions persist no CSRF plaintext or hash. |
| 21. Replacement timing and access token | The helper computes `refresh_expires_at = now + configured days`, adds the replacement row, then calls `create_access_token` with current user role/version and the same `now`. | Access-token generation occurs before flush/commit; all timestamps and bounded user-agent data are derived inside this transaction family. |
| 22. Token hash persistence | The pending `RefreshSession` stores `hash_token(refresh_token)` and `hash_token(csrf_token)`, never raw values, with the new ID, owner, `created_at=now`, expiry, and safe user-agent. | The unique refresh-hash constraint remains active; persistence failure rolls back the old mutation and leaves no replacement. |
| 23. Audit UUID creation | `_append_audit` is the historical alias for `append_security_audit`, which creates `AuditLog.id = uuid4()` when called. | UUID generation happens before flush and is discarded on rollback; no token, CSRF, cookie, or authorization value is included. |
| 24. Audit append and flush/commit | The helper adds `auth.refreshed` with `resource_id=new_session_id` and `{"rotated_session_id": old_session_id}` to the same transaction. Refresh has no explicit flush; the context flushes old row, replacement, and audit during commit. | Audit append/flush/commit failure rolls back all session and audit state and maps to `StorageUnavailableError`. |
| 25. Result, rollback, and API mapping | `AuthResult` is built before the in-context `return`; the caller receives it only after context exit commits. SQLAlchemy/operational errors are mapped to `StorageUnavailableError`; route code returns access data and sets replacement cookies. | A failed commit cannot return success. Validation/security failures roll back the same transaction; the route maps authentication to 401, CSRF to 403, and storage to 503 without exposing secrets. |

## Invariants and characterized edge cases

- A valid opaque refresh token succeeds once. The old row is revoked before a
  replacement is committed; replay locks the old row and rejects it.
- Exactly one replacement exists after successful sequential or concurrent
  rotation. There is no `replaced_by`/replacement foreign-key field.
- Expired and revoked rows do not rotate. Rejected expired rows remain
  unrevoked because expiry validation precedes old-session mutation.
- CSRF mismatch, malformed token, unknown session, and hash mismatch do not
  mutate the old row or create audit/replacement rows.
- Inactive users do not rotate. Password and role changes invalidate existing
  sessions through their own service transactions, so subsequent refresh is
  rejected as revoked.
- The method has no separate principal parameter. Bearer ownership is the
  session row identified by the opaque token; a different user's CSRF value
  cannot rotate the session.
- Old/new session rows, token hashes, audit state, and revocation are atomic.
  Failure before replacement creation and failure during audit append both
  leave the original session active with no replacement/audit event.
- Row locking plus the revoked-state check yields one winner under concurrent
  refresh. The existing integration tests assert one replacement and one
  `auth.refreshed` event.

## Tests protecting the contract

`tests/test_security_postgres_characterization.py` covers persistent success,
hash-only storage, old/new state, absent replacement relationship, sequential
replay, cross-token CSRF isolation, expired/revoked sessions, inactive state,
password/role invalidation, replacement failure rollback, audit failure
rollback, and concurrent single-winner persistence. Existing authentication
tests protect API behavior and concurrent refresh; pure token tests protect
opaque parsing, hashing, CSRF generation, claims, and expiry.

No production refresh implementation was moved in this phase. The next safe
candidate is a shared session-result/token-generation contract only if login
and refresh can adopt it without changing generation timing or transaction
ownership.

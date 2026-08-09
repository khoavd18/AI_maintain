# Security transaction contract

Date: 2026-08-06. This contract records the smallest persistence boundary
supported by the current implementation. It is an application contract, not a
generic repository or unit-of-work framework.

## Selected boundary

Option C is selected for one complete family: single-session logout/revocation.
The public port is `src/security/contracts.py:SessionRevocationPort`; the
current PostgreSQL-backed implementation is
`src/security/session_service.py:SessionRevocationService`.

`AuthService.logout` remains the historical application entry point and
delegates the entire operation to the port. The component owns the complete
sequence:

```text
parse refresh-session identifier
→ acquire one SQLAlchemy session
→ begin one transaction
→ lock the refresh session
→ verify refresh and CSRF hashes
→ load the session owner
→ revoke the active session
→ append auth.logout audit
→ commit, or roll back everything
```

No half-transaction remains in `AuthService`. The port does not expose
SQLAlchemy `Session`, ORM models, FastAPI types, response schemas, or concrete
PostgreSQL repository classes.

## Public contract

`SessionRevocationPort.logout` accepts:

- `refresh_token: str | None`;
- `csrf_token: str | None`;
- `request_id: str`;
- returns `None`.

Missing, malformed, unknown, or already-revoked refresh sessions preserve the
existing silent/idempotent behavior. A valid active session requires a matching
CSRF token and produces one revocation plus one `auth.logout` audit event. A bad
CSRF token raises the historical `CsrfValidationError`; database failures map
to `StorageUnavailableError`.

## Ownership and invariants

`SessionRevocationService` owns the session factory usage, transaction context,
row lock, validation order, audit call, commit, rollback, and exception mapping.
The outer composition root injects the same session factory used by
`AuthService`; the component does not create another engine, factory, or nested
transaction. `append_security_audit` is the single shared audit-row
implementation, and it generates the audit UUID when the event is appended,
matching the previous helper timing.

Logout creates no tokens. It persists only the existing session revocation
timestamp; refresh and CSRF values are compared against their stored hashes.
The operation is isolated to the token's owning user/session and does not
implement cleanup, idempotency keys, email delivery, or any other workflow.

## Compatibility strategy

The existing `AuthService` constructor remains compatible with its historical
two arguments. Its optional `session_revocation` port is used by the
composition root and defaults to the current concrete implementation for
direct CLI/test construction. `src.security.service.logout`, route behavior,
CLI construction, exception types, and the `get_auth_service().cache_clear()`
composition seam remain unchanged.

The existing `AuthenticationError`, `CsrfValidationError`, `CurrentUser`, and
other historical security imports remain available from `src.security.service`.

## Alternatives rejected

Option A, a broad persistence repository protocol, was rejected because the
current operation is not a collection of independently useful CRUD calls. A
CRUD-shaped port would expose transaction sequencing to its caller and invite
the old session-revocation/audit split.

Option B, a general security unit-of-work protocol, was rejected because it
would introduce a framework-sized abstraction for one operation and would
obscure the current concrete ownership. The selected component already makes
one session and one transaction explicit without creating nested or competing
owners.

Refresh rotation, password revoke-all, login/session creation, and user/account
security updates remain in `AuthService`. The exact refresh sequence and its
retained-in-place decision are documented in
[`security-refresh-rotation-contract.md`](security-refresh-rotation-contract.md).
Their complete sequences combine more validation, token timing, locks, bulk
updates, concurrency, or multiple audit states. They are not authorized for
extraction by this contract.

## Contract-level evidence

`tests/test_security_transaction_contract.py` verifies that the port is ORM-free
and application-facing. The PostgreSQL characterization test verifies that the
concrete component uses one session per operation and that an audit failure
rolls back revocation and audit state together. Existing API/PostgreSQL tests
continue to invoke `AuthService.logout`, protecting the historical facade.

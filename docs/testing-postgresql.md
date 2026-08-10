# PostgreSQL integration testing

PostgreSQL integration tests use a dedicated local Compose project. The test
database is deliberately separate from the development Compose stack:

- image: `postgres:16-alpine`;
- host port: `15433`;
- database: `maintenance_copilot_test`;
- user: `maintenance_test`;
- volume: `postgres_test_data` in project `ai-maintenance-copilot-test`.

The database name must end in `_test`. Test URLs are accepted only for local
loopback hosts, with explicit credentials, the `postgresql+psycopg` driver, and
no development placeholders or development credentials. During scripted runs,
`DATABASE_URL` and `TEST_DATABASE_URL` must be identical so Alembic and pytest
cannot silently target different databases.

## PowerShell workflow

From the repository root:

```powershell
.\scripts\test-postgres.ps1 -Action reset
.\scripts\test-postgres.ps1 -Action test -Keep
```

The default action migrates the test database, runs `pytest -m postgres -q`,
prints `alembic heads` and `alembic current`, and runs `alembic check`. Add
`-Full` to run the complete pytest suite in the same isolated environment.
Use `-Keep` to leave the container running for inspection; without it, the
script stops the test service after the command. The explicit reset action is
the only action that removes the dedicated test volume.

To start or stop the service without running tests:

```powershell
.\scripts\test-postgres.ps1 -Action up -Keep
.\scripts\test-postgres.ps1 -Action down
```

The checked-in `.env.test.example` contains only safe local example values.
Never point destructive test fixtures at the normal development database or at
a host outside loopback.

## Metadata equivalence checkpoint

Before a SQLAlchemy model split, generate a complete representation with:

```powershell
.\.venv\Scripts\python.exe -m src.database.metadata_snapshot --output docs/metadata-snapshot.json
```

The snapshot includes tables, columns, types, nullability, defaults, primary
and foreign keys, unique/check constraints, indexes, and enum definitions.
`metadata_fingerprint()` provides a stable before/after comparison. A model
package split remains deferred until this comparison and `alembic check` both
remain unchanged.

The current baseline is recorded in `docs/metadata-snapshot.json`. The model
package split and subsequent repository query/catalogue decomposition have
been validated against this snapshot; no migration is generated for structural
refactoring.

Service, RAG, and frontend decomposition phases use this same isolated database.
Run `.\scripts\test-postgres.ps1 -Action test -Keep` for the PostgreSQL
selection and add `-Full` for the complete suite in the same validated
environment. Do not carry a historical expected failure forward: record every
failure as current-change, pre-existing, or infrastructure-blocked. If Docker is
unavailable, PostgreSQL tests and database-backed Alembic checks are blocked,
not passed. The frontend deterministic command is:

```powershell
npm --prefix frontend run test -- --run --pool=forks --no-file-parallelism --maxWorkers=1
```

The installed Vitest version rejects the older `singleFork=true` option.

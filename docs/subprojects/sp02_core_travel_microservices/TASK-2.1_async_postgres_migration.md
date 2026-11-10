# TASK-2.1 — Async PostgreSQL Migration

| Field         | Value                                                                                                                                                   |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Epic          | SP02 — Productionizing Flight & Hotel Core Microservices                                                                                                |
| PR            | PR 1 of 4                                                                                                                                               |
| Branch        | `feat/sp02-t01-async-postgres`                                                                                                                          |
| Target branch | `productionize`                                                                                                                                         |
| Status        | **Design proposed, awaiting confirmation.** No application code has been changed yet                                                                    |
| Depends on    | SP01 (Neon Postgres and `DATABASE_URL` secret via Terraform, Postgres in Compose, CI/CD to Cloud Run), SP00 (`pip-tools` lockfile workflow, pre-commit) |
| Parent docs   | [`EPIC_PRD.md`](EPIC_PRD.md), [`00_MASTER_PRD.md`](../../00_MASTER_PRD.md)                                                                              |

---

## 1. Objective

Replace the per-service SQLite files with the shared managed Postgres, using a fully async data layer, versioned migrations, and a test setup that runs against real Postgres everywhere. This is a **pure platform migration**: the REST contract that `flight_mcp_server`, `hotel_mcp_server` and the agent rely on does not change. It lays the foundation for transactional bookings (TASK-2.3), idempotency (TASK-2.4) and users (TASK-2.2), all of which need real constraints, row locks and a real schema history.

## 2. Scope

### In scope

| Area                                    | Change                                                                                                                                                                                              |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `requirements.in`                       | Add `sqlalchemy[asyncio]`, `asyncpg`, `alembic` (lockfile recompiled with `scripts/compile-requirements.ps1`)                                                                                       |
| `common/` (new)                         | `db.py`: `DATABASE_URL` normalization, engine and pool factory, readiness check, guarded migration runner. Shared by both services                                                                  |
| `flight_api/`, `hotel_api/`             | `database.py` rewritten (schema, `MetaData`, `Table` definitions, engine access); `app.py` made fully async with a lifespan handler; new `seed.py`; new `alembic.ini` and `migrations/` per service |
| Endpoints                               | Same routes and JSON as today, plus `GET /ready`. `/health` stays a pure liveness check                                                                                                             |
| `tests/`                                | `conftest.py` with Postgres fixtures; existing API tests kept and pointed at Postgres; new tests for URL normalization, migrations, seed idempotency, readiness and schema isolation                |
| `pytest.ini`                            | New `db` marker                                                                                                                                                                                     |
| `.github/workflows/ci.yml`              | Postgres service container for the test job; `DATABASE_URL` for the API processes it starts; fix the unquoted `pip install pre-commit>=4.0.0` in `format-check` (see Risks)                         |
| `.github/workflows/cd.yml`              | The post-deploy gate checks `/ready` (database reachable) instead of `/health`                                                                                                                      |
| `docker-compose.yml`                    | APIs receive `DATABASE_URL` and wait for Postgres to be healthy; header comments updated                                                                                                            |
| Dockerfiles (`flight_api`, `hotel_api`) | Also copy `common/`; the SQLite write-permission workaround is removed                                                                                                                              |
| `.env.example`, `README.md`             | `DATABASE_URL` and related settings documented; local run and test instructions updated                                                                                                             |

### Out of scope

- Any write endpoint, booking table, user table, idempotency key or email (TASK-2.2 to TASK-2.5).
- Per-service database roles and `GRANT` hardening, and separate databases per service.
- Pagination, new filters, or any other API change beyond the two documented validation changes below.
- Terraform changes: `DATABASE_URL` is already created and injected into both services by SP01.
- Moving migrations out of service start-up into a separate release job (see decision D4).

## 3. Architectural Notes

### 3.1 Design decisions (proposed)

| #   | Decision                                                                                                                               | Alternative considered                                          | Why this choice                                                                                                                                                                                                                                                                                                                 |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | **SQLAlchemy 2.0 Core (async) + asyncpg + Alembic**                                                                                    | Bare `asyncpg` with hand-written SQL and ad-hoc migration files | TASK-2.2 to 2.5 add tables, constraints and locking. Alembic gives reviewed, reversible, per-service migration history; Core's `select(...).with_for_update()` makes row locks explicit; `Table` metadata is the single schema source. Core (not the ORM) keeps queries SQL-shaped and avoids session and lazy-loading pitfalls |
| D2  | **One schema per service** (`flight`, `hotel`) in the shared database, tables schema-qualified in code, one Alembic history per schema | Table-name prefixes in one schema; separate databases           | Real isolation and ownership without any Terraform change; avoids reliance on `search_path` (PgBouncer-safe); keeps the door open to database-per-service. See the epic's database design section                                                                                                                               |
| D3  | **Test on real Postgres everywhere**: a GitHub Actions service container in CI and the Compose Postgres locally                        | An in-memory or file SQLite fallback via `aiosqlite`            | TASK-2.3 depends on `SELECT ... FOR UPDATE`, which SQLite does not support, and Postgres differs in types, case handling and DDL. A SQLite fallback would pass tests that production fails                                                                                                                                      |
| D4  | **Run migrations at service start-up**, serialized by a Postgres advisory lock                                                         | A separate release job (Cloud Run Job or CD step)               | Keeps CD, IAM and Terraform unchanged (the deployer has no database access by design). The lock makes concurrent instances safe. A failed migration stops the container, so the revision never becomes ready and CD rolls back. Revisit when migrations get heavy                                                               |
| D5  | **Seed data lives in `seed.py`, not in migrations**, applied idempotently at start-up (`SEED_MOCK_DATA`, default `true`)               | Seed rows inside a migration                                    | Migrations should be schema-only and reversible; mock data is a product choice that will change or be disabled. Idempotent `INSERT ... ON CONFLICT DO NOTHING` makes concurrent start-ups safe                                                                                                                                  |
| D6  | **Column types chosen to keep the JSON output identical**                                                                              | `TIMESTAMPTZ`, `NUMERIC` for rating                             | `TIMESTAMP` (no zone) serializes as `2026-06-10T08:30:00`, `DATE` as `2026-06-10`, `DOUBLE PRECISION` as `4.2`. The agent slices `departure_time[:10]`, so an offset suffix or `Decimal` strings would be a contract change                                                                                                     |
| D7  | **Add `GET /ready`** (database reachable) and point the CD gate at it; `/health` remains liveness                                      | Reuse `/health` for both                                        | The current gate cannot detect a database problem. Liveness must not depend on the database, or a brief Neon hiccup would look like a dead process                                                                                                                                                                              |
| D8  | **Normalize `DATABASE_URL`** inside `common/db.py`                                                                                     | Require the exact asyncpg URL form from the secret              | Neon's URI is `postgresql://...?sslmode=require` (possibly with `channel_binding`). SQLAlchemy's asyncpg dialect forwards unknown query parameters to asyncpg, which rejects `sslmode`. The helper rewrites the scheme to `postgresql+asyncpg`, maps `sslmode` to `ssl`, and drops `channel_binding`                            |
| D9  | **`DATABASE_URL` defaults to the Compose development URL** for local runs                                                              | No default; fail if unset                                       | Matches the repository's convention of local defaults (the API base URLs); in Cloud Run the secret always overrides it, and a wrong default fails fast with a connection error                                                                                                                                                  |

### 3.2 Layout after this task

```text
common/
  __init__.py
  db.py               URL normalization, engine factory, readiness check, guarded migration runner
flight_api/
  app.py              FastAPI app, lifespan handler, async endpoints
  database.py         schema name, MetaData, `flights` table, engine accessor
  seed.py             MOCK_FLIGHTS and the idempotent seed
  alembic.ini         for CLI use (`alembic -c flight_api/alembic.ini ...`)
  migrations/         env.py, script.py.mako, versions/0001_create_flights.py
hotel_api/            same shape, with `hotels`
tests/
  conftest.py         Postgres fixtures (test database, environment wiring, clean schema per session)
  test_common_db.py   URL normalization and engine configuration
  test_migrations.py  upgrade/downgrade round trip and schema isolation
  test_flight_api.py, test_hotel_api.py   existing tests plus /ready and seed idempotency
```

### 3.3 Data model

Both tables keep the existing columns so the API output is unchanged, and gain the constraints and indexes the later tasks depend on.

**`flight.flights`**

| Column            | Type                                  | Constraints                                       |
| ----------------- | ------------------------------------- | ------------------------------------------------- |
| `id`              | `BIGINT GENERATED ALWAYS AS IDENTITY` | Primary key                                       |
| `flight_number`   | `TEXT`                                | Not null                                          |
| `airline`         | `TEXT`                                | Not null                                          |
| `origin`          | `TEXT`                                | Not null                                          |
| `destination`     | `TEXT`                                | Not null                                          |
| `departure_time`  | `TIMESTAMP`                           | Not null                                          |
| `arrival_time`    | `TIMESTAMP`                           | Not null, `CHECK (arrival_time > departure_time)` |
| `price`           | `INTEGER`                             | Not null, `CHECK (price >= 0)`                    |
| `seats_available` | `INTEGER`                             | Not null, `CHECK (seats_available >= 0)`          |

Also: `UNIQUE (flight_number, departure_time)` (makes seeding idempotent) and an index on `(origin, destination, departure_time)` for search.

**`hotel.hotels`**

| Column            | Type                                  | Constraints                                        |
| ----------------- | ------------------------------------- | -------------------------------------------------- |
| `id`              | `BIGINT GENERATED ALWAYS AS IDENTITY` | Primary key                                        |
| `name`            | `TEXT`                                | Not null                                           |
| `city`            | `TEXT`                                | Not null                                           |
| `area`            | `TEXT`                                | Not null                                           |
| `check_in_date`   | `DATE`                                | Not null                                           |
| `check_out_date`  | `DATE`                                | Not null, `CHECK (check_out_date > check_in_date)` |
| `price_per_night` | `INTEGER`                             | Not null, `CHECK (price_per_night >= 0)`           |
| `rooms_available` | `INTEGER`                             | Not null, `CHECK (rooms_available >= 0)`           |
| `rating`          | `DOUBLE PRECISION`                    | Not null, `CHECK (rating BETWEEN 0 AND 5)`         |

Also: `UNIQUE (name, check_in_date)` and an index on `(city, check_in_date)`.

The non-negative checks are deliberate groundwork: in TASK-2.3 they make "seats can never go below zero" a database guarantee, not just application logic. The seed inserts rows in the same order as today so `/flights/1` is still `AI101` and `/hotels/1` is still `Delhi Stay`.

### 3.4 Behavior and contract

- **Unchanged:** routes, field names, JSON formats, result ordering (departure time; nightly price), case-insensitive `origin`/`destination`/`city` matching, and the 404 messages `Flight not found` / `Hotel not found`.
- **Two deliberate tightenings:** `date` (flights) and `check_in_date` (hotels) become typed date parameters. An invalid value such as `?date=tomorrow` now returns **422** with a validation message instead of silently returning an empty list. Valid `YYYY-MM-DD` values behave as before.
- **New:** `GET /ready` returns `200 {"status":"ready"}` when a short `SELECT 1` succeeds and `503 {"status":"unavailable"}` otherwise. `GET /health` is unchanged.
- **Date filtering** uses a half-open range on `departure_time` (`>= date` and `< date + 1 day`) so it can use the index, replacing the SQLite `substr(...)` trick.

### 3.5 Connection and migration mechanics

- **Engine lifecycle.** Each app creates its async engine inside the lifespan handler (never at import time, which would bind it to the wrong event loop) and stores it on `app.state`; it is disposed on shutdown. The lifespan handler replaces the deprecated `@app.on_event("startup")`.
- **Pool.** Small pool (default 3) with pre-ping and recycling, because Neon suspends idle compute and silently drops connections. The direct (non-pooled) Neon endpoint is used, which is what Terraform stores. If the PgBouncer pooler endpoint is ever used, asyncpg's prepared-statement cache must be disabled.
- **Start-up sequence.** Normalize URL, build engine, take the advisory lock, run `alembic upgrade head`, release the lock, run the idempotent seed, start serving. uvicorn finishes lifespan start-up before it opens the listening socket, so the Cloud Run TCP startup probe only passes once migrations succeed; a failed migration means the revision never becomes ready and CD's health gate and rollback handle it.
- **Alembic in an async app.** Migrations run on the connection that already holds the lock and inside the already-running event loop, so `env.py` accepts a connection passed in through Alembic's `config.attributes` and runs migrations with `run_sync`. The same `env.py` also supports the plain CLI path (`alembic -c ... upgrade head`) by creating its own engine.
- **Per-service history.** `version_table_schema` is the service schema, and `env.py` creates the schema first (`CREATE SCHEMA IF NOT EXISTS`), so `flight.alembic_version` and `hotel.alembic_version` are independent. Each service uses its own advisory-lock key, so the two never block each other.

### 3.6 Test strategy

| Layer                                 | Runs against                                           | Notes                                                                                                                                                                    |
| ------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Pure unit tests                       | Nothing external                                       | URL normalization, agent mock logic. Run alone with `pytest -m "not db and not integration"`                                                                             |
| API and migration tests (`db` marker) | A dedicated test database `travel_agent_test`          | A session fixture drops the `flight` and `hotel` schemas, then each app's lifespan rebuilds them from migration zero, so **every run exercises the full migration path** |
| End-to-end (`integration` marker)     | The same test database, through real uvicorn processes | The fixture starts the APIs with `DATABASE_URL` pointing at the test database (subprocesses inherit the environment) or reuses APIs that are already running             |

- **Local:** `docker compose up -d postgres` provides the server. The fixture connects to `TEST_DATABASE_URL` (default `postgresql://travel:travel_dev_password@127.0.0.1:5432/travel_agent_test`) and creates the test database if it is missing, so development data in `travel_agent` is never touched. If Postgres is unreachable, tests **fail with an actionable message** rather than skip, so a broken setup cannot look like a pass.
- **CI:** the `Lint & Test` job gets a `postgres` service container (`pgvector/pgvector:pg16`, the same image as Compose and the same major version as Neon, with a health check) and `TEST_DATABASE_URL` / `DATABASE_URL` set to it, including for the step that starts the API processes.
- **Why not SQLite.** See decision D3. The `db` marker plus the `-m "not db and not integration"` selector give developers without Docker a fast path for pure unit tests without pretending SQLite results are meaningful.

### 3.7 Deployment

- **Cloud Run:** no Terraform change. `DATABASE_URL` is already mounted from Secret Manager for both services. The first deploy of the new image creates the `flight` and `hotel` schemas and seeds them in Neon. Both services share that data, replacing today's per-instance copies.
- **Start-up time budget:** the TASK-1.4 startup probe allows about 50 seconds (10 checks, 5 seconds apart). A Neon cold start plus one small migration and seed is expected to take a few seconds. If it proves tight, raise `failure_threshold` in Terraform as a follow-up.
- **CD gate:** switches to `/ready`, so a deploy that cannot reach the database is rolled back automatically. The rollback drill is unaffected.
- **Compose:** both APIs get `DATABASE_URL` for the `postgres` service and wait for it to be healthy; their health checks use `/ready` so the `agent` smoke test only starts once the database is usable.

## 4. Acceptance Criteria

| #    | Criterion                                                                                                                                                                                                                            |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| AC1  | `requirements.in` adds `sqlalchemy[asyncio]`, `asyncpg` and `alembic`; the recompiled `requirements.txt` pins them and CI's lockfile-parity check passes.                                                                            |
| AC2  | `common/db.py` normalizes `postgres://` and `postgresql://` URLs to `postgresql+asyncpg://`, maps `sslmode` to `ssl`, drops `channel_binding`, and is covered by unit tests including a Neon-style URI.                              |
| AC3  | Neither API imports `sqlite3`; every endpoint is `async def` using SQLAlchemy Core with parameterized queries; the lifespan handler replaces `@app.on_event`.                                                                        |
| AC4  | Each service has its own Alembic environment. `upgrade head` creates its schema, its table and `<schema>.alembic_version`; `downgrade base` and `upgrade head` round-trip cleanly; the two services never touch each other's schema. |
| AC5  | The tables carry the identity primary keys, `CHECK` constraints, unique constraints and indexes in section 3.3.                                                                                                                      |
| AC6  | Seeding is idempotent: starting two instances at the same moment, or restarting, leaves exactly five rows per table, and `/flights/1` is `AI101` and `/hotels/1` is `Delhi Stay`.                                                    |
| AC7  | The REST contract is unchanged for valid requests (routes, fields, JSON formats, ordering, 404 messages); an invalid `date` or `check_in_date` returns 422.                                                                          |
| AC8  | `GET /health` stays 200 without a database; `GET /ready` returns 200 when the database is reachable and 503 when it is not.                                                                                                          |
| AC9  | The existing unit tests pass against Postgres, and the end-to-end tests pass with the agent, MCP servers and APIs unchanged.                                                                                                         |
| AC10 | CI runs a Postgres service container, passes `DATABASE_URL` to the API processes, and all tests (unit and integration) pass; the `format-check` install command is quoted correctly.                                                 |
| AC11 | `docker compose up --build --abort-on-container-exit --exit-code-from agent` succeeds with both APIs on Postgres.                                                                                                                    |
| AC12 | Both images include `common/`, build, and run as non-root.                                                                                                                                                                           |
| AC13 | `cd.yml` gates on `/ready`.                                                                                                                                                                                                          |
| AC14 | _(Manual, after merge)_ The CD run passes the gate against Neon; `flight` and `hotel` schemas exist in Neon with five rows each; both Cloud Run services return identical data.                                                      |
| AC15 | `README.md` and `.env.example` document `DATABASE_URL`, the local Postgres requirement, and the `db` marker.                                                                                                                         |

## 5. Verification Commands

Run from the repository root (PowerShell) with the virtual environment active. Docker Desktop must be running.

```powershell
# 0. Recompile the lockfile in a Linux container, sync, and confirm the new packages (AC1)
.\scripts\compile-requirements.ps1
.\scripts\sync-dev.ps1
Select-String -Path requirements.txt -Pattern "^(sqlalchemy|asyncpg|alembic)=="    # expect: three pinned lines

# 1. Local Postgres (AC9, AC11)
docker compose up -d postgres
docker compose ps                                                 # expect: postgres healthy

# 2. Fast tests that need nothing external (AC2)
pytest -m "not db and not integration"

# 3. Full suite against Postgres (AC3-AC10)
pytest                                                            # expect: all pass; report.html written

# 4. No SQLite left (AC3)
git grep -n "sqlite3" -- "*.py"                                   # expect: no output

# 5. Migrations from the CLI: round trip and per-service history (AC4, AC5)
$env:DATABASE_URL = "postgresql://travel:travel_dev_password@127.0.0.1:5432/travel_agent_test"
alembic -c flight_api/alembic.ini upgrade head
alembic -c hotel_api/alembic.ini upgrade head
alembic -c flight_api/alembic.ini current                         # expect: 0001 (head)
alembic -c flight_api/alembic.ini downgrade base
alembic -c flight_api/alembic.ini upgrade head
docker compose exec postgres psql -U travel -d travel_agent_test -c "\dt flight.*" -c "\dt hotel.*"
docker compose exec postgres psql -U travel -d travel_agent_test -c "SELECT version_num FROM flight.alembic_version" -c "SELECT version_num FROM hotel.alembic_version"
docker compose exec postgres psql -U travel -d travel_agent_test -c "\d flight.flights"   # expect: identity PK, CHECKs, unique, index
Remove-Item Env:DATABASE_URL

# 6. Idempotent seeding under concurrent start-up (AC6): start two instances at once against an empty schema
docker compose exec postgres psql -U travel -d travel_agent_test -c "DROP SCHEMA IF EXISTS flight CASCADE"
$env:DATABASE_URL = "postgresql://travel:travel_dev_password@127.0.0.1:5432/travel_agent_test"
$a = Start-Process python -ArgumentList "-m","uvicorn","flight_api.app:app","--port","8000" -PassThru -WindowStyle Hidden
$b = Start-Process python -ArgumentList "-m","uvicorn","flight_api.app:app","--port","8010" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 10
docker compose exec postgres psql -U travel -d travel_agent_test -c "SELECT count(*) FROM flight.flights"   # expect: 5, not 10
Invoke-RestMethod http://127.0.0.1:8000/flights/1                 # expect: flight_number AI101
Stop-Process -Id $a.Id, $b.Id
Remove-Item Env:DATABASE_URL

# 7. Contract and readiness (AC7, AC8): run the API against the compose database
$env:DATABASE_URL = "postgresql://travel:travel_dev_password@127.0.0.1:5432/travel_agent"
$api = Start-Process python -ArgumentList "-m","uvicorn","flight_api.app:app","--port","8000" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 8
Invoke-RestMethod "http://127.0.0.1:8000/flights?origin=blr&destination=del"        # expect: AI101 and 6E202, ISO timestamps
try { Invoke-RestMethod "http://127.0.0.1:8000/flights?date=tomorrow" } catch { $_.Exception.Response.StatusCode.value__ }   # expect: 422
Invoke-RestMethod http://127.0.0.1:8000/ready                     # expect: status ready
docker compose stop postgres
Invoke-RestMethod http://127.0.0.1:8000/health                    # expect: status ok (liveness does not need the database)
try { Invoke-RestMethod http://127.0.0.1:8000/ready } catch { $_.Exception.Response.StatusCode.value__ }   # expect: 503
docker compose start postgres
Stop-Process -Id $api.Id
Remove-Item Env:DATABASE_URL

# 8. Whole stack in Docker (AC11, AC12)
docker compose up --build --abort-on-container-exit --exit-code-from agent
"Exit code: $LASTEXITCODE"                                        # expect: 0, with AI101/6E202 and Delhi Stay/Budget Inn Delhi
docker compose run --rm --no-deps flight_api id                   # expect: uid=10001(appuser)
docker compose down

# 9. Lint, format and workflow checks (AC10, AC13)
pre-commit run --all-files
docker run --rm -v "${PWD}:/repo" -w /repo rhysd/actionlint:1.7.12 -color

# 10. Push and confirm CI is green (AC10)
git push -u origin feat/sp02-t01-async-postgres

# 11. After merge: verify production (AC14)
gh run watch                                                      # the CD run: expect the gate to pass on /ready
$flight = gcloud run services describe flight-api --region <region> --format "value(status.url)"
$hotel  = gcloud run services describe hotel-api  --region <region> --format "value(status.url)"
Invoke-RestMethod "$flight/ready"; Invoke-RestMethod "$hotel/ready"                  # expect: status ready for both
Invoke-RestMethod "$flight/flights/1"                             # expect: AI101, identical on every request and instance
$url = gcloud secrets versions access latest --secret travel-agent-database-url
docker run --rm postgres:16 psql "$url" -c "\dn" -c "SELECT count(*) FROM flight.flights" -c "SELECT count(*) FROM hotel.hotels"   # expect: flight and hotel schemas, 5 rows each
```

## 6. Rollout & Rollback

- **Rollout:** merge the PR (CI passes), and CD deploys both services. The first start of each new revision runs its migration and seed on Neon, then the `/ready` gate verifies connectivity before traffic is committed.
- **Automatic rollback:** a revision that cannot migrate or reach Neon never becomes ready, or fails the gate, and CD returns traffic to the previous revision. The previous (SQLite) image ignores `DATABASE_URL`, so it keeps working.
- **Manual data cleanup (optional):** the schemas are additive and harmless if the change is reverted. To remove them: `DROP SCHEMA flight CASCADE; DROP SCHEMA hotel CASCADE;`.
- **Reverting the PR** restores the SQLite code. The local `flights.db` and `hotels.db` files, no longer used after this task, can be deleted (they are already gitignored).
- **Schema changes after this task** are always new Alembic revisions; existing revisions are never edited once merged.

## 7. Risks

| Risk                                                                                                                                                                                      | Mitigation                                                                                                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Neon cold start or a dropped connection makes the first request or a start-up slow or fail                                                                                                | Pre-ping and pool recycling; start-up budget of about 50 s; `/ready` gate in CD; probe threshold can be raised in Terraform                      |
| Migrations at start-up on multi-instance Cloud Run could race                                                                                                                             | Advisory lock per service; idempotent seed; a failed migration stops the revision from becoming ready                                            |
| A crashed instance leaves a lock held                                                                                                                                                     | The lock is session-scoped and released automatically when the connection drops; a `lock_timeout` stops others waiting forever                   |
| Neon's connection URI uses parameters asyncpg rejects (`sslmode`, `channel_binding`)                                                                                                      | Normalization in `common/db.py`, unit-tested with a Neon-style URI                                                                               |
| Connection exhaustion on the free tier                                                                                                                                                    | Small pools; `max_instances = 2` per service; roughly a dozen connections in total                                                               |
| JSON output drifts (timestamps, ratings) and breaks the MCP wrappers or agent date slicing                                                                                                | Column types chosen to preserve formats (D6); end-to-end tests run the real agent against the migrated APIs                                      |
| Two deliberate contract tightenings (422 on invalid dates)                                                                                                                                | Documented here and in the PR; valid requests are unaffected; the MCP servers only send ISO dates                                                |
| Tests become slower or require Docker                                                                                                                                                     | `-m "not db and not integration"` fast path; Compose already provides Postgres; CI uses a service container                                      |
| Async engine bound to the wrong event loop in tests                                                                                                                                       | Engine is created in the lifespan handler, never at import time                                                                                  |
| Shared role means schema isolation is logical only                                                                                                                                        | Documented; per-service roles are a later hardening step                                                                                         |
| `pip install pre-commit>=4.0.0` in `format-check` is unquoted, so the shell treats `>=4.0.0` as an output redirect: it installs the latest `pre-commit` and creates a file named `=4.0.0` | Quote the requirement (`pip install "pre-commit>=4.0.0"`), fixed in this PR as a drive-by                                                        |
| Greenlet or asyncpg wheels unavailable for a platform                                                                                                                                     | Both publish wheels for CPython 3.11 on Linux and Windows; the Linux lockfile is compiled in the `python:3.11-slim` container used by the images |

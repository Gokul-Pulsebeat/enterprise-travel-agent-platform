# TASK-2.1 — Async PostgreSQL Migration

| Field         | Value                                                                                                                                                                                                    |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Epic          | SP02 — Productionizing Flight & Hotel Core Microservices                                                                                                                                                 |
| PR            | PR 1 of 4                                                                                                                                                                                                |
| Branch        | `feat/sp02-t01-async-postgres`                                                                                                                                                                           |
| Target branch | `productionize`                                                                                                                                                                                          |
| Status        | **Implemented in the working tree, not yet run.** Design confirmed (decisions D1–D10). The code was written without the ability to execute it, so the verification commands below are the first real run |
| Depends on    | SP01 (Neon Postgres and `DATABASE_URL` secret via Terraform, Postgres in Compose, CI/CD to Cloud Run), SP00 (`pip-tools` lockfile workflow, pre-commit)                                                  |
| Parent docs   | [`EPIC_PRD.md`](EPIC_PRD.md), [`00_MASTER_PRD.md`](../../00_MASTER_PRD.md)                                                                                                                               |

---

## 1. Objective

Replace the per-service SQLite files with the shared managed Postgres, using a fully async data layer, a **normalized** schema, versioned migrations, and a test setup that runs against real Postgres everywhere. The REST contract that `flight_mcp_server`, `hotel_mcp_server` and the agent rely on does not change. The task lays the foundation for transactional bookings (TASK-2.3), idempotency (TASK-2.4) and users (TASK-2.2), all of which need real constraints, row locks and a real schema history.

## 2. Scope

### In scope

| Area                                            | Change                                                                                                                                                                                                                                                           |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `requirements.in`                               | Add `sqlalchemy[asyncio]`, `asyncpg`, `alembic` (lockfile recompiled with `scripts/compile-requirements.ps1`)                                                                                                                                                    |
| `common/` (new)                                 | `db.py`: `DATABASE_URL` normalization, engine and pool factory, readiness check, request-scoped connection dependency, guarded migration runner. `alembic_env.py`: the Alembic environment shared by both services                                               |
| `flight_api/`                                   | `database.py` (schema, tables, joined select), `seed.py`, `app.py` (async, lifespan, `/ready`), `alembic.ini`, `migrations/` (`env.py`, `script.py.mako`, `0001_create_flight_schema.py`)                                                                        |
| `hotel_api/`                                    | The same shape for `hotels` and `hotel_offers` (`0001_create_hotel_schema.py`)                                                                                                                                                                                   |
| `tests/`                                        | `conftest.py` and `db_helpers.py` (Postgres fixtures); `test_common_db.py`, `test_migrations.py`, `test_schema_integrity.py` (new); `test_flight_api.py`, `test_hotel_api.py` (rewritten, original assertions kept); `test_integration_e2e.py` (database wiring) |
| `pytest.ini`                                    | New `db` marker                                                                                                                                                                                                                                                  |
| `.github/workflows/ci.yml`                      | Postgres service container, `TEST_DATABASE_URL` and `DATABASE_URL`, readiness wait on `/ready`; fix the unquoted `pip install pre-commit>=4.0.0` in `format-check`; add dedicated `Verify Non-Root User` container security job                                  |
| `.github/workflows/cd.yml`                      | Post-deploy gate checks `/ready` instead of `/health`                                                                                                                                                                                                            |
| `docker-compose.yml`                            | APIs get `DATABASE_URL` and wait for Postgres to be healthy; health checks use `/ready`                                                                                                                                                                          |
| `flight_api/Dockerfile`, `hotel_api/Dockerfile` | Also copy `common/`; the SQLite write-permission workaround is removed                                                                                                                                                                                           |
| `.env.example`, `README.md`                     | `DATABASE_URL`, `SEED_MOCK_DATA`, pool and test settings; local run, test and cloud sections updated                                                                                                                                                             |

### Out of scope

- Any write endpoint, booking table, user table, idempotency key or email (TASK-2.2 to TASK-2.5).
- Per-service database roles and `GRANT` hardening, and separate databases per service.
- Pagination, new filters, per-night room inventory or room types, currency, or any API change beyond those listed in section 3.4.
- Terraform changes: `DATABASE_URL` is already created and injected into both services by SP01.
- Moving migrations out of service start-up into a separate release job (decision D4).

## 3. Architectural Notes

### 3.1 Design decisions (confirmed)

| #   | Decision                                                                                                                                            | Alternative considered                                          | Why this choice                                                                                                                                                                                                                                                           |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | **SQLAlchemy 2.0 Core (async) + asyncpg + Alembic**                                                                                                 | Bare `asyncpg` with hand-written SQL and ad-hoc migration files | Tasks 2.2 to 2.5 add tables, constraints and locking. Alembic gives reviewed, reversible, per-service history; Core's `select(...).with_for_update()` makes row locks explicit; `Table` metadata is the single schema source. Core (not the ORM) keeps queries SQL-shaped |
| D2  | **One schema per service** (`flight`, `hotel`), tables schema-qualified in code, one Alembic history per schema, shared plumbing in `common/`       | Table-name prefixes; separate databases                         | Real isolation and ownership with no Terraform change; no reliance on `search_path` (PgBouncer-safe); keeps database-per-service possible later                                                                                                                           |
| D3  | **Test on real Postgres everywhere**: a service container in CI, the Compose Postgres locally; unreachable Postgres fails the run with instructions | A SQLite fallback via `aiosqlite`; skipping DB tests            | TASK-2.3 needs `SELECT ... FOR UPDATE`, which SQLite lacks, and the dialects differ. A fallback would pass tests that production fails; a silent skip would hide a broken setup                                                                                           |
| D4  | **Run migrations at start-up** inside one transaction with the seed, serialized by a transaction-scoped Postgres advisory lock                      | A separate release job (Cloud Run Job or CD step)               | Keeps CD, IAM and Terraform unchanged (the deployer has no database access by design). The lock makes concurrent instances safe and is released automatically on commit, rollback or a crash; a failed migration stops the revision from becoming ready                   |
| D5  | **Seed data in `seed.py`, not in migrations**; idempotent (`ON CONFLICT DO NOTHING`); `SEED_MOCK_DATA` (default `true`)                             | Seed rows inside a migration                                    | Migrations stay schema-only and reversible; mock data is a product choice. Seeding inside the lock also keeps ids deterministic on first start (`AI101` is flight 1)                                                                                                      |
| D6  | **Column types that keep the JSON identical**: `TIMESTAMP` (no zone), `DATE`, `DOUBLE PRECISION`, `INTEGER`                                         | `TIMESTAMPTZ`, `NUMERIC` rating                                 | Timestamps serialize as `2026-06-10T08:30:00` (the agent slices `departure_time[:10]`), dates as `2026-06-10`, ratings as `4.2`. Airports carry a time zone, so a later move to `TIMESTAMPTZ` needs no reshaping                                                          |
| D7  | **`GET /ready`** (database reachable) and the CD gate and Compose health checks use it; `/health` stays liveness                                    | One endpoint for both                                           | Liveness must not depend on the database, or a Neon hiccup would look like a dead process; the old gate could not detect a database problem                                                                                                                               |
| D8  | **Normalize `DATABASE_URL`** in `common/db.py`: scheme to `postgresql+asyncpg`, `sslmode` to `ssl`, drop `channel_binding`                          | Require the exact asyncpg form in the secret                    | Neon's URI uses `sslmode` and possibly `channel_binding`, which asyncpg rejects or does not implement                                                                                                                                                                     |
| D9  | **`DATABASE_URL` defaults to the Compose development URL**                                                                                          | No default; fail if unset                                       | Matches the repository's convention of local defaults; Cloud Run always overrides it                                                                                                                                                                                      |
| D10 | **Normalize the schema now**: `airlines`, `airports` (keyed by IATA code), `flights`; `hotels` (property) and `hotel_offers` (bookable stay window) | Flat tables now, normalize in a later task                      | There is no data to migrate and every query is being rewritten anyway; later tasks then extend these tables instead of reshaping them. See the epic's normalization section                                                                                               |

### 3.2 Layout after this task

```text
common/
  db.py               URL normalization, engine factory, readiness check, connection dependency, migration runner
  alembic_env.py      Alembic environment logic shared by both services
flight_api/
  app.py              FastAPI app, lifespan handler, async endpoints, /ready
  database.py         schema, tables (airlines, airports, flights), flight_select()
  seed.py             mock airlines, airports and flights; idempotent seed
  alembic.ini         CLI use:  alembic -c flight_api/alembic.ini ...
  migrations/         env.py (3 lines), script.py.mako, versions/0001_create_flight_schema.py
hotel_api/            same shape: hotels, hotel_offers, offer_select()
tests/
  conftest.py         postgres_url and migrations_database_url fixtures
  db_helpers.py       ensure_database, run_alembic (real CLI), fetch_all, execute_sql
  test_common_db.py   URL normalization, flags, pool settings (no database)
  test_flight_api.py, test_hotel_api.py   contract, formats, filters, /ready, 422/404 cases, idempotent seed
  test_migrations.py  CLI upgrade/downgrade round trip, per-service history, isolation
  test_schema_integrity.py   every constraint enforced by the database, each with a positive control
```

### 3.3 Data model

**Schema `flight`**

| Table      | Columns                                                                                                                                                                                              | Constraints and indexes                                                                                                                                                                                                                |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `airlines` | `id` BIGINT identity PK, `iata_code` TEXT, `name` TEXT                                                                                                                                               | `UNIQUE (iata_code)`, `UNIQUE (name)`                                                                                                                                                                                                  |
| `airports` | `iata_code` TEXT PK, `city` TEXT, `timezone` TEXT                                                                                                                                                    | `CHECK (iata_code ~ '^[A-Z]{3}$')`                                                                                                                                                                                                     |
| `flights`  | `id` BIGINT identity PK, `flight_number`, `airline_id` FK, `origin_code` FK, `destination_code` FK, `departure_time` TIMESTAMP, `arrival_time` TIMESTAMP, `price` INTEGER, `seats_available` INTEGER | FKs `ON DELETE RESTRICT`; `UNIQUE (flight_number, departure_time)`; `CHECK` arrival after departure, origin differs from destination, `price >= 0`, `seats_available >= 0`; index on `(origin_code, destination_code, departure_time)` |

**Schema `hotel`**

| Table          | Columns                                                                                                                                   | Constraints and indexes                                                                                                                                                                            |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `hotels`       | `id` BIGINT identity PK, `name`, `city`, `area`, `rating` DOUBLE PRECISION                                                                | `UNIQUE (name, city)`; `CHECK (rating >= 0 AND rating <= 5)`; index on `upper(city)` (searches match the city case-insensitively)                                                                  |
| `hotel_offers` | `id` BIGINT identity PK, `hotel_id` FK, `check_in_date` DATE, `check_out_date` DATE, `price_per_night` INTEGER, `rooms_available` INTEGER | FK `ON DELETE RESTRICT`; `UNIQUE (hotel_id, check_in_date, check_out_date)`; `CHECK` checkout after check-in, `price_per_night >= 0`, `rooms_available >= 0`; index on `(hotel_id, check_in_date)` |

Each service's Alembic version table lives in its own schema (`flight.alembic_version`, `hotel.alembic_version`). The non-negative checks are groundwork: in TASK-2.3 they make "inventory can never go below zero" a database guarantee. Seeds insert in listed order, so `/flights/1` is `AI101` and `/hotels/1` is `Delhi Stay` on an empty database.

### 3.4 Behavior and contract

- **Unchanged:** routes, field names, JSON formats, result ordering (departure time; nightly price), case-insensitive `origin`, `destination` and `city` matching, and the 404 messages.
- **Flat responses.** The joins happen in the query, so each result still looks like one row. For hotels, `id` is the **offer** id (the thing that will be booked).
- **Two harmless additions:** `airline_code` on flights, `hotel_id` on hotel results.
- **Two deliberate tightenings:** `date` (flights) and `check_in_date` (hotels) are typed dates. An invalid value returns **422** instead of silently returning an empty list.
- **IDs outside BIGINT's range** (or below 1) return **404**, not a database error.
- **New:** `GET /ready` returns `200 {"status":"ready"}` when a `SELECT 1` succeeds within 5 seconds, else `503 {"status":"unavailable"}`. `GET /health` is unchanged and never touches the database.
- **Date filtering** uses a half-open range on `departure_time` so it can use the index.

### 3.5 Connection and migration mechanics

- **Engine lifecycle.** Each app creates its async engine inside the lifespan handler (never at import time, which would bind it to the wrong event loop), stores it on `app.state`, and disposes it on shutdown. The lifespan handler replaces the deprecated `@app.on_event("startup")`.
- **Pool.** Small pool (default 3, overflow 2) with pre-ping and 300-second recycling, because Neon suspends idle compute and silently drops connections. Settings come from `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE_SECONDS`. The direct (non-pooled) Neon endpoint is used, which is what Terraform stores; behind PgBouncer asyncpg's prepared-statement cache would need disabling.
- **Start-up sequence.** One transaction: `SET LOCAL lock_timeout`, take `pg_advisory_xact_lock`, run `alembic upgrade head` on that same connection, run the seed. Commit releases the lock; any failure rolls everything back and the exception stops the service. uvicorn finishes lifespan start-up before opening its listening socket, so the Cloud Run TCP startup probe only passes once this succeeds.
- **Alembic in an async app.** `common.db.migrate_and_seed` passes its connection to Alembic through `config.attributes`, and `common/alembic_env.py` runs the migrations on it with no second event loop. The same `env.py` also supports the plain CLI (`alembic -c ... upgrade head`), where it builds its own engine from `DATABASE_URL`.
- **Per-service history and locks.** `version_table_schema` is the service schema and `env.py` creates the schema first. Each service uses a different advisory-lock key (`7202601` flight, `7202602` hotel), so the two never block each other.

### 3.6 Test strategy

| Layer                                | Runs against                                                  | Notes                                                                                                                                                                                              |
| ------------------------------------ | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pure unit tests                      | Nothing external                                              | URL normalization (including a Neon-style URI), flags, pool settings, agent mock logic. `pytest -m "not db and not integration"`                                                                   |
| API tests (`db`)                     | `travel_agent_test`                                           | The app's own lifespan migrates and seeds. Includes formats, filters, `/ready`, 422 and 404 cases, and "a second start-up does not duplicate the seed"                                             |
| Migration and integrity tests (`db`) | `travel_agent_test_migrations`, recreated empty every session | The real Alembic CLI upgrades, downgrades and re-upgrades each service; every constraint is violated on purpose (and each has a valid positive control); runs are rolled back, so nothing persists |
| End-to-end (`integration`)           | `travel_agent_test`, through real uvicorn processes           | The fixture exports `DATABASE_URL` to the subprocesses it starts, or reuses APIs that are already running                                                                                          |

- **Why migrations are tested on a separate, recreated database.** The full migration path from zero is exercised on every run without dropping schemas under API processes that CI starts before pytest (their pooled connections would hit vanished tables).
- **Local:** `docker compose up -d postgres`. Tests use their own databases (created automatically), never `travel_agent`. `TEST_DATABASE_URL` overrides the server.
- **CI:** the `Lint & Test` job gets a `pgvector/pgvector:pg16` service container (same image as Compose, same major version as Neon) with a health check, plus `TEST_DATABASE_URL` and `DATABASE_URL`, so the API processes it starts migrate and seed the container before listening.

### 3.7 Deployment

- **Cloud Run:** no Terraform change. `DATABASE_URL` is already mounted from Secret Manager for both services. The first start of each new revision creates its schema and seeds it in Neon. Both services now share that data, replacing today's per-instance copies.
- **Start-up budget:** the TASK-1.4 startup probe allows about 50 seconds (10 checks, 5 seconds apart). A Neon cold start plus one small migration and seed should take a few seconds. If it proves tight, raise `failure_threshold` in Terraform.
- **CD gate:** `/ready`, so a revision that cannot reach the database is rolled back automatically. The rollback drill is unaffected.
- **Compose:** both APIs wait for Postgres to be healthy; their health checks use `/ready`, so the `agent` smoke test starts only once the database is usable.

## 4. Acceptance Criteria

| #    | Criterion                                                                                                                                                                                                                                                                                       |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1  | `requirements.in` adds `sqlalchemy[asyncio]`, `asyncpg` and `alembic`; the recompiled `requirements.txt` pins them and CI's lockfile-parity check passes.                                                                                                                                       |
| AC2  | `common/db.py` normalizes `postgres://` and `postgresql://` URLs to `postgresql+asyncpg://`, maps `sslmode` to `ssl`, drops `channel_binding`, rejects other schemes without leaking the password, and is unit tested including a Neon-style URI.                                               |
| AC3  | Neither API imports `sqlite3`; every endpoint is `async def` using SQLAlchemy Core with parameterized queries; the lifespan handler replaces `@app.on_event`.                                                                                                                                   |
| AC4  | Each service has its own Alembic environment. `upgrade head` creates its schema, its tables and `<schema>.alembic_version`; `downgrade base` and `upgrade head` round-trip; the two services never touch each other's schema.                                                                   |
| AC5  | The schema is normalized as in section 3.3: `airlines`, `airports` (IATA-code key), `flights` with foreign keys; `hotels` and `hotel_offers` with a foreign key; identity primary keys, `CHECK` and `UNIQUE` constraints and indexes.                                                           |
| AC6  | The database enforces its constraints: unknown airline, airport or hotel, negative inventory or price, arrival before departure, check-out not after check-in, bad rating, bad airport code, duplicates, and deleting a referenced row are all rejected (each with a passing positive control). |
| AC7  | Seeding is idempotent: starting two instances at the same moment, or restarting, leaves exactly five flights and five hotel offers; `/flights/1` is `AI101` and `/hotels/1` is `Delhi Stay`.                                                                                                    |
| AC8  | The REST contract is unchanged for valid requests (routes, field names, JSON formats, ordering, 404 messages); `airline_code` and `hotel_id` are the only additions; an invalid `date` or `check_in_date` returns 422; out-of-range ids return 404.                                             |
| AC9  | `GET /health` stays 200 without a database; `GET /ready` returns 200 when the database is reachable and 503 when it is not.                                                                                                                                                                     |
| AC10 | The existing assertions in the API tests pass against Postgres, and the end-to-end tests pass with the agent and MCP servers unchanged.                                                                                                                                                         |
| AC11 | CI runs a Postgres service container, passes `DATABASE_URL` to the API processes, waits on `/ready`, and every test passes; the `format-check` install command is quoted; CI builds both images and verifies they execute as a non-root user.                                                   |
| AC12 | `docker compose up --build --abort-on-container-exit --exit-code-from agent` succeeds with both APIs on Postgres; the images include `common/` and run as non-root.                                                                                                                             |
| AC13 | `cd.yml` gates on `/ready`.                                                                                                                                                                                                                                                                     |
| AC14 | _(Manual, after merge)_ The CD run passes the gate against Neon; the `flight` and `hotel` schemas exist there with the expected rows; both Cloud Run services return identical data across requests and instances.                                                                              |
| AC15 | `README.md` and `.env.example` document `DATABASE_URL`, the local Postgres requirement, the test databases and the `db` marker.                                                                                                                                                                 |

## 5. Verification Commands

Run from the repository root (PowerShell) with the virtual environment active. Docker Desktop must be running.

```powershell
# 0. Re-lock in a Linux container, sync, and confirm the new packages (AC1)
.\scripts\compile-requirements.ps1
.\scripts\sync-dev.ps1
Select-String -Path requirements.txt -Pattern "^(sqlalchemy|asyncpg|alembic|greenlet)=="    # expect: four pinned lines

# 1. Format and lint the new files, then confirm CI's checks pass locally (AC11)
pre-commit run --all-files                                        # commit whatever the formatters changed
ruff check .

# 2. Local Postgres
docker compose up -d postgres
docker compose ps                                                 # expect: postgres healthy

# 3. Fast tests that need nothing external (AC2)
pytest -m "not db and not integration"

# 4. Full suite against Postgres (AC3-AC10)
pytest                                                            # expect: all pass; report.html written

# 5. No SQLite left (AC3)
git grep -n "sqlite3" -- "*.py"                                   # expect: no output

# 6. Migrations from the CLI against a scratch database (AC4, AC5)
docker compose exec postgres psql -U travel -d postgres -c "CREATE DATABASE scratch"
$env:DATABASE_URL = "postgresql://travel:travel_dev_password@127.0.0.1:5432/scratch"
alembic -c flight_api/alembic.ini upgrade head
alembic -c hotel_api/alembic.ini upgrade head
alembic -c flight_api/alembic.ini current                         # expect: 0001 (head)
alembic -c flight_api/alembic.ini downgrade base
alembic -c flight_api/alembic.ini upgrade head
docker compose exec postgres psql -U travel -d scratch -c "\dt flight.*" -c "\dt hotel.*"
docker compose exec postgres psql -U travel -d scratch -c "SELECT version_num FROM flight.alembic_version" -c "SELECT version_num FROM hotel.alembic_version"
docker compose exec postgres psql -U travel -d scratch -c "\d flight.flights" -c "\d hotel.hotel_offers"    # expect: identity PK, foreign keys, CHECKs, unique, indexes
Remove-Item Env:DATABASE_URL
docker compose exec postgres psql -U travel -d postgres -c "DROP DATABASE scratch"

# 7. Idempotent seeding under concurrent start-up (AC7): two instances at once against an empty schema
docker compose exec postgres psql -U travel -d travel_agent_test -c "DROP SCHEMA IF EXISTS flight CASCADE"
$env:DATABASE_URL = "postgresql://travel:travel_dev_password@127.0.0.1:5432/travel_agent_test"
$a = Start-Process python -ArgumentList "-m","uvicorn","flight_api.app:app","--port","8000" -PassThru -WindowStyle Hidden
$b = Start-Process python -ArgumentList "-m","uvicorn","flight_api.app:app","--port","8010" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 12
docker compose exec postgres psql -U travel -d travel_agent_test -c "SELECT count(*) FROM flight.flights" -c "SELECT count(*) FROM flight.airlines"   # expect: 5 and 4, not doubled
Invoke-RestMethod http://127.0.0.1:8000/flights/1                 # expect: AI101, airline Air India, airline_code AI
Stop-Process -Id $a.Id, $b.Id
Remove-Item Env:DATABASE_URL

# 8. Contract, validation and readiness (AC8, AC9), against the compose database
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

# 9. Whole stack in Docker (AC12)
docker compose up --build --abort-on-container-exit --exit-code-from agent
"Exit code: $LASTEXITCODE"                                        # expect: 0, with AI101/6E202 and Delhi Stay/Budget Inn Delhi
docker compose run --rm --no-deps flight_api id                   # expect: uid=10001(appuser)
docker compose down

# 10. Workflow lint and push (AC11, AC13)
docker run --rm -v "${PWD}:/repo" -w /repo rhysd/actionlint:1.7.12 -color
git push -u origin feat/sp02-t01-async-postgres # Expect 5 green CI jobs (Lint & Test, Format check, Terraform check, actionlint, and Verify Non-Root User)

# 11. After merge: verify production (AC14)
gh run watch                                                      # the CD run: expect the gate to pass on /ready
$flight = gcloud run services describe flight-api --region <region> --format "value(status.url)"
$hotel  = gcloud run services describe hotel-api  --region <region> --format "value(status.url)"
Invoke-RestMethod "$flight/ready"; Invoke-RestMethod "$hotel/ready"                  # expect: status ready for both
Invoke-RestMethod "$flight/flights/1"                             # expect: AI101, identical on every request and instance
$url = gcloud secrets versions access latest --secret travel-agent-database-url
docker run --rm postgres:16 psql "$url" -c "\dn" -c "SELECT count(*) FROM flight.flights" -c "SELECT count(*) FROM hotel.hotel_offers"   # expect: flight and hotel schemas, 5 rows each
```

## 6. Rollout & Rollback

- **Rollout:** merge the PR (CI passes), and CD deploys both services. The first start of each new revision runs its migration and seed on Neon, then the `/ready` gate verifies connectivity before traffic is committed.
- **Automatic rollback:** a revision that cannot migrate or reach Neon never becomes ready, or fails the gate, and CD returns traffic to the previous revision. The previous (SQLite) image ignores `DATABASE_URL`, so it keeps working.
- **Manual data cleanup (optional):** the schemas are additive and harmless if the change is reverted. To remove them: `DROP SCHEMA flight CASCADE; DROP SCHEMA hotel CASCADE;`.
- **Reverting the PR** restores the SQLite code. Local `flights.db` and `hotels.db` files (if any) are unused after this task and can be deleted; they are already gitignored.
- **Schema changes after this task** are always new Alembic revisions; merged revisions are never edited.

## 7. Risks

| Risk                                                                                                                                                                            | Mitigation                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **The code was written without being run**, including the Alembic-on-a-shared-async-connection mechanics                                                                        | The verification commands are the first execution; the tests cover both migration entry points (app lifespan and CLI) and every constraint, so a mistake should surface immediately and locally                                                                                                                                                                                                                                         |
| **Mock rows were reconstructed, not copied.** The original `database.py` constants were overwritten before being extracted, and no local database remained to recover them from | Only the facts pinned by existing tests and docs are guaranteed (`AI101` is flight 1 and `6E202` also flies BLR to DEL on 2026-06-10; `Delhi Stay` is hotel 1 and `Budget Inn Delhi` is also in Delhi on 2026-06-10). Prices, seats and the other rows are plausible values. Compare with `git show productionize:flight_api/database.py` and `git show productionize:hotel_api/database.py` and edit `seed.py` if the originals matter |
| Neon cold start or a dropped connection makes a start-up slow or fail                                                                                                           | Pre-ping and pool recycling; start-up budget of about 50 s; `/ready` gate in CD; probe threshold can be raised in Terraform                                                                                                                                                                                                                                                                                                             |
| A crashed instance leaves a lock held                                                                                                                                           | The lock is transaction-scoped and released automatically; `lock_timeout` stops others waiting forever                                                                                                                                                                                                                                                                                                                                  |
| Neon's connection URI uses parameters asyncpg rejects                                                                                                                           | Normalization in `common/db.py`, unit-tested with a Neon-style URI                                                                                                                                                                                                                                                                                                                                                                      |
| Connection exhaustion on the free tier                                                                                                                                          | Small pools; `max_instances = 2` per service; roughly a dozen connections in total                                                                                                                                                                                                                                                                                                                                                      |
| JSON output drifts and breaks the MCP wrappers or agent date slicing                                                                                                            | Column types preserve formats (D6); tests assert the exact formats; end-to-end tests run the real agent                                                                                                                                                                                                                                                                                                                                 |
| Two deliberate contract tightenings (422 on invalid dates)                                                                                                                      | Documented; valid requests are unaffected; the MCP servers only send ISO dates                                                                                                                                                                                                                                                                                                                                                          |
| Tests require Docker                                                                                                                                                            | `-m "not db and not integration"` fast path; Compose already provides Postgres; CI uses a service container                                                                                                                                                                                                                                                                                                                             |
| Hand-written files may not match `ruff format` / Prettier exactly, so `format-check` could fail                                                                                 | Run `pre-commit run --all-files` and commit the result before pushing (step 1)                                                                                                                                                                                                                                                                                                                                                          |
| Async engine bound to the wrong event loop in tests                                                                                                                             | The engine is created in the lifespan handler, never at import time; test helpers create and dispose an engine inside each `asyncio.run`                                                                                                                                                                                                                                                                                                |
| Shared role means schema isolation is logical only                                                                                                                              | Documented; per-service roles are a later hardening step                                                                                                                                                                                                                                                                                                                                                                                |
| Greenlet or asyncpg wheels unavailable for a platform                                                                                                                           | Both publish wheels for CPython 3.11 on Linux and Windows; the Linux lockfile is compiled in the `python:3.11-slim` container used by the images                                                                                                                                                                                                                                                                                        |

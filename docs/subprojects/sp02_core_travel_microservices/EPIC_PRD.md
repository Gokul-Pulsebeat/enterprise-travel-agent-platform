# EPIC SP02 — Productionizing Flight & Hotel Core Microservices

**Status:** In Progress (TASK-2.1)
**Depends on:** SP01 (Neon Postgres and `DATABASE_URL` secret provisioned by Terraform, Postgres in Docker Compose, CI/CD to Cloud Run)
**Master PRD:** [`../../00_MASTER_PRD.md`](../../00_MASTER_PRD.md)

## Goal

Turn the read-only SQLite demo APIs into transactional services that can safely take bookings under concurrent load, on managed Postgres, without breaking the REST contract that the MCP wrappers and the agent already depend on.

## Starting Point (end of SP01)

| Aspect      | Today                                                                                                                                                                                                             |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Data layer  | Synchronous `sqlite3`, one file per service (`flights.db`, `hotels.db`), created and seeded in a deprecated `@app.on_event("startup")` hook. Each Cloud Run instance has its own private copy of the data         |
| Schema      | One table per service, no constraints beyond the primary key, no indexes, no migration history                                                                                                                    |
| Writes      | None. The APIs are read-only (`GET /flights`, `GET /flights/{id}`, `GET /hotels`, `GET /hotels/{id}`, `GET /health`)                                                                                              |
| Infra ready | Neon Postgres is provisioned and its connection string is injected into **both** Cloud Run services as `DATABASE_URL` (Secret Manager). Docker Compose runs `pgvector/pgvector:pg16`. Neither is used by code yet |
| Consumers   | `flight_mcp_server` and `hotel_mcp_server` call the REST APIs over HTTP; the agent calls the MCP servers. The REST contract must stay stable                                                                      |

## Delivery Plan: Four Pull Requests

Tasks are grouped by **what must ship together to be safe**, not one-to-one. The governance rule is "atomic task branches", and each PR below still contains only closely related work.

| PR  | Branch                                     | Tasks               | Why this grouping                                                                                                                                                                                                                                    |
| --- | ------------------------------------------ | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `feat/sp02-t01-async-postgres`             | TASK-2.1            | The foundation: everything else needs Postgres, migrations and a real test database. It changes infrastructure wiring (Compose, CI, Docker images) and every data-access line, so it is reviewed alone with **no behavior change** for API consumers |
| 2   | `feat/sp02-t02-users-and-role-tiers`       | TASK-2.2            | Adds the `identity` schema (users, role tiers). Independent of booking logic and small enough to review on its own; bookings in PR 3 reference it                                                                                                    |
| 3   | `feat/sp02-t03-t04-transactional-bookings` | TASK-2.3 + TASK-2.4 | A booking endpoint that is lock-safe (2.3) but not retry-safe (2.4) can still double-charge a client that retries a timed-out request, so neither is shippable alone. Delivered as one PR with separate commits per task so the diff stays readable  |
| 4   | `feat/sp02-t05-email-notifications`        | TASK-2.5            | Needs bookings to exist (PR 3) and introduces new infrastructure (a worker and a mail provider). Keeping it separate isolates that risk and lets the booking API ship without waiting on it                                                          |

Alternatives considered: **one PR per task** (five PRs) was rejected because 2.3 and 2.4 cannot be released independently; **one PR for the whole epic** was rejected because it would mix an infrastructure migration with new business logic and make rollback impractical.

## Tasks

| Task     | PRD                                                                            | Summary                                                                                                                                                                                                                      |
| -------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TASK-2.1 | [`TASK-2.1_async_postgres_migration.md`](TASK-2.1_async_postgres_migration.md) | **Async PostgreSQL migration** for `flight_api` and `hotel_api`: SQLAlchemy 2.0 (async) + asyncpg + Alembic, one schema per service, seed data, FastAPI lifespan instead of `on_event`, Postgres in CI and Compose, `/ready` |
| TASK-2.2 | TBD                                                                            | **Users and role tiers**: employee identity and role-tier tables used later by policy checks                                                                                                                                 |
| TASK-2.3 | TBD                                                                            | **ACID booking transactions** using `SELECT ... FOR UPDATE` row-level locking on seat and room inventory to prevent double-booking                                                                                           |
| TASK-2.4 | TBD                                                                            | **Idempotency keys** on booking and cancellation endpoints so client retries never duplicate a booking                                                                                                                       |
| TASK-2.5 | TBD                                                                            | **Background transactional email** on booking confirmation and cancellation, via a worker decoupled from the request path                                                                                                    |

## Database Design: Shared Instance, Per-Service Schemas

Terraform injects **one** Neon connection string (`DATABASE_URL`) into **both** Cloud Run services, and Docker Compose runs **one** Postgres. The two services therefore share a database server, a database and a role. The design keeps them independent **logically** with one Postgres **schema per service**.

```text
Neon project  (one database: travel_agent, one role: travel_app, one DATABASE_URL)
 |
 +-- schema flight       owned by flight_api
 |     +-- flights                  (TASK-2.1)
 |     +-- bookings                 (TASK-2.3)
 |     +-- idempotency_keys         (TASK-2.4)
 |     +-- alembic_version          (flight_api's migration history)
 |
 +-- schema hotel        owned by hotel_api
 |     +-- hotels                   (TASK-2.1)
 |     +-- bookings                 (TASK-2.3)
 |     +-- idempotency_keys         (TASK-2.4)
 |     +-- alembic_version          (hotel_api's migration history)
 |
 +-- schema identity     users, role_tiers                  (TASK-2.2; ownership decided in that PRD)
 |
 +-- schema policy       policy chunks, approvals           (SP05; reserved, not created in SP02)
```

| Concern                  | Decision                                                                                                                                                                                                           |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Isolation unit           | A Postgres **schema per service**. Table names no longer need a service prefix, and each service can create, alter or drop its own objects without colliding with the other                                        |
| Name resolution          | Tables are **schema-qualified in code** (`flight.flights`); the connection's `search_path` is not relied on. This also keeps the design safe behind a transaction-mode pooler such as PgBouncer                    |
| Migration history        | **One Alembic environment per service**, with the version table stored in that service's schema (`flight.alembic_version`, `hotel.alembic_version`). The two histories never interfere                             |
| Cross-service references | **No foreign keys across schemas.** A booking stores a `user_id` as a plain value validated by the API. This preserves service independence and lets a service move to its own database later                      |
| Shared code              | A small `common/` package holds what both services must do identically: `DATABASE_URL` normalization, engine and pool configuration, and the guarded migration runner. Each service imports it                     |
| Privileges               | Both services share one role today, so the isolation is **logical, not a security boundary**. Per-service roles with `GRANT` limited to their own schema are a hardening step (candidate for SP03)                 |
| Connection budget        | Each service instance holds a small pool (default 3). With `max_instances = 2` per service that is about 12 connections, well inside Neon's free-tier limit. Pools use pre-ping because Neon suspends idle compute |
| Why not separate DBs     | Database-per-service is cleaner still but needs a second Neon database and a second secret, plus Terraform changes, for no benefit at this scale. The schema boundary keeps that option open                       |

## Exit Criteria

- Concurrent booking tests against the last seat or room produce exactly one success.
- Retrying a booking request with the same idempotency key returns the original result.
- Confirmation and cancellation emails are sent without blocking the API response.
- The REST contract consumed by the MCP servers is unchanged by the migration (PR 1), proven by the existing unit and end-to-end tests passing against Postgres.

## Key Risks

Lock contention and deadlocks; email deliverability; keeping the existing read endpoints backward compatible for the MCP wrappers; Neon cold starts and connection limits on the free tier; schema migrations running at service start-up on multi-instance Cloud Run; tests that pass on SQLite but not on Postgres (avoided by testing on Postgres everywhere).

# EPIC SP02 — Productionizing Flight & Hotel Core Microservices

**Status:** Placeholder — detailed task PRDs to be written when the epic starts
**Depends on:** SP01
**Master PRD:** [`../../00_MASTER_PRD.md`](../../00_MASTER_PRD.md)

## Goal

Turn the read-only SQLite demo APIs into transactional services that can safely take bookings under concurrent load.

## Planned Tasks

| Task     | Summary                                                                                                                                                                           |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TASK-2.1 | **Async PostgreSQL migration** for `flight_api` and `hotel_api`: schema, migrations, async driver, seed data; replace the deprecated startup hook with a FastAPI lifespan handler |
| TASK-2.2 | **Users and role tiers**: employee identity and role-tier tables used later by policy checks                                                                                      |
| TASK-2.3 | **ACID booking transactions** using `SELECT ... FOR UPDATE` row-level locking on seat and room inventory to prevent double-booking                                                |
| TASK-2.4 | **Idempotency keys** on booking and cancellation endpoints so client retries never duplicate a booking                                                                            |
| TASK-2.5 | **Background transactional email** on booking confirmation and cancellation, via a worker decoupled from the request path                                                         |

## Exit Criteria

- Concurrent booking tests against the last seat or room produce exactly one success.
- Retrying a booking request with the same idempotency key returns the original result.
- Confirmation and cancellation emails are sent without blocking the API response.

## Key Risks

Lock contention and deadlocks; email deliverability; keeping the existing read endpoints backward compatible for the MCP wrappers.

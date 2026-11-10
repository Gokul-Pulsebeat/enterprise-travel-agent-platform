# TASK-1.3 — Docker Compose Local Stack

| Field         | Value                                                                      |
| ------------- | -------------------------------------------------------------------------- |
| Epic          | SP01 — CI/CD Pipelines, Dockerization & Serverless Terraform IaC           |
| PR            | PR 1 of 2                                                                  |
| Branch        | `feat/sp01-cicd-and-docker`                                                |
| Target branch | `productionize`                                                            |
| Depends on    | TASK-1.2 (images)                                                          |
| Parent docs   | [`EPIC_PRD.md`](EPIC_PRD.md), [`00_MASTER_PRD.md`](../../00_MASTER_PRD.md) |

---

## 1. Objective

One command brings up a complete local environment that mirrors the production topology: the two REST APIs, an agent that exercises them end to end, and the stateful services (Postgres with pgvector, Redis) that later epics depend on. A developer should be able to clone the repository and verify the whole system without installing Python dependencies.

## 2. Scope

### In scope

| Area                 | Change                                                                                                      |
| -------------------- | ----------------------------------------------------------------------------------------------------------- |
| `docker-compose.yml` | Five services: `postgres`, `redis`, `flight_api`, `hotel_api`, `agent`, plus a named volume `postgres_data` |
| `.env.example`       | Documents every environment variable used for local development and Compose                                 |

### Services

| Service      | Image / build                                | Ports                 | Healthcheck                                                    | Notes                                                                       |
| ------------ | -------------------------------------------- | --------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `postgres`   | `pgvector/pgvector:pg16`                     | `127.0.0.1:5432:5432` | `pg_isready`                                                   | Named volume `postgres_data`. Ready for SP02 and SP05; not used by code yet |
| `redis`      | `redis:7-alpine`                             | `127.0.0.1:6379:6379` | `redis-cli ping`                                               | Ready for SP03/SP04; not used by code yet                                   |
| `flight_api` | build `flight_api/Dockerfile` (root context) | `8000:8000`           | Python `urllib.request` against `http://127.0.0.1:8000/health` | `python:3.11-slim` has no `curl`                                            |
| `hotel_api`  | build `hotel_api/Dockerfile` (root context)  | `8001:8001`           | Python `urllib.request` against `http://127.0.0.1:8001/health` |                                                                             |
| `agent`      | build `agent/Dockerfile` (root context)      | none                  | none (one-shot)                                                | Waits for both APIs to be healthy, then runs a smoke prompt and exits       |

### Out of scope

- Wiring the APIs to Postgres or any component to Redis (SP02, SP03, SP04).
- Cloud deployment (PR 2).
- Hot-reload or bind-mounted source for development; this stack is for parity and verification.

## 3. Architectural Notes

**Startup ordering.** The `agent` service uses `depends_on` with `condition: service_healthy` for both APIs, so the smoke test never races API startup. The APIs do not depend on `postgres` or `redis` yet because they do not use them; those dependencies are added in SP02.

**Service-name networking.** Inside the Compose network each API is reachable by its service name. The agent is configured with `FLIGHT_API_BASE_URL=http://flight_api:8000` and `HOTEL_API_BASE_URL=http://hotel_api:8001`. The agent forwards these to the MCP servers it spawns over `stdio` (see TASK-1.2). Without that forwarding the servers would call `127.0.0.1` inside the agent container and fail.

**The agent is a one-shot smoke test.** It runs `python agent/agent.py "Help me travel from Bangalore to Delhi on 2026-06-10 and stay there"` with `LLM_PROVIDER=mock`, prints flights and hotels, and exits (`restart: "no"`). Using `--abort-on-container-exit --exit-code-from agent` turns that into a pass/fail check. The provider is pinned to `mock` in the Compose file so the smoke test is deterministic and needs no LLM or API key, regardless of what is set in the developer's shell.

**Security defaults.** Postgres and Redis are published on `127.0.0.1` only. Redis has no password and Postgres uses a documented development password, so neither should be reachable from other machines. The `.env` file is gitignored and `.env.example` marks these values as local-dev only.

**`.env` semantics.** Compose reads `.env` automatically for `${...}` substitution (Postgres credentials). It does **not** inject those variables into containers; each service's `environment:` block is explicit. `.env.example` also documents the variables used when running services directly on the host. The Python code does **not** load `.env`; for host runs, set those variables in the shell (for example `$env:LLM_PROVIDER = "mock"`).

**Healthchecks.** `python:3.11-slim` ships without `curl`, so the API healthchecks use `python -c "import urllib.request; urllib.request.urlopen(...)"`, which raises (non-zero exit) on any non-2xx response.

## 4. Acceptance Criteria

| #   | Criterion                                                                                                                                      |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1 | `docker compose config` validates the file with no errors.                                                                                     |
| AC2 | `postgres` uses `pgvector/pgvector:pg16`, a named data volume, and a `pg_isready` healthcheck, and becomes healthy.                            |
| AC3 | `redis` uses `redis:7-alpine` with a `redis-cli ping` healthcheck and becomes healthy.                                                         |
| AC4 | `flight_api` (8000) and `hotel_api` (8001) build from the root context and become healthy via the Python `urllib.request` healthchecks.        |
| AC5 | `agent` starts only after both APIs are healthy, runs with `LLM_PROVIDER=mock` and the Compose-network API URLs, and exits with code 0.        |
| AC6 | The agent's output contains flights (`AI101`, `6E202`) and hotels (`Delhi Stay`, `Budget Inn Delhi`), proving the full path across containers. |
| AC7 | The pgvector extension can be created in the Postgres container.                                                                               |
| AC8 | `.env.example` documents all environment variables used across local development and Compose, and no real secrets.                             |
| AC9 | Data in `postgres_data` survives `docker compose down` and is removed only by `docker compose down -v`.                                        |

## 5. Verification Commands

Run from the repository root (PowerShell). Docker Desktop must be running.

```powershell
# 1. Validate the Compose file (AC1)
docker compose config --quiet                                     # expect: no output, exit code 0

# 2. Full smoke test (AC4, AC5, AC6): build, start everything, run the agent, stop when it exits
docker compose up --build --abort-on-container-exit --exit-code-from agent
"Exit code: $LASTEXITCODE"                                        # expect: 0
#    expect in the agent output: "Flights:" with AI101 and 6E202, and "Hotels:" with Delhi Stay and Budget Inn Delhi

# 3. Bring the stack up detached and inspect health (AC2, AC3, AC4)
docker compose up -d postgres redis flight_api hotel_api
docker compose ps                                                 # expect: all four "healthy" (wait ~15 s)
Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing | Select-Object StatusCode   # expect: 200
Invoke-WebRequest http://127.0.0.1:8001/health -UseBasicParsing | Select-Object StatusCode   # expect: 200

# 4. Postgres has pgvector available (AC7)
docker compose exec postgres psql -U travel -d travel_agent -c "CREATE EXTENSION IF NOT EXISTS vector;"
docker compose exec postgres psql -U travel -d travel_agent -c "SELECT extname, extversion FROM pg_extension;"   # expect: a 'vector' row

# 5. Redis answers (AC3)
docker compose exec redis redis-cli ping                          # expect: PONG

# 6. Run an ad-hoc prompt against the running stack (AC5)
docker compose run --rm agent python agent/agent.py "Find a flight from Bangalore to Delhi and then find hotels based on when I arrive"

# 7. Persistence (AC9): the extension created in step 4 must survive a restart without -v
docker compose down
docker compose up -d postgres
docker compose exec postgres psql -U travel -d travel_agent -c "SELECT extname FROM pg_extension;"   # expect: 'vector' still present

# 8. Clean up everything, including the volume
docker compose down -v

# 9. .env.example (AC8): copy and confirm Compose still works with it
Copy-Item .env.example .env
docker compose config --quiet
Remove-Item .env
```

## 6. Rollout & Rollback

- **Rollout:** merge with PR 1. The README can then point developers to `docker compose up` as the quickest way to run the system.
- **Rollback:** revert the PR. No application behavior depends on the Compose file.

## 7. Risks

| Risk                                                                          | Mitigation                                                                                                                                                   |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Port conflicts with services already running locally (8000, 8001, 5432, 6379) | Stop local servers first, or change the host side of the port mapping                                                                                        |
| Compose parity drifts from Cloud Run behavior                                 | PR 2 (Terraform/CD) reuses the same images; parity gaps are reviewed there                                                                                   |
| Unused Postgres and Redis containers consume resources                        | Accepted: they are provisioned now so SP02-SP05 start with a ready environment; start only needed services with `docker compose up -d <service>`             |
| Using the Ollama or OpenAI providers from the agent container                 | Smoke test pins `mock`. For other providers, pass `-e LLM_PROVIDER=...` and use `host.docker.internal` for a host-side Ollama (documented in `.env.example`) |

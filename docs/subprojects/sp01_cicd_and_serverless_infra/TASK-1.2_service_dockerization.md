# TASK-1.2 — Service Dockerization

| Field         | Value                                                                      |
| ------------- | -------------------------------------------------------------------------- |
| Epic          | SP01 — CI/CD Pipelines, Dockerization & Serverless Terraform IaC           |
| PR            | PR 1 of 2                                                                  |
| Branch        | `feat/sp01-cicd-and-docker`                                                |
| Target branch | `productionize`                                                            |
| Depends on    | SP00 (pinned `requirements.txt`), TASK-1.1                                 |
| Parent docs   | [`EPIC_PRD.md`](EPIC_PRD.md), [`00_MASTER_PRD.md`](../../00_MASTER_PRD.md) |

---

## 1. Objective

Package the application as reproducible, least-privilege container images: one for `flight_api`, one for `hotel_api`, and one for the `agent` (which also contains both MCP servers). Images install the **pinned** dependencies, run as a **non-root** user, and are configured through environment variables so the same image works on a developer machine, on the Compose network, and later on Cloud Run.

## 2. Scope

### In scope

| Area                                                        | Change                                                                                                                                                      |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `flight_api/Dockerfile`                                     | `python:3.11-slim`, non-root `appuser` (UID 10001), copies `flight_api/`, exposes 8000, writable dir for `flights.db`, runs uvicorn on `0.0.0.0:8000`       |
| `hotel_api/Dockerfile`                                      | Same pattern: copies `hotel_api/`, exposes 8001, writable dir for `hotels.db`, runs uvicorn on `0.0.0.0:8001`                                               |
| `agent/Dockerfile`                                          | Copies `agent/`, `flight_mcp_server/` and `hotel_mcp_server/`; default command lists tools                                                                  |
| `.dockerignore`                                             | Excludes `.venv/`, `.git/`, `__pycache__/`, `.pytest_cache/`, `report.html`, `docs/`, `*.db`, `.env` (plus `tests/`, `.github/`, caches, scratch folders)   |
| `agent/agent.py`                                            | New `build_mcp_server_env()`; the agent forwards `FLIGHT_API_BASE_URL`/`HOTEL_API_BASE_URL` to the MCP server subprocesses                                  |
| `tests/test_agent_mock.py`                                  | Two unit tests for `build_mcp_server_env()`                                                                                                                 |
| `flight_mcp_server/server.py`, `hotel_mcp_server/server.py` | Verified: already read `FLIGHT_API_BASE_URL` (default `http://127.0.0.1:8000`) and `HOTEL_API_BASE_URL` (default `http://127.0.0.1:8001`). No change needed |

### Out of scope

- Standalone MCP server images (SP03, when they move to Streamable HTTP).
- Pushing images to a registry and deploying them (TASK-1.4, TASK-1.5).
- Splitting dev/test dependencies out of the runtime image (see Risks).
- Persisting SQLite data across container restarts (SP02 replaces SQLite with Postgres).

## 3. Architectural Notes

**The MCP servers are packaged inside the `agent` image.** The servers use the `stdio` transport: the agent spawns each as a child process (`sys.executable flight_mcp_server/server.py`) and exchanges JSON-RPC over stdin/stdout. A child process must be on the same filesystem as its parent, so the servers cannot be separate containers yet. This gives three application images instead of five. In SP03 the servers move to stateless Streamable HTTP and become standalone containers, at which point each gets its own Dockerfile and the agent image no longer contains them.

**Environment variables must be forwarded explicitly.** The MCP SDK's `stdio_client` gives a child process only a small allowlist of inherited variables (`PATH`, `HOME`, `USER`, ...) merged with whatever is passed in `StdioServerParameters(env=...)`. Setting `FLIGHT_API_BASE_URL=http://flight_api:8000` on the agent container would therefore be **silently dropped**, and the spawned server would fall back to `127.0.0.1:8000` and fail inside Docker. The agent now forwards `FLIGHT_API_BASE_URL` and `HOTEL_API_BASE_URL` (only when set) to each server it launches. This is unit tested and also makes local runs on non-default ports work.

**Non-root user.** Each image creates a system user `appuser` (UID/GID 10001) and switches to it before `CMD`. The API images additionally `chown` their service directory, because SQLite creates `flights.db`/`hotels.db` beside `database.py` at startup and needs write access to the _directory_, not just the copied files.

**Build context and layer caching.** All images build from the repository root (`-f <service>/Dockerfile .`) so `requirements.txt` is in context. `requirements.txt` is copied and installed before application code, so the dependency layer is rebuilt only when the lockfile changes. `pip install --no-cache-dir -r requirements.txt` installs the pinned versions.

**Ephemeral databases.** `*.db` files are excluded from the build context. Each API container creates and seeds its own SQLite file on startup, and it is discarded with the container. This is acceptable until SP02.

## 4. Acceptance Criteria

| #   | Criterion                                                                                                                                                                               |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1 | `flight_mcp_server/server.py` and `hotel_mcp_server/server.py` read `FLIGHT_API_BASE_URL` (default `http://127.0.0.1:8000`) and `HOTEL_API_BASE_URL` (default `http://127.0.0.1:8001`). |
| AC2 | The agent forwards both variables to the MCP server subprocesses, and the unit tests for `build_mcp_server_env()` pass.                                                                 |
| AC3 | A root `.dockerignore` excludes `.venv/`, `.git/`, `__pycache__/`, `.pytest_cache/`, `report.html`, `docs/`, `*.db` and `.env`.                                                         |
| AC4 | `flight_api/Dockerfile`, `hotel_api/Dockerfile` and `agent/Dockerfile` exist, use `python:3.11-slim`, and install dependencies with `pip install --no-cache-dir -r requirements.txt`.   |
| AC5 | All containers run as `appuser` with UID 10001, not root.                                                                                                                               |
| AC6 | The `flight_api` and `hotel_api` images start, create their SQLite files without permission errors, and answer `GET /health` with 200 on 8000 and 8001 respectively.                    |
| AC7 | The `agent` image contains both MCP servers and lists all four tools when run with `LLM_PROVIDER=mock`.                                                                                 |
| AC8 | Images build from the repository root with the documented commands.                                                                                                                     |

## 5. Verification Commands

Run from the repository root (PowerShell). Docker Desktop must be running.

```powershell
# 0. Unit tests for the env-forwarding fix (AC2)
pytest tests/test_agent_mock.py -k build_mcp_server_env

# 1. Build all three images (AC4, AC8)
docker build -f flight_api/Dockerfile -t travel-agent/flight-api:local .
docker build -f hotel_api/Dockerfile  -t travel-agent/hotel-api:local  .
docker build -f agent/Dockerfile      -t travel-agent/agent:local      .

# 2. flight_api: runs as non-root, creates flights.db, answers /health (AC5, AC6)
docker run --rm -d --name flight-api -p 8000:8000 travel-agent/flight-api:local
Start-Sleep -Seconds 5
Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing | Select-Object StatusCode, Content   # expect: 200 {"status":"ok"}
docker exec flight-api id                                         # expect: uid=10001(appuser) gid=10001(appuser)
docker exec flight-api ls -l /app/flight_api                      # expect: flights.db owned by appuser
docker stop flight-api

# 3. hotel_api: same checks on port 8001 (AC5, AC6)
docker run --rm -d --name hotel-api -p 8001:8001 travel-agent/hotel-api:local
Start-Sleep -Seconds 5
Invoke-WebRequest http://127.0.0.1:8001/health -UseBasicParsing | Select-Object StatusCode, Content   # expect: 200 {"status":"ok"}
docker exec hotel-api id                                          # expect: uid=10001(appuser)
docker exec hotel-api ls -l /app/hotel_api                        # expect: hotels.db owned by appuser
docker stop hotel-api

# 4. agent: contains both MCP servers, lists four tools, non-root (AC5, AC7)
docker run --rm -e LLM_PROVIDER=mock travel-agent/agent:local python agent/agent.py "What travel tools can you use?"
#    expect: Available MCP tools: flight.search_flights, flight.get_flight, hotel.search_hotels, hotel.get_hotel
docker run --rm travel-agent/agent:local id                       # expect: uid=10001(appuser)

# 5. .dockerignore keeps junk out of images (AC3)
docker run --rm travel-agent/agent:local ls -a /app               # expect: agent, flight_mcp_server, hotel_mcp_server, requirements.txt (no docs, tests, .env, .git)
```

The full cross-container flow (agent → MCP → APIs over the Docker network) is verified in [TASK-1.3](TASK-1.3_docker_compose_local_stack.md).

## 6. Rollout & Rollback

- **Rollout:** merge with PR 1. Images are built locally and by Compose only; nothing is published yet.
- **Rollback:** revert the PR. The only runtime code change is `build_mcp_server_env()`, which is a no-op when the variables are unset.

## 7. Risks

| Risk                                                                                                                 | Mitigation                                                                                                                                                                                               |
| -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `requirements.txt` includes test and lint tools (`pytest`, `ruff`, ...), so runtime images are larger than necessary | Accepted for now (single lockfile). Splitting runtime and dev requirements is a candidate follow-up before the Cloud Run deploy                                                                          |
| Lockfile compiled on Windows may contain platform-specific pins that fail `pip install` on the Linux image           | Re-lock with `scripts/compile-requirements.ps1` / `.sh` (Linux container, same `python:3.11-slim` base as the images); CI's lockfile-parity step catches a host-compiled lockfile before the image build |
| New MCP servers or env vars added later need explicit forwarding                                                     | `MCP_FORWARDED_ENV_VARS` in `agent.py` is the single place to extend; covered by unit tests                                                                                                              |
| Container filesystem is ephemeral, so SQLite data resets on every start                                              | Intentional until SP02                                                                                                                                                                                   |

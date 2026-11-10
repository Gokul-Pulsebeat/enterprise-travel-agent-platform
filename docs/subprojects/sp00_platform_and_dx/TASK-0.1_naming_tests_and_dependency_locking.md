# TASK-0.1 — Naming Standardization, Baseline Tests & Dependency Locking

| Field         | Value                                                                                                                                                  |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Epic          | SP00 — Platform, DX & Repo Standardization                                                                                                             |
| Branch        | `feat/sp00-baseline-standardization-and-mcp2`                                                                                                          |
| Target branch | `productionize`                                                                                                                                        |
| Parent docs   | [`EPIC_PRD.md`](EPIC_PRD.md), [`00_MASTER_PRD.md`](../../00_MASTER_PRD.md), [`01_STEP_0_POC_BASELINE_AUDIT.md`](../../01_STEP_0_POC_BASELINE_AUDIT.md) |

---

## 1. Objective

Establish a clean, symmetric, tested foundation before productionization begins. Specifically:

1. **Repository rename** to `enterprise-travel-agent-platform`.
2. **Symmetric naming** across the flight and hotel domains: `flight_api/`, `flight_mcp_server/`, `hotel_api/`, `hotel_mcp_server/`, `agent/` all at the project root, using identical conventions inside each pair.
3. **Upgrade to MCP Python SDK 2.x**: `mcp>=2.0.0`, replacing `FastMCP` (`mcp.server.fastmcp`) with `MCPServer` (`mcp.server.mcpserver`) in both servers, and adapting the agent client to 2.x model attribute names.
4. **Baseline `pytest` suite** (`tests/`) covering REST APIs, unit logic, and full end-to-end integration tests over `stdio` MCP connections.
5. **Dependency Locking**: Introduction of `pip-tools` to separate loose top-level dependencies (`requirements.in`) from strict production lockfiles (`requirements.txt`).
6. **Master PRD initialization**: the documentation hierarchy under `docs/` and the pull request template.

## 2. Scope

### In scope

| Area             | Change                                                                                                                                                                 |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Folder rename    | `mcp_server/` → `flight_mcp_server/` (history-preserving rename)                                                                                                       |
| `agent/agent.py` | `MCP_SERVER_PATHS["flight"]` points to `flight_mcp_server/server.py`; `tool.inputSchema` → `tool.input_schema` (MCP 2.x snake_case)                                    |
| MCP servers      | `from mcp.server.mcpserver import MCPServer`; `mcp = MCPServer("flight-mcp-server")` and `mcp = MCPServer("hotel-mcp-server")`; `mcp.run(transport="stdio")` unchanged |
| Dependencies     | requirements.in added with `mcp>=2.0.0`, `pytest>=8.0.0`, `httpx>=0.27.0`. `requirements.txt` becomes an auto-generated lockfile via `pip-tools`.                      |
| `README.md`      | Architecture diagram and Project Folders reflect `flight_mcp_server/`                                                                                                  |
| Tests            | `tests/test_flight_api.py`, `tests/test_hotel_api.py`, `tests/test_agent_mock.py`. Added `pytest-html` plugin to generate `report.html`.                               |
| Docs             | `docs/00_MASTER_PRD.md`, `docs/01_STEP_0_POC_BASELINE_AUDIT.md`, `docs/subprojects/**/EPIC_PRD.md`, this ticket                                                        |
| Process          | `.github/pull_request_template.md`                                                                                                                                     |

### Naming conventions after this task

| Concern              | Flight                         | Hotel                        |
| -------------------- | ------------------------------ | ---------------------------- |
| REST package         | `flight_api/`                  | `hotel_api/`                 |
| MCP package          | `flight_mcp_server/`           | `hotel_mcp_server/`          |
| MCP server name      | `flight-mcp-server`            | `hotel-mcp-server`           |
| FastAPI title        | `Flight Search API`            | `Hotel Search API`           |
| API base URL env var | `FLIGHT_API_BASE_URL`          | `HOTEL_API_BASE_URL`         |
| Default API port     | `8000`                         | `8001`                       |
| DB path constant     | `DB_PATH` → `flights.db`       | `DB_PATH` → `hotels.db`      |
| Tool names           | `search_flights`, `get_flight` | `search_hotels`, `get_hotel` |

### Out of scope (tracked elsewhere)

- Migrating from `stdio` to Streamable HTTP (SP03).
- Replacing SQLite (SP02) and the deprecated `@app.on_event("startup")` hook with a FastAPI lifespan handler (SP02).
- CI automation of the test suite (SP01).
- The mock planner infers routes from city names in dictionary order rather than prompt order, so "Delhi to Bangalore" resolves as BLR→DEL. Known limitation of the mock; the LLM planner is unaffected. No test asserts the incorrect behavior.

## 3. Acceptance Criteria

| #    | Criterion                                                                                                                                                     |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1  | `flight_api/`, `flight_mcp_server/`, `hotel_api/`, `hotel_mcp_server/`, `agent/` exist at the project root and `mcp_server/` does not.                        |
| AC2  | No code or docs reference the old path `mcp_server/server.py` as the flight server.                                                                           |
| AC3  | Neither server imports `FastMCP` or `mcp.server.fastmcp`; both import `MCPServer` from `mcp.server.mcpserver`.                                                |
| AC4  | MCP server names are exactly `flight-mcp-server` and `hotel-mcp-server`.                                                                                      |
| AC5  | `requirements.in` declares loose dependencies (`mcp>=2.0.0`, etc.), and `requirements.txt` contains strictly pinned `==` versions generated by `pip-compile`. |
| AC6  | `pytest` passes with no failures from the repository root.                                                                                                    |
| AC7  | The agent starts both MCP servers and lists all four tools in mock mode.                                                                                      |
| AC8  | The `README.md` architecture diagram and folder list show `flight_mcp_server/`.                                                                               |
| AC9  | `docs/00_MASTER_PRD.md`, `docs/01_STEP_0_POC_BASELINE_AUDIT.md`, six `EPIC_PRD.md` placeholders, and `.github/pull_request_template.md` exist.                |
| AC10 | Running `pytest` generates a self-contained `report.html` visual test report, which is excluded from version control via `.gitignore`.                        |

## 4. Verification Commands

Run from the repository root with the virtual environment active (PowerShell shown; use the equivalent in your shell).

```powershell
# 0. Install dependencies using the strict lockfile
pip install pip-tools
pip-sync requirements.txt          # Windows: use .\scripts\sync-dev.ps1 instead (see SP01 TASK-1.1)
# (To re-lock after editing requirements.in, use scripts/compile-requirements.ps1 or .sh; see SP01 TASK-1.1. Avoid running pip-compile directly on Windows.)

# 1. Layout (AC1): old folder gone, new folder present
Test-Path mcp_server                 # expect: False
Test-Path flight_mcp_server          # expect: True

# 2. No stale references or v1 imports (AC2, AC3) -- scoped to code, since docs mention the old names on purpose
git grep --untracked -n "mcp.server.fastmcp" -- "*.py"                  # expect: no output
git grep --untracked -nE "(^|[^_a-z])mcp_server" -- "*.py" README.md     # expect: no output

# 3. Dependencies (AC5)
Select-String -Path requirements.in -Pattern "mcp>=2.0.0|pytest>=8.0.0|httpx>=0.27.0"

# 4. Full test suite (AC6, AC10)
pytest
Test-Path report.html                # expect: True
git status --short                   # expect: report.html does not appear (gitignored)

# 5. Agent end-to-end in mock mode (AC7)
$env:LLM_PROVIDER = "mock"
python agent/agent.py "What travel tools can you use?"
# expect: Available MCP tools: flight.search_flights, flight.get_flight, hotel.search_hotels, hotel.get_hotel

# 6. Optional full flow with live APIs (two extra terminals)
#    Terminal A: uvicorn flight_api.app:app --port 8000
#    Terminal B: uvicorn hotel_api.app:app  --port 8001
python agent/agent.py "Help me travel from Bangalore to Delhi on 2026-06-10 and stay there."
```

## 5. Test Plan Summary

| File                            | Covers                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_flight_api.py`      | `GET /health`, `GET /flights`, `GET /flights?origin=BLR&destination=DEL`, `GET /flights/1`, 404 on an unknown ID                                                                                                                                                                                                                                                                                                                                                                                                      |
| `tests/test_hotel_api.py`       | `GET /health`, `GET /hotels`, `GET /hotels?city=Delhi`, `GET /hotels/1`, 404 on an unknown ID                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `tests/test_agent_mock.py`      | Pure unit tests, no subprocesses or network: `extract_airport_codes`, `extract_date`, `infer_route`, `plan_with_mock` (parallel plan and sequential `$first_flight_date:search_flights` plan, no-route fallback, tools prompt), and `resolve_arguments` placeholder resolution                                                                                                                                                                                                                                        |
| `tests/test_integration_e2e.py` | All integration tests (module-level `integration` marker). Handshake check: `run_agent("What travel tools can you use?")` spawns both MCP servers over `stdio` and lists their four tools. Full end-to-end path, `agent -> MCP client -> MCP server (stdio) -> REST API -> SQLite`, using real uvicorn processes on ports 8000/8001 (reused if already running), covering the parallel flight+hotel plan and the sequential plan, which proves `call_tool` and `$first_flight_date` resolution work against real data |

Every test in `tests/test_integration_e2e.py` carries `@pytest.mark.integration` (registered in `pytest.ini`). Run only the fast unit tests with `pytest -m "not integration"`, or only the subprocess-based tests with `pytest -m integration`.

## 6. Rollout & Rollback

- **Rollout:** open a PR from `feat/sp00-baseline-standardization-and-mcp2` into `productionize` using the PR template; merge after review.
- **Rollback:** revert the squash commit. The only user-visible change is the flight server path, the MCP server names, and the MCP SDK major version. Anyone running the old layout must reinstall dependencies (`pip install -r requirements.txt`).

## 7. Risks

| Risk                                                                                                                        | Mitigation                                                                        |
| --------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| MCP 2.x speaks a newer protocol version than 1.x; the `stdio` handshake is covered only by the `run_agent` integration test | Test AC7 exercises the real client/server handshake; failures surface immediately |
| SQLite DB files are created next to the code on first test run                                                              | `*.db` is already in `.gitignore`; tests tolerate an existing seeded database     |

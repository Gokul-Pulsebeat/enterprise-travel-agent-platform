# 01 — Step-0 PoC Baseline Audit (`v0.1.0-poc`)

| Field          | Value                                                                               |
| -------------- | ----------------------------------------------------------------------------------- |
| Baseline       | `v0.1.0-poc` on `main`                                                              |
| Purpose        | Establish exactly what exists, and what is missing, before productionization begins |
| Companion docs | [`00_MASTER_PRD.md`](00_MASTER_PRD.md) (target state and roadmap)                   |

---

## 1. Context

`v0.1.0-poc` is a functional **proof-of-concept** built to validate one core idea: that a single agent can orchestrate **multiple independent MCP servers** (flight and hotel) over the `stdio` transport, plan multi-step work as a small dependency graph, and execute independent steps in parallel.

It was built for learning and demonstration, not for operation. The shape of the system is:

```
User prompt
   -> agent/agent.py            (planner + executor + MCP client)
        -> flight_mcp_server/server.py  --HTTP-->  flight_api/app.py  --> flights.db (SQLite)
        -> hotel_mcp_server/server.py   --HTTP-->  hotel_api/app.py   --> hotels.db  (SQLite)
```

The PoC deliberately favored simplicity: every moving part runs on one developer machine, state lives in two local SQLite files, and every guardrail was left out so the orchestration mechanics were easy to read.

> **Naming note.** At the time of the `v0.1.0-poc` tag the flight MCP server lived in `mcp_server/` and the hotel server in `hotel_mcp_server/`. SP00 (see [`TASK-0.1`](subprojects/sp00_repo_standardization/TASK-0.1_naming_and_mcp2_migration.md)) renames the former to `flight_mcp_server/` so both domains are symmetric. This audit describes behavior, which is unaffected by that rename.

---

## 2. What Step-0 Can Do

### 2.1 Read-only flight and hotel queries

- `flight_api` serves `GET /health`, `GET /flights` (filters: `origin`, `destination`, `date`) and `GET /flights/{id}` from `flights.db`.
- `hotel_api` serves `GET /health`, `GET /hotels` (filters: `city`, `check_in_date`) and `GET /hotels/{id}` from `hotels.db`.
- Both databases are **SQLite files created and seeded on first startup** with five mock rows each. Queries are parameterized (no SQL injection through filters).
- Each MCP server is a thin wrapper: it exposes `search_*` and `get_*` tools and forwards them to the matching REST API with `requests`, translating connection failures into friendly error messages.

### 2.2 `stdio` subprocess MCP spawning

- On every CLI invocation the agent launches **both MCP servers as child processes** (`sys.executable server.py`) and talks to them over stdin/stdout using the MCP client SDK.
- Sessions are held open together with an `AsyncExitStack` for the duration of one prompt, then torn down.

### 2.3 Basic JSON DAG planner

- The planner emits a JSON plan: a list of steps, each with `step_id`, `server_name`, `tool_name`, `arguments` and `depends_on`.
- The executor repeatedly finds steps whose dependencies are complete and runs all of them concurrently with `asyncio.gather`. A plan with unresolvable dependencies fails fast with a clear error.
- **Variable resolution:** an argument value of `$first_flight_date:<step_id>` is replaced at execution time with the departure date (`YYYY-MM-DD`) of the first flight returned by that step. This lets a hotel search depend on flight results.

### 2.4 Static provider switching

`LLM_PROVIDER` selects the planner and summarizer at process start:

| Provider           | Planner                                | Summarizer              | Notes                             |
| ------------------ | -------------------------------------- | ----------------------- | --------------------------------- |
| `ollama` (default) | Local model returns JSON plan          | Local model             | Free; needs Ollama running        |
| `openai`           | OpenAI Responses API returns JSON plan | OpenAI                  | Needs `OPENAI_API_KEY`            |
| `mock`             | Deterministic keyword/regex planner    | Deterministic formatter | No network or LLM; used for tests |

---

## 3. What Step-0 Cannot Do (Production Gaps)

### Gap 1 — No persistence or concurrency control

- Both databases are **read-only in practice**: there is no booking, cancellation, user, or payment state.
- `seats_available` and `rooms_available` are static numbers. There is **no inventory locking** and **no double-booking protection**; two simultaneous bookings (if they existed) could both "succeed" against the last seat.
- SQLite files are local to one process host, so the APIs cannot be run as multiple replicas against shared state.
- There are no idempotency keys, so a retried write (once writes exist) could duplicate a booking.

### Gap 2 — Subprocess-per-request overhead

- Every prompt spawns **two Python interpreters**, imports the MCP SDK in each, performs an MCP handshake, and discards everything afterwards.
- This adds fixed startup latency to every request and **prevents horizontal scaling**: there is no long-lived, shared, network-addressable MCP endpoint that a load balancer could front.
- `stdio` couples the agent's lifetime to the servers' lifetime and cannot carry per-request identity or auth.

### Gap 3 — Zero ingress/egress guardrails

- **Prompt injection:** user text goes straight into the planner prompt with no screening.
- **Indirect (tool-data) injection:** raw tool output, which may contain attacker-controlled text, is fed back into the summarizer prompt unfiltered.
- **Out-of-domain cost exhaustion:** any prompt, relevant or not, reaches a billable LLM; there is no early-reject router, rate limiting, or budget cap.
- **Hallucinated facts:** the summarizer is only _instructed_ not to invent prices, flight numbers, dates or availability. Nothing **verifies** the final answer against tool results.
- **No identity:** there is no authentication, authorization, or PII redaction; tool calls carry no user context.

### Gap 4 — Brittle Infrastructure

- The PoC uses an unpinned `requirements.txt` (using loose open bounds like `>=` for everything or no bounds at all).
- This risks "dependency hell" where a future transitive package update can break the application on deployment. (Addressed in SP00 via `pip-tools` dependency locking).

### Gap 5 — Brittle orchestration

- The "agent" is a hand-written planner plus a `while` loop. There is **no state checkpointing**: a crash or timeout mid-plan loses everything.
- There are **no retries, backoff, or per-step failure handling**; one failed step aborts the run.
- There is **no Human-in-the-Loop (HITL)** approval gate for sensitive actions, and no typed state or structured-output validation of the plan beyond `json.loads`.
- A single planner sees the entire tool catalog, which will bloat context as more servers are added.
- The mock planner's city-to-route inference follows dictionary order rather than prompt order (e.g., "Delhi to Bangalore" resolves as BLR→DEL). This is acceptable for a mock but illustrates the heuristic nature of the PoC.

### Gap 6 — Limited domain scope (two MCP servers only)

- **No corporate policy compliance.** Nothing checks a trip against travel policy, employee role tiers, fare caps, or manager-approval requirements. The target design adds a `policy_mcp_server` with hybrid RAG (pgvector + BM25) over policy documents.
- **No FinOps capability.** There is no safe place to run multi-currency per-diem math, GST calculations, or cost charts. Letting an LLM do arithmetic directly is unreliable; the target design adds a `finops_mcp_server` backed by an **isolated code sandbox**.
- **No transactional notifications.** There is no email or other notification on booking confirmation or cancellation.
- **No observability.** There is no tracing, cost accounting, or evaluation harness; debug output is `print` to stderr.

---

## 4. Summary Matrix

| Capability                  | Step-0 (`v0.1.0-poc`)             | Target                                          | Addressed in |
| --------------------------- | --------------------------------- | ----------------------------------------------- | ------------ |
| Flight/hotel search         | ✅ SQLite, read-only              | Postgres, async                                 | SP02         |
| Bookings, inventory locking | ❌                                | ACID, `SELECT ... FOR UPDATE`, idempotency      | SP02         |
| Transport                   | `stdio` subprocess per prompt     | Stateless Streamable HTTP                       | SP03         |
| AuthN/Z, rate limiting, PII | ❌                                | JWT propagation, Redis limits, redaction        | SP03         |
| Injection defense           | ❌                                | Ingress router + tool-output screening          | SP03         |
| Orchestration               | Custom DAG loop                   | LangGraph supervisor + sub-agents, checkpointer | SP04         |
| HITL approvals              | ❌                                | Manager-approval interrupts                     | SP04         |
| Policy compliance           | ❌                                | `policy_mcp_server` hybrid RAG                  | SP05         |
| Expense / FX / GST math     | ❌                                | `finops_mcp_server` sandbox                     | SP05         |
| Groundedness checks         | ❌                                | Deterministic egress validator                  | SP06         |
| Model routing, cost control | Static provider                   | Cost-aware router + fallbacks                   | SP06         |
| Observability, evals        | ❌                                | OpenTelemetry + Langfuse, golden-set CI gate    | SP06         |
| CI/CD, IaC, containers      | ❌                                | GitHub Actions, Docker, Terraform               | SP01         |
| Test suite                  | ❌                                | Baseline pytest suite                           | SP00         |
| Dependency Management       | Loose/unpinned `requirements.txt` | Strict lockfile separation via `pip-tools`      | SP00         |

---

## 5. Conclusion

Step-0 successfully demonstrates multi-server MCP orchestration, which was its goal. It is **not** deployable: it has no state, no isolation, no security boundary, and no way to scale or observe it. The roadmap in [`00_MASTER_PRD.md`](00_MASTER_PRD.md) closes each gap above in a defined order, beginning with SP00, which standardizes naming, upgrades to MCP 2.x, and adds the baseline tests that every later epic will rely on to detect regressions.

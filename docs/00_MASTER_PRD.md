# 00 — Master PRD & Engineering Roadmap

**Product:** Enterprise Corporate Travel, Expense & Policy Compliance Platform
**Repository:** `enterprise-travel-agent-platform`
**Status:** Draft v1 — initialized in SP00
**Related:** [`01_STEP_0_POC_BASELINE_AUDIT.md`](01_STEP_0_POC_BASELINE_AUDIT.md)

---

## 1. Executive Summary & Business Case

Corporate travel is a high-volume, rules-heavy process. Employees want to book quickly; finance needs spend within policy; managers need to approve exceptions; and everyone needs accurate totals. Today these concerns live in separate tools, so employees book first and discover policy violations later, finance reconciles expenses by hand, and managers approve by email.

This platform puts a conversational agent in front of those workflows. An employee asks, in plain language, for a trip. The system:

1. **Finds and books** flights and hotels against live inventory, without double-booking.
2. **Checks the trip against corporate travel policy** for the employee's role tier *before* committing, and routes out-of-policy bookings to a manager for approval.
3. **Computes costs correctly** (multi-currency per-diems, GST, charts) in an isolated sandbox rather than trusting an LLM to do arithmetic.
4. **Verifies its own answers** against tool data so prices and flight numbers are never invented.

**Why this matters**

| Business outcome | Mechanism |
|---|---|
| Fewer policy violations and less rework | Policy check happens at booking time via RAG over the actual policy documents |
| Lower and more predictable LLM spend | Early-reject intent router, cost-aware model routing, context compaction |
| Trustworthy answers | Deterministic egress groundedness validation; evals gate CI |
| Safe automation of money-touching actions | ACID booking transactions, idempotency keys, HITL approvals |
| Operability | Stateless services, IaC, tracing, golden-set regression tests |

The repository began as a proof-of-concept (`v0.1.0-poc`, see the [baseline audit](01_STEP_0_POC_BASELINE_AUDIT.md)). This document defines how it becomes a production system, in small, reviewable, independently shippable increments.

### Non-goals (for this roadmap)
- Real payment processing or live GDS/airline integrations (mock inventory stays mock, but is stored and locked like real inventory).
- A polished end-user web UI (the client is a thin CLI/API consumer; UI is out of scope).
- Multi-tenant SaaS billing.

---

## 2. Four-Server, Multi-Domain MCP Tool Layer

The PoC had two MCP servers. The target has **four specialized MCP servers** but still only **two backend REST APIs**. This is deliberate, and it demonstrates both integration patterns in one codebase.

### 2.1 Why four servers
Each MCP server is a **bounded domain** with its own tools, its own failure modes, and its own security posture. Splitting by domain, and scoping each sub-agent to only the servers it needs (see SP04), prevents the *tool-context bloat* that degrades model accuracy when one agent sees every tool. It also lets servers scale and deploy independently.

### 2.2 Why only two REST APIs
| Pattern | Servers | Description |
|---|---|---|
| **A. Wrap a legacy REST microservice** | `flight_mcp_server`, `hotel_mcp_server` | The business logic and database live behind an existing REST API. The MCP server is a thin adapter. This mirrors the common real-world case of exposing existing services to agents without rewriting them. |
| **B. Native MCP microservice** | `policy_mcp_server`, `finops_mcp_server` | There is no REST API in front. The MCP server owns its logic and talks directly to its backing resource (Postgres/pgvector, or a code sandbox). This mirrors greenfield, agent-first services. |

### 2.3 Server catalog

| # | Server | Pattern | Backing resource | Responsibility |
|---|---|---|---|---|
| 1 | `flight_mcp_server` | A — wraps `flight_api` | Neon Postgres (via `flight_api`): inventory, ACID seat locking, bookings | Search flights, get flight, hold/book/cancel seats |
| 2 | `hotel_mcp_server` | A — wraps `hotel_api` | Neon Postgres (via `hotel_api`): room inventory, row-level locking, bookings | Search hotels, get hotel, hold/book/cancel rooms |
| 3 | `policy_mcp_server` | B — native | Neon Postgres with `pgvector` + BM25 full-text: corporate travel policy chunks, employee role tiers, manager-approval tables | Hybrid RAG over policy text (with cross-encoder reranking); look up role tier limits; create/read approval requests |
| 4 | `finops_mcp_server` | B — native | Isolated Python sandbox (E2B or Docker) | Multi-currency per-diem math, GST calculations, cost-chart generation; **no network, no secrets, resource-limited** |

---

## 3. Target Production Architecture

```
                         +---------------------------+
                         |     Client (CLI / API)    |
                         +-------------+-------------+
                                       |
                                       v
 +-----------------------------------------------------------------------+
 |              INGRESS GUARDRAIL  &  SEMANTIC ROUTER                    |
 |  JWT auth | Redis rate limit | PII redaction | fast SLM intent router |
 |  (reject off-domain early)   | prompt-injection screening             |
 +-----------------------------------+-----------------------------------+
                                     |
                                     v
 +-----------------------------------------------------------------------+
 |        LANGGRAPH SUPERVISOR   (typed state, Postgres checkpointer)    |
 |                                                                       |
 |   +-----------------+   +------------------+   +------------------+   |
 |   | Booking         |   | Compliance       |   | FinOps           |   |
 |   | Sub-Agent       |   | Sub-Agent        |   | Sub-Agent        |   |
 |   | (flight, hotel) |   | (policy)         |   | (finops)         |   |
 |   +--------+--------+   +---------+--------+   +---------+--------+   |
 |            |     HITL manager-approval interrupts        |            |
 +------------|--------------------|-----------------------|------------+
              |  Stateless Streamable HTTP, JWT propagated  |
 +------------v--------------------v-----------------------v------------+
 |                    4-SERVER MCP TOOL LAYER                            |
 |  +----------------+ +----------------+ +---------------+ +---------+ |
 |  | flight_mcp_    | | hotel_mcp_     | | policy_mcp_   | | finops_ | |
 |  | server         | | server         | | server        | | mcp_    | |
 |  | (wraps REST)   | | (wraps REST)   | | (native)      | | server  | |
 |  |                | |                | |               | | (native)| |
 |  +-------+--------+ +-------+--------+ +-------+-------+ +----+----+ |
 +----------|------------------|------------------|--------------|------+
            v                  v                  |              |
      +-----------+      +-----------+            |              |
      | flight_api|      | hotel_api |            |              |
      | (REST)    |      | (REST)    |            |              |
      +-----+-----+      +-----+-----+            |              |
            |                  |                  |              |
            |  booking events  |                  |              |
            v                  v                  v              v
 +-----------------------------------------------------------------------+
 |                         BACKING STORES                                |
 |  Neon Postgres + pgvector : inventory, bookings, policy chunks,       |
 |                             roles, approvals, graph checkpoints       |
 |  Upstash Redis            : rate limits, idempotency keys, caches     |
 |  Email Worker             : booking confirmation / cancellation mail  |
 |  Code Sandbox (E2B/Docker): isolated per-diem / GST / chart execution |
 +-----------------------------------+-----------------------------------+
                                     |
                                     v
 +-----------------------------------------------------------------------+
 |        EGRESS GROUNDEDNESS VALIDATOR                                  |
 |  Deterministically verifies every price / flight ID / date in the     |
 |  answer against tool results before it reaches the client             |
 +-----------------------------------+-----------------------------------+
                                     |
                                     v
                          Response returned to Client

 ======================================================================
  OpenTelemetry + Langfuse: traces, token/cost metrics, eval scores
  span EVERY layer above (ingress -> agents -> MCP -> stores -> egress)
 ======================================================================
```

**Reading the diagram**
- **Ingress** is cheap and fast: authenticate, rate limit, redact PII, and use a small model to reject or route obviously irrelevant or hostile requests *before* any expensive model runs.
- **Supervisor** owns the conversation state and checkpoints it to Postgres, so a run can pause for human approval and resume, or recover after a crash.
- **Sub-agents** each see only their own MCP server(s). The booking sub-agent never sees finance tools, and so on.
- **MCP layer** is stateless Streamable HTTP, so any replica can serve any request; identity travels as a JWT.
- **Egress** is the last line of defense against hallucinated numbers.

---

## 4. Git & Release Governance

```
main            production release  (tagged: v0.1.0-poc, v1.0.0, ...)
   ^
   |  release PR, after productionize is green and soaked
productionize   CI/CD integration branch  (auto-deploys to staging/prod infra)
   ^
   |  one PR per task, squash-merged
feat/spXX-tYY-*  atomic feature branches
```

| Branch | Purpose | Rules |
|---|---|---|
| `main` | Production release line. Only receives merges from `productionize`. | Protected. Tagged releases. |
| `productionize` | CI/CD integration branch. Everything here has passed CI. Merge triggers automatic deployment (SP01). | Protected. PR required. CI required. |
| `feat/spXX-tYY-*` | One atomic task. Example: `feat/sp00-baseline-standardization-and-mcp2`. | Branched from `productionize`. Must include its task PRD, unit/integration tests, and pass CI. |

**Definition of Done for every task branch**
1. A task PRD exists under `docs/subprojects/spXX_*/` (and is linked from the PR).
2. New behavior has unit tests; cross-component behavior has integration tests.
3. `pytest` passes locally and in CI.
4. The PR template (`.github/pull_request_template.md`) is fully completed, including architectural impact on security, cost, latency and concurrency.
5. Docs affected by the change (README, architecture diagrams) are updated in the same PR.

---

## 5. Sequenced Sub-Project Roadmap (The 7 Epics)

Epics are sequenced so each one unblocks the next. Each lives in its own folder under `docs/subprojects/` with an `EPIC_PRD.md` and per-task `TASK-X.Y_*.md` tickets.

### SP00 — Repo Standardization, Naming Symmetry & MCP 2.x Baseline
`docs/subprojects/sp00_repo_standardization/`
Rename the repo and standardize flight/hotel naming (`flight_mcp_server` / `hotel_mcp_server`); upgrade to the MCP Python SDK 2.x (`MCPServer`); add the baseline `pytest` suite; initialize this PRD hierarchy and the PR template. **Outcome:** a clean, symmetric, tested foundation. First ticket: [`TASK-0.1`](subprojects/sp00_repo_standardization/TASK-0.1_naming_and_mcp2_migration.md).

### SP01 — CI/CD Pipelines, Dockerization & Serverless Terraform IaC
`docs/subprojects/sp01_cicd_and_serverless_infra/`
GitHub Actions CI on every PR (lint, tests); Docker images and a Docker Compose stack for local parity with production; Terraform for **GCP Cloud Run + Neon Postgres + Upstash Redis**, with **auto-deploy on merge to `productionize`**.

### SP02 — Productionizing Flight & Hotel Core Microservices
`docs/subprojects/sp02_core_travel_microservices/`
Migrate SQLite to **async PostgreSQL**; add users and role tiers; implement **ACID booking transactions** using `SELECT ... FOR UPDATE` row-level locking to prevent double-booking; add **idempotency keys** for safe retries; send **background transactional emails** on booking confirmation and cancellation.

### SP03 — Stateless Streamable HTTP MCP Layer, Auth & Security Guardrails
`docs/subprojects/sp03_mcp_http_layer_and_security/`
Move MCP from `stdio` to **stateless Streamable HTTP**; **JWT identity propagation** end to end; **Redis rate limiting**; **PII redaction**; a **fast SLM intent router** for early rejection of off-domain requests; **indirect prompt-injection defense** on tool outputs.

### SP04 — LangGraph Multi-Agent Architecture & HITL Workflows
`docs/subprojects/sp04_langgraph_multi_agent_core/`
A typed **LangGraph state machine** with a **Postgres checkpointer**; a **Supervisor plus three sub-agents** (Booking, Compliance, FinOps), each scoped to specific MCP servers to prevent tool-context bloat; **Pydantic structured outputs**; **Human-in-the-Loop manager-approval interrupts** for out-of-policy bookings.

### SP05 — Native Policy RAG MCP Server & FinOps Sandbox MCP Server
`docs/subprojects/sp05_policy_rag_and_finops_mcp_servers/`
Build `policy_mcp_server` with **pgvector + BM25 hybrid retrieval and cross-encoder reranking**; build `finops_mcp_server` with **isolated Python sandbox execution** for multi-currency per-diem and GST calculations and chart generation.

### SP06 — Dynamic Model Router, Egress Validation, Observability & Evals
`docs/subprojects/sp06_model_router_evals_and_observability/`
**Cost-aware model switching with fallbacks**; context compaction; a **deterministic price/flight-ID groundedness verifier**; **OpenTelemetry + Langfuse** tracing; a **50-case golden dataset** run with Ragas/DeepEval that **gates CI**.

### Dependency order

```
SP00 -> SP01 -> SP02 -> SP03 -> SP04 -> SP05 -> SP06
 base    infra   data    transport  agents   new      quality
                         + security          servers  + cost
```

SP05's servers can begin in parallel with SP04 once SP03's HTTP transport pattern exists; SP06 requires everything before it to evaluate end to end.

---

## 6. Cross-Cutting Requirements

| Area | Requirement |
|---|---|
| **Security** | No secrets in the repo; secrets via environment/secret manager; least-privilege service accounts; the finops sandbox has no network and no secrets. |
| **Cost** | Every LLM call is attributable (per request, per model); early rejection and routing must demonstrably reduce average cost per request. |
| **Latency** | Persistent MCP connections replace per-request process spawn; independent steps continue to run in parallel. |
| **Concurrency** | Inventory changes are transactional and lock-protected; writes are idempotent. |
| **Testability** | Mock LLM mode is retained so the full suite runs offline and deterministically. |
| **Documentation** | Every task ships its PRD; architecture diagrams in README stay in sync. |

## 7. Risks & Open Questions

| Risk | Mitigation |
|---|---|
| MCP SDK 2.x is new; APIs may shift between minor releases (middleware APIs are marked provisional) | Pin a tested version range in CI; isolate SDK usage behind thin server modules |
| Sandbox provider lock-in (E2B vs Docker) | Define a small sandbox interface in SP05; support both |
| LLM-based evals are noisy | Use deterministic checks wherever possible (egress validator); use LLM judges only for fuzzy criteria; fixed golden set with tolerances |
| Cloud free-tier limits (Neon, Upstash, Cloud Run) | Track usage in SP01; keep Compose parity so work never depends on cloud availability |

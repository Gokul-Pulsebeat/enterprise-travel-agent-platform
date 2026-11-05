# EPIC SP03 — Stateless Streamable HTTP MCP Layer, Auth & Security Guardrails

**Status:** Placeholder — detailed task PRDs to be written when the epic starts
**Depends on:** SP02
**Master PRD:** [`../../00_MASTER_PRD.md`](../../00_MASTER_PRD.md)

## Goal
Replace per-request `stdio` subprocesses with network-addressable, horizontally scalable MCP services, and put a security boundary around the agent.

## Planned Tasks
| Task | Summary |
|---|---|
| TASK-3.1 | **Streamable HTTP transport**: run each MCP server as a stateless HTTP service; agent connects as a long-lived client |
| TASK-3.2 | **JWT identity propagation** from the client through the agent to every MCP tool call and backing API |
| TASK-3.3 | **Redis rate limiting** per user and per tool, with budget caps |
| TASK-3.4 | **PII redaction** on ingress and in logs/traces |
| TASK-3.5 | **Fast SLM intent router** at ingress to reject off-domain or hostile requests before any expensive model runs |
| TASK-3.6 | **Indirect prompt-injection defense** on tool outputs before they reach any model |

## Exit Criteria
- Any replica of any MCP server can serve any request; no per-session server state.
- Unauthenticated and over-limit requests are rejected with correct status codes.
- A red-team suite of injection prompts, including injections embedded in tool data, does not change agent behavior.

## Key Risks
MCP SDK 2.x transport and middleware APIs are new; false positives from the router and injection filters; added latency from guardrail hops.

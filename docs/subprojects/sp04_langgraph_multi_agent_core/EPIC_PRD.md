# EPIC SP04 — LangGraph Multi-Agent Architecture & HITL Workflows

**Status:** Placeholder — detailed task PRDs to be written when the epic starts
**Depends on:** SP03
**Master PRD:** [`../../00_MASTER_PRD.md`](../../00_MASTER_PRD.md)

## Goal

Replace the hand-written planner loop with a durable, typed, multi-agent graph that can pause for human approval.

## Planned Tasks

| Task     | Summary                                                                                                                               |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| TASK-4.1 | **Typed LangGraph state machine** replacing the custom DAG loop, preserving parallel execution and dependency semantics               |
| TASK-4.2 | **Postgres checkpointer** so runs survive crashes and can resume                                                                      |
| TASK-4.3 | **Supervisor plus three sub-agents** (Booking, Compliance, FinOps), each scoped to specific MCP servers to prevent tool-context bloat |
| TASK-4.4 | **Pydantic structured outputs** for plans and agent hand-offs, replacing free-form JSON parsing                                       |
| TASK-4.5 | **HITL manager-approval interrupts** for out-of-policy bookings, with approve/reject resume paths                                     |

## Exit Criteria

- Killing the process mid-run and restarting resumes from the last checkpoint.
- Each sub-agent can see only its own MCP tools.
- An out-of-policy booking halts for approval and completes or aborts correctly on the manager's decision.

## Key Risks

Framework lock-in; checkpoint schema evolution; keeping mock mode working for offline tests.

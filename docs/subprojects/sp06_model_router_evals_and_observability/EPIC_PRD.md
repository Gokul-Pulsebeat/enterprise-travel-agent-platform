# EPIC SP06 — Dynamic Model Router, Egress Validation, Observability & Evals

**Status:** Placeholder — detailed task PRDs to be written when the epic starts
**Depends on:** SP04, SP05
**Master PRD:** [`../../00_MASTER_PRD.md`](../../00_MASTER_PRD.md)

## Goal
Make the system cheap to run, hard to make lie, visible in production, and protected against regressions by a measurable quality gate.

## Planned Tasks
| Task | Summary |
|---|---|
| TASK-6.1 | **Cost-aware model router** that picks a model per task and falls back on failure or timeout |
| TASK-6.2 | **Context compaction** to keep long conversations within budget without losing booking-critical facts |
| TASK-6.3 | **Deterministic egress groundedness verifier** that checks every price, flight ID, and date in an answer against tool results before it is returned |
| TASK-6.4 | **OpenTelemetry + Langfuse tracing** across ingress, agents, MCP calls, and egress, with per-request token and cost metrics |
| TASK-6.5 | **50-case golden dataset** evaluated with Ragas/DeepEval, wired in as a **CI gate** with agreed score thresholds |

## Exit Criteria
- Average cost per request drops measurably versus a single-model baseline.
- Answers containing figures not present in tool results are blocked or corrected.
- Every request produces a complete trace.
- A PR that regresses the golden-set score below threshold fails CI.

## Key Risks
LLM-judge noise in evals (mitigated by preferring deterministic checks); trace volume and cost; golden-set drift as the product evolves.

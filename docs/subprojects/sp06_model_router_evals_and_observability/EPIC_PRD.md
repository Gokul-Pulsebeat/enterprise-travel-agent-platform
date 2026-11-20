# EPIC SP06 — Dynamic Model Router, Egress Validation, Observability & Evals

**Status:** Placeholder — detailed task PRDs to be written when the epic starts
**Depends on:** SP04, SP05
**Master PRD:** [`../../00_MASTER_PRD.md`](../../00_MASTER_PRD.md)

## Goal

Make the system cheap to run, hard to make lie, visible in production, and protected against regressions by a measurable quality gate.

> **Scope note (observability).** Logging, metrics, tracing and alerting for the **business APIs** are delivered earlier, as SP00 platform tasks ([`TASK-0.4`](../sp00_platform_and_dx/TASK-0.4_api_logging_foundation.md) and [`TASK-0.5`](../sp00_platform_and_dx/TASK-0.5_api_metrics_traces_and_free_alerting.md)), because the APIs need to be observable before bookings go live. SP06 builds the **AI-specific layer on top of that pipeline** and does not rebuild it: it reuses the structured-logging setup, the OpenTelemetry tracer and the free-alerting approach (including its strict $0 constraint and the cost pitfalls recorded there).

## Planned Tasks

| Task     | Summary                                                                                                                                                                                                                                                                                                        |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TASK-6.1 | **Cost-aware model router** that picks a model per task and falls back on failure or timeout                                                                                                                                                                                                                   |
| TASK-6.2 | **Context compaction** to keep long conversations within budget without losing booking-critical facts                                                                                                                                                                                                          |
| TASK-6.3 | **Deterministic egress groundedness verifier** that checks every price, flight ID, and date in an answer against tool results before it is returned                                                                                                                                                            |
| TASK-6.4 | **Agent and LLM observability** on top of the SP00 pipeline: **Langfuse** traces across ingress, agents, MCP calls, and egress, trace-context propagation from the agent through the MCP HTTP layer into the APIs (so one trace spans the whole request), and per-request token, cost and model-choice metrics |
| TASK-6.5 | **50-case golden dataset** evaluated with Ragas/DeepEval, wired in as a **CI gate** with agreed score thresholds                                                                                                                                                                                               |

## Exit Criteria

- Average cost per request drops measurably versus a single-model baseline.
- Answers containing figures not present in tool results are blocked or corrected.
- Every request produces a complete trace, from the agent through the MCP layer to the API and database.
- A PR that regresses the golden-set score below threshold fails CI.

## Key Risks

LLM-judge noise in evals (mitigated by preferring deterministic checks); trace volume and cost (SP00's free-tier budgets and cost guardrails apply, and LLM telemetry must not push the project out of the free tiers); golden-set drift as the product evolves.

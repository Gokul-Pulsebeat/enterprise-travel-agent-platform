# EPIC SP05 — Native Policy RAG MCP Server & FinOps Sandbox MCP Server

**Status:** Placeholder — detailed task PRDs to be written when the epic starts
**Depends on:** SP03 (transport pattern); integrates with SP04 sub-agents
**Master PRD:** [`../../00_MASTER_PRD.md`](../../00_MASTER_PRD.md)

## Goal

Add the two native MCP servers that give the platform its policy-compliance and expense-math capabilities. Neither sits behind a REST API.

## Planned Tasks

| Task     | Summary                                                                                                                            |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| TASK-5.1 | **`policy_mcp_server` foundation**: Postgres schema for policy documents, employee role tiers, and manager-approval requests       |
| TASK-5.2 | **Hybrid retrieval**: `pgvector` semantic search plus BM25 keyword search, fused into one ranked list                              |
| TASK-5.3 | **Cross-encoder reranking** of retrieved policy chunks, with citations back to the source document                                 |
| TASK-5.4 | **`finops_mcp_server` sandbox**: isolated Python execution (E2B or Docker) with no network, no secrets, and CPU/memory/time limits |
| TASK-5.5 | **FinOps tools**: multi-currency per-diem math, GST calculations, and cost-chart generation                                        |

## Exit Criteria

- Policy answers cite the retrieved policy text and respect the employee's role tier.
- Sandboxed code cannot reach the network, read secrets, or exceed its resource limits.
- Per-diem and GST results match a reference calculation on a fixed test set.

## Key Risks

Retrieval quality on real policy documents; sandbox provider lock-in (mitigated by a small sandbox interface); sandbox cold-start latency.

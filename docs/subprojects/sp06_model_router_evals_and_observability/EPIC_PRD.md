# EPIC SP06 — Dynamic Model Router, Egress Validation, Observability, Evals & AI-BOM

**Status:** Placeholder — detailed task PRDs to be written when the epic starts (security scope expanded by the [threat model](../../02_AI_AND_MCP_SECURITY_THREAT_MODEL.md))
**Depends on:** SP04, SP05
**Master PRD:** [`../../00_MASTER_PRD.md`](../../00_MASTER_PRD.md)

## Goal

Make the system cheap to run, hard to make lie, visible in production, protected against regressions by a measurable quality gate, and fully inventoried: every model, prompt, tool and dataset it relies on is known and checked.

> **Scope note (observability).** Logging, metrics, tracing and alerting for the **business APIs** are delivered earlier, as SP00 platform tasks ([`TASK-0.4`](../sp00_platform_and_dx/TASK-0.4_api_logging_foundation.md) and [`TASK-0.5`](../sp00_platform_and_dx/TASK-0.5_api_metrics_traces_and_free_alerting.md)), because the APIs need to be observable before bookings go live. SP06 builds the **AI-specific layer on top of that pipeline** and does not rebuild it: it reuses the structured-logging setup, the OpenTelemetry tracer and the free-alerting approach (including its strict $0 constraint and the cost pitfalls recorded there).

> **Standing constraint: nothing may cost money.** Two items in this epic need explicit care. The **model router** is "cost-aware" in the sense of staying inside free quotas (local models, free-tier providers), not of optimizing a bill. The **golden-set gate** must not depend on paid LLM-as-judge calls: gating checks are deterministic and run against the mock provider; model-judged metrics (Ragas, DeepEval) run only with local models and are advisory (see TASK-6.5 and TASK-6.7).

## Planned Tasks

| Task     | Summary                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TASK-6.1 | **Quota-aware model router** that picks a model per task and falls back on failure, timeout or an exhausted free quota; candidates are local models and free-tier providers only. Circuit breakers stop cascading failures (ASI08)                                                                                                                                                                                                                                                          |
| TASK-6.2 | **Context compaction** to keep long conversations within budget without losing booking-critical facts                                                                                                                                                                                                                                                                                                                                                                                       |
| TASK-6.3 | **Deterministic egress groundedness verifier** that checks every price, flight ID, and date in an answer against tool results before it is returned (C-15, LLM07)                                                                                                                                                                                                                                                                                                                           |
| TASK-6.4 | **Agent and LLM observability** on top of the SP00 pipeline: **Langfuse** traces (free tier or self-hosted) across ingress, agents, MCP calls, and egress, trace-context propagation from the agent through the MCP HTTP layer into the APIs (so one trace spans the whole request), and per-request token and model-choice metrics                                                                                                                                                         |
| TASK-6.5 | **50-case golden dataset** wired in as a **CI gate**. The gating assertions are **deterministic** (structural and exact checks against the mock provider); Ragas or DeepEval model-judged scores run with a **local model** and are advisory, because a hosted judge would cost money and is non-deterministic                                                                                                                                                                              |
| TASK-6.6 | **AI-BOM**, new: generate, validate and drift-check a CycloneDX AI bill of materials in CI (design below)                                                                                                                                                                                                                                                                                                                                                                                   |
| TASK-6.7 | **Adversarial evaluation, hidden-context and consumption controls**, new: open-source red-team scanners run against the agent with **local models** (reported, never gating); a **deterministic gating subset** of hostile prompts; **hidden-context exposure tests** (prompts hold no secrets, extraction attempts fail) (C-16, LLM08); **budgets and quotas** per user, day and run with token and spend caps (C-12, LLM06); **egress DLP** and safe output handling (C-15, LLM02, LLM10) |

## AI-BOM Design

**Decision on placement.** SP06 is the right epic for the **generator and the CI gate**: it is where model routing, prompts and evaluation are finalized, so the inventory is stable enough to check. Three refinements make it work:

1. **Use a standard format, not an ad hoc file.** The AI-BOM is a **CycloneDX** document. CycloneDX has first-class types for machine-learning models and datasets (with model-card fields) and a `service` type that fits hosted model APIs and MCP servers. Using the same format as the SBOM ([`TASK-0.6`](../sp00_platform_and_dx/TASK-0.6_sbom_generation_and_validation.md)) means one set of validators covers both, and the two can be merged into one release inventory. Emerging AI-SBOM minimum-element guidance is aligned with when it stabilizes. The output is `aibom.cdx.json`.
2. **Start the inventory early.** SP03 TASK-3.7 creates `docs/security/ai-inventory.yaml` listing every MCP server and its tool-manifest hash. SP04 adds the agents, model providers and prompts; SP05 adds the embedding and reranker models and the policy corpus manifest. SP06 does not retrofit; it turns a maintained inventory into a validated document.
3. **Enforce, do not rely on remembering.** "Update the file whenever routing changes" will be forgotten. A CI **drift check** fails the build if the code or configuration references a model, provider, tool or prompt that the inventory does not list.

**What it records**

| Component type                | Examples                                                                       | Recorded                                                                                                 |
| ----------------------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| Models (hosted or local)      | The providers and model identifiers the router can choose, local model weights | Provider, identifier or version, license and terms, purpose, a digest for local weights                  |
| Embedding and reranker models | The retrieval models in `policy_mcp_server`                                    | Name, version, source, license, hash                                                                     |
| Prompts and templates         | Supervisor and sub-agent prompts, router prompts                               | Path, version, content hash (not secrets; prompts hold none by rule C-16)                                |
| Tools and MCP servers         | `flight`, `hotel`, `policy`, `finops`                                          | A `service` entry with endpoint (non-secret), scopes, state-changing flag, owner, **tool-manifest hash** |
| Datasets                      | The policy corpus, the golden set, the red-team set                            | Hash manifest, source, whether it contains personal data                                                 |
| Guardrail components          | Intent-router model, injection screen, groundedness verifier                   | Version and thresholds                                                                                   |
| Frameworks and SDKs           | LangGraph, MCP SDK                                                             | Cross-referenced to the SBOM, not duplicated                                                             |

**Pipeline.** Generate from the inventory plus introspection (model identifiers in configuration, the tool-manifest lock, prompt files, dataset manifests); validate with the CycloneDX schema tooling; run the completeness and drift checks; upload as an artifact on every CI run. No secrets or credentials are ever written to it. It is free: the tooling is open source and runs in CI.

## Exit Criteria

- A weaker or free model is chosen for simple tasks, with fallback on failure or quota exhaustion, and no provider outside the free allowance is called.
- Answers containing figures not present in tool results are blocked or corrected.
- Every request produces a complete trace, from the agent through the MCP layer to the API and database.
- A PR that regresses the deterministic golden-set checks fails CI.
- `aibom.cdx.json` is generated, schema-valid and drift-checked on every CI run; adding a model, provider, tool or prompt without updating the inventory fails the build.
- The deterministic adversarial subset passes in CI; red-team scanner results are tracked over time.
- Per-user, per-day and per-run budgets are enforced; hidden-context extraction attempts do not reveal secrets.
- No paid service is used in CI or at runtime.

## Key Risks

LLM-judge noise and cost in evals (mitigated by gating on deterministic checks and running judges only locally); trace volume and cost (SP00's free-tier budgets and cost guardrails apply, and LLM telemetry must not push the project out of the free tiers); golden-set drift as the product evolves; an inventory that falls behind the code (mitigated by the drift check); free-tier provider terms change (mitigated by the router's quota awareness and local-model fallback).

# EPIC SP00 — Platform, DX & Repo Standardization

**Status:** Continuous track (no end date) — TASK-0.1 and TASK-0.2 complete; TASK-0.3 to TASK-0.6 fully specified (implementation deferred)
**Depends on:** none
**Master PRD:** [`../../00_MASTER_PRD.md`](../../00_MASTER_PRD.md)

## Goal

SP00 is the umbrella for **platform, developer-experience (DX) and repository-standardization work**, plus ad-hoc infrastructure chores that no single feature epic owns. Unlike SP01–SP06, which are delivered in a linear sequence, SP00 is a **continuous track that runs alongside them**: a chore can land at any point, on its own short-lived branch, without waiting for or blocking a feature epic.

It started as the one-off "foundation" epic (naming symmetry, MCP 2.x, baseline tests, dependency locking). It now also holds the tooling and housekeeping that keep every later epic fast and safe to change.

## What Belongs in SP00

| Belongs here                                                             | Belongs in a feature epic (SP01–SP06) instead                |
| ------------------------------------------------------------------------ | ------------------------------------------------------------ |
| Repository layout, naming conventions, documentation structure           | New product behavior (bookings, auth, agents, RAG, ...)      |
| Developer tooling: linters, formatters, pre-commit, scripts, local setup | Infrastructure that delivers a specific epic's capability    |
| Dependency management and lockfile tooling                               | Application dependencies added to implement a feature        |
| Cross-cutting CI hygiene (workflow linting, check enforcement)           | Epic-specific pipeline stages (for example eval gates, SP06) |
| Ad-hoc chores and clean-ups surfaced while working on any epic           |                                                              |

Cross-cutting **runtime** concerns that apply to every service (structured logging, metrics, tracing and free alerting) also belong here: they are platform foundations rather than features of one epic. They are built once, early, and each feature epic then adds its own events and metrics through the SP00 helpers as part of its acceptance criteria. SP06 keeps only the AI-specific layer (LLM cost, latency, evals) on top of the same pipeline. Supply-chain security (the SBOM, TASK-0.6) is likewise a platform foundation, and the project-wide [AI and MCP security threat model](../../02_AI_AND_MCP_SECURITY_THREAT_MODEL.md) maps each control to the task that delivers it.

## Conventions

- **Tasks** are numbered `TASK-0.N` and each has its own PRD in this folder, with the same structure as the SP01 task PRDs (objective, scope, architectural notes, acceptance criteria, verification commands, rollout, risks).
- **Branches** are named `chore/sp00-tNN-<slug>` for tooling and housekeeping (or `feat/sp00-...` when a change adds behavior), and target `productionize` through a normal PR.
- **Definition of done** is the Master PRD's: task PRD linked from the PR, tests where behavior changes, CI green, PR template completed, affected docs updated in the same PR.

## Tasks

| Task     | PRD                                                                                                    | Status                              | Summary                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| -------- | ------------------------------------------------------------------------------------------------------ | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TASK-0.1 | [`TASK-0.1_naming_tests_and_dependency_locking.md`](TASK-0.1_naming_tests_and_dependency_locking.md)   | Complete                            | **Naming symmetry, MCP 2.x, baseline tests, dependency locking:** `flight_mcp_server` / `hotel_mcp_server` symmetry, `MCPServer` (MCP SDK 2.x), `pytest` suite with an HTML report, `pip-tools` lockfile, Master PRD hierarchy and the pull request template                                                                                                                                                                                                                                |
| TASK-0.2 | [`TASK-0.2_dx_tooling.md`](TASK-0.2_dx_tooling.md)                                                     | Complete                            | **DX tooling:** `pre-commit` hooks (Ruff lint and format, Prettier for YAML/JSON/Markdown, Terraform fmt and validate, actionlint) plus dedicated Format check (Ruff & Prettier) and actionlint jobs in CI; SP00 reorganized as a continuous platform track                                                                                                                                                                                                                                 |
| TASK-0.3 | [`TASK-0.3_code_coverage.md`](TASK-0.3_code_coverage.md)                                               | Specified (implementation deferred) | **Code coverage:** `pytest-cov` with branch coverage configured for greenlets, a ratcheting `fail_under` threshold set from a measured baseline (legacy `agent/` reported but not gated), coverage reports as CI artifacts and in the job summary, light in-process tests for MCP tool functions, and an optional phase for API-process and changed-lines coverage; the stdio MCP subprocesses are deliberately not measured because SP03 replaces them with HTTP services; no paid service |
| TASK-0.4 | [`TASK-0.4_api_logging_foundation.md`](TASK-0.4_api_logging_foundation.md)                             | Specified (implementation deferred) | **API logging foundation:** `structlog` with Cloud Logging JSON (severity, trace correlation, `serviceContext` for Error Reporting), a pure ASGI request-correlation middleware, a stdlib bridge for uvicorn, SQLAlchemy and Alembic, lifecycle, slow-query and readiness events, hard redaction rules and a sentinel-secret test; zero cost, no new infrastructure                                                                                                                         |
| TASK-0.5 | [`TASK-0.5_api_metrics_traces_and_free_alerting.md`](TASK-0.5_api_metrics_traces_and_free_alerting.md) | Specified (implementation deferred) | **API metrics, traces and free alerting:** OpenTelemetry to Cloud Trace and (through the Google exporter, not OTLP) Cloud Monitoring custom metrics within the free tiers, a Terraform dashboard, and a strictly $0 alerting set (Error Reporting notifications, uptime-check alerts, a billing budget alert, an optional GitHub probe) with exact setup steps; chargeable log and metric alert policies documented but off by default                                                      |
| TASK-0.6 | [`TASK-0.6_sbom_generation_and_validation.md`](TASK-0.6_sbom_generation_and_validation.md)             | Specified (implementation deferred) | **SBOM generation and validation:** CycloneDX SBOMs for the pinned dependencies (every CI run) and for each container image (CD, and CI when Dockerfiles or dependencies change), validated for schema, lockfile completeness and NTIA minimum elements, then used to gate fixable High or Critical vulnerabilities and denied licenses, with expiring exceptions; signed attestations only for public repositories; all open-source tooling, $0                                            |

> **Planned order.** TASK-0.4 and then TASK-0.5 are scheduled **after SP02 TASK-2.2 and before TASK-2.3**, so booking locks, retries and notifications are observable from their first release. TASK-0.3 can land at any time; TASK-0.6 (SBOM) can land at any time, ideally before SP03 when the dependency footprint grows.

## Candidate Backlog (not committed)

Ideas that fit this track and may become `TASK-0.N` tickets when they are worth the effort:

- Split runtime and development requirements so the Docker images stop installing test and lint tools.
- Automated dependency and hook-version updates (Dependabot or Renovate) for pip, GitHub Actions and pre-commit revisions. Needs care: the lockfile is compiled in a Linux container and checked for parity, so a bot must run the same compile step or propose changes to `requirements.in`.
- Secret scanning of the repository and its history (an open-source scanner in CI and as a pre-commit hook).
- Static analysis for Python security issues (open-source SAST) and security scanning of the Terraform configuration and Dockerfiles.
- Pinning GitHub Actions to commit SHAs, with an automated check.
- A `.git-blame-ignore-revs` file so large formatting commits do not obscure `git blame`.

## Exit Criteria

SP00 has no epic-level exit: it is a standing track. Each task is complete when its own acceptance criteria pass.

## Key Risks

Scope creep into feature work (mitigated by the inclusion table above); local tooling drifting from what CI enforces (mitigated by keeping versions in sync and enforcing format checks in CI via pre-commit); chores accumulating without a ticket (mitigated by requiring a task PRD for every change).

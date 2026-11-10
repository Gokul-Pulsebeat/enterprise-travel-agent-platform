# EPIC SP00 — Platform, DX & Repo Standardization

**Status:** Continuous track (no end date) — TASK-0.1 complete, TASK-0.2 in complete
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

## Conventions

- **Tasks** are numbered `TASK-0.N` and each has its own PRD in this folder, with the same structure as the SP01 task PRDs (objective, scope, architectural notes, acceptance criteria, verification commands, rollout, risks).
- **Branches** are named `chore/sp00-tNN-<slug>` for tooling and housekeeping (or `feat/sp00-...` when a change adds behavior), and target `productionize` through a normal PR.
- **Definition of done** is the Master PRD's: task PRD linked from the PR, tests where behavior changes, CI green, PR template completed, affected docs updated in the same PR.

## Tasks

| Task     | PRD                                                                                                  | Status      | Summary                                                                                                                                                                                                                                                      |
| -------- | ---------------------------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| TASK-0.1 | [`TASK-0.1_naming_tests_and_dependency_locking.md`](TASK-0.1_naming_tests_and_dependency_locking.md) | Complete    | **Naming symmetry, MCP 2.x, baseline tests, dependency locking:** `flight_mcp_server` / `hotel_mcp_server` symmetry, `MCPServer` (MCP SDK 2.x), `pytest` suite with an HTML report, `pip-tools` lockfile, Master PRD hierarchy and the pull request template |
| TASK-0.2 | [`TASK-0.2_dx_tooling.md`](TASK-0.2_dx_tooling.md)                                                   | In progress | **DX tooling:** `pre-commit` hooks (Ruff lint and format, Prettier for YAML/JSON/Markdown, Terraform fmt and validate, actionlint) plus dedicated Format check (Ruff & Prettier) and actionlint jobs in CI; SP00 reorganized as a continuous platform track  |

## Candidate Backlog (not committed)

Ideas that fit this track and may become `TASK-0.N` tickets when they are worth the effort:

- Split runtime and development requirements so the Docker images stop installing test and lint tools.
- Automated dependency and hook-version updates (Dependabot or Renovate) for pip, GitHub Actions and pre-commit revisions.
- A `.git-blame-ignore-revs` file so large formatting commits do not obscure `git blame`.

## Exit Criteria

SP00 has no epic-level exit: it is a standing track. Each task is complete when its own acceptance criteria pass.

## Key Risks

Scope creep into feature work (mitigated by the inclusion table above); local tooling drifting from what CI enforces (mitigated by keeping versions in sync and enforcing format checks in CI via pre-commit); chores accumulating without a ticket (mitigated by requiring a task PRD for every change).

# EPIC SP01 — CI/CD Pipelines, Dockerization & Serverless Terraform IaC

**Status:** In Progress (Phase 1: CI & Dockerization)
**Depends on:** SP00
**Master PRD:** [`../../00_MASTER_PRD.md`](../../00_MASTER_PRD.md)

## Goal

Make every change automatically verified and every merge to `productionize` automatically deployable, with a local environment that matches production.

## Delivery Plan: Two Pull Requests

SP01 ships as two PRs so that the developer-facing foundation (CI, images, local stack) is reviewed and merged before the cloud infrastructure that builds on it.

### PR 1 — `feat/sp01-cicd-and-docker` (CI, Dockerization, local parity)

| Task     | PRD                                                                                  | Summary                                                                                                                                                                  |
| -------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| TASK-1.1 | [`TASK-1.1_github_actions_ci.md`](TASK-1.1_github_actions_ci.md)                     | **GitHub Actions CI** on every PR and push to `productionize`/`main`: verify lockfile parity, install from the lockfile, `ruff check .`, start both APIs, run the full `pytest` suite, upload the report |
| TASK-1.2 | [`TASK-1.2_service_dockerization.md`](TASK-1.2_service_dockerization.md)             | **Dockerization**: one non-root image each for `flight_api`, `hotel_api` and the `agent` (which also contains both MCP servers), with pinned dependencies                |
| TASK-1.3 | [`TASK-1.3_docker_compose_local_stack.md`](TASK-1.3_docker_compose_local_stack.md)   | **Docker Compose** local parity stack: Postgres (pgvector), Redis, both APIs and an agent smoke test, started with one command                                           |

> **Architectural note (TASK-1.2): why the MCP servers live inside the `agent` image.**
> The MCP servers currently use the `stdio` transport: the agent launches each one as a **child process** (`sys.executable <server>.py`) and talks to it over stdin/stdout. A child process must live on the same filesystem as its parent, so in SP01 `flight_mcp_server/` and `hotel_mcp_server/` are packaged **inside the `agent` image**, and there are only three application images, not five. The REST APIs remain separate containers because the MCP servers reach them over HTTP.
> In **SP03** the MCP servers move to stateless Streamable HTTP and are split into standalone containers behind their own endpoints; at that point each gets its own Dockerfile and the agent image drops them.
> One consequence is handled in SP01: `stdio_client` only passes a small allowlist of environment variables (`PATH`, `HOME`, ...) to child processes, so the agent explicitly forwards `FLIGHT_API_BASE_URL` and `HOTEL_API_BASE_URL` to the servers it spawns.

> **Lockfile tooling (TASK-1.1).** `requirements.txt` is produced by `pip-compile`, which resolves dependencies for the *host* platform, so a lockfile compiled on Windows can differ from one compiled on Linux (for example Windows-only dependencies such as `colorama`), while CI and the Docker images run Linux. `scripts/compile-requirements.ps1` and `.sh` therefore run `pip-compile` inside a `python:3.11-slim` container, the same base as the images. A **Verify lockfile parity** step in CI recompiles on Linux and fails the build if the committed pins differ, so a host-compiled lockfile is caught immediately. Windows developers install the Linux lockfile plus `requirements-windows.txt` (hand-maintained pins for Windows-only packages such as `pywin32`) with `scripts/sync-dev.ps1`; CI and Docker never read that file.

### PR 2 — `feat/sp01-terraform-and-cd` (cloud infrastructure and delivery)

| Task     | PRD | Summary                                                                                                              |
| -------- | --- | -------------------------------------------------------------------------------------------------------------------- |
| TASK-1.4 | TBD | **Terraform IaC** for GCP Cloud Run, Neon Postgres, and Upstash Redis; secrets via a secret manager                   |
| TASK-1.5 | TBD | **Auto-deploy on merge to `productionize`** with a health-check gate and rollback path                                |

PR 2 starts after PR 1 is merged. Its task PRDs are written when that branch starts.

## Exit Criteria

- A PR cannot merge unless CI is green. *(CI workflow in PR 1; enabling "required status check" on `productionize` and `main` is a manual GitHub repository setting.)*
- `docker compose up` yields a working stack from a clean checkout. *(PR 1)*
- `terraform plan` is clean and a merge to `productionize` deploys without manual steps. *(PR 2)*

## Key Risks

Cloud free-tier limits; secret handling in CI; keeping Compose and Cloud Run behavior aligned; a lockfile compiled on one OS being installed on another (mitigated by compiling in a Linux container via `scripts/compile-requirements.*` and enforced by CI's lockfile-parity check).

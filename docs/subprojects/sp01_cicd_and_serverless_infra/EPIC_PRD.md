# EPIC SP01 — CI/CD Pipelines, Dockerization & Serverless Terraform IaC

**Status:** In Progress (Phase 2: Terraform & CD) — Phase 1 (CI & Dockerization) merged
**Depends on:** SP00
**Master PRD:** [`../../00_MASTER_PRD.md`](../../00_MASTER_PRD.md)

## Goal

Make every change automatically verified and every merge to `productionize` automatically deployable, with a local environment that matches production.

## Delivery Plan: Two Pull Requests

SP01 ships as two PRs so that the developer-facing foundation (CI, images, local stack) is reviewed and merged before the cloud infrastructure that builds on it.

### PR 1 — `feat/sp01-cicd-and-docker` (CI, Dockerization, local parity) — merged

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

| Task     | PRD                                                                    | Summary                                                                                                                                                                                  |
| -------- | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TASK-1.4 | [`TASK-1.4_terraform_iac.md`](TASK-1.4_terraform_iac.md)               | **Terraform IaC** (`infra/terraform/`): Artifact Registry, two Cloud Run services, Secret Manager, least-privilege service accounts, Workload Identity Federation for GitHub Actions, and Neon Postgres + Upstash Redis wired in through Secret Manager. `fmt`/`validate` enforced in CI |
| TASK-1.5 | [`TASK-1.5_cd_pipeline.md`](TASK-1.5_cd_pipeline.md)                   | **Auto-deploy on merge to `productionize`** (`.github/workflows/cd.yml`): keyless WIF auth, build and push SHA-tagged images, deploy to Cloud Run, `/health` gate, automatic rollback of both services on failure, and a rollback drill |

> **Architectural note (TASK-1.4 / 1.5): who owns what.**
> Terraform creates the Cloud Run services with a **placeholder image** and then **ignores** the image, revision name and traffic routing, which the CD pipeline owns from the first deploy on. Infrastructure is applied manually from a trusted machine; the pipeline only ships application images, so it needs no infrastructure-changing permissions. Its service account is limited to pushing to one registry and updating two services, and it is reachable only through Workload Identity Federation from this repository's `productionize` branch. No long-lived credential exists anywhere.
> Rollbacks pin traffic to an old revision, which Cloud Run does not undo on its own, so every deploy explicitly routes traffic to the newest revision, and each run uses a unique revision name so a re-run or a drill always creates a real revision.

> **Free-tier posture.** Cloud Run scales to zero and is capped at two instances, Artifact Registry cleanup policies bound storage, and Neon and Upstash run on their free plans. Neon and Upstash can be disabled independently with `enable_neon` / `enable_upstash`.

## Exit Criteria

- A PR cannot merge unless CI is green. *(CI workflow in PR 1; enabling "required status check" on `productionize` and `main` for `Lint & Test` and `Terraform fmt & validate` is a manual GitHub repository setting.)*
- `docker compose up` yields a working stack from a clean checkout. *(PR 1)*
- `terraform plan` is clean and a merge to `productionize` deploys without manual steps, verifies health, and rolls back automatically on failure. *(PR 2; the rollback drill demonstrates it.)*

## Key Risks

Cloud free-tier limits; secret handling in CI and in Terraform state; keeping Compose and Cloud Run behavior aligned; a lockfile compiled on one OS being installed on another (mitigated by compiling in a Linux container via `scripts/compile-requirements.*` and enforced by CI's lockfile-parity check, and for Terraform by a multi-platform `.terraform.lock.hcl`); community Terraform providers for Neon and Upstash changing between releases (caught by `terraform validate`); CD running in parallel with CI on `productionize` (mitigated by requiring CI on PRs and forbidding direct pushes).

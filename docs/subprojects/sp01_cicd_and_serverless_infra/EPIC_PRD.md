# EPIC SP01 — CI/CD Pipelines, Dockerization & Serverless Terraform IaC

**Status:** Placeholder — detailed task PRDs to be written when the epic starts
**Depends on:** SP00
**Master PRD:** [`../../00_MASTER_PRD.md`](../../00_MASTER_PRD.md)

## Goal
Make every change automatically verified and every merge to `productionize` automatically deployable, with a local environment that matches production.

## Planned Tasks
| Task | Summary |
|---|---|
| TASK-1.1 | **GitHub Actions CI** on every pull request: install dependencies, lint, run `pytest`, fail the PR on any error |
| TASK-1.2 | **Dockerization**: one image per service (`flight_api`, `hotel_api`, the MCP servers, the agent) with pinned dependencies and non-root users |
| TASK-1.3 | **Docker Compose** stack for local parity: all services plus Postgres and Redis, one command to start |
| TASK-1.4 | **Terraform IaC** for GCP Cloud Run, Neon Postgres, and Upstash Redis; secrets via a secret manager |
| TASK-1.5 | **Auto-deploy on merge to `productionize`** with a health-check gate and rollback path |

## Exit Criteria
- A PR cannot merge unless CI is green.
- `docker compose up` yields a working stack from a clean checkout.
- `terraform plan` is clean and a merge to `productionize` deploys without manual steps.

## Key Risks
Cloud free-tier limits; secret handling in CI; keeping Compose and Cloud Run behavior aligned.

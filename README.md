# Enterprise Corporate Travel, Expense & Policy Compliance Platform

A production-grade, multi-agent enterprise platform demonstrating advanced orchestration using the **Model Context Protocol (MCP 2.x)**, LangGraph, and Serverless infrastructure.

Unlike standard tutorials, this repository is architected for real-world corporate scale. It transitions from a basic local proof-of-concept into a fully persistent, concurrent, and secure multi-domain system.

## 📖 Architecture & Roadmap

We utilize a **4-Server Multi-Domain MCP Tool Layer** to cleanly decouple domain logic from the AI orchestrator, preventing context bloat and ensuring strict security boundaries:

1. **Flight MCP** (Transactional API / Neon Postgres)
2. **Hotel MCP** (Transactional API / Neon Postgres)
3. **Policy MCP** (Native MCP / pgvector Hybrid RAG)
4. **FinOps MCP** (Native MCP / Python Execution Sandbox)

**👉 [Read the Master PRD & Engineering Roadmap](docs/00_MASTER_PRD.md) for the full target architecture and sub-project breakdown.**

## 📂 Project Folders (Current Phase: SP02)

```text
flight_api/          FastAPI REST service (Flight state & business logic)
flight_mcp_server/   MCP v2 server exposing flight logic as agent tools
hotel_api/           FastAPI REST service (Hotel state & business logic)
hotel_mcp_server/    MCP v2 server exposing hotel logic as agent tools
agent/               Agent orchestrator and dynamic MCP client
tests/               Baseline pytest suite (Unit & Integration)
scripts/             Helper scripts (containerized lockfile compilation)
docs/                Enterprise PRDs, Architecture docs, and task tracking
.github/             CI and CD workflows (GitHub Actions) and pull request template
infra/terraform/     Terraform for GCP Cloud Run, Artifact Registry, Secret Manager, WIF, Neon & Upstash
docker-compose.yml   Local parity stack (Postgres, Redis, both APIs, agent smoke test)
.env.example         Documented environment variables
```

Each runnable service (`flight_api/`, `hotel_api/`, `agent/`) contains its own `Dockerfile`. The `agent` image also bundles both MCP servers, because they currently run as `stdio` child processes of the agent (they become standalone HTTP services in SP03).

## ⚙️ Installation

This repository uses `pip-tools` for strict dependency locking. Ensure you have Python 3.11+ installed.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows (PowerShell)
# source .venv/bin/activate # macOS/Linux

# 2. Install dependencies from the lockfile
pip install pip-tools
.\scripts\sync-dev.ps1          # Windows (PowerShell)
# pip-sync requirements.txt     # macOS / Linux
```

**Why a separate step on Windows?** `requirements.txt` is compiled in a Linux container so it matches CI and the Docker images, which means it omits Windows-only packages (notably `pywin32`, which the MCP SDK needs on Windows). `scripts/sync-dev.ps1` runs `pip-sync requirements.txt requirements-windows.txt`, adding them back. Do not run `pip-sync requirements.txt` on its own on Windows: it uninstalls them.

### Enable pre-commit hooks

After syncing your virtual environment, install the Git hooks once per clone:

```powershell
pre-commit install
```

From then on, every `git commit` runs these hooks on the files you changed:

- **Ruff**: lint with auto-fix, and format, for Python
- **Prettier**: formats YAML, JSON and Markdown
- **Terraform**: `terraform fmt` and `terraform validate` on `infra/terraform/`
- **actionlint**: validates `.github/workflows/`

If a hook rewrites files (the formatters do), the commit is stopped so you can review the changes: `git add` them and commit again. To run every hook on the whole repository at any time:

```powershell
pre-commit run --all-files
```

The first run downloads tools (Node for Prettier, Go for actionlint) and takes a few minutes. The Terraform hooks need `terraform` on your `PATH` (`winget install Hashicorp.Terraform`).CI re-runs every check (`ruff check`, `ruff-format`, `prettier`, `terraform fmt`/`validate`, and `actionlint`), so skipping the hooks with `--no-verify` will still fail the pull request.

### Changing dependencies

Edit `requirements.in` (loose top-level dependencies), then re-lock **inside a Linux container** so `requirements.txt` matches CI and the Docker images. Running `pip-compile` directly on Windows produces a Windows-specific lockfile. These scripts require Docker.

```powershell
.\scripts\compile-requirements.ps1          # Windows (PowerShell)
```

```bash
bash scripts/compile-requirements.sh       # macOS / Linux / WSL
```

Commit both `requirements.in` and `requirements.txt`. The CI step **Verify lockfile parity** fails the build if `requirements.txt` was not compiled this way or is out of sync with `requirements.in`.

## 🐳 Run with Docker Compose

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine with the Compose plugin). No local Python setup is needed.

```bash
docker compose up --build --abort-on-container-exit --exit-code-from agent
```

This starts Postgres (pgvector) and Redis, builds and starts both REST APIs, waits until they are healthy, then runs the agent once in mock mode with _"Help me travel from Bangalore to Delhi on 2026-06-10 and stay there"_ and exits with the agent's exit code. Postgres and Redis are provisioned for later epics; the code does not use them yet.

Run your own prompt against the running stack, and clean up when finished:

```bash
docker compose up -d flight_api hotel_api
docker compose run --rm agent python agent/agent.py "Find hotels in Delhi"
docker compose down -v
```

_Compose reads a `.env` file automatically (copy `.env.example` to `.env` to change the Postgres defaults). The Python code does **not** load `.env`; when running locally, set variables such as `LLM_PROVIDER` in your shell as shown below._

## ☁️ Cloud Deployment (Terraform & CD)

The two REST APIs deploy to **GCP Cloud Run**. Infrastructure is defined in `infra/terraform/` and applied manually; every merge to `productionize` then ships new images automatically through `.github/workflows/cd.yml`.

```text
merge to productionize
  -> GitHub Actions authenticates to GCP via Workload Identity Federation (no JSON keys)
  -> build + push flight-api / hotel-api images to Artifact Registry, tagged with the commit SHA
  -> deploy to Cloud Run
  -> poll /health on both services (post-deploy gate)
  -> on failure: roll BOTH services back to the previous revisions automatically
```

**What Terraform provisions:** Artifact Registry, two Cloud Run services (scale-to-zero, capped at 2 instances), Secret Manager secrets, least-privilege service accounts, Workload Identity Federation limited to this repository's `productionize` branch, a Neon Postgres project and an Upstash Redis database (free tiers). Their connection strings are injected into the services as `DATABASE_URL` / `REDIS_URL` through Secret Manager; the applications do not use them until SP02+.

**One-time setup** (you need a GCP project with billing enabled, plus Neon and Upstash accounts; see [TASK-1.4](docs/subprojects/sp01_cicd_and_serverless_infra/TASK-1.4_terraform_iac.md) for details):

```powershell
gcloud auth application-default login
Copy-Item infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars   # set project_id and github_repository
$env:TF_VAR_neon_api_key    = "<neon-api-key>"        # credentials stay in the environment, never in a file
$env:TF_VAR_upstash_email   = "<upstash-email>"
$env:TF_VAR_upstash_api_key = "<upstash-api-key>"

terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan -out tfplan      # review before applying
terraform -chdir=infra/terraform apply tfplan
terraform -chdir=infra/terraform output github_actions_variables   # add these as GitHub repository variables
```

After the variables are set, the next push to `productionize` (or **Actions → CD → Run workflow**) performs the first deploy. The **Run workflow** form has a `rollback_drill` option that forces the health gate to fail so you can watch the automatic rollback work safely. Details and verification steps: [TASK-1.5](docs/subprojects/sp01_cicd_and_serverless_infra/TASK-1.5_cd_pipeline.md).

_Terraform state contains secrets: never commit it (it is gitignored) and prefer the remote GCS backend described in `infra/terraform/backend.tf.example` for anything shared. Commit `.terraform.lock.hcl`, generated for all platforms with `terraform providers lock`._

## 🚀 Run the Base Architecture

### 1. Start the Microservices

Terminal 1: Start the Flight API

```powershell
.\.venv\Scripts\activate
uvicorn flight_api.app:app --reload --port 8000
```

Terminal 2: Start the Hotel API

```powershell
.\.venv\Scripts\activate
uvicorn hotel_api.app:app --reload --port 8001
```

_(Optional) Test the REST endpoints directly:_

```bash
curl "http://127.0.0.1:8000/flights?origin=BLR&destination=DEL"
curl "http://127.0.0.1:8001/hotels?city=Delhi"
```

### 2. Run the Multi-Server Agent

Terminal 3: Execute the agent logic. The agent will dynamically spawn the MCP servers, build a unified tool catalog, execute a JSON plan (in parallel where possible), and summarize the results.

**Option A: Deterministic Mock Planner (No API keys needed)**

```powershell
.\.venv\Scripts\activate
$env:LLM_PROVIDER="mock"
python agent/agent.py "Find flights from BLR to DEL"
python agent/agent.py "Find hotels in Delhi"
python agent/agent.py "Help me travel from Bangalore to Delhi on 2026-06-10 and stay there"
```

**Option B: Free Local LLM (Ollama)**
Install [Ollama](https://ollama.com) and run `ollama pull llama3.2`.

```powershell
$env:LLM_PROVIDER="ollama"
$env:OLLAMA_MODEL="llama3.2"
python agent/agent.py "Find the cheapest flights from BLR to DEL"
```

**Option C: OpenAI**

```powershell
$env:LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="your_api_key_here"
$env:OPENAI_MODEL="gpt-4o"
python agent/agent.py "Find a flight from Bangalore to Delhi and then find hotels based on when I arrive"
```

## 🧪 Testing & Linting

Run from the repository root with the virtual environment active:

```bash
ruff check .   # lint (the same check CI runs)
pytest         # full suite: unit + integration, writes report.html
```

The integration tests exercise the full path `agent → MCP (stdio) → REST API → SQLite`, so they need the APIs on ports 8000 and 8001. The test fixture reuses them if they are already running and otherwise starts (and stops) its own. To run only the fast tests that spawn no processes:

```bash
pytest -m "not integration"
```

_The test suite generates a `report.html` file showing unit logic validation and full end-to-end `stdio` protocol integration checks._

Every pull request into `productionize` or `main` runs this same lint and test sequence in GitHub Actions (`.github/workflows/ci.yml`), plus `Format check (Ruff & Prettier)`, `Terraform fmt & validate`, and `Lint workflows (actionlint)` jobs. To run the Terraform checks locally:

```powershell
terraform -chdir=infra/terraform fmt -check -recursive
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform validate
```

## 🗺️ Platform Roadmap (Epics)

We are incrementally productionizing the platform through the following phases:

- [x] **SP00:**
      Platform, DX &
      Repo
      Standardization
      _(Continuous track
      — naming symmetry,
      MCP 2.x baseline
      and dependency
      locking,
      linting/formatting
      both locally and in
      CI done;
      ongoing platform,
      tooling and chore
      tasks)_
- [x] **SP01:** CI/CD Pipelines, Dockerization & Serverless Terraform IaC _(Completed — CI, Docker & Compose, Terraform & CD to Cloud Run)_
- [ ] **SP02:** Productionizing Flight & Hotel Core Microservices (Async Postgres, Row-Level Locking, Background Email Workers)
- [ ] **SP03:** Stateless Streamable HTTP MCP Layer, Auth & Security Guardrails
- [ ] **SP04:** LangGraph Multi-Agent Architecture & HITL Workflows
- [ ] **SP05:** Native Policy RAG MCP Server & FinOps Sandbox MCP Server
- [ ] **SP06:** Dynamic Model Router, Egress Validation, Observability & Evals

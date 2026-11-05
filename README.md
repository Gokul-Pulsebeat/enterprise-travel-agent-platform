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

## 📂 Project Folders (Current Phase: SP00)

```text
flight_api/          FastAPI REST service (Flight state & business logic)
flight_mcp_server/   MCP v2 server exposing flight logic as agent tools
hotel_api/           FastAPI REST service (Hotel state & business logic)
hotel_mcp_server/    MCP v2 server exposing hotel logic as agent tools
agent/               Agent orchestrator and dynamic MCP client
docs/                Enterprise PRDs, Architecture docs, and task tracking
tests/               Baseline pytest suite (Unit & Integration)
```

## ⚙️ Installation

This repository uses `pip-tools` for strict dependency locking. Ensure you have Python 3.11+ installed.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows (PowerShell)
# source .venv/bin/activate # macOS/Linux

# 2. Install dependencies via pip-tools lockfile
pip install pip-tools
pip-sync requirements.txt
```

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
curl "[http://127.0.0.1:8000/flights?origin=BLR&destination=DEL](http://127.0.0.1:8000/flights?origin=BLR&destination=DEL)"
curl "[http://127.0.0.1:8001/hotels?city=Delhi](http://127.0.0.1:8001/hotels?city=Delhi)"
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

## 🧪 Testing

Run the automated test suite (which includes HTML visual reporting) from the repository root:

```bash
pytest
```

_The test suite generates a `report.html` file showing unit logic validation and full end-to-end `stdio` protocol integration checks._

## 🗺️ Platform Roadmap (Epics)

We are incrementally productionizing the platform through the following phases:

- [x] **SP00:** Repo Standardization, Naming Symmetry & MCP 2.x Baseline
- [ ] **SP01:** CI/CD Pipelines, Dockerization & Serverless Terraform IaC _(Active)_
- [ ] **SP02:** Productionizing Flight & Hotel Core Microservices (Async Postgres, Row-Level Locking, Background Email Workers)
- [ ] **SP03:** Stateless Streamable HTTP MCP Layer, Auth & Security Guardrails
- [ ] **SP04:** LangGraph Multi-Agent Architecture & HITL Workflows
- [ ] **SP05:** Native Policy RAG MCP Server & FinOps Sandbox MCP Server
- [ ] **SP06:** Dynamic Model Router, Egress Validation, Observability & Evals

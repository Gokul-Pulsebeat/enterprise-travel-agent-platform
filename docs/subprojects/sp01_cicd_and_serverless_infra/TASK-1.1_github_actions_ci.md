# TASK-1.1 — GitHub Actions CI

| Field         | Value                                                                                                                  |
| ------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Epic          | SP01 — CI/CD Pipelines, Dockerization & Serverless Terraform IaC                                                       |
| PR            | PR 1 of 2                                                                                                              |
| Branch        | `feat/sp01-cicd-and-docker`                                                                                            |
| Target branch | `productionize`                                                                                                        |
| Depends on    | SP00 (pinned lockfile, pytest suite, `report.html`)                                                                    |
| Parent docs   | [`EPIC_PRD.md`](EPIC_PRD.md), [`00_MASTER_PRD.md`](../../00_MASTER_PRD.md)                                             |

---

## 1. Objective

Make quality gates automatic. Every pull request and every push to `productionize` or `main` must lint the code and run the **complete** test suite, including the integration tests that exercise `agent → MCP (stdio) → REST API → SQLite`, on a clean Linux machine using exactly the pinned dependencies. A failing run blocks the merge.

## 2. Scope

### In scope

| Area                        | Change                                                                                                                                                       |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `.github/workflows/ci.yml`  | New workflow: lint, start APIs, wait for health, run `pytest`, upload report                                                                                 |
| `requirements.in`           | Add `ruff>=0.9.0` (the lockfile `requirements.txt` is recompiled with `pip-compile`)                                                                         |
| `ruff.toml`                 | Ruff configuration: `target-version = "py311"`, explicit rule set `E4, E7, E9, F`, excludes for scratch folders                                              |
| `agent/agent.py`            | Whitespace/blank-line formatting fixes in `extract_text_content` so the file is clean                                                                        |
| `.gitignore`                | Add `.ruff_cache/` and `.env`                                                                                                                                |

### Lockfile tooling (added with this task)

- `scripts/compile-requirements.ps1` and `scripts/compile-requirements.sh`: run `pip-compile` inside a `python:3.11-slim` container (requires Docker) so `requirements.txt` is always compiled for Linux, matching CI and the Docker images.
- **Verify lockfile parity** step in `ci.yml`: recompiles on Linux and fails the build if the committed `requirements.txt` differs.

### Out of scope

- Building Docker images in CI (images are introduced in TASK-1.2; a CI image-build check is a candidate follow-up).
- Deployment (TASK-1.5).
- Multi-version Python matrix, coverage thresholds, and security scanning.
- Enabling branch protection ("require the `Lint & Test` check") — this is a GitHub repository setting, not code. See acceptance criterion AC12.

## 3. Architectural Notes

**Workflow shape.** One job, `Lint & Test`, on `ubuntu-latest` with Python 3.11 (matching the Dockerfiles and `ruff.toml`). `pip` caching is keyed on `requirements.txt`. Triggers are `pull_request` and `push` for `productionize` and `main`. A `concurrency` group cancels superseded runs, `permissions` is read-only, and the job has a 15-minute timeout.

**Why `pip-sync`.** `pip-sync requirements.txt` makes the environment match the lockfile exactly (installing missing packages and removing extras), so CI runs the same versions as local development. A plain `pip install` could silently diverge.

**Why `target-version` is set.** `agent/agent.py` uses `BaseExceptionGroup`, a Python 3.11 builtin. Without a declared target, ruff assumes an older Python and reports it as an undefined name (F821). The rule set is the ruff default, stated explicitly so it does not change silently across ruff releases.

**Lockfile parity.** `pip-compile` resolves for the host platform, so compiling on Windows can yield a different lockfile than Linux (for example Windows-only packages such as `colorama`), even though CI and the images run Linux. Two layers prevent that. First, `scripts/compile-requirements.*` run `pip-compile` in a `python:3.11-slim` container (the same base as the images). Second, the **Verify lockfile parity** CI step catches mistakes: it copies the committed `requirements.txt` to `requirements.check.txt` so `pip-compile` keeps the pinned versions, recompiles on Linux, and diffs the two with comment lines removed. The seed copy matters: without it, `pip-compile` would resolve to the newest releases and the check would fail whenever any upstream package published a new version. Comments are ignored because the generated header records the output filename. The step runs before `pip-sync` so a bad lockfile fails fast with a clear message.

**Why real API processes in CI.** The MCP servers call the REST APIs over HTTP, and FastAPI's `TestClient` cannot serve real network requests. CI therefore starts `flight_api` (8000) and `hotel_api` (8001) with `uvicorn` in the background and polls `/health` until each returns HTTP 200 (up to 30 s) before running `pytest`. The e2e test fixture checks `/health` first and **reuses** already-running APIs rather than starting duplicates, so CI-started and locally started APIs both work. On timeout the step prints both API logs and fails.

**Ports are fixed.** The integration tests and the MCP servers default to `127.0.0.1:8000/8001`.

**Artifacts.** `report.html` (generated by `pytest.ini`) is uploaded with `if: always()` so it exists for failed runs too. The API logs are uploaded alongside it because they are the first thing needed to debug an integration failure.

## 4. Acceptance Criteria

| #    | Criterion                                                                                                                                       |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1  | `.github/workflows/ci.yml` triggers on `pull_request` to `productionize` and `main`, and on `push` to `productionize` and `main`.               |
| AC2  | The job runs on `ubuntu-latest` with Python `3.11` and pip caching enabled.                                                                     |
| AC3  | Dependencies are installed with `pip-tools` via `pip-sync requirements.txt`.                                                                    |
| AC4  | `requirements.in` contains `ruff>=0.9.0` and the recompiled `requirements.txt` pins `ruff==`.                                                   |
| AC5  | `ruff check .` passes with no errors locally and in CI.                                                                                         |
| AC6  | CI starts `flight_api` on 8000 and `hotel_api` on 8001 and waits for HTTP 200 from both `/health` endpoints before running tests.               |
| AC7  | `pytest` runs unit **and** integration tests in CI (nothing is deselected) and passes.                                                          |
| AC8  | `report.html` is uploaded as a workflow artifact on every run, including failures (`if: always()`, `actions/upload-artifact@v4`).               |
| AC9  | `.gitignore` excludes `.ruff_cache/` and `.env`.                                                                                                |
| AC10 | `scripts/compile-requirements.ps1` and `.sh` exist and regenerate `requirements.txt` inside a `python:3.11-slim` container.                    |
| AC11 | CI runs a **Verify lockfile parity** step before `pip-sync` that fails when `requirements.txt` differs from a Linux recompile of `requirements.in`. |
| AC12 | *(Manual)* Branch protection on `productionize` and `main` requires the `Lint & Test` status check before merging.                              |

## 5. Verification Commands

Run from the repository root with the virtual environment active (PowerShell).

```powershell
# 0. Re-lock inside a Linux container so ruff is included (AC4, AC10; requires Docker Desktop), then sync the environment
pip install pip-tools
.\scripts\compile-requirements.ps1
pip-sync requirements.txt
Select-String -Path requirements.txt -Pattern "^ruff=="          # expect: a pinned ruff version

# 1. Lint (AC5)
ruff check .                                                      # expect: All checks passed!

# 2. Simulate the CI run locally (AC6, AC7): start both APIs, wait for health, run the full suite
$flight = Start-Process python -ArgumentList "-m","uvicorn","flight_api.app:app","--port","8000" -PassThru -WindowStyle Hidden
$hotel  = Start-Process python -ArgumentList "-m","uvicorn","hotel_api.app:app","--port","8001" -PassThru -WindowStyle Hidden
foreach ($port in 8000, 8001) {
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            if ((Invoke-WebRequest "http://127.0.0.1:$port/health" -UseBasicParsing).StatusCode -eq 200) { $ready = $true; break }
        } catch { }
        Start-Sleep -Seconds 1
    }
    "Port ${port} healthy: $ready"                                # expect: True for both
}
pytest                                                            # expect: all tests pass, report.html written
Stop-Process -Id $flight.Id, $hotel.Id

# 3. .gitignore (AC9)
git check-ignore -v .env .ruff_cache report.html                  # expect: all three reported as ignored

# 4. Workflow on GitHub (AC1-AC3, AC8): push the branch and open a PR into productionize
git push -u origin feat/sp01-cicd-and-docker
#    Then open the PR's "Checks" tab: expect "Lint & Test" green and a "pytest-report" artifact attached.
```

## 6. Rollout & Rollback

- **Rollout:** merge PR 1 into `productionize`. Then enable the required status check (AC12).
- **Rollback:** delete or revert `.github/workflows/ci.yml`. No runtime code depends on CI.

## 7. Risks

| Risk                                                                                                                         | Mitigation                                                                                                                       |
| ---------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `requirements.txt` compiled on Windows may contain platform-specific pins that behave differently under `pip-sync` on Linux  | Re-lock only with `scripts/compile-requirements.ps1` / `.sh` (Linux container); the **Verify lockfile parity** CI step fails fast if a host-compiled lockfile is pushed                                                  |
| Fixed ports 8000/8001 could clash on a shared runner                                                                         | GitHub-hosted runners are single-job VMs; the health wait fails loudly with logs if a port is unavailable                        |
| Background processes started in one step must survive into later steps                                                       | `nohup` is used and the health-wait step verifies both APIs before tests run                                                     |
| Open-ended `>=` ranges in `requirements.in` can pull new versions on recompile                                               | Versions only change when someone runs `pip-compile`; CI always installs the committed lockfile                                  |

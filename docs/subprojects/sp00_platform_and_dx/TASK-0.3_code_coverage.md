# TASK-0.3 — Code Coverage Measurement and Enforcement

| Field         | Value                                                                                                    |
| ------------- | -------------------------------------------------------------------------------------------------------- |
| Epic          | SP00 — Platform, DX & Repo Standardization                                                               |
| PR            | Single PR (chore); optional phase B may follow as a second PR                                            |
| Branch        | `chore/sp00-t03-code-coverage`                                                                           |
| Target branch | `productionize`                                                                                          |
| Status        | **Fully specified; implementation deferred.** Writing this document changes no code and no configuration |
| Depends on    | TASK-0.1 (pytest suite), TASK-0.2 (pre-commit and CI hygiene), SP02 TASK-2.1 (Postgres-backed API tests) |
| Parent docs   | [`EPIC_PRD.md`](EPIC_PRD.md), [`00_MASTER_PRD.md`](../../00_MASTER_PRD.md)                               |

---

## 1. Objective

Make it visible, and then enforceable, how much of the code the test suite actually exercises. Coverage must be measured the same way on a developer machine and in CI, must not silently under-report code that runs in greenlets or subprocesses, and must cost nothing: no paid service, no account, no token. The goal is a **ratchet that prevents regressions** and a signal on **new code in each pull request**, not a vanity percentage.

The task is deliberately shaped by the roadmap: the MCP servers move from `stdio` subprocesses to standalone HTTP services in SP03, and the agent is rebuilt in SP03/SP04. Effort goes into the code that will live on (the REST services and the shared package), not into measuring plumbing that is about to be replaced.

## 2. Scope

### In scope

| Area                          | Change                                                                                                                                                                                                          |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `requirements.in`             | Add `pytest-cov` (brings `coverage`); recompile the lockfile with `scripts/compile-requirements.ps1`                                                                                                            |
| `.coveragerc` (new)           | Source packages, branch coverage, greenlet and thread concurrency, parallel data files, relative paths, omit and exclusion rules, report settings, and the `fail_under` threshold                               |
| `.github/workflows/ci.yml`    | The `Lint & Test` job runs the suite with coverage, publishes `coverage.xml` and an HTML report as artifacts, writes a Markdown summary to the job summary, and fails below the threshold                       |
| New unit tests                | Light in-process tests for the MCP tool functions (they survive the SP03 transport change unchanged) and for agent code that is cheap to test; **no** tests whose only purpose is the `stdio` spawning plumbing |
| `.gitignore`, `.dockerignore` | Exclude `.coverage*`, `coverage.xml`, `htmlcov/`                                                                                                                                                                |
| `README.md`                   | How to run coverage locally and what CI enforces                                                                                                                                                                |
| Phase B (optional, see 3.4)   | Measure the API processes that CI starts and the uvicorn processes the end-to-end tests spawn; `diff-cover` check that changed lines in a PR are covered                                                        |

### Packages measured and gated

| Package                                 | Measured | Counts toward the threshold | Why                                                                                                                                                 |
| --------------------------------------- | -------- | --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `common`, `flight_api`, `hotel_api`     | Yes      | Yes                         | The long-lived core; every later epic builds on it                                                                                                  |
| `flight_mcp_server`, `hotel_mcp_server` | Yes      | Yes                         | Their tool functions persist across the SP03 move to HTTP; only the transport line changes                                                          |
| `agent`                                 | Yes      | **No** (reported only)      | Legacy: the stdio client is replaced in SP03 and the orchestrator is rebuilt in SP04, so a threshold would ratchet code that is about to be deleted |

The gate excludes `agent/` by running the threshold check with `--omit` for that package (see 3.4); it still appears in every report.

Not measured: `tests/`, `scripts/`, `infra/`, and each service's `migrations/` folder. Migrations are verified by the migration and integrity tests (they run against a real database), where line coverage of generated-style DDL adds noise and no insight.

### Out of scope

- **Measuring the `stdio` MCP subprocesses.** They become HTTP services in SP03 and are then measured like the REST APIs (3.3). No plumbing is built for the interim.
- Hosted coverage services (Codecov, Coveralls, SonarCloud): they need accounts or tokens and add a dependency for little gain at this size. Alternatives are listed in 3.1 for a future decision.
- A target of 100%, mutation testing, or coverage of Terraform, YAML and shell.
- Badges and trend dashboards.
- Splitting runtime and development requirements (the coverage packages join the single `requirements.in`, like the other test tools).

## 3. Architectural Notes

### 3.1 Tool choice

`coverage.py` through `pytest-cov` is the standard free option: it supports branch coverage, subprocess measurement, parallel data files, and XML, HTML, JSON and Markdown reports. It is already what every alternative uses underneath.

| Option                      | Cost and friction                                                             | Verdict                                            |
| --------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------- |
| `pytest-cov` only           | Free; no accounts; reports as CI artifacts and job summary                    | **Chosen**                                         |
| `pytest-cov` + `diff-cover` | Free; adds a "changed lines must be covered" check                            | **Phase B**, valuable and cheap                    |
| Codecov / Coveralls         | Account, token secret, third-party access to source metadata; free tiers vary | Revisit later if PR comments and badges are wanted |
| SonarCloud                  | Heavier setup; broader scope than coverage                                    | Not now                                            |

### 3.2 What the configuration must get right (the design core)

1. **Branch coverage on.** Line coverage alone reports a function as covered when only its happy path ran. Branch coverage is cheap and catches the untested `if` side.
2. **Greenlets.** SQLAlchemy's asyncio support runs database calls inside greenlets. Without `concurrency = greenlet, thread` in the coverage configuration, lines executed inside those greenlets can be missed, and the API handlers would under-report. An acceptance criterion checks that endpoint bodies show as covered.
3. **Parallel data files and relative paths.** `parallel = True` gives each process its own data file, combined before reporting. `relative_files = True` keeps paths identical between a Windows developer machine and the Linux CI runner.
4. **Exclusions are explicit.** Standard exclusions only: `pragma: no cover`, `if __name__ == "__main__":`, `if TYPE_CHECKING:`, `raise NotImplementedError`, overloads and abstract methods. The `mcp.run(...)` entry point sits under the `__main__` guard and is therefore excluded. Any other exclusion needs a justification in review.

### 3.3 Subprocesses and the roadmap

The suite runs code in several places a plain `pytest --cov` does not see.

| Where the code runs                                                              | Measured by default? | Plan                                                                                                                                                    |
| -------------------------------------------------------------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| In the pytest process (TestClient API tests, unit tests)                         | Yes                  | Covers the bulk of `common`, `flight_api`, `hotel_api`                                                                                                  |
| MCP servers spawned over `stdio` by the agent                                    | No                   | **Not a concern**: replaced by HTTP services in SP03. Their tool functions get light in-process tests now; nothing is built to measure the subprocesses |
| uvicorn APIs started by the end-to-end fixture, and by the CI step before pytest | No                   | **Phase B**: start them under coverage; on Linux, SIGTERM lets uvicorn exit normally so data is written; combine before reporting                       |
| The `alembic` CLI (migration tests)                                              | No                   | Not worth measuring; migrations are excluded and tested by behavior                                                                                     |

**Evolution after SP03.** Once the MCP servers are standalone HTTP services, they are started exactly like `flight_api` and `hotel_api`. Phase B's mechanism (run the process under coverage, stop it with SIGTERM, combine the data files) then covers them with no new design. At that point the agent's stdio client is gone, and after SP04 the `agent/` package is replaced, so the `--omit` in the gate is removed together with the legacy code.

Two cautions apply to phase B. Coverage data is written when the interpreter exits normally, and on Windows `terminate()` is a hard kill, so subprocess coverage is **only authoritative on the Linux CI runner**. And CI's pre-started API processes must be stopped explicitly (with SIGTERM) before the data files are combined, not left for the runner to kill.

### 3.4 Thresholds: a ratchet, not a guess

1. **Measure first.** The baseline (overall and per package) is the first deliverable and is recorded in section 4's baseline table. No number is chosen before it exists.
2. **Set `fail_under` to the baseline rounded down.** From then on a change that lowers total coverage fails CI. The gate runs `coverage report --omit="agent/*" --fail-under=<N>` so legacy agent code cannot hold the number hostage; the normal report still lists it.
3. **Ratchet upward** in small steps as tests are added; never lower it without an explicit review note.
4. **Do not chase 100%.** Prefer meaningful tests on risky code (locking and idempotency in SP02, auth in SP03) over lines for their own sake.
5. **Differential coverage (phase B).** `diff-cover` checks that the lines a pull request changes are covered (default proposal: 80%). This is fairer than a global number: new code must be tested, legacy code is not punished.

The threshold applies to the **full** suite as CI runs it. A local run with `-m "not db and not integration"` omits the database tests and will report lower numbers; that is expected and not a failure.

### 3.5 Reporting without an external service

- **Job log:** terminal report with missing lines, skipping fully covered files.
- **Artifacts:** `coverage.xml` and an HTML report uploaded with `if: always()`, so they exist for failed runs.
- **Job summary:** a Markdown table from `coverage report --format=markdown`, written to the GitHub job summary, so the numbers appear on the run page without downloading anything.

### 3.6 Developer experience

- Coverage is **opt-in locally** (`pytest --cov`): it slows runs and is rarely needed on every save. The default `pytest.ini` options stay unchanged.
- Documented commands show how to open the HTML report and how to see missing lines for one file.
- `pytest-cov` and `coverage` are not needed in the Docker images, but until requirements are split they are installed there with the other test tools, which is accepted.

### 3.7 Security and cost

Reports contain file paths and line numbers only: no source, secrets or connection strings. Everything used is open source and runs inside the existing CI job, so cost is zero and no new secret or account is introduced.

## 4. Acceptance Criteria

| #    | Criterion                                                                                                                                                                                                         |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1  | `requirements.in` adds `pytest-cov`; the recompiled `requirements.txt` pins `pytest-cov==` and `coverage==`; CI's lockfile-parity check passes.                                                                   |
| AC2  | `.coveragerc` exists and defines: the six measured packages, branch coverage, `concurrency = greenlet, thread`, parallel data files, relative paths, the omit list, the standard exclusions, and report settings. |
| AC3  | `pytest --cov` locally prints per-file coverage with missing lines for all six packages.                                                                                                                          |
| AC4  | The baseline (overall and per package) is measured and recorded in the table below.                                                                                                                               |
| AC5  | `fail_under` equals the recorded baseline (excluding `agent/`) rounded down, and CI fails when coverage drops below it (demonstrated by temporarily removing a test).                                             |
| AC6  | CI produces `coverage.xml` and an HTML report as artifacts on every run (`if: always()`) and writes a Markdown coverage summary to the job summary.                                                               |
| AC7  | Branch coverage is enabled and reported.                                                                                                                                                                          |
| AC8  | Endpoint bodies in `flight_api/app.py` and `hotel_api/app.py` show as covered, proving the greenlet setting works.                                                                                                |
| AC9  | Light in-process tests cover the MCP tool functions; no test or configuration exists solely to measure the `stdio` subprocesses.                                                                                  |
| AC10 | `agent/` appears in the reports but does not count toward the gate, and the reason (replaced in SP03/SP04) is recorded in `.coveragerc` or the CI step.                                                           |
| AC11 | _(Phase B)_ The API processes CI starts, and the uvicorn processes the end-to-end tests spawn, contribute coverage data on Linux; the combined report includes them.                                              |
| AC12 | _(Phase B)_ A `diff-cover` step fails a pull request whose changed lines are below the agreed percentage.                                                                                                         |
| AC13 | `.gitignore` and `.dockerignore` exclude `.coverage*`, `coverage.xml` and `htmlcov/`.                                                                                                                             |
| AC14 | `README.md` documents running coverage locally and what CI enforces.                                                                                                                                              |
| AC15 | No paid or external service, secret, token or account is introduced.                                                                                                                                              |

### Baseline (recorded at implementation)

| Package             | Statements | Branches | Coverage | Counts toward the gate |
| ------------------- | ---------- | -------- | -------- | ---------------------- |
| `common`            |            |          |          | Yes                    |
| `flight_api`        |            |          |          | Yes                    |
| `hotel_api`         |            |          |          | Yes                    |
| `flight_mcp_server` |            |          |          | Yes                    |
| `hotel_mcp_server`  |            |          |          | Yes                    |
| `agent`             |            |          |          | No (legacy)            |
| **Gated total**     |            |          |          |                        |

## 5. Verification Commands

Run after implementation, from the repository root (PowerShell) with the virtual environment active. Docker Desktop must be running for the database.

```powershell
# 0. Install the new packages (AC1)
.\scripts\compile-requirements.ps1
.\scripts\sync-dev.ps1
Select-String -Path requirements.txt -Pattern "^(pytest-cov|coverage)=="      # expect: two pinned lines

# 1. Start the database the tests need
docker compose up -d postgres

# 2. Measure the baseline with the full suite (AC3, AC4, AC7)
pytest --cov --cov-branch --cov-report=term-missing:skip-covered

# 3. Reports (AC6)
coverage xml
coverage html
Start-Process htmlcov\index.html
coverage report --format=markdown                                              # the table CI writes to the job summary

# 4. Greenlet check: handler bodies must be measured (AC8)
coverage report --include="flight_api/app.py,hotel_api/app.py" --show-missing   # expect: endpoint bodies covered, not 0%

# 5. Threshold gate (AC5, AC10): agent/ is excluded from the gate but still reported
coverage report --omit="agent/*" --fail-under=100; "Exit code: $LASTEXITCODE"   # expect: 2 (below 100%)
coverage report --include="agent/*"                                             # expect: agent still listed
#    Then, as a drill, temporarily rename tests\test_hotel_api.py and re-run step 2 with the real threshold:
#    expect a non-zero exit code. Restore the file afterwards.

# 6. Artifacts are ignored by Git (AC13)
git check-ignore -v .coverage coverage.xml htmlcov

# 7. Fast local run without the database (expect lower numbers; this is not a failure)
pytest -m "not db and not integration" --cov --cov-report=term

# 8. Phase B: subprocess measurement of the API processes. Authoritative on the Linux CI runner only (AC11)
$env:COVERAGE_PROCESS_START = (Resolve-Path .coveragerc)
pytest --cov
coverage combine
coverage report
Remove-Item Env:COVERAGE_PROCESS_START

# 9. Phase B: changed-lines coverage against the target branch (AC12)
git fetch origin productionize
diff-cover coverage.xml --compare-branch=origin/productionize --fail-under=80

# 10. CI (AC6): push the branch, open a PR, then check the "Lint & Test" run page
git push -u origin chore/sp00-t03-code-coverage
#     Expect: the coverage table in the job summary, and coverage-report artifacts attached
```

## 6. Rollout & Rollback

- **Rollout:** merge the PR. The first CI run records the real baseline on Linux; if it differs from the Windows number, adjust `fail_under` in the same PR before merging. Contributors need no action; coverage stays opt-in locally.
- **Raising the bar later:** change `fail_under` in a small PR whenever tests have raised the baseline.
- **After SP03/SP04:** remove the `agent/` omit from the gate when that package is replaced, and add the MCP HTTP services to phase B.
- **Rollback:** remove the coverage flags and the threshold from the CI command, or revert the PR. Nothing at runtime depends on this task.

## 7. Risks

| Risk                                                                                                               | Mitigation                                                                                                                                                   |
| ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Async and greenlet code under-reports, making handlers look untested                                               | `concurrency = greenlet, thread`, plus AC8 that checks endpoint bodies are measured                                                                          |
| Subprocess code is invisible, so the total under-reports reality                                                   | The only subprocesses that matter long-term are the HTTP services, which phase B covers; the `stdio` MCP servers are temporary and deliberately not measured |
| Windows and Linux numbers differ (subprocess data is lost to hard kills on Windows)                                | The CI number on Linux is authoritative; local numbers are for guidance                                                                                      |
| A threshold set before measuring is arbitrary and either blocks work or means nothing                              | Baseline first; `fail_under` is the baseline rounded down; ratchet only upward                                                                               |
| Legacy agent code drags the number down or tempts tests for code about to be deleted                               | `agent/` is reported but excluded from the gate until SP03/SP04 replace it                                                                                   |
| Coverage becomes a goal in itself and encourages low-value tests                                                   | No 100% target; phase B focuses on changed lines; review judges test quality                                                                                 |
| Slower CI and local runs                                                                                           | Coverage is opt-in locally; in CI the overhead is a small fraction of the database and integration tests                                                     |
| Coverage packages enlarge the Docker images (single requirements file)                                             | Accepted until the runtime and development requirements are split (SP00 backlog)                                                                             |
| Phase B (`COVERAGE_PROCESS_START`, SIGTERM handling) is fiddly and may behave differently across coverage versions | It is optional, behind its own acceptance criteria, and verified on the pinned version before being relied on                                                |
| `diff-cover` needs the target branch fetched in CI                                                                 | The CI step fetches `origin/productionize` explicitly                                                                                                        |

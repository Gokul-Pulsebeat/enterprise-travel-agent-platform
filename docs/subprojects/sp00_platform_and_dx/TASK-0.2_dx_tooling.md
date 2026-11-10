# TASK-0.2 — Developer Experience Tooling (pre-commit, formatters, workflow linting)

| Field         | Value                                                                                  |
| ------------- | -------------------------------------------------------------------------------------- |
| Epic          | SP00 — Platform, DX & Repo Standardization                                             |
| PR            | Single PR (chore)                                                                      |
| Branch        | `chore/sp00-t02-dx-tooling`                                                            |
| Target branch | `productionize`                                                                        |
| Depends on    | TASK-0.1 (`ruff.toml`, lockfile tooling), SP01 (CI workflows, Terraform configuration) |
| Parent docs   | [`EPIC_PRD.md`](EPIC_PRD.md), [`00_MASTER_PRD.md`](../../00_MASTER_PRD.md)             |

---

## 1. Objective

Shorten the feedback loop. Today a formatting slip, an invalid workflow, or an unformatted Terraform file is discovered only after pushing, when CI fails. This task runs the same checks on the developer's machine at commit time through [`pre-commit`](https://pre-commit.com), and adds the missing CI gates (Ruff/Prettier format checks and workflow linting) so broken GitHub Actions files can no longer merge. It also reorganizes SP00 as a continuous platform track so tooling and chore work like this has a permanent home alongside the feature epics.

## 2. Scope

### In scope

| Area                            | Change                                                                                                                                                                                                                                                                          |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.pre-commit-config.yaml` (new) | Hooks: `ruff-check` (with `--fix`) and `ruff-format`; `prettier` for YAML, JSON and Markdown; `terraform_fmt` and `terraform_validate` scoped to `infra/terraform/`; `actionlint`. All revisions pinned                                                                         |
| `requirements.in`               | Add `pre-commit>=4.0.0` (the lockfile is recompiled with `scripts/compile-requirements.ps1`, then synced with `scripts/sync-dev.ps1`)                                                                                                                                           |
| `.github/workflows/ci.yml`      | New dedicated jobs `Format check (Ruff & Prettier)` (running `ruff-format` and `prettier` via `pre-commit`) and `Lint workflows (actionlint)`. The existing `Lint & Test` and `Terraform fmt & validate` jobs are unchanged                                                     |
| `README.md`                     | "Enable pre-commit hooks" section (`pre-commit install` after syncing the environment); SP00 retitled; SP01 marked complete                                                                                                                                                     |
| SP00 reorganization             | SP00's folder renamed to `docs/subprojects/sp00_platform_and_dx/`; new `EPIC_PRD.md` framing SP00 as a continuous track with `TASK-0.1` and `TASK-0.2`; titles and links updated in `README.md`, `docs/00_MASTER_PRD.md`, `docs/01_STEP_0_POC_BASELINE_AUDIT.md` and `TASK-0.1` |

### What runs where

| Check                           | Pre-commit (local)  | CI                                       |
| ------------------------------- | ------------------- | ---------------------------------------- |
| Ruff lint (`ruff check`)        | Yes (`ruff-check`)  | Yes (`Lint & Test`)                      |
| Ruff format                     | Yes (`ruff-format`) | Yes (`Format check (Ruff & Prettier)`)   |
| Prettier (YAML, JSON, Markdown) | Yes                 | Yes (`Format check (Ruff & Prettier)`)   |
| `terraform fmt`                 | Yes                 | Yes (`Terraform fmt & validate`)         |
| `terraform validate`            | Yes                 | Yes (`Terraform fmt & validate`)         |
| actionlint                      | Yes                 | Yes (`Lint workflows (actionlint)`, new) |

### Out of scope

- Splitting development and runtime requirements. `pre-commit` joins the single `requirements.in`, so it is also installed in the Docker images until that split happens.
- Adding general-purpose hooks (trailing whitespace, merge-conflict markers, large-file checks, secret scanning).
- A Prettier configuration file; default settings are used.
- Automated hook-version updates (Dependabot/Renovate).

## 3. Architectural Notes

**Hook set and rationale.**

| Hook                 | Source                              | Role                                                                                                                                                |
| -------------------- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ruff-check`         | `astral-sh/ruff-pre-commit`         | Lint with auto-fix, using the rules in `ruff.toml`. The hook id is `ruff-check`; the older id `ruff` is a deprecated alias that may no longer exist |
| `ruff-format`        | `astral-sh/ruff-pre-commit`         | Python formatting (line length 120, from `ruff.toml`)                                                                                               |
| `prettier`           | `rbubley/mirrors-prettier`          | Formats files tagged `yaml`, `json` or `markdown` (`types_or`)                                                                                      |
| `terraform_fmt`      | `antonbabenko/pre-commit-terraform` | Canonical Terraform formatting, limited to `^infra/terraform/`                                                                                      |
| `terraform_validate` | `antonbabenko/pre-commit-terraform` | Configuration validation, limited to `^infra/terraform/`, with `--tf-init-args=-backend=false`                                                      |
| `actionlint`         | `rhysd/actionlint`                  | Validates `.github/workflows/*.yml`: syntax, expressions, action inputs, and ShellCheck on `run:` scripts                                           |

**Version consistency with CI.** The `ruff-check`/`ruff-format` revision matches the Ruff version pinned in `requirements.txt`, so local and CI results agree; update both together. The `actionlint` revision matches the pinned Docker image used by the CI job. `pre-commit autoupdate` bumps all hook revisions at once.

**Terraform hooks are safe around local state.** `terraform_validate` runs `terraform init` with `-backend=false`, so it never reads or writes remote state. Local state, plans and `*.tfvars` are gitignored, so pre-commit (which only processes tracked files) never formats or validates them. The hooks need the `terraform` binary on `PATH`; they download providers on first use.

**Init-argument syntax.** Arguments for `terraform init` are passed with the hook's own `--tf-init-args=` option. The `--args=` option instead feeds `terraform validate` itself, so it is not used here.

**Prettier and its
source repository.**
Uses the maintained
community mirror
`rbubley/mirrors-prettier`
(pinned to a
specific tag)
because the original
`pre-commit/mirrors-prettier`
is archived and
frozen at 3.x. The
CI format check runs
this exact hook from
`.pre-commit-config.yaml`
so local and CI
Prettier versions
never drift.

**Why a separate CI job for actionlint.** It needs no Python or dependency install, so it finishes in seconds and runs in parallel with the other jobs. As its own job it appears as its own status check and can be made required independently. It runs the pinned `rhysd/actionlint` Docker image, which bundles ShellCheck, so the `run:` scripts in `ci.yml` and `cd.yml` are linted too.

**Formatter side effects.** When a formatter changes a file, pre-commit fails the commit so the change can be reviewed and re-staged. The first `pre-commit run --all-files` can therefore rewrite many existing Python, Markdown and YAML files. Commit that one-time cleanup separately from functional changes so reviews stay readable.

**SP00 as a continuous track.** SP00 is no longer a one-off "foundation" epic. Its `EPIC_PRD.md` defines what belongs in it (repository standardization, developer tooling, dependency management, cross-cutting CI hygiene, ad-hoc chores), the `TASK-0.N` and `chore/sp00-tNN-*` conventions, and a non-committal backlog.

## 4. Acceptance Criteria

| #    | Criterion                                                                                                                                                                                                                             |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1  | `.pre-commit-config.yaml` exists at the repository root and defines `ruff-check` (with `--fix`), `ruff-format`, `prettier` (YAML, JSON, Markdown), `terraform_fmt`, `terraform_validate` and `actionlint`, each at a pinned revision. |
| AC2  | The Terraform hooks are scoped to `infra/terraform/` and run `init` with `-backend=false`.                                                                                                                                            |
| AC3  | `requirements.in` contains `pre-commit>=4.0.0`, and the recompiled `requirements.txt` pins `pre-commit==`.                                                                                                                            |
| AC4  | The README instructs developers to run `pre-commit install` after syncing their environment, and explains what the hooks do and which checks CI repeats.                                                                              |
| AC5  | `pre-commit validate-config` succeeds, and after the one-time formatting cleanup `pre-commit run --all-files` passes on every hook, twice in a row (idempotent).                                                                      |
| AC6  | A staged file with a lint error is fixed or rejected at commit time.                                                                                                                                                                  |
| AC7  | `ci.yml` contains a dedicated `Format check (Ruff & Prettier)` and `Lint workflows (actionlint)` jobs that pass; the `Lint & Test` and `Terraform fmt & validate` jobs are unchanged.                                                 |
| AC8  | No file in the repository refers to the old SP00 folder name or to the old `TASK-0.1` filename, and every relative Markdown link resolves.                                                                                            |
| AC9  | SP00's `EPIC_PRD.md` is titled "SP00 — Platform, DX & Repo Standardization", describes a continuous track, and lists `TASK-0.1` and `TASK-0.2`.                                                                                       |
| AC10 | The README roadmap uses the new SP00 title and marks SP01 as completed.                                                                                                                                                               |
| AC11 | _(Manual)_ `Format check (Ruff & Prettier)` and `Lint workflows (actionlint)` are added as required status checks on `productionize` and `main`.                                                                                      |

## 5. Verification Commands

Run from the repository root (PowerShell) with the virtual environment active. Docker Desktop must be running for step 0.

```powershell
# 0. Re-lock in a Linux container and sync the environment (AC3)
.\scripts\compile-requirements.ps1
.\scripts\sync-dev.ps1
Select-String -Path requirements.txt -Pattern "^pre-commit=="     # expect: a pinned version
pre-commit --version                                              # expect: pre-commit 4.x

# 1. Install the Git hook and validate the configuration (AC1, AC2, AC4)
pre-commit install                                                # expect: pre-commit installed at .git\hooks\pre-commit
pre-commit validate-config .pre-commit-config.yaml                # expect: no output, exit code 0

# 2. One-time cleanup: run every hook on every tracked file (AC5).
#    The first run downloads tools and may rewrite many files. Review, then commit the cleanup on its own.
pre-commit run --all-files
git diff --stat                                                   # review what the formatters changed
git add -A
git commit -m "style: apply Ruff and Prettier formatting"

# 3. Hooks must now pass, twice in a row (AC5)
pre-commit run --all-files                                        # expect: every hook Passed
pre-commit run --all-files                                        # expect: every hook Passed again, no files modified

# 4. Run hooks individually when debugging
pre-commit run ruff-check --all-files
pre-commit run ruff-format --all-files
pre-commit run prettier --all-files
pre-commit run terraform_fmt --all-files
pre-commit run terraform_validate --all-files
pre-commit run actionlint --all-files

# 5. A lint error must be fixed or rejected at commit time (AC6)
"import os" | Set-Content scratch_hook_test.py
git add scratch_hook_test.py
git commit -m "test: hooks should stop this"                      # expect: ruff-check Failed (it removes the unused import) and no commit is created
git restore --staged scratch_hook_test.py
Remove-Item scratch_hook_test.py

# 6. No stale references to the old SP00 folder or task filename (AC8)
git grep --untracked -n -i "sp00_repo_standardi[sz]ation" -- .                 # expect: no output
git grep --untracked -n "TASK-0.1_naming_and_mcp2_migratio[n]" -- .          # expect: no output

# 7. Every relative Markdown link resolves (AC8)
Get-ChildItem -Path . -Recurse -Filter *.md -File |
    Where-Object { $_.FullName -notmatch '\\(\.venv|\.git|node_modules|\.terraform)\\' } |
    ForEach-Object {
        $file = $_
        Select-String -Path $file.FullName -Pattern '\]\(([^)#\s]+)' -AllMatches |
            ForEach-Object { $_.Matches } |
            ForEach-Object {
                $target = $_.Groups[1].Value
                if ($target -notmatch '^(https?:|mailto:)' -and -not (Test-Path (Join-Path $file.DirectoryName $target))) {
                    "BROKEN: $($file.Name) -> $target"
                }
            }
    }                                                             # expect: no output

# 8. The existing tests and lint are unaffected by the formatter run (regression check)
ruff check .
pytest

# 9. CI (AC7): push the branch and open a PR into productionize
git push -u origin chore/sp00-t02-dx-tooling
#    Expect four green jobs: "Lint & Test", "Format check (Ruff & Prettier)", "Terraform fmt & validate" and "Lint workflows (actionlint)".
```

## 6. Rollout & Rollback

- **Rollout:** merge the PR. Each developer then runs `pre-commit install` once after syncing their environment. Add `Lint workflows (actionlint)` as a required check (AC11). Land the one-time formatting cleanup (step 2) as its own commit.
- **Rollback:** delete `.pre-commit-config.yaml` and the `actionlint` job, and remove `pre-commit` from `requirements.in` (recompile). Nothing at runtime depends on this task. Developers who installed the Git hook run `pre-commit uninstall`.
- **Bypass:** CI enforces all checks (Ruff lint and format, Prettier, Terraform fmt/validate, and actionlint), so `--no-verify` will not bypass formatting or linting in a PR.

## 7. Risks

| Risk                                                                                                                 | Mitigation                                                                                                                                                     |
| -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The first `--all-files` run rewrites many existing files (Ruff format, Prettier)                                     | Commit the cleanup on its own (step 2); consider a `.git-blame-ignore-revs` entry so `git blame` skips it (SP00 backlog)                                       |
| Hook revisions were chosen without network access in the authoring environment, so a tag may not exist or may be old | `pre-commit validate-config` and the first `pre-commit run` surface a bad revision immediately; `pre-commit autoupdate` moves every hook to the latest release |
| `rbubley/mirrors-prettier` is a community mirror                                                                     | Pinned to a specific tag in `.pre-commit-config.yaml`                                                                                                          |
| ShellCheck inside actionlint may flag existing `run:` scripts in `ci.yml` or `cd.yml`                                | Fix the reported lines (usually quoting or unused variables); the CI job prints exact file and line                                                            |
| Terraform hooks need the `terraform` binary and network access on first run                                          | Documented in the README (`winget install Hashicorp.Terraform`); CI's Terraform job remains the authoritative check                                            |
| `pre-commit` and its dependencies are also installed in Docker images while requirements are unsplit                 | Accepted; splitting runtime and development requirements is a backlog item                                                                                     |
| Prettier realigns the Markdown tables in existing PRDs                                                               | Cosmetic and one-time; code blocks and ASCII diagrams are left untouched                                                                                       |

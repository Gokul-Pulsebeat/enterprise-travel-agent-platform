# TASK-1.5 — Continuous Deployment Pipeline

| Field         | Value                                                                                       |
| ------------- | ------------------------------------------------------------------------------------------- |
| Epic          | SP01 — CI/CD Pipelines, Dockerization & Serverless Terraform IaC                            |
| PR            | PR 2 of 2                                                                                   |
| Branch        | `feat/sp01-terraform-and-cd`                                                                |
| Target branch | `productionize`                                                                             |
| Depends on    | TASK-1.4 (registry, services, WIF, deployer account), TASK-1.2 (Dockerfiles), TASK-1.1 (CI) |
| Parent docs   | [`EPIC_PRD.md`](EPIC_PRD.md), [`00_MASTER_PRD.md`](../../00_MASTER_PRD.md)                  |

---

## 1. Objective

Every merge to `productionize` ships to Cloud Run with no manual steps, safely. The pipeline authenticates to GCP without any stored key, builds and pushes both API images tagged with the commit SHA, deploys them, proves the new revisions are healthy, and, if they are not, automatically puts traffic back on the revisions that were serving before.

## 2. Scope

### In scope

| Area                       | Change                                                                                                                                         |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `.github/workflows/cd.yml` | New workflow: trigger on push to `productionize` and on `workflow_dispatch`; WIF auth; build, push, deploy; `/health` gate; automatic rollback |
| `.github/workflows/ci.yml` | `Terraform fmt & validate` job (delivered with TASK-1.4; it is the Terraform check required by this task)                                      |

### Out of scope

- **Applying Terraform from the pipeline.** CD deploys application images only; infrastructure is applied manually (TASK-1.4).
- Deploying the `agent` image. It is a CLI/one-shot process, not a service, until SP03/SP04.
- Canary or gradual traffic shifting, and pre-promotion testing on a tagged revision. Candidates for a later iteration.
- Notifications (Slack/email) and deployment dashboards.
- Staging environments.

## 3. Architectural Notes

**Pipeline flow.**

```
push to productionize  (or manual run)
        |
        v
 verify GitHub repo variables are set
        |
        v
 authenticate to GCP  <--- GitHub OIDC token --->  Workload Identity Federation  --> deployer service account
        |                                                  (repo + branch checked)
        v
 build + push flight-api:<sha> and hotel-api:<sha>  --> Artifact Registry
        |
        v
 record the revision currently serving traffic, per service   (the rollback target)
        |
        v
 gcloud run deploy  +  update-traffic --to-latest   (per service)
        |
        v
 poll <service-url>/health until HTTP 200           (post-deploy gate, up to 2 minutes per service)
        |                               |
     success                         failure
        |                               |
        v                               v
 write deploy summary          roll BOTH services back to their recorded revisions
```

**Keyless authentication.** The job requests a GitHub OIDC token (`permissions: id-token: write`), and `google-github-actions/auth` exchanges it through Workload Identity Federation for short-lived credentials that impersonate the `github-deployer` service account. No JSON key exists in GitHub secrets or anywhere else. The provider only honors tokens from this repository on the `productionize` branch, so a manual run (`workflow_dispatch`) on any other branch cannot authenticate.

**Configuration lives in repository variables, not secrets.** `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_ARTIFACT_REPO`, `GCP_WIF_PROVIDER` and `GCP_DEPLOYER_SA` are identifiers, not credentials. `terraform output github_actions_variables` prints all of them. The first workflow step fails with a clear message if any are missing.

**Image tagging.** Images are tagged only with the full commit SHA, never `latest`. Each Cloud Run revision therefore maps to exactly one commit, and a rollback target is always an immutable image.

**Traffic and rollback mechanics.**

- Every run deploys with a unique revision name (`<service>-<sha7>-<run number>-<attempt>`). That guarantees a _new_ revision even when the image is unchanged (a re-run, or a rollback drill), because Cloud Run creates no revision for an identical template, and it ties each revision to a commit.
- Before deploying, the pipeline records the revision that currently receives traffic for each service.
- After `gcloud run deploy`, it always runs `update-traffic --to-latest`. This matters: a rollback pins traffic to a fixed revision, and Cloud Run does not move _pinned_ traffic to new revisions on its own. Without the explicit step, a deploy after a rollback would pass the health gate while still serving the old revision.
- On any failure after the recording step, both services are rolled back together to their recorded revisions, so flight and hotel never run mismatched versions. A service already serving its recorded revision is skipped. If nothing was recorded (the failure happened earlier, e.g. in the build), the rollback step is skipped because nothing was deployed.
- The job still ends red after a successful rollback, so a bad deploy is never mistaken for a good one.
- Terraform ignores image and traffic changes (TASK-1.4), so a later `terraform apply` neither reverts a deploy nor undoes a rollback.

**Health gate semantics.** The gate polls `GET /health` on each service's URL (24 attempts, 5 s apart). Cloud Run only routes traffic to a revision after its startup probe passes, so a passing check confirms the new code is serving. The check is a liveness signal for the process and its dependencies as they exist today (SQLite); deeper readiness checks arrive with SP02.

**Rollback drill.** A manual run has a `rollback_drill` input. When enabled, the deploy proceeds normally but the gate requests a path that does not exist, so it fails and the rollback runs for real. This proves the safety net works without shipping a broken image.

**Concurrency and environment.** A single `cd-productionize` concurrency group serializes deploys and never cancels one in flight (cancelling mid-deploy could leave traffic half-shifted). The job runs in a GitHub `production` environment, which is created automatically and can be given required reviewers for a manual approval gate.

**CD does not run CI.** CI and CD both start on a push to `productionize`, in parallel. CD therefore relies on branch protection: with CI required to pass before a PR can merge (see EPIC exit criteria), only code that already passed CI reaches the branch. Directly pushing to `productionize` bypasses this and should be disallowed.

**Terraform check.** The `Terraform fmt & validate` CI job (`fmt -check`, `init -backend=false`, `validate`) runs on every pull request, so an unformatted or invalid configuration never merges. It needs no cloud credentials.

## 4. Acceptance Criteria

| #    | Criterion                                                                                                                                                                                            |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1  | `.github/workflows/cd.yml` triggers on `push` to `productionize` and on `workflow_dispatch`.                                                                                                         |
| AC2  | Authentication uses Workload Identity Federation (`google-github-actions/auth` with `workload_identity_provider` and `service_account`); no JSON key or long-lived credential is used or referenced. |
| AC3  | The workflow requests `id-token: write` and otherwise only `contents: read`.                                                                                                                         |
| AC4  | `flight_api` and `hotel_api` images are built from the repository root and pushed to Artifact Registry tagged with the commit SHA.                                                                   |
| AC5  | Both services are deployed to Cloud Run from those images, and traffic is explicitly routed to the latest revision after each deploy.                                                                |
| AC6  | After deploying, the pipeline polls each service's `/health` URL and fails the job unless both return HTTP 200 within the timeout.                                                                   |
| AC7  | On failure after deployment started, traffic for both services is restored to the revisions recorded before the deploy, and the job still fails.                                                     |
| AC8  | The rollback drill (`workflow_dispatch` with `rollback_drill = true`) fails the gate, triggers the rollback, and the services keep serving the previous revisions with HTTP 200.                     |
| AC9  | A deploy after a rollback serves the new revision (traffic is restored to latest).                                                                                                                   |
| AC10 | Missing repository variables fail fast with an actionable message before any GCP call.                                                                                                               |
| AC11 | A Terraform `fmt -check` and `validate` job runs in CI (see TASK-1.4 AC11).                                                                                                                          |
| AC12 | `actionlint` reports no errors for `cd.yml` and `ci.yml`.                                                                                                                                            |

## 5. Verification Commands

Run from the repository root (PowerShell). Steps 1–2 need no cloud account; steps 3–7 require TASK-1.4 to be applied.

```powershell
# 1. Lint both workflows (AC12). Docker Desktop must be running.
docker run --rm -v "${PWD}:/repo" -w /repo rhysd/actionlint:latest -color        # expect: no output, exit code 0

# 2. Confirm no static credentials are referenced (AC2)
Select-String -Path .github/workflows/cd.yml -Pattern "credentials_json","GOOGLE_CREDENTIALS","service_account_key"   # expect: no output

# 3. Copy Terraform's outputs into GitHub repository variables (needs the GitHub CLI: winget install GitHub.cli; gh auth login)
$vars = terraform -chdir=infra/terraform output -json github_actions_variables | ConvertFrom-Json
$vars.PSObject.Properties | ForEach-Object { gh variable set $_.Name --body $_.Value }
gh variable list                                                  # expect: the five GCP_* variables

# 4. Real deploy (AC1, AC4, AC5, AC6): merge to productionize, or run manually on that branch
gh workflow run cd.yml --ref productionize
gh run watch                                                      # expect: green; the summary lists both service URLs

# 5. Verify the live services and the deployed image tag (AC4, AC5)
$flight = gcloud run services describe flight-api --region <region> --format "value(status.url)"
$hotel  = gcloud run services describe hotel-api  --region <region> --format "value(status.url)"
Invoke-RestMethod "$flight/health"                                # expect: status ok
Invoke-RestMethod "$hotel/health"                                 # expect: status ok
Invoke-RestMethod "$flight/flights?origin=BLR&destination=DEL"    # expect: AI101 and 6E202
gcloud run services describe flight-api --region <region> --format "value(spec.template.spec.containers[0].image)"   # expect: ...flight-api:<commit sha>

# 6. Rollback drill (AC7, AC8): the run must end RED, and the services must still be healthy afterwards
gcloud run services describe flight-api --region <region> --format "value(status.traffic[0].revisionName)"   # note this revision
gh workflow run cd.yml --ref productionize -f rollback_drill=true
gh run watch                                                      # expect: gate fails, "Roll back traffic" step succeeds, job red
gcloud run services describe flight-api --region <region> --format "value(status.traffic[0].revisionName)"   # expect: the same revision as before the drill
Invoke-RestMethod "$flight/health"                                # expect: still status ok

# 7. Deploy again after the drill (AC9): the new revision must receive traffic
gh workflow run cd.yml --ref productionize
gh run watch
gcloud run services describe flight-api --region <region> --format "value(status.traffic[0].latestRevision)"   # expect: True
```

## 6. Rollout & Rollback

- **Rollout:** merge the PR, apply TASK-1.4, set the repository variables (step 3), then push or run the workflow. Add required reviewers to the `production` environment if manual approval is wanted. Make the `Lint & Test` and `Terraform fmt & validate` checks required on `productionize`.
- **Automatic rollback:** described above; it needs no action.
- **Manual rollback of a bad deploy that passed the gate:** re-run the workflow on the last good commit (`workflow_dispatch` on `productionize` after reverting), or pin traffic by hand: `gcloud run services update-traffic <service> --to-revisions <revision>=100 --region <region>`. Remember the next deploy restores latest routing.
- **Disabling CD:** disable the workflow in the Actions tab, or revert `cd.yml`. Running services are unaffected.

## 7. Risks

| Risk                                                                                | Mitigation                                                                                                                         |
| ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| First run fails with a missing permission (least-privilege roles are narrow)        | The `gcloud` error names the permission; grant the narrowest resource-level role in Terraform and record it in TASK-1.4            |
| Workflow has not been executed against a real project in the authoring environment  | `actionlint` plus the rollback drill (steps 1 and 6) validate it before it is trusted                                              |
| A bad deploy passes `/health` but is functionally broken                            | The gate is a liveness check; deeper checks arrive with SP02 (DB) and SP06 (evals). Manual rollback is documented above            |
| CD and CI run in parallel on `productionize`                                        | Require CI on PRs and forbid direct pushes to the branch                                                                           |
| `allow_unauthenticated = false` breaks the gate (public URL no longer reachable)    | Adapt the gate to send an identity token, or run the gate from inside the project. Keep the default until SP03 adds app-level auth |
| Old images deleted by the registry cleanup policy break a rollback                  | Policy keeps the 10 newest versions per image, far more than any rollback target                                                   |
| Third-party actions (`google-github-actions/*`, `hashicorp/setup-terraform`) change | Pinned to major versions; Dependabot or a periodic review can move them to commit SHAs                                             |
| Two services deployed one after the other briefly run different versions            | Acceptable for read-only APIs that do not call each other; if a deploy fails, both roll back together                              |

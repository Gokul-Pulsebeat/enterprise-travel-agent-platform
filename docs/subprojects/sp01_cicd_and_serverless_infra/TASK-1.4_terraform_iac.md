# TASK-1.4 — Terraform Infrastructure as Code

| Field         | Value                                                                                          |
| ------------- | ---------------------------------------------------------------------------------------------- |
| Epic          | SP01 — CI/CD Pipelines, Dockerization & Serverless Terraform IaC                               |
| PR            | PR 2 of 2                                                                                      |
| Branch        | `feat/sp01-terraform-and-cd`                                                                   |
| Target branch | `productionize`                                                                                |
| Depends on    | TASK-1.2 (images), TASK-1.1 (CI)                                                               |
| Parent docs   | [`EPIC_PRD.md`](EPIC_PRD.md), [`00_MASTER_PRD.md`](../../00_MASTER_PRD.md)                     |

---

## 1. Objective

Describe the cloud environment as code so it can be reviewed, reproduced and destroyed. One `terraform apply` provisions everything the CD pipeline ([TASK-1.5](TASK-1.5_cd_pipeline.md)) needs to ship the two REST APIs to GCP Cloud Run: an image registry, the services themselves, secrets, least-privilege identities, and keyless authentication for GitHub Actions. It also provisions the managed Postgres (Neon) and Redis (Upstash) that SP02–SP05 will use, and wires their connection strings into the services through Secret Manager so no credential is ever committed or baked into an image.

## 2. Scope

### In scope

| Area                                       | Change                                                                                                                                       |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `infra/terraform/versions.tf`              | Terraform `>= 1.6`; providers `hashicorp/google ~> 6.0`, `kislerdm/neon ~> 0.6`, `upstash/upstash ~> 1.5`                                    |
| `infra/terraform/variables.tf`             | All inputs, with defaults chosen for the free tier; `github_repository` is validated                                                        |
| `infra/terraform/main.tf`                  | All resources (inventory below)                                                                                                              |
| `infra/terraform/outputs.tf`               | Registry path, service URLs, service accounts, the WIF provider, and a `github_actions_variables` map for the CD workflow                    |
| `infra/terraform/terraform.tfvars.example` | Documented inputs; credentials are supplied through `TF_VAR_*` environment variables, never in a file                                        |
| `infra/terraform/backend.tf.example`       | Inactive example of remote state in a GCS bucket                                                                                             |
| `.github/workflows/ci.yml`                 | New `Terraform fmt & validate` job                                                                                                           |
| `.gitignore`, `.dockerignore`              | Ignore Terraform state, plans, real `*.tfvars` and `.terraform/`; keep `infra/` out of images                                                |

### Resource inventory

| Group                | Resources                                                                                                                                                              |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| APIs                 | `google_project_service` for Artifact Registry, Cloud Run, Secret Manager, IAM, IAM Credentials, STS, Resource Manager                                                  |
| Registry             | `google_artifact_registry_repository` (Docker) with cleanup policies: keep the 10 newest versions, delete anything older than 30 days                                  |
| Compute              | `google_cloud_run_v2_service` ×2 (`flight-api` on 8000, `hotel-api` on 8001); scale to zero, capped at `max_instances`; secret-backed env vars                        |
| Secrets              | `google_secret_manager_secret` + version for `DATABASE_URL` and `REDIS_URL`                                                                                            |
| Third-party services | `neon_project` (Postgres 16, one branch/database/role) and `upstash_redis_database` (global, free tier); each can be disabled with `enable_neon` / `enable_upstash`    |
| Identities           | Runtime service account per service; one `github-deployer` service account                                                                                            |
| IAM                  | Resource-level bindings only (table below)                                                                                                                             |
| Federation           | `google_iam_workload_identity_pool` + OIDC provider for GitHub, bound to your repository and the `productionize` branch                                               |

### Out of scope

- **Running `terraform apply`.** Infrastructure is applied by a person from a trusted machine. The CD pipeline only deploys application images (TASK-1.5). Automated apply is a possible later task.
- Creating the remote-state bucket (documented in `backend.tf.example`; a bucket cannot be managed by the Terraform that stores its state in it).
- Applications reading `DATABASE_URL` / `REDIS_URL`. The secrets are injected now; SP02 and SP03/SP04 consume them.
- Custom domains, private networking/VPC connectors, WAF, alerting and dashboards.
- Authenticated (non-public) service invocation. That arrives with JWT auth in SP03.

## 3. Architectural Notes

**Ownership split with CD.** Terraform cannot create a Cloud Run service without an image, and the registry that will hold that image is created by the same apply. The services are therefore created with Google's public `hello` image as a placeholder, and `lifecycle.ignore_changes` hands the container image, revision name, revision labels/annotations, client metadata and traffic routing to the CD pipeline. Without this, every `terraform apply` would revert the last deploy, and would undo a rollback (which pins traffic to an old revision). The placeholder works with the real port wiring because Cloud Run sets `PORT` to the configured container port, and the startup probe is a TCP check that passes for both the placeholder and the real API.

**Least-privilege identities.**

| Principal                         | Role                                  | Scope                                         | Why                                                          |
| --------------------------------- | ------------------------------------- | --------------------------------------------- | ------------------------------------------------------------ |
| `flight-api-runtime`, `hotel-api-runtime` | `secretmanager.secretAccessor` | Only the two secrets                          | Runtime reads its config and nothing else                    |
| `github-deployer`                 | `artifactregistry.writer`             | The one repository                            | Push images                                                  |
| `github-deployer`                 | `run.developer`                       | Each of the two services                      | Deploy revisions and shift traffic (including rollback)      |
| `github-deployer`                 | `iam.serviceAccountUser`              | Each runtime service account                  | Required to deploy a revision that runs as that account      |
| GitHub OIDC principal             | `iam.workloadIdentityUser`            | The deployer service account                  | Lets the federated identity impersonate the deployer         |
| `allUsers`                        | `run.invoker`                         | Each service (when `allow_unauthenticated`)   | Public HTTP access; the APIs have no auth until SP03         |

No project-level roles are granted to any service account. The deployer cannot create or delete services, read secrets, or touch other repositories or services.

**Workload Identity Federation.** GitHub issues each workflow run an OIDC token. The provider accepts only tokens where `assertion.repository` equals `github_repository` **and** `assertion.ref` equals `refs/heads/<deploy_branch>` (default `productionize`), so a fork, another repository, or a feature branch cannot obtain credentials. No JSON key is created or stored anywhere. The pool also maps `attribute.repository`, which the service-account binding uses.

**Secrets flow.** `neon_project.connection_uri` and the assembled `rediss://` URL are written to Secret Manager and mounted as `DATABASE_URL` and `REDIS_URL` with `version = latest`. They never appear in the repository, the image, the workflow logs, or Cloud Run's plain-text configuration. They **do** appear in Terraform state, which is why state must be protected (see below).

**State.** Local state is acceptable for a first run. Because state contains secrets, anything shared or long-lived should use the GCS backend in `backend.tf.example`: an encrypted, versioned bucket with access limited to the people who run Terraform. State, plans and real `*.tfvars` are gitignored.

**Third-party providers.** Neon and Upstash have no first-party Terraform providers; this task uses the community `kislerdm/neon` and the Upstash `upstash/upstash` provider, both configured from credentials passed as sensitive variables (`TF_VAR_neon_api_key`, `TF_VAR_upstash_email`, `TF_VAR_upstash_api_key`; Neon also honors `NEON_API_KEY`). Each is switchable with an `enable_*` flag. When a flag is `false` the resources and secret are skipped and the env var is not injected, but the provider block is still configured, so a placeholder credential may still be needed to run `plan`.

**Cost controls (free-tier friendly).** Cloud Run scales to zero and is capped at 2 instances per service with 1 vCPU / 512 MiB; Artifact Registry cleanup policies bound storage; Secret Manager holds two secret versions; Neon and Upstash use their free plans. The Cloud Run free tier still requires billing to be enabled on the project. The default region `us-central1` is a low-cost tier; change `region`, `neon_region_id` and `upstash_primary_region` together if lower latency to another geography matters more than cost.

**Public access trade-off.** With `allow_unauthenticated = true` anyone can call the read-only demo APIs, and the CD health gate polls the public URL. That is acceptable for mock inventory and is superseded by JWT authentication in SP03. An organization policy that restricts public IAM members (domain-restricted sharing) will reject the `allUsers` binding; set the variable to `false` in that case and adapt the health gate to use an identity token.

**Provider lock file and platforms.** `.terraform.lock.hcl` pins provider versions and is committed. A lock file generated on Windows contains only Windows checksums and makes `terraform init` fail on the Linux CI runner (the same class of problem as the pip lockfile in TASK-1.1). Generate it for every platform with `terraform providers lock` (command below).

**Formatting and validation in CI.** The `Terraform fmt & validate` job runs `terraform fmt -check -recursive`, `init -backend=false`, and `validate` with no credentials, on every pull request.

## 4. Acceptance Criteria

| #    | Criterion                                                                                                                                                                      |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| AC1  | `infra/terraform/` contains `versions.tf`, `variables.tf`, `main.tf`, `outputs.tf` and `terraform.tfvars.example`.                                                              |
| AC2  | `terraform fmt -check -recursive` passes.                                                                                                                                      |
| AC3  | `terraform init -backend=false` and `terraform validate` succeed with no credentials.                                                                                          |
| AC4  | The configuration defines an Artifact Registry repository, two Cloud Run services (`flight-api`, `hotel-api`), two Secret Manager secrets, runtime service accounts, a deployer service account, and a Workload Identity pool and provider. |
| AC5  | No service account has a project-level role; every binding is on a specific repository, service, secret or service account.                                                    |
| AC6  | The WIF provider's condition restricts access to the configured repository **and** the deploy branch; no service-account key resource exists anywhere.                         |
| AC7  | Neon and Upstash are configured as providers and their connection strings are stored in Secret Manager and injected as `DATABASE_URL` / `REDIS_URL`; no secret value appears in any committed file. |
| AC8  | Cloud Run ignores image, revision-name, traffic, and revision-metadata changes (`ignore_changes`), so `terraform plan` after a CD deploy shows no diff for those attributes.    |
| AC9  | `outputs.tf` exposes the values the CD workflow needs (`github_actions_variables`), and none of them are secrets.                                                              |
| AC10 | `.gitignore` excludes `.terraform/`, `*.tfstate*`, plans and `*.tfvars`; `.terraform.lock.hcl` is committed and covers `linux_amd64` and the developer's platform.            |
| AC11 | CI runs a `Terraform fmt & validate` job on every pull request and it passes.                                                                                                  |
| AC12 | *(Manual, after review)* `terraform plan` against a real project is clean and `terraform apply` creates the resources; GitHub repository variables are set from `terraform output`. |

## 5. Verification Commands

Run from the repository root (PowerShell). Steps 1–3 need no cloud account.

```powershell
# 0. Install the tools once
winget install Hashicorp.Terraform
terraform version                                                 # expect: 1.6 or newer

# 1. Format check (AC2). If it reports files, run the fix and re-check.
terraform -chdir=infra/terraform fmt -check -recursive -diff
terraform -chdir=infra/terraform fmt -recursive                   # only if the check above failed

# 2. Initialize without a backend and validate (AC3)
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform validate                         # expect: Success! The configuration is valid.

# 3. Generate a cross-platform provider lock file, then commit it (AC10)
terraform -chdir=infra/terraform providers lock -platform=linux_amd64 -platform=windows_amd64 -platform=darwin_arm64
git status --short infra/terraform                                # expect: .terraform.lock.hcl present; no *.tfstate, no *.tfvars

# 4. Confirm secrets and state are ignored (AC10)
git check-ignore -v infra/terraform/terraform.tfvars infra/terraform/terraform.tfstate infra/terraform/.terraform

# 5. Confirm no key material exists (AC6)
Select-String -Path infra/terraform/*.tf -Pattern "service_account_key","private_key"   # expect: no output

# 6. Plan against a real project (AC12). Needs a GCP project with billing, a Neon API key and an Upstash key.
gcloud auth login
gcloud auth application-default login
gcloud config set project <your-project-id>
Copy-Item infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars   # then edit project_id and github_repository
$env:TF_VAR_neon_api_key    = "<neon-api-key>"
$env:TF_VAR_upstash_email   = "<upstash-email>"
$env:TF_VAR_upstash_api_key = "<upstash-api-key>"
terraform -chdir=infra/terraform plan -out tfplan                 # review carefully; nothing is created yet

# 7. Apply (only when the plan looks right), then read the values for GitHub (AC9, AC12)
terraform -chdir=infra/terraform apply tfplan
terraform -chdir=infra/terraform output github_actions_variables

# 8. After a CD deploy (TASK-1.5), the plan must show no changes to image or traffic (AC8)
terraform -chdir=infra/terraform plan                             # expect: No changes (or only unrelated drift)
```

## 6. Rollout & Rollback

- **Rollout:** merge the PR (CI validates the configuration), then apply from a trusted machine as in step 7, set the GitHub repository variables from the outputs, and push to `productionize` to trigger the first deploy.
- **Rollback:** infrastructure changes are reverted by reverting the commit and applying again. `terraform destroy` removes everything (set `deletion_protection = true` for production-like use). Note that deleted Workload Identity pools and providers are soft-deleted for 30 days, so recreating one with the same ID right after a destroy fails until it is undeleted or an ID is changed.

## 7. Risks

| Risk                                                                                                                        | Mitigation                                                                                                                              |
| --------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Community-provider schemas (Neon, Upstash) can change between releases; attribute names were not checked against a live `init` in the authoring environment | `terraform validate` in CI and locally catches schema errors immediately; provider versions are constrained and pinned by the lock file |
| Hand-formatted HCL may differ from `terraform fmt` output                                                                    | Run `terraform fmt -recursive` once and commit; CI keeps it enforced                                                                    |
| Secrets are stored in Terraform state                                                                                       | Use the GCS backend with restricted access; never commit state; rotate by re-applying                                                   |
| Least-privilege roles may omit a permission the first deploy needs                                                           | The error names the missing permission; add the narrowest role at resource level and document it here                                   |
| Org policy blocks `allUsers`                                                                                                | Set `allow_unauthenticated = false` and adapt the health gate (see TASK-1.5 risks)                                                      |
| Lock file generated on one OS fails on another                                                                              | Generate it with `providers lock` for all platforms (step 3)                                                                            |
| Free-tier limits change                                                                                                     | Cost controls are variables; billing alerts are recommended on the GCP project                                                         |

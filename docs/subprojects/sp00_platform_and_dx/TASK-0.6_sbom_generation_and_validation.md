# TASK-0.6 — Software Bill of Materials (SBOM): Generation, Validation and Vulnerability Gating

| Field         | Value                                                                                                                                                                                                        |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Epic          | SP00 — Platform, DX & Repo Standardization                                                                                                                                                                   |
| PR            | Single PR (feat)                                                                                                                                                                                             |
| Branch        | `feat/sp00-t06-sbom`                                                                                                                                                                                         |
| Target branch | `productionize`                                                                                                                                                                                              |
| Status        | **Fully specified; implementation deferred.** Writing this document changes no code and no configuration                                                                                                     |
| Sequencing    | Any time; recommended before SP03, when the dependency footprint grows (HTTP MCP transport, auth, Redis)                                                                                                     |
| Depends on    | TASK-0.1 (pinned lockfile), SP01 (CI, CD, Dockerfiles)                                                                                                                                                       |
| Related       | [`00_MASTER_PRD.md`](../../00_MASTER_PRD.md), [`02_AI_AND_MCP_SECURITY_THREAT_MODEL.md`](../../02_AI_AND_MCP_SECURITY_THREAT_MODEL.md) (supply chain controls), SP06 AI-BOM (reuses this format and tooling) |

---

## 1. Objective

Know, at any moment and for any deployed version, **exactly what the software contains**: every Python package (direct and transitive) and every operating-system package inside each container image, with versions, licenses and identifiers. Generate that inventory automatically on every CI run, **validate** it (it is well-formed, complete, and meets minimum-element quality), **use it** to gate known vulnerabilities and disallowed licenses, and keep it as a build artifact. The whole chain uses open-source tools and the free GitHub Actions allowance: **$0**.

An SBOM that is generated but never checked is decoration. The validation and scanning stages are what make it a control.

## 2. Scope

### In scope

| Area                               | Change                                                                                                                                                                                                                                                           |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dependency SBOM (CI)               | On every CI run, generate a CycloneDX JSON SBOM from the repository's pinned dependencies (`requirements.txt`), then validate, scan and publish it                                                                                                               |
| Image SBOMs (CD, and CI on change) | Generate a CycloneDX JSON SBOM for each image (`flight-api`, `hotel-api`, `agent`) covering OS packages and Python packages; scan before deploy; publish as a workflow artifact. CI builds and scans the images only when Dockerfiles or dependency files change |
| Validation stages                  | Schema check, lockfile completeness check, NTIA minimum-elements quality check, vulnerability gate, license policy (3.3)                                                                                                                                         |
| Policy files (new)                 | `security/vulnerability-ignore.yaml` (justified, expiring exceptions) and `security/license-policy.yaml` (allow-list and deny-list)                                                                                                                              |
| `scripts/` (new)                   | A small completeness checker (compares `requirements.txt` pins with the SBOM) and a license-policy checker, both runnable locally and in CI                                                                                                                      |
| `.github/workflows/`               | A reusable SBOM job in `ci.yml`; image SBOM steps in `cd.yml`; tool versions pinned by digest                                                                                                                                                                    |
| Docs                               | `README.md`: where SBOMs come from, how to generate and read one locally, and how to request a vulnerability exception                                                                                                                                           |
| Optional, public repos only        | Signed SBOM attestations (3.6)                                                                                                                                                                                                                                   |

### Out of scope

- The **AI-BOM** (models, prompts, tools, datasets): SP06 TASK-6.6. It reuses this format and these validators.
- Automated dependency updates (Dependabot or Renovate): a candidate backlog item; see 3.8 for why it needs care with the Linux-compiled lockfile.
- Secret scanning, static analysis (SAST) and Terraform security scanning: separate backlog candidates in the SP00 epic.
- Paid or hosted platforms (Snyk, Dependency-Track SaaS, GitHub Advanced Security): not used.
- Publishing SBOMs to customers or registries as OCI referrers.

## 3. Architectural Notes

### 3.1 What is produced, and why two kinds

| SBOM                | Describes                                                                                        | Generated from                  | Answers                                                                                          |
| ------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Dependency SBOM** | The Python packages the project pins (direct and transitive)                                     | The lockfile `requirements.txt` | "Which versions of which libraries does this commit depend on?" Fast, runs on every PR           |
| **Image SBOM**      | Everything inside a built image: base-image OS packages, Python packages, the application layers | The built container image       | "What is actually running in production?" Catches vulnerable OS packages the lockfile cannot see |

Both matter: a clean lockfile can still ship a vulnerable `libssl` from the base image, and an image scan cannot tell you which `requirements.in` change introduced a package.

### 3.2 Format and tools (all free and open source)

**Format: CycloneDX JSON.** It is a mature standard, well supported by free validators, and, importantly, the same format the SP06 AI-BOM will use (CycloneDX supports machine-learning components), so one toolchain validates both. SPDX is an acceptable alternative; GitHub's own dependency-graph export is SPDX and can serve as an independent cross-check.

| Stage           | Tool (open source)                  | Notes                                                                                    |
| --------------- | ----------------------------------- | ---------------------------------------------------------------------------------------- |
| Generate        | **Syft**                            | One tool for both the lockfile and the images; emits CycloneDX                           |
| Validate schema | **CycloneDX CLI**                   | Fails on a malformed or schema-invalid document                                          |
| Quality         | **sbomqs**                          | Scores the SBOM against NTIA minimum elements and other profiles                         |
| Vulnerabilities | **Grype** (reads the SBOM as input) | Proves the SBOM is usable; a second opinion from `pip-audit` on the lockfile is optional |
| Completeness    | A short in-repo script              | The one check no off-the-shelf tool does: every pin in the lockfile is in the SBOM       |

Tools run from **pinned versions or image digests**, not `latest`: the scanners are themselves part of the supply chain. Exact versions are chosen and verified at implementation.

### 3.3 Validation stages (the control)

| #   | Stage               | Passes when                                                                                                                                                                                                                 | Failure means                             |
| --- | ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| 1   | **Schema**          | The document validates against the CycloneDX JSON schema                                                                                                                                                                    | The generator or format is broken         |
| 2   | **Completeness**    | Every `name==version` in `requirements.txt` appears in the SBOM with the same version and a package URL (`purl`); no duplicate `bom-ref`; the application itself is `metadata.component` with the commit SHA as its version | The SBOM does not match what is installed |
| 3   | **Quality**         | sbomqs reports the NTIA minimum elements present (supplier, component name, version, unique identifier, dependency relationships, SBOM author, timestamp) at or above an agreed score                                       | The SBOM is too thin to be useful         |
| 4   | **Vulnerabilities** | No known vulnerability at or above the gate severity that has a fix available, except entries in `security/vulnerability-ignore.yaml`                                                                                       | A dependency or base image needs updating |
| 5   | **Licenses**        | Every license is on the allow-list; none is on the deny-list; unknown licenses warn                                                                                                                                         | A license conflicts with project policy   |
| 6   | **Publish**         | The SBOM and the scan reports are uploaded as workflow artifacts (`if: always()`) and summarized in the job summary                                                                                                         | (not a gate; for traceability)            |

### 3.4 Vulnerability policy

- **Pull requests (CI):** fail on **High or Critical** findings **with a fix available**. Findings without a fix are reported but do not block (nothing can be done yet).
- **Deploys (CD):** fail only on **Critical with a fix available**. A newly published High in a base image should not block an unrelated urgent fix; it is caught by the next PR's gate.
- **Exceptions:** `security/vulnerability-ignore.yaml`. Every entry needs the identifier, a written justification (for example "not reachable: the vulnerable function is never called"), and an **expiry date**, so exceptions cannot become permanent. CI fails on an expired entry.
- **Vulnerability database freshness:** Grype downloads its database on each run. If the download fails, the stage fails closed on pull requests and warns on deploys, so an outage of the database cannot silently disable the gate or block an emergency deploy.
- **Reachability caveat:** an SBOM scan reports vulnerable components, not exploitable behavior. The exceptions file is where a human records that judgment.

### 3.5 License policy

An allow-list of permissive licenses (for example MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0) and a deny-list of licenses that would impose obligations on distributing the images (for example GPL and AGPL families) in `security/license-policy.yaml`. Unknown or missing licenses produce a warning, because many packages declare licenses imperfectly. The checker reads licenses from the SBOM, so it needs no second pass over the packages.

### 3.6 Placement, cost and attestations

- **CI (every PR):** the dependency SBOM, all six stages. Cost is well under a minute of runner time.
- **CI (path-filtered):** build and scan the three images only when `Dockerfile`s, `requirements.in`, `requirements.txt` or `common/` change, to protect the free Actions minutes (a private repository gets 2,000 a month).
- **CD (every deploy):** build, **generate the image SBOM and scan before pushing**, so a vulnerable image is never published. This reuses the images CD already builds.
- **Retention:** artifacts use GitHub's default retention; long-term history is not needed because every SBOM can be regenerated from a commit.
- **Attestations (conditional):** GitHub artifact attestations (signed provenance and signed SBOM attestations) are available for **public repositories on all current plans, but private repositories require GitHub Enterprise Cloud**. They are therefore **enabled only when the repository is public** (`github.event.repository.private == false`) and skipped otherwise, so the task never silently depends on a paid plan. The attestation action takes the SBOM as an input and the result can be verified with the GitHub CLI. How attestations interact with images stored in Artifact Registry (as opposed to GHCR) is verified at implementation.

### 3.7 Safety of the SBOM itself

An SBOM contains package names and versions, not secrets. In a public repository it is public, which is acceptable and standard. CI logs and the job summary must not print environment variables. The `security/` policy files are reviewed like code, because an over-broad exception defeats the gate.

### 3.8 Relationship to other work

- **Dependabot or Renovate** is the natural companion (the gate finds problems, the bot proposes fixes), but this repository's lockfile is compiled in a Linux container and checked for parity in CI, so a bot must either run the same compile step or open PRs against `requirements.in`. That integration is a separate task.
- **AI-BOM (SP06):** the AI-BOM is a CycloneDX document describing models, prompts, tools (including every MCP server, modeled as a service) and datasets. It is validated with the same CycloneDX tooling and may be merged with the SBOM into one release inventory.
- **Threat model:** this task implements the supply-chain controls for LLM04 (Supply Chain) and ASI04 (Agentic Supply Chain) in the [threat model](../../02_AI_AND_MCP_SECURITY_THREAT_MODEL.md).

## 4. Acceptance Criteria

| #    | Criterion                                                                                                                                                                               |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1  | Every CI run generates a CycloneDX JSON dependency SBOM from `requirements.txt` with Syft (or an equivalent open-source generator).                                                     |
| AC2  | The SBOM passes CycloneDX schema validation in CI.                                                                                                                                      |
| AC3  | The completeness check fails when a lockfile pin is missing from the SBOM or has a different version (demonstrated by a deliberately broken SBOM).                                      |
| AC4  | The quality check runs and the agreed minimum score is enforced.                                                                                                                        |
| AC5  | The vulnerability stage fails a pull request on a fixable High or Critical finding (demonstrated with a known-vulnerable pin on a scratch branch) and passes after the pin is fixed.    |
| AC6  | Exceptions in `security/vulnerability-ignore.yaml` require an identifier, a justification and an expiry; CI fails on an expired entry.                                                  |
| AC7  | The license policy fails on a denied license and warns on an unknown one.                                                                                                               |
| AC8  | CD generates an SBOM for each of the three images, scans it **before** the push, and blocks the deploy only on a fixable Critical finding; SBOMs and reports are uploaded as artifacts. |
| AC9  | CI builds and scans the images only when Dockerfiles or dependency files change.                                                                                                        |
| AC10 | SBOMs and scan reports are uploaded as artifacts on every run (`if: always()`) and summarized in the job summary.                                                                       |
| AC11 | All tools are pinned by version or digest; no tool is run from `latest`.                                                                                                                |
| AC12 | Signed SBOM attestations are produced only for a public repository and skipped without error for a private one.                                                                         |
| AC13 | No paid service, account, token or plan is introduced; the added CI time is recorded in the results table.                                                                              |
| AC14 | `README.md` explains how to generate and read an SBOM locally, and how to request, justify and expire a vulnerability exception.                                                        |

### Results (recorded at implementation)

| Item                                                 | Measured |
| ---------------------------------------------------- | -------- |
| Components in the dependency SBOM                    |          |
| Components in each image SBOM (flight, hotel, agent) |          |
| Added CI time per pull request (dependency SBOM)     |          |
| Added CI time when images are built and scanned      |          |
| Findings on first run, and how each was resolved     |          |

## 5. Verification Commands

Run after implementation, from the repository root (PowerShell). Docker Desktop must be running. Image tags below are placeholders for the pinned versions chosen at implementation.

```powershell
# 0. Generate the dependency SBOM locally from the lockfile (AC1)
docker run --rm -v "${PWD}:/src" anchore/syft:<pinned> scan file:/src/requirements.txt -o cyclonedx-json=/src/sbom-dependencies.cdx.json
(Get-Content sbom-dependencies.cdx.json | ConvertFrom-Json).components.Count        # expect: one component per pinned package

# 1. Validate the schema (AC2)
docker run --rm -v "${PWD}:/src" cyclonedx/cyclonedx-cli:<pinned> validate --input-file /src/sbom-dependencies.cdx.json --input-format json   # expect: BOM validated successfully

# 2. Completeness against the lockfile (AC3)
python scripts/check_sbom_completeness.py requirements.txt sbom-dependencies.cdx.json   # expect: all pins present
#    Drill: delete one component from a copy of the SBOM and re-run. Expect a failure naming that package.

# 3. Quality (AC4)
docker run --rm -v "${PWD}:/src" ghcr.io/interlynk-io/sbomqs:<pinned> score /src/sbom-dependencies.cdx.json   # expect: a score at or above the agreed minimum

# 4. Vulnerability gate from the SBOM (AC5)
docker run --rm -v "${PWD}:/src" anchore/grype:<pinned> sbom:/src/sbom-dependencies.cdx.json --fail-on high --only-fixed   # expect: exit code 0 on a clean tree
#    Drill: on a scratch branch pin a package to a version with a known fix available; expect a non-zero exit code.

# 5. Exceptions and licenses (AC6, AC7)
python scripts/check_vulnerability_exceptions.py security/vulnerability-ignore.yaml   # expect: fails on an entry with a past expiry date
python scripts/check_licenses.py sbom-dependencies.cdx.json security/license-policy.yaml   # expect: fails on a denied license, warns on unknown

# 6. Image SBOM and scan (AC8): build one image, generate, scan
docker build -f flight_api/Dockerfile -t travel-agent/flight-api:sbom-test .
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock anchore/syft:<pinned> travel-agent/flight-api:sbom-test -o cyclonedx-json > sbom-flight-api.cdx.json
(Get-Content sbom-flight-api.cdx.json | ConvertFrom-Json).components.Count          # expect: far more than the dependency SBOM (OS packages included)
docker run --rm -v "${PWD}:/src" anchore/grype:<pinned> sbom:/src/sbom-flight-api.cdx.json --fail-on critical --only-fixed

# 7. CI and CD behavior (AC8-AC10, AC12)
git push -u origin feat/sp00-t06-sbom
#    Expect in the PR's checks: SBOM job green, artifacts attached (sbom, scan report), summary table in the job summary.
#    Change a Dockerfile in a scratch commit: expect the image SBOM job to run; revert: expect it skipped.
#    After the first CD run: expect three image SBOM artifacts, produced before the push step.

# 8. Clean up
Remove-Item sbom-*.cdx.json
```

## 6. Rollout & Rollback

- **Rollout:** merge the PR. Run the new job as **report-only for the first week** (the vulnerability stage warns instead of failing), fix or justify the first findings, then switch the gate to blocking. Add the SBOM job to the required status checks.
- **Rollback:** disable the SBOM job and the CD steps, or revert the PR. Nothing at runtime depends on this task.
- **Emergency deploy:** because CD blocks only on fixable Critical findings, a blocked deploy is resolved by updating the dependency or base image, or by adding a justified, expiring exception through a reviewed PR.

## 7. Risks

| Risk                                                                      | Mitigation                                                                                                            |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| A new CVE in the base image blocks an unrelated deploy                    | CD blocks only fixable Critical; High is caught by the next PR; time-boxed exceptions exist; report-only rollout week |
| False positives and findings with no reachable code create noise          | The exceptions file with justification and expiry; findings without a fix do not block                                |
| The vulnerability database cannot be downloaded                           | Fail closed on pull requests, warn on deploys, so neither a silent bypass nor a blocked emergency fix                 |
| Added CI time or free-minute use                                          | Dependency SBOM is seconds; image jobs are path-filtered; durations are recorded in the results table                 |
| An SBOM generated from the lockfile misses packages installed another way | The image SBOM covers what is really installed; the completeness check ties the lockfile to the SBOM                  |
| License metadata is incomplete, so the policy mis-fires                   | Unknown licenses warn rather than fail; the allow-list is reviewed when warnings recur                                |
| The scanning tools are themselves compromised or changed                  | Pinned versions and digests; tool updates are reviewed changes                                                        |
| Attestations require a plan that costs money for private repositories     | Conditional on the repository being public; skipped otherwise; AC12 checks both paths                                 |
| Policy files drift into permanent exceptions                              | Mandatory expiry and a CI failure on expired entries                                                                  |

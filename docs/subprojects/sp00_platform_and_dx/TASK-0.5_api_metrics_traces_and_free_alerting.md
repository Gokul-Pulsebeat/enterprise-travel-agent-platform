# TASK-0.5 — API Metrics, Traces and Free Alerting

| Field         | Value                                                                                                                           |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Epic          | SP00 — Platform, DX & Repo Standardization                                                                                      |
| PR            | Single PR (feat); second of two observability tasks, after [`TASK-0.4`](TASK-0.4_api_logging_foundation.md)                     |
| Branch        | `feat/sp00-t05-api-metrics-traces-alerting`                                                                                     |
| Target branch | `productionize`                                                                                                                 |
| Status        | **Fully specified; implementation deferred.** Writing this document changes no code and no configuration                        |
| Sequencing    | Planned after TASK-0.4 and before SP02 TASK-2.3, so booking locks and retries are measurable from their first release           |
| Depends on    | TASK-0.4 (structured logs, request correlation), SP01 (Terraform, Cloud Run, CD), SP02 TASK-2.1 (async APIs, `common/` package) |
| Parent docs   | [`EPIC_PRD.md`](EPIC_PRD.md), [`00_MASTER_PRD.md`](../../00_MASTER_PRD.md)                                                      |

---

## 1. Objective

Logs say what happened; metrics and traces say how the service is behaving and where time goes. This task adds **traces, a small set of custom metrics, a dashboard and alerting** for the business APIs, under a strict constraint: **$0**. That constraint drives the design, because several obvious choices are not free (OTLP-style metrics have no free tier, and alerting policies become chargeable). The task therefore picks the free paths deliberately and documents the exact setup steps, including the optional alerts that will start costing money.

## 2. Scope

### In scope

| Area                                       | Change                                                                                                                                                                                                   |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `requirements.in`                          | OpenTelemetry API and SDK, the FastAPI and SQLAlchemy instrumentations, and the Google Cloud trace and monitoring exporters and resource detector (exact list in 3.1)                                    |
| `common/telemetry.py` (proposed)           | One `configure_telemetry()` for every service: tracer provider, meter provider, sampler, exporters, shutdown flush; a tiny helper for declaring metrics so later tasks add business metrics consistently |
| `flight_api/app.py`, `hotel_api/app.py`    | Call `configure_telemetry()` in the lifespan; instrument FastAPI and SQLAlchemy; record the metric catalog (3.4)                                                                                         |
| `common/logging_config.py` (from TASK-0.4) | Trace and span fields now come from the active span instead of the inbound header, so logs and traces join exactly                                                                                       |
| `infra/terraform/`                         | New `observability.tf` and variables: APIs, runtime IAM, dashboard, notification channel, uptime checks with alert, optional budget alert; optional (default off) chargeable alert policies              |
| Free alerting set                          | Error Reporting notifications, uptime-check alerts, a billing budget alert, an optional scheduled GitHub probe (3.7, Appendix A)                                                                         |
| Tests                                      | In-memory exporter tests for spans and metrics; configuration and failure-mode tests (3.10)                                                                                                              |
| `.env.example`, `README.md`                | Telemetry settings and where to look: dashboard, trace explorer, Error Reporting                                                                                                                         |

### Out of scope

- Agent, LLM and MCP-specific telemetry (token cost, model latency, evals): SP06. It reuses the pipeline built here.
- Instrumenting the MCP servers: they become HTTP services in SP03 and adopt this foundation then; propagating `traceparent` from the agent through the MCP layer to the APIs is part of that work.
- Any paid or third-party backend (Grafana Cloud, Datadog, Langfuse for API telemetry), SLO burn-rate alerting, and Cloud Profiler.
- Business metrics themselves (`bookings`, `lock wait`, `idempotent replays`, `emails`): the helper is built here, and TASK-2.3 to 2.5 define and record their own as acceptance criteria.

## 3. Architectural Notes

### 3.1 Pipeline and library choices

| Signal  | Mechanism                                                  | Backend          | Why this path                                                                                   |
| ------- | ---------------------------------------------------------- | ---------------- | ----------------------------------------------------------------------------------------------- |
| Traces  | OpenTelemetry SDK, `opentelemetry-exporter-gcp-trace`      | Cloud Trace      | The first 2.5 million spans per billing account each month are free                             |
| Metrics | OpenTelemetry SDK, `opentelemetry-exporter-gcp-monitoring` | Cloud Monitoring | Writes classic custom metrics, which are **byte-metered with 150 MiB per billing account free** |
| Logs    | structlog to stdout (TASK-0.4)                             | Cloud Logging    | Already free within 50 GiB per project per month                                                |

**Do not use the OTLP/Prometheus-format metrics path.** Google bills Prometheus-format data per sample with **no free allotment**, and "most OTLP metrics" fall into that category. The Google exporter used here writes through the Monitoring API as ordinary custom metrics, which keeps the 150 MiB free tier. A guardrail (3.9) measures ingestion so a library or endpoint change cannot silently move the project onto the paid path.

**Packages (to be pinned by the lockfile):** `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy`, `opentelemetry-exporter-gcp-trace`, `opentelemetry-exporter-gcp-monitoring`, `opentelemetry-resourcedetector-gcp`, `opentelemetry-propagator-gcp`. SQLAlchemy is instrumented rather than asyncpg, so each statement produces one span, not two.

### 3.2 What Cloud Run already gives for free (do not rebuild it)

Google Cloud system metrics are free to view and alert on, and Cloud Run publishes the operational basics: request count by response-code class, request latency distribution, instance count, container CPU and memory utilization, and container start-up latency. The dashboard and the quick "is it healthy" questions use these. Custom metrics are added only for what the platform cannot know: database behavior and, later, business outcomes.

### 3.3 Traces

- **Instrumentation:** the FastAPI instrumentation produces one server span per request named by route template; the SQLAlchemy instrumentation produces one span per statement.
- **Excluded:** `/health` and `/ready` (probe noise).
- **Sampling:** a parent-based sampler. A request already sampled upstream stays sampled; a request with no parent is sampled at `TRACE_SAMPLE_RATIO` (default `0.25`). Errors are always interesting, so the ratio is configurable and can be raised temporarily.
- **Span budget:** a request produces roughly 5 spans (one server span plus about 4 statements). At 25% sampling, 100,000 requests a month is about 125,000 spans, roughly 5% of the free 2.5 million. The formula `requests x spans per request x ratio` goes in the README so the budget can be rechecked as traffic grows.
- **Attributes:** route template, method, status class, service, revision. **Never** SQL parameters, query strings, headers, bodies or personal data. The statement text is the parameterized fingerprint only.
- **Propagation:** W3C `traceparent` in and out; the GCP propagator also reads Cloud Run's `X-Cloud-Trace-Context`.
- **Log correlation:** the structlog processor reads the active span, so `logging.googleapis.com/trace` and `spanId` are exact for every log line, and the log viewer links straight to the trace.

### 3.4 Custom metrics

Labels must be **bounded** (service, route template, status class, result). Never a user, booking or flight ID.

| Metric (proposed name)          | Type      | Labels                        | Purpose                                                                                  |
| ------------------------------- | --------- | ----------------------------- | ---------------------------------------------------------------------------------------- |
| `db.client.operation.duration`  | histogram | service, operation            | Query latency by kind (`select`, `insert`, `update`), the first thing to check when slow |
| `db.pool.connections`           | gauge     | service, state (in_use, idle) | Pool saturation before it becomes `pool_exhausted` errors                                |
| `app.startup.duration`          | gauge     | service                       | How long migrations and seeding take on a cold start (feeds the Cloud Run probe budget)  |
| `app.migrations.duration`       | gauge     | service, outcome              | Migration time and result per revision                                                   |
| _(later)_ `bookings.total`      | counter   | service, result               | TASK-2.3: success, conflict, failure                                                     |
| _(later)_ `booking.lock_wait`   | histogram | service                       | TASK-2.3: time waiting on row locks                                                      |
| _(later)_ `idempotency.replays` | counter   | service                       | TASK-2.4: duplicate requests absorbed                                                    |
| _(later)_ `email.sent.total`    | counter   | result                        | TASK-2.5: notification outcomes                                                          |

HTTP request rate, latency and errors are **not** custom metrics; Cloud Run's system metrics cover them (3.2).

**Byte budget.** Classic custom metrics count about 8 bytes per numeric point and about 80 bytes per distribution point (verify against the pricing page at implementation). At a 60-second export interval, a series that is exported all month is about 43,000 points: roughly 0.35 MB for a gauge or counter and 3.5 MB for a histogram. The initial catalog (about 24 simple series and 8 histograms across two services) is about 36 MB a month, around a quarter of the free 150 MiB, even assuming the services never scale to zero. Rule: keep the total under about 100 MiB, add a metric only with its label set justified in review, and check the real figure after deployment (3.9).

### 3.5 Cloud Run behavior that affects exporters

With request-based billing, a Cloud Run instance's CPU is throttled between requests, so a background exporter thread can stall until the next request, and an instance that scales to zero may be stopped with unsent data. Mitigations, all free: a 60-second export interval; `force_flush` on the lifespan's shutdown (Cloud Run sends SIGTERM and allows a few seconds); and accepting small, bounded loss of low-traffic metrics. Always-on CPU would remove the issue but costs money, so it is rejected. Telemetry must never affect request handling: exporters run off the request path, and an export failure is logged once at `WARNING` and the service carries on.

### 3.6 Dashboard (free)

One Terraform-managed dashboard with: request rate by response class, latency p50, p95 and p99, 5xx ratio, instance count, CPU and memory utilization, container start-up latency (all Cloud Run system metrics); the custom database and start-up metrics; and a log panel filtered to `ERROR`. Dashboards have no charge.

### 3.7 Alerting under a strict $0 constraint

**What Google charges for.** Alerting policies are slated to become chargeable: $0.35 per month per metric reference, and $0.50 per million points returned by metric conditions, with no free allotment. The pricing page currently says this starts **no sooner than September 1, 2027** (earlier versions of the page named earlier dates, so the date has moved and must be rechecked at implementation). Two details decide the design:

1. **Log-based alerts are not free.** Log-match conditions return no points, but each condition still counts as one metric reference, so each costs $0.35 per month. Google's own pricing example prices 100 log-based policies at $3.50 per month.
2. **Some policies are exempt.** Metric alerting policies that use **Uptime**, **Billing** or **Quota** metrics are not charged. Error Reporting's notifications are configured on the Error Reporting page and delivered through Monitoring notification channels, not as alerting policies you create.

| Alert source                                     | Cost                                                                                                 | Catches                                                                                                          | Default                                                      |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| **Error Reporting notifications**                | Free per the pricing page (no line item); confirm in billing                                         | A new exception type, or a resolved one coming back (driven entirely by the structured error logs from TASK-0.4) | Yes                                                          |
| **Uptime check + alert on the uptime metric**    | Free: executions are free up to 1 million per project per month, and uptime-metric alerts are exempt | The service is down or unreachable                                                                               | Yes                                                          |
| **Billing budget alert**                         | Free; notification only, it does not cap spend                                                       | Any unexpected charge, including these very services leaving the free tier                                       | Yes                                                          |
| Scheduled GitHub Actions probe of `/ready`       | Free within Actions minutes (hourly is about 720 minutes a month; a private repo gets 2,000)         | The database is unreachable even though the process is up                                                        | Optional                                                     |
| Log-match alert policy (for example any `ERROR`) | **$0.35 per condition per month once alerting charges begin; free until then**                       | Immediate notice of any error log                                                                                | **No**, behind `enable_log_alert_policies` (default `false`) |
| Metric threshold alert (latency, error ratio)    | Same: chargeable per metric reference                                                                | Latency and error-rate regressions                                                                               | **No**                                                       |

**Trade-offs, stated plainly.** The default set detects (a) new kinds of errors, (b) outages and (c) cost surprises, with no recurring cost. It does **not** page on a rising error _rate_ or a latency regression; those are visible on the dashboard but unannounced. For a project of this size that is the right trade; the optional chargeable policies exist, with exact steps (Appendix B), for the day that changes.

**Uptime-check design.** The check probes `/health` (liveness) every 15 minutes from the minimum regions, not `/ready`: `/ready` runs `SELECT 1`, so frequent probes would keep Neon's compute awake and spend its free compute hours. Database health is covered by Error Reporting (`readiness_failed`, `migration_failed`), the dashboard, and the optional hourly GitHub probe. Executions are counted per region, so two services, four regions and a 15-minute period is about 35,000 executions a month, far below the free million.

**Notification channel.** One email channel (free), created from a Terraform variable `alert_email`.

### 3.8 Terraform changes

| Item                       | Detail                                                                                                                                                                                                                                                            |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| APIs                       | Enable `monitoring.googleapis.com` and `cloudtrace.googleapis.com`; `billingbudgets.googleapis.com` only when the budget is managed by Terraform                                                                                                                  |
| Runtime IAM                | `roles/cloudtrace.agent` and `roles/monitoring.metricWriter` for the two runtime service accounts. These roles can only be granted on the project, so they are a **deliberate, documented exception** to the resource-level rule in TASK-1.4; both are write-only |
| Environment variables      | `TELEMETRY_ENABLED`, `TRACE_SAMPLE_RATIO`, `METRICS_EXPORT_INTERVAL_SECONDS` on both services (the log variables come from TASK-0.4)                                                                                                                              |
| Dashboard                  | `google_monitoring_dashboard` with the widgets in 3.6                                                                                                                                                                                                             |
| Notification channel       | `google_monitoring_notification_channel` (type `email`) from `alert_email`                                                                                                                                                                                        |
| Uptime checks and alert    | `google_monitoring_uptime_check_config` per service (path from `uptime_check_path`, default `/health`, period 900 s) and `google_monitoring_alert_policy` on the uptime metric (exempt from alert charges)                                                        |
| Budget                     | `google_billing_budget` when `billing_account_id` is set (a small amount, for example USD 1, with 50, 90 and 100 percent thresholds); otherwise the console steps in Appendix A. Needs a billing permission the Terraform identity may not have                   |
| Optional chargeable alerts | `google_monitoring_alert_policy` with a log-match condition, created only when `enable_log_alert_policies = true`                                                                                                                                                 |
| Variables                  | `alert_email`, `uptime_check_path`, `enable_log_alert_policies` (default `false`), `billing_account_id`, `budget_amount_usd`, `telemetry_enabled`, `trace_sample_ratio`                                                                                           |

CD needs no change: `K_REVISION` already embeds the commit SHA, so traces and metrics are labeled with the version automatically.

### 3.9 Cost guardrails

- **The budget alert** is the backstop for anything that escapes this analysis.
- **Ingestion check:** after deployment, read the Monitoring metrics-ingestion figure (Metrics Management) and record it in this PRD's results table; the target is well under 100 MiB a month.
- **Pricing watch:** the alerting charge date and the exporter's metric path are re-verified at implementation and noted in the PR; if either changes, the default set is revisited before merging.
- **Billing report check:** one month after launch, filter billing by Cloud Monitoring, Cloud Trace and Cloud Logging and confirm the cost is zero.

### 3.10 Test strategy

| Test                       | What it proves                                                                                                          |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Spans (in-memory exporter) | A request creates a server span named by route template with the expected attributes, and one child span per statement  |
| Excluded routes            | `/health` and `/ready` create no spans                                                                                  |
| Sampling                   | A sampled parent is honored; a root is sampled at the configured ratio (deterministic ratio in the test)                |
| Privacy                    | No span carries SQL parameters, query strings, headers or bodies                                                        |
| Metrics (in-memory reader) | The catalog metrics record with only the allowed labels; label cardinality stays bounded                                |
| Log correlation            | A log line written during a request carries the trace and span of the active span                                       |
| Failure isolation          | With an exporter that raises, requests still succeed and a single warning is logged                                     |
| Configuration              | `TELEMETRY_ENABLED=false` makes the SDK a no-op (the local and CI default, since the Google exporters need credentials) |
| Terraform                  | `terraform fmt -check` and `validate` pass in CI; no resource in the default configuration is priced                    |

## 4. Acceptance Criteria

| #    | Criterion                                                                                                                                                                                                  |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1  | Telemetry packages are in `requirements.in` and pinned; a single `configure_telemetry()` configures both services; `TELEMETRY_ENABLED=false` (the local and CI default) makes it a no-op.                  |
| AC2  | Traces appear in Cloud Trace for a sampled request, with a server span by route template and one child span per statement; probes create none.                                                             |
| AC3  | Every log line written during a request carries the active trace and span, and the log viewer links to the trace.                                                                                          |
| AC4  | The custom metrics in 3.4 (initial set) are visible in Cloud Monitoring and use only bounded labels; HTTP metrics are not duplicated.                                                                      |
| AC5  | Metrics are written through the Google Monitoring exporter, **not** an OTLP or Prometheus path, and measured ingestion is under 100 MiB a month (recorded in the results table).                           |
| AC6  | The dashboard exists in Terraform and shows the widgets in 3.6 with live data.                                                                                                                             |
| AC7  | Error Reporting notifications are enabled with the email channel; a deliberately triggered new error produces an email, and a repeat of the same error does not (Appendix A2).                             |
| AC8  | Uptime checks for both services run every 15 minutes against `/health`, and an uptime-metric alert policy emails on failure (verified by pointing a copy of the check at a failing path, Appendix A3).     |
| AC9  | A billing budget alert exists with the thresholds in 3.8 (Terraform or console).                                                                                                                           |
| AC10 | No default resource is chargeable: log-match and metric alert policies exist only when `enable_log_alert_policies = true`, which defaults to `false`.                                                      |
| AC11 | Telemetry failures never break or slow requests (failure-isolation test); exporter errors produce one warning.                                                                                             |
| AC12 | Runtime service accounts hold only `cloudtrace.agent` and `monitoring.metricWriter` in addition to their existing roles, and the exception to the resource-level IAM rule is documented in TASK-1.4's PRD. |
| AC13 | One month after launch, the billing report shows $0 for Cloud Monitoring, Cloud Trace and Cloud Logging; the alerting charge date on Google's pricing page is re-read and noted.                           |
| AC14 | `README.md` documents where to look (dashboard, Trace explorer, Error Reporting), the span-budget formula, and the free-versus-chargeable table.                                                           |

### Results (recorded at implementation)

| Item                                                   | Measured |
| ------------------------------------------------------ | -------- |
| Alerting charge effective date (pricing page)          |          |
| Custom-metric ingestion, MiB per month                 |          |
| Spans per request (observed) and monthly span estimate |          |
| Log volume, MiB per 1,000 requests                     |          |

## 5. Verification Commands

Run after implementation, from the repository root (PowerShell). Steps 1 to 3 need no cloud account.

```powershell
# 0. Install and run the telemetry tests (AC1-AC4, AC11)
.\scripts\compile-requirements.ps1
.\scripts\sync-dev.ps1
docker compose up -d postgres
pytest tests/test_telemetry.py -v                                               # expect: all pass with in-memory exporters

# 1. Telemetry is a no-op by default (AC1)
pytest -m "not db and not integration" -k telemetry_disabled

# 2. Terraform checks (AC6, AC8-AC10, AC12)
terraform -chdir=infra/terraform fmt -check -recursive
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform plan -var "alert_email=you@example.com"       # expect: no priced resources by default; no log-match alert policy

# 3. Apply (manual, as in SP01), then confirm what exists
terraform -chdir=infra/terraform apply -var "alert_email=you@example.com"
gcloud monitoring dashboards list --format "table(displayName)"                 # expect: the API dashboard
gcloud monitoring channels list --format "table(displayName,type)"              # expect: one email channel
gcloud monitoring uptime list-configs --format "table(displayName,period)"      # expect: two checks, period 900s
gcloud alpha monitoring policies list --format "table(displayName,enabled)"     # expect: the uptime alert only

# 4. After the CD deploy, generate traffic and look at traces and logs (AC2, AC3)
$flight = gcloud run services describe flight-api --region <region> --format "value(status.url)"
1..20 | ForEach-Object { Invoke-RestMethod "$flight/flights?origin=BLR&destination=DEL" | Out-Null }
#   Console: Trace > Trace explorer (service flight-api): spans named by route template with child statement spans
$filter = 'resource.type="cloud_run_revision" AND resource.labels.service_name="flight-api" AND jsonPayload.event="request_completed"'
gcloud logging read $filter --limit 1 --format "value(trace)"                   # expect: projects/<id>/traces/<trace-id>

# 5. Custom metrics exist and are classic custom metrics, not Prometheus-format (AC4, AC5)
gcloud monitoring metrics-descriptors list --filter 'metric.type = starts_with("workload.googleapis.com/")' --format "table(type,valueType)"
#   Console: Monitoring > Metrics management > Ingestion: record MiB per month in the Results table

# 6. Free alerting end to end (AC7, AC8): follow Appendix A2 and A3 exactly

# 7. Cost check one month after launch (AC13)
#   Console: Billing > Reports, group by service; expect $0 for Cloud Monitoring, Cloud Trace, Cloud Logging
```

## 6. Rollout & Rollback

- **Rollout:** merge the PR (CI validates Terraform and runs the tests), apply Terraform manually with `alert_email` set, let CD deploy the services, then perform Appendix A2 (Error Reporting notifications) and A4 (budget, if not in Terraform). Set `TELEMETRY_ENABLED=true` on the Cloud Run services only after the IAM roles exist.
- **Rollback:** set `TELEMETRY_ENABLED=false` on the services (a new revision) to stop all export instantly, or revert the PR. Dashboards, channels and uptime checks can be removed with `terraform destroy -target`. Nothing in the request path depends on telemetry.
- **If a cost surprise appears:** disable the exporter flag first, then investigate with the ingestion page and billing report.

## 7. Risks

| Risk                                                                                   | Mitigation                                                                                                                                                            |
| -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Metrics silently move to a paid, per-sample path (a library or endpoint change)        | Use the Google monitoring exporter explicitly; AC5 measures ingestion; the budget alert is the backstop; the exporter version is pinned                               |
| Alerting charges start earlier than expected, or the exemptions change                 | The default set uses only exempt or non-alerting-policy mechanisms; chargeable policies are off by default; the pricing page is re-read at implementation and monthly |
| The default set misses rate and latency regressions                                    | Accepted and documented; the dashboard shows them; the chargeable alerts (Appendix B) are ready if the trade-off stops being acceptable                               |
| Uptime checks wake instances every 15 minutes                                          | `/health` does not touch the database; the traffic is about 35,000 requests a month, far inside Cloud Run's free request allowance                                    |
| Cloud Run CPU throttling delays or drops metric exports                                | Short interval, flush on shutdown, accepted small loss; always-on CPU rejected as paid                                                                                |
| Free span or byte budgets are exceeded as traffic grows                                | Sampling ratio, probe exclusion, bounded labels, documented budget formulas, and the ingestion and billing checks                                                     |
| OpenTelemetry imports and instrumentation add start-up time on a scale-to-zero service | Measure cold start before and after; the start-up metric and the 50-second probe budget make a regression visible; `TELEMETRY_ENABLED` can switch it off              |
| Telemetry leaks personal data through attributes                                       | Attribute allow-list, no SQL parameters or query strings, and a privacy test                                                                                          |
| Project-level IAM roles for telemetry weaken least privilege                           | They are write-only, limited to the two runtime accounts, and documented as an exception                                                                              |
| The budget needs a billing permission Terraform may lack                               | The console steps in Appendix A4 are the fallback                                                                                                                     |
| Google exporters or APIs change, or are retired                                        | Versions pinned; a failure-isolation test; the pipeline is OpenTelemetry, so the backend can be swapped without touching application code                             |

---

## Appendix A — Exact steps for the free alerting set

Every step uses the Google Cloud console unless noted. Menu names can shift slightly; the resource names are stable.

### A1. Create the email notification channel (free)

1. Console, **Monitoring**, then **Alerting**, then **Edit notification channels**.
2. Under **Email**, click **Add new**.
3. Enter the address and a display name (for example `Platform alerts`), then **Save**.
4. Terraform equivalent: `google_monitoring_notification_channel` with `type = "email"` and `labels = { email_address = var.alert_email }`.

### A2. Error Reporting notifications (free; fires on a new error type or a regression)

1. Confirm the services have logged at least one `ERROR` with a traceback (TASK-0.4 does this for unhandled exceptions), so **Error Reporting** shows them.
2. Console, **Error Reporting**, then **Configure notifications**.
3. Select the email channel from A1, then **Save**. (Needs the Error Reporting Admin, Editor or Owner role.)
4. Test: trigger a new, harmless exception type in a non-production way agreed in the PR. Expect one email.
5. Behavior to know: notifications fire for a **new error group** or a resolved group that **recurs**. Repeats of an open group are silent, at most 5 notifications per group are sent per hour, and further ones are silenced for six hours. To be notified again for the same error, mark its group **Resolved**.

### A3. Uptime checks with an alert (free)

1. Console, **Monitoring**, then **Uptime checks**, then **Create uptime check**.
2. Protocol **HTTPS**, resource type **URL**, hostname the service's host without `https://` (for example `flight-api-xxxxx-uc.a.run.app`), path `/health`.
3. **Check frequency:** 15 minutes. **Regions:** the minimum the console allows (at least three).
4. **Response validation:** status code 200. Click **Next**.
5. In the alert section choose **Create an alert**, select the A1 channel, name it (for example `flight-api down`), then **Create**.
6. Repeat for `hotel-api`.
7. Terraform equivalents: `google_monitoring_uptime_check_config` (`http_check` with `path`, `port = 443`, `use_ssl = true`; `period = "900s"`; `monitored_resource` of type `uptime_url` with the host label) and `google_monitoring_alert_policy` with a `condition_threshold` on `monitoring.googleapis.com/uptime_check/check_passed`.
8. Test: create a temporary copy of the check that points at a path that returns 404, wait for it to fail, confirm the email arrives, then delete the copy.
9. Cost note: executions are free up to 1 million per project per month, and alerts on uptime metrics are exempt from the alerting charge. Verify both on the pricing page at implementation.

### A4. Billing budget alert (free; notification only)

1. Console, **Billing**, select the billing account, then **Budgets & alerts**, then **Create budget**.
2. Scope: the project that hosts the services. Amount: **Specified amount**, USD 1.
3. Thresholds: 50%, 90% and 100% of **actual** spend, plus 100% **forecasted**.
4. Notifications: email to the billing account admins, and optionally the A1 channel.
5. Terraform equivalent: `google_billing_budget` (needs `billingbudgets.googleapis.com` and a billing role such as Billing Account Costs Manager for the Terraform identity).
6. Remember: budgets only notify. They do **not** stop spending.

### A5. Optional scheduled GitHub probe of `/ready` (free within Actions minutes)

1. Add a workflow with a `schedule` trigger (hourly, for example `17 * * * *`) and `workflow_dispatch`.
2. One job that runs `curl --fail --max-time 20` against `/ready` of both services (URLs from repository variables).
3. A failing run notifies by GitHub's own mechanisms; optionally open an issue with `gh issue create` (needs `issues: write`).
4. Minutes: an hourly run is billed at about one minute, roughly 720 a month; private repositories get 2,000 free minutes. A 15-minute schedule would exceed that on a private repository.
5. Scheduled workflows run only from the default branch and GitHub may disable them after 60 days of repository inactivity.

## Appendix B — Optional alerts that will become chargeable (off by default)

These are documented so they can be enabled deliberately. **Each condition costs $0.35 per month once alerting charges begin** (currently "no sooner than September 1, 2027"; re-check). To stop the charge, modify, delete or disable the policy.

### B1. Log-match alert on any `ERROR` (console)

1. Console, **Logging**, then **Logs Explorer**.
2. Enter the query: `resource.type="cloud_run_revision" AND severity>=ERROR AND resource.labels.service_name=("flight-api" OR "hotel-api")`.
3. **Actions**, then **Create log alert**.
4. Name it (for example `API errors`), choose a notification frequency (for example one every 5 minutes at most) and an auto-close period.
5. Select the A1 channel, then **Create**.

### B2. The same alert in Terraform (only when `enable_log_alert_policies = true`)

A `google_monitoring_alert_policy` with `combiner = "OR"`, one `conditions` block whose `condition_matched_log` has `filter` set to the query above, an `alert_strategy` with `notification_rate_limit { period = "300s" }` and an `auto_close`, and `notification_channels` pointing at the A1 channel. Validate with `terraform validate` before applying.

### B3. Metric threshold alerts

Alerts on request latency or 5xx ratio use Cloud Run's system metrics but are chargeable per metric reference. If enabled, use **one policy with one condition per concern** and aggregate to the service level, as Google's cost-control guidance recommends, so the monthly cost stays at the number of conditions times $0.35.

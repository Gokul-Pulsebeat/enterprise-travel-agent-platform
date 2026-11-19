# TASK-0.4 — API Logging Foundation (structlog + Cloud Logging)

| Field         | Value                                                                                                                   |
| ------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Epic          | SP00 — Platform, DX & Repo Standardization                                                                              |
| PR            | Single PR (feat); first of two observability tasks (see [`TASK-0.5`](TASK-0.5_api_metrics_traces_and_free_alerting.md)) |
| Branch        | `feat/sp00-t04-api-logging`                                                                                             |
| Target branch | `productionize`                                                                                                         |
| Status        | **Fully specified; implementation deferred.** Writing this document changes no code and no configuration                |
| Sequencing    | Planned after SP02 TASK-2.2 and before TASK-2.3, so locking and idempotency are observable from their first release     |
| Depends on    | SP01 (Cloud Run, Terraform, CD), SP02 TASK-2.1 (async APIs, `common/` package, lifespan start-up)                       |
| Parent docs   | [`EPIC_PRD.md`](EPIC_PRD.md), [`00_MASTER_PRD.md`](../../00_MASTER_PRD.md)                                              |

---

## 1. Objective

Today the APIs run silently: a failed request, a slow query or a failed migration leaves no trace beyond uvicorn's default text lines. SP06's observability work covers the **AI agent**; the business APIs are services this project owns and operates, so they need their own observability, and it must not wait until the last epic.

This task builds the **logging foundation**: every request and every significant internal event in `flight_api` and `hotel_api` (and every future service) emits a structured, correlated, level-appropriate log event that Cloud Logging indexes natively, with no secrets or personal data, at **zero cost** and with **no new infrastructure**. Cloud Run already ships anything written to stdout to Cloud Logging, so the integration is a log format, not a service.

## 2. Scope

### In scope

| Area                                    | Change                                                                                                                                                                                                                          |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `requirements.in`                       | Add `structlog` (lockfile recompiled with `scripts/compile-requirements.ps1`)                                                                                                                                                   |
| `common/` (proposed names)              | `logging_config.py`: one `configure_logging()` for every service. `request_context.py`: a pure ASGI middleware for request correlation, timing and the access event. A small redaction processor and the event-name conventions |
| `flight_api/app.py`, `hotel_api/app.py` | Call `configure_logging()`, install the middleware and the unhandled-exception handler, log lifecycle events (start-up, migrations, seed, shutdown) and readiness failures                                                      |
| `common/db.py`                          | Log migration and seed outcomes with durations and revisions; log slow queries and pool exhaustion through SQLAlchemy events (statement fingerprints, never parameters)                                                         |
| Stdlib bridge                           | Route uvicorn, SQLAlchemy, Alembic and asyncpg standard-library logs through the same pipeline; switch off uvicorn's own access log                                                                                             |
| Tests                                   | Unit and API tests for the log schema, correlation, redaction, levels and the exception handler (see 3.8)                                                                                                                       |
| `infra/terraform/main.tf`               | Cloud Run environment variables (`GCP_PROJECT_ID`, `LOG_LEVEL`), explicit API enablement; optional log exclusion (3.7). No new resources that cost money                                                                        |
| `.env.example`, `README.md`             | Logging settings and how to read logs locally and in Cloud Logging                                                                                                                                                              |
| `docs/`                                 | A short "logging conventions" section in this PRD becomes the reference for event names and fields (section 3.3)                                                                                                                |

### Out of scope

- Metrics, traces, dashboards and alerting: [`TASK-0.5`](TASK-0.5_api_metrics_traces_and_free_alerting.md).
- Logging for the MCP servers and the agent: the servers become HTTP services in SP03 and adopt this foundation then; the agent is SP06's scope (LLM-specific events) and reuses the same `configure_logging()`.
- Shipping logs anywhere other than Cloud Logging (no third-party log service, no extra agent, no sink to a paid destination).
- Audit logging of business actions (who booked what): arrives with identity and bookings (TASK-2.2 to 2.4), using this foundation.

## 3. Architectural Notes

### 3.1 Why structlog, and how it fits

structlog produces **events with key-value context** rather than formatted strings, which is exactly what Cloud Logging's JSON ingestion wants, and its context variables carry the request ID and trace automatically through async code. The pipeline:

1. Application code calls `logger.info("event_name", key=value, ...)`.
2. Processors merge request-scoped context (`structlog.contextvars`), add the level and timestamp, apply redaction, convert exceptions to text, and map names to Cloud Logging's field names.
3. A renderer writes one JSON object per line to **stdout** in Cloud Run, or a human-friendly console format locally.
4. Cloud Run's logging agent ingests stdout and recognises the special fields (`severity`, `message`, trace, `httpRequest`), so entries are filterable, correlated and grouped with no extra library or credential.

Standard-library records (uvicorn, SQLAlchemy, Alembic) pass through the same processors via structlog's `ProcessorFormatter`, so there is one format, not two.

| Library choice                      | Verdict                                                                                        |
| ----------------------------------- | ---------------------------------------------------------------------------------------------- |
| `structlog`                         | **Chosen** (decided): structured events, context variables, and a clean bridge for stdlib logs |
| stdlib `logging` + custom formatter | Zero dependencies, but context propagation and structured fields need hand-rolled code         |
| `google-cloud-logging` client       | Not needed on Cloud Run (stdout is collected) and it adds a credential-bearing network path    |

### 3.2 Configuration

| Setting                             | Default                                                    | Purpose                                                                                                                  |
| ----------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `LOG_FORMAT`                        | `json` when `K_SERVICE` is set (Cloud Run), else `console` | Human-readable colour output for development; JSON in production. Overridable                                            |
| `LOG_LEVEL`                         | `INFO`                                                     | Minimum level. `DEBUG` is for local use only                                                                             |
| `LOG_ACCESS`                        | `on`                                                       | `on` logs one `request_completed` per non-probe request, `errors` logs only 4xx/5xx and slow requests, `off` disables it |
| `SLOW_REQUEST_MS` / `SLOW_QUERY_MS` | `1000` / `250`                                             | Thresholds for the `slow_request` and `slow_query` warnings                                                              |
| `GCP_PROJECT_ID`                    | unset locally; set by Terraform in Cloud Run               | Needed to build the Cloud Logging trace field (`projects/<id>/traces/<trace-id>`)                                        |

`configure_logging()` runs once at process start (before the lifespan handler), is idempotent, and sets the service name and revision from Cloud Run's own variables (`K_SERVICE`, `K_REVISION`; the revision name already embeds the commit SHA from CD), so no deploy-time change is needed.

### 3.3 Log schema and conventions

**Fields every entry carries**

| JSON field                      | Source                                   | Notes                                                                                        |
| ------------------------------- | ---------------------------------------- | -------------------------------------------------------------------------------------------- |
| `severity`                      | structlog level                          | Mapped to Cloud Logging severities (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)         |
| `message`                       | the event name (plus a short human text) | Cloud Logging's primary text field                                                           |
| `event`                         | the event name                           | Stable `snake_case` identifier used in filters, for example `request_completed`              |
| `time`                          | ISO 8601 UTC                             |                                                                                              |
| `service`, `version`            | `K_SERVICE`, `K_REVISION`                | `serviceContext` is also emitted so Error Reporting can group by service and version         |
| `request_id`                    | middleware                               | From a valid inbound `X-Request-ID`, else a generated UUID; echoed in the response header    |
| `logging.googleapis.com/trace`  | `X-Cloud-Trace-Context` or `traceparent` | `projects/<GCP_PROJECT_ID>/traces/<trace-id>`; joins app logs to Cloud Run's own request log |
| `logging.googleapis.com/spanId` | same header                              | Lets the log viewer link to the span once TASK-0.5 adds tracing                              |

**Event naming.** Past-tense `snake_case` facts: `service_started`, `migration_completed`, `request_completed`, `readiness_failed`. One event name per kind of fact; variation goes in fields, never in the name. TASK-2.3 to 2.5 add their own (`booking_confirmed`, `idempotent_replay`, `email_enqueued`) following the same rule.

**Level policy**

| Level      | Use                                                                                                                                   |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `DEBUG`    | Developer detail; disabled in production; health and readiness probe requests are logged only here                                    |
| `INFO`     | Lifecycle (start, migrations, seed, shutdown) and `request_completed` for 2xx and 3xx, and 4xx (client errors are not service faults) |
| `WARNING`  | Degraded but working: `slow_request`, `slow_query`, retried operations, a configuration fallback                                      |
| `ERROR`    | The service failed to do its job: 5xx responses, unhandled exceptions, `readiness_failed`, `migration_failed`                         |
| `CRITICAL` | The process cannot continue (start-up aborted)                                                                                        |

**Access events.** Cloud Run already writes a platform request log with `httpRequest` for every request. The application's `request_completed` event does **not** duplicate it: it adds what only the application knows (route template such as `/flights/{flight_id}`, duration, outcome, later the user and booking identifiers) and is joined to the platform entry by the trace field. Health and readiness probes are excluded.

**Exceptions.** Unhandled exceptions are logged once, at `ERROR`, with the formatted traceback in the entry's text fields, plus `serviceContext`, which is what Error Reporting needs to detect and group them. The client receives a generic `500` body with the request ID, never the exception text.

### 3.4 Privacy, secrets and safety (hard rules)

1. **Never logged:** request or response bodies, `Authorization` and `Cookie` headers, the `DATABASE_URL` and any connection string, API keys, tokens, passwords, and raw exception messages that embed them.
2. **Redaction processor.** Any key matching a deny-list (`authorization`, `cookie`, `password`, `token`, `secret`, `api_key`, `database_url`, `dsn`) has its value replaced with `[REDACTED]` before rendering, wherever it appears in the event.
3. **URLs.** Log the route template and path, not the query string. Query strings can carry personal data later (emails, names); an explicit allow-list of safe keys (`origin`, `destination`, `date`, `city`, `check_in_date`) may be logged at `DEBUG` only.
4. **Database errors.** Connection errors are logged with the password hidden (SQLAlchemy's `render_as_string(hide_password=True)`); statements are logged as a normalized fingerprint without parameters.
5. **People.** Only opaque identifiers (user ID from TASK-2.2), never names or email addresses.
6. **A test enforces it** (3.8): the suite runs start-up and requests with a sentinel secret in the environment and asserts it appears in no captured output.

### 3.5 Request correlation

A **pure ASGI middleware** (not `BaseHTTPMiddleware`, which interferes with context variables and streaming) does, per request: read or generate the request ID; parse the trace context from `traceparent` or `X-Cloud-Trace-Context`; bind `request_id`, trace and span to structlog's context variables; time the request; emit `request_completed` (or `slow_request`) with route template, method, status and duration; and add `X-Request-ID` to the response. Context is cleared when the request ends so nothing leaks between requests on a reused instance.

### 3.6 Database and lifecycle events

| Event                                       | Level   | Fields                                                                    |
| ------------------------------------------- | ------- | ------------------------------------------------------------------------- |
| `service_started`                           | INFO    | service, version, log level, pool size (no URLs)                          |
| `migration_started` / `migration_completed` | INFO    | schema, from and to revision, duration in ms                              |
| `migration_failed`                          | ERROR   | schema, revision, exception (the process then exits)                      |
| `seed_completed`                            | INFO    | rows inserted per table                                                   |
| `slow_query`                                | WARNING | duration in ms, statement fingerprint, route when known; never parameters |
| `pool_exhausted`                            | ERROR   | pool size, overflow, wait time                                            |
| `readiness_failed`                          | ERROR   | reason class (timeout, connection refused), duration                      |
| `service_stopping`                          | INFO    | uptime                                                                    |

### 3.7 Cost and Terraform

- **Cost: $0.** The first 50 GiB of logs per project per month is free, and the default 30-day retention is free (only retention beyond 30 days is charged). The services produce well under 1 MiB per 1,000 requests, so even heavy use stays orders of magnitude below the allowance. Never raise retention above 30 days.
- **Terraform (small):** add `GCP_PROJECT_ID` and `LOG_LEVEL` to the Cloud Run environment; enable `logging.googleapis.com` and `clouderrorreporting.googleapis.com` explicitly (they are normally on already); **no new IAM**, because Cloud Run collects stdout with its own platform identity.
- **Optional guard:** a `google_logging_project_exclusion` for noisy probe request logs and a `google_logging_project_bucket_config` pinning `_Default` retention to 30 days, both behind variables with safe defaults. The bucket config manages an existing resource and may need to be imported; verify with `terraform plan` before applying.

### 3.8 Test strategy

| Test                  | What it proves                                                                                                                                           |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Schema                | A rendered JSON line has `severity`, `message`, `event`, `time`, `service`, valid JSON, one object per line                                              |
| Severity mapping      | Each structlog level maps to the right Cloud Logging severity                                                                                            |
| Correlation           | A request with `traceparent` or `X-Cloud-Trace-Context` produces the expected `logging.googleapis.com/trace` and span fields; `X-Request-ID` round-trips |
| Request ID safety     | An oversized or malformed inbound ID is replaced, not logged                                                                                             |
| Access policy         | Probes are silent at `INFO`; a 404 is `INFO`; a 500 is `ERROR`; a slow request is `WARNING`; `LOG_ACCESS` modes behave                                   |
| Exception handling    | An unhandled exception is logged exactly once with a traceback and `serviceContext`, and the client sees a generic 500 containing the request ID         |
| Redaction             | Deny-listed keys are redacted at any depth; a sentinel secret set in the environment appears in no output across start-up and requests                   |
| Stdlib bridge         | A log record from `logging.getLogger("sqlalchemy.engine")` is rendered in the same JSON schema                                                           |
| Lifecycle             | Start-up emits `service_started` and migration events with durations; a forced migration failure emits `migration_failed` and aborts                     |
| Local vs Cloud format | `LOG_FORMAT` auto-detection follows `K_SERVICE`                                                                                                          |

Tests use structlog's capture helpers and the API `TestClient`; none needs GCP.

## 4. Acceptance Criteria

| #    | Criterion                                                                                                                                                                                    |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1  | `requirements.in` adds `structlog`; the recompiled `requirements.txt` pins it; CI's lockfile-parity check passes.                                                                            |
| AC2  | One `configure_logging()` in `common/` configures every service; `flight_api` and `hotel_api` call it and emit identical schemas.                                                            |
| AC3  | In Cloud Run every entry is a single-line JSON object with the fields in 3.3; locally the default is the readable console format, and `LOG_FORMAT=json` switches to JSON.                    |
| AC4  | Each request produces one `request_completed` event with route template, method, status and duration, joined to Cloud Run's request log by the trace field; probes are not logged at `INFO`. |
| AC5  | `X-Request-ID` is accepted when valid, generated otherwise, logged on every event of the request, and echoed in the response.                                                                |
| AC6  | uvicorn, SQLAlchemy and Alembic standard-library logs appear in the same format; uvicorn's separate access log is off.                                                                       |
| AC7  | Unhandled exceptions are logged once at `ERROR` with traceback and `serviceContext`, appear in **Error Reporting** grouped by service and revision, and the client receives a generic 500.   |
| AC8  | Start-up, migration, seed, readiness and shutdown events exist with the fields in 3.6; slow queries and pool exhaustion are logged without parameters.                                       |
| AC9  | The redaction rules in 3.4 hold: no secret, connection string, header value or body appears in any log, enforced by an automated test.                                                       |
| AC10 | Terraform sets `GCP_PROJECT_ID` and `LOG_LEVEL` and enables the logging APIs; `terraform fmt`, `validate` and `plan` are clean; no paid resource is added.                                   |
| AC11 | Log volume is measured after deployment and recorded (entries and MiB per 1,000 requests), confirming the free allowance is far from reached.                                                |
| AC12 | `README.md` and `.env.example` document the settings, the event conventions and how to query logs locally and in Cloud Logging.                                                              |

## 5. Verification Commands

Run after implementation, from the repository root (PowerShell). Docker Desktop must be running for the database.

```powershell
# 0. Install the new package (AC1)
.\scripts\compile-requirements.ps1
.\scripts\sync-dev.ps1
Select-String -Path requirements.txt -Pattern "^structlog=="                    # expect: one pinned line

# 1. Tests for the logging foundation (AC2-AC9)
docker compose up -d postgres
pytest tests/test_logging.py -v                                                 # expect: all pass

# 2. Local readable output (AC3)
$api = Start-Process python -ArgumentList "-m","uvicorn","flight_api.app:app","--port","8000" -PassThru -WindowStyle Hidden -RedirectStandardOutput logs-console.txt
Start-Sleep -Seconds 8
Invoke-RestMethod http://127.0.0.1:8000/flights/1 | Out-Null
Get-Content logs-console.txt                                                    # expect: service_started, migration events, request_completed (human-readable)
Stop-Process -Id $api.Id

# 3. JSON output parses and carries the schema (AC3, AC4, AC5)
$env:LOG_FORMAT = "json"
$api = Start-Process python -ArgumentList "-m","uvicorn","flight_api.app:app","--port","8000" -PassThru -WindowStyle Hidden -RedirectStandardOutput logs-json.txt
Start-Sleep -Seconds 8
Invoke-WebRequest http://127.0.0.1:8000/flights/1 -Headers @{ "X-Request-ID" = "demo-123"; "X-Cloud-Trace-Context" = "105445aa7843bc8bf206b12000100000/1;o=1" } -UseBasicParsing | Select-Object -ExpandProperty Headers
Stop-Process -Id $api.Id
Get-Content logs-json.txt | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object event -eq "request_completed"   # expect: request_id demo-123, a trace field, duration, status 200
Remove-Item Env:LOG_FORMAT, logs-console.txt

# 4. No secrets in the output (AC9)
Select-String -Path logs-json.txt -Pattern "travel_dev_password|postgresql://"  # expect: no output
Remove-Item logs-json.txt

# 5. Terraform (AC10)
terraform -chdir=infra/terraform fmt -check -recursive
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform plan                                           # expect: env vars and API enablement only

# 6. After the CD deploy: read production logs (AC4, AC5, AC7)
$filter = 'resource.type="cloud_run_revision" AND resource.labels.service_name="flight-api" AND jsonPayload.event="request_completed"'
gcloud logging read $filter --limit 5 --format json                             # expect: structured entries with a trace field
$trace = (gcloud logging read $filter --limit 1 --format "value(trace)")
gcloud logging read "trace=`"$trace`"" --format "table(timestamp,severity,logName,jsonPayload.event)"   # expect: the app event AND Cloud Run's request log for one request

# 7. Error Reporting (AC7): trigger a handled-by-the-handler error in a non-production way agreed in the PR,
#    then confirm it is grouped
gcloud beta error-reporting events list --service flight-api --limit 5          # expect: the exception, grouped by service and revision

# 8. Measure volume (AC11)
gcloud logging read 'resource.type="cloud_run_revision"' --freshness 1d --format json | Measure-Object | Select-Object Count
```

## 6. Rollout & Rollback

- **Rollout:** merge the PR; CD deploys both services. No data migration or infrastructure beyond the Terraform environment variables (applied manually, as in SP01). Local developers see the new console output immediately.
- **Rollback:** revert the PR; the services return to uvicorn's default logs. Nothing depends on the new format, and logs already written stay in Cloud Logging for their 30-day retention.
- **Disabling noise without a deploy:** set `LOG_LEVEL=WARNING` or `LOG_ACCESS=errors` on the Cloud Run service (a new revision) if volume or verbosity ever needs trimming.

## 7. Risks

| Risk                                                                                                 | Mitigation                                                                                                                                                    |
| ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Secrets or personal data leak through a log field or an exception message                            | Deny-list redaction, no bodies or query strings, sanitized database URLs, and a sentinel-secret test in CI                                                    |
| uvicorn configures its own loggers before the app starts, so the bridge misses or duplicates records | `configure_logging()` resets the uvicorn and root loggers explicitly; the stdlib-bridge test and the local console check (step 2) catch duplicates            |
| Context variables leak between requests on a reused instance                                         | Pure ASGI middleware clears context in a `finally`; a test sends two requests and asserts no carry-over                                                       |
| Cloud Logging does not group exceptions as expected because of the entry shape                       | AC7 verifies in the Error Reporting console on a real deployment; the shape is documented in 3.3 and adjusted if grouping fails                               |
| Log volume grows (verbose levels, noisy loops)                                                       | Probes excluded, `LOG_ACCESS` and `LOG_LEVEL` switches, volume measured in AC11, the free allowance is about 50 GiB per month                                 |
| Logging overhead adds latency                                                                        | Events are small and written to stdout; the cost per request is microseconds, checked in the test suite's timing assertions only if it ever becomes a concern |
| structlog and Cloud Logging field conventions change                                                 | The mapping lives in one module with a schema test; versions are pinned by the lockfile                                                                       |
| Developers add ad-hoc `print` or free-form messages                                                  | Conventions in 3.3, plus a Ruff rule (`T201`) to forbid `print` in application packages if it proves necessary                                                |

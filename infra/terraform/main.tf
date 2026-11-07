# Infrastructure for the Enterprise Travel Agent Platform (SP01, TASK-1.4).
#
# Provisions on GCP: Artifact Registry, two Cloud Run services (flight-api, hotel-api), Secret Manager,
# least-privilege service accounts, and Workload Identity Federation so GitHub Actions can deploy without
# static keys. Also creates a Neon Postgres project and an Upstash Redis database and stores their
# connection strings in Secret Manager.
#
# Ownership split with the CD pipeline (TASK-1.5): Terraform creates the Cloud Run services with a
# placeholder image; the CD workflow owns the image and traffic routing afterwards (see the
# lifecycle.ignore_changes block on the services).

locals {
  # Cloud Run service names use hyphens (underscores are not allowed); the map keys match the repo folders.
  services = {
    flight_api = {
      name = "flight-api"
      port = 8000
    }
    hotel_api = {
      name = "hotel-api"
      port = 8001
    }
  }

  registry_url = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repository}"

  required_apis = [
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sts.googleapis.com",
  ]

  # Secrets exposed to every Cloud Run service as environment variables (env var name => secret ID).
  # The applications do not read them yet; SP02 (Postgres) and SP03/SP04 (Redis) will.
  runtime_secrets = merge(
    var.enable_neon ? { DATABASE_URL = google_secret_manager_secret.database_url[0].secret_id } : {},
    var.enable_upstash ? { REDIS_URL = google_secret_manager_secret.redis_url[0].secret_id } : {},
  )

  # One entry per (service, secret) pair so each runtime identity gets access to exactly these secrets.
  secret_access = {
    for pair in setproduct(keys(local.services), keys(local.runtime_secrets)) :
    "${pair[0]}-${pair[1]}" => {
      service  = pair[0]
      env_name = pair[1]
    }
  }
}

# -----------------------------------------------------------------------------
# Providers
# -----------------------------------------------------------------------------
provider "google" {
  project = var.project_id
  region  = var.region
}

provider "neon" {
  # An empty value falls back to the NEON_API_KEY environment variable.
  api_key = var.neon_api_key != "" ? var.neon_api_key : null
}

provider "upstash" {
  email   = var.upstash_email
  api_key = var.upstash_api_key
}

# -----------------------------------------------------------------------------
# Google APIs
# -----------------------------------------------------------------------------
resource "google_project_service" "apis" {
  for_each = toset(local.required_apis)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# -----------------------------------------------------------------------------
# Artifact Registry
# -----------------------------------------------------------------------------
resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_registry_repository
  format        = "DOCKER"
  description   = "Container images for the Enterprise Travel Agent Platform."

  # Stay inside the free storage tier: keep the 10 newest versions of each image (so a rollback always
  # has an image to return to) and delete anything older than 30 days.
  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "keep-recent-versions"
    action = "KEEP"

    most_recent_versions {
      keep_count = 10
    }
  }

  cleanup_policies {
    id     = "delete-old-versions"
    action = "DELETE"

    condition {
      tag_state  = "ANY"
      older_than = "2592000s"
    }
  }

  depends_on = [google_project_service.apis]
}

# -----------------------------------------------------------------------------
# Service accounts (least privilege)
# -----------------------------------------------------------------------------
# One runtime identity per Cloud Run service. It can read only the secrets listed in local.runtime_secrets.
resource "google_service_account" "runtime" {
  for_each = local.services

  project      = var.project_id
  account_id   = "${each.value.name}-runtime"
  display_name = "Cloud Run runtime identity for ${each.value.name}"

  depends_on = [google_project_service.apis]
}

# The identity GitHub Actions impersonates (through WIF) to push images and deploy revisions.
resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = "github-deployer"
  display_name = "GitHub Actions deployer (CD pipeline)"

  depends_on = [google_project_service.apis]
}

# -----------------------------------------------------------------------------
# Neon Postgres (free tier) -> Secret Manager
# -----------------------------------------------------------------------------
resource "neon_project" "main" {
  count = var.enable_neon ? 1 : 0

  name       = var.neon_project_name
  region_id  = var.neon_region_id
  pg_version = var.neon_pg_version

  branch {
    name          = "main"
    database_name = var.neon_database_name
    role_name     = var.neon_role_name
  }
}

resource "google_secret_manager_secret" "database_url" {
  count = var.enable_neon ? 1 : 0

  project   = var.project_id
  secret_id = "travel-agent-database-url"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "database_url" {
  count = var.enable_neon ? 1 : 0

  secret      = google_secret_manager_secret.database_url[0].id
  secret_data = neon_project.main[0].connection_uri
}

# -----------------------------------------------------------------------------
# Upstash Redis (free tier) -> Secret Manager
# -----------------------------------------------------------------------------
resource "upstash_redis_database" "main" {
  count = var.enable_upstash ? 1 : 0

  database_name  = var.upstash_database_name
  region         = "global"
  primary_region = var.upstash_primary_region
}

resource "google_secret_manager_secret" "redis_url" {
  count = var.enable_upstash ? 1 : 0

  project   = var.project_id
  secret_id = "travel-agent-redis-url"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "redis_url" {
  count = var.enable_upstash ? 1 : 0

  secret      = google_secret_manager_secret.redis_url[0].id
  secret_data = "rediss://default:${upstash_redis_database.main[0].password}@${upstash_redis_database.main[0].endpoint}:${upstash_redis_database.main[0].port}"
}

# Each runtime identity may read exactly the secrets above, and nothing else in Secret Manager.
resource "google_secret_manager_secret_iam_member" "runtime_access" {
  for_each = local.secret_access

  project   = var.project_id
  secret_id = local.runtime_secrets[each.value.env_name]
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime[each.value.service].email}"
}

# -----------------------------------------------------------------------------
# Cloud Run services
# -----------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "api" {
  for_each = local.services

  project             = var.project_id
  name                = each.value.name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = var.deletion_protection

  template {
    service_account = google_service_account.runtime[each.key].email

    # Scale to zero when idle (no cost) and cap instances (bounded cost).
    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    containers {
      # Placeholder only. The CD pipeline deploys the real image tagged with the commit SHA.
      image = var.placeholder_image

      ports {
        container_port = each.value.port
      }

      resources {
        cpu_idle          = true
        startup_cpu_boost = true

        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      # Secret-backed environment variables (DATABASE_URL / REDIS_URL), resolved at revision start.
      dynamic "env" {
        for_each = local.runtime_secrets

        content {
          name = env.key

          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      # A TCP probe works for both the placeholder image and the real APIs. Application-level health
      # (/health) is verified by the CD pipeline after each deploy.
      startup_probe {
        initial_delay_seconds = 0
        period_seconds        = 5
        timeout_seconds       = 3
        failure_threshold     = 10

        tcp_socket {
          port = each.value.port
        }
      }
    }
  }

  lifecycle {
    # The CD pipeline owns the container image, revision metadata and traffic routing. Ignoring them keeps
    # terraform apply from reverting a deploy, or undoing a rollback that pinned traffic to an old revision.
    ignore_changes = [
      client,
      client_version,
      template[0].containers[0].image,
      template[0].labels,
      template[0].annotations,
      template[0].revision,
      traffic,
    ]
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_iam_member.runtime_access,
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_version.redis_url,
  ]
}

# Public invocation. The APIs have no authentication until SP03; disable with allow_unauthenticated = false
# (the CD health gate then needs an identity token and must be adapted).
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  for_each = { for key, service in local.services : key => service if var.allow_unauthenticated }

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api[each.key].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# -----------------------------------------------------------------------------
# GitHub Actions deployer permissions (resource-level, not project-wide)
# -----------------------------------------------------------------------------
resource "google_artifact_registry_repository_iam_member" "deployer_writer" {
  project    = var.project_id
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_cloud_run_v2_service_iam_member" "deployer_run_developer" {
  for_each = local.services

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api[each.key].name
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

# Deploying a revision that runs as a service account requires permission to "act as" that account.
resource "google_service_account_iam_member" "deployer_acts_as_runtime" {
  for_each = local.services

  service_account_id = google_service_account.runtime[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

# -----------------------------------------------------------------------------
# Workload Identity Federation: GitHub Actions -> GCP without static keys
# -----------------------------------------------------------------------------
resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
  description               = "Federated identities for GitHub Actions workflows."

  depends_on = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"
  attribute_condition                = "assertion.repository == '${var.github_repository}' && assertion.ref == 'refs/heads/${var.deploy_branch}'"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Only tokens from the allowed repository (and, via the provider condition, the deploy branch) may
# impersonate the deployer service account.
resource "google_service_account_iam_member" "github_workload_identity" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

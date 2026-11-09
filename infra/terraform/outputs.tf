output "artifact_registry_url" {
  description = "Docker registry path for the application images."
  value       = local.registry_url
}

output "cloud_run_urls" {
  description = "URL of each Cloud Run service."
  value       = { for key, service in google_cloud_run_v2_service.api : key => service.uri }
}

output "runtime_service_accounts" {
  description = "Runtime identity of each Cloud Run service."
  value       = { for key, account in google_service_account.runtime : key => account.email }
}

output "deployer_service_account_email" {
  description = "Service account the GitHub Actions CD workflow impersonates."
  value       = google_service_account.deployer.email
}

output "workload_identity_provider" {
  description = "Full resource name of the WIF provider (GCP_WIF_PROVIDER for the CD workflow)."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "github_actions_variables" {
  description = "Values to set as GitHub repository VARIABLES (Settings > Secrets and variables > Actions > Variables). None of these are secrets."
  value = {
    GCP_PROJECT_ID    = var.project_id
    GCP_REGION        = var.region
    GCP_ARTIFACT_REPO = var.artifact_registry_repository
    GCP_WIF_PROVIDER  = google_iam_workload_identity_pool_provider.github.name
    GCP_DEPLOYER_SA   = google_service_account.deployer.email
  }
}

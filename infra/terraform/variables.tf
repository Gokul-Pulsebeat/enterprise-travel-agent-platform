# -----------------------------------------------------------------------------
# GCP
# -----------------------------------------------------------------------------
variable "project_id" {
  description = "GCP project ID that hosts all resources (billing must be enabled)."
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run and Artifact Registry."
  type        = string
  default     = "us-central1"
}

variable "artifact_registry_repository" {
  description = "Name of the Artifact Registry Docker repository."
  type        = string
  default     = "travel-agent"
}

variable "placeholder_image" {
  description = "Public image Cloud Run runs until the CD pipeline deploys the real one (Terraform ignores image changes afterwards)."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "max_instances" {
  description = "Maximum Cloud Run instances per service. Keeps cost bounded and inside the free tier."
  type        = number
  default     = 2
}

variable "allow_unauthenticated" {
  description = "Allow public, unauthenticated invocation of the Cloud Run services. The APIs have no authentication until SP03, and the CD health gate polls the public URL."
  type        = bool
  default     = true
}

variable "deletion_protection" {
  description = "Protect the Cloud Run services from accidental deletion by terraform destroy."
  type        = bool
  default     = false
}

# -----------------------------------------------------------------------------
# GitHub Actions federation
# -----------------------------------------------------------------------------
variable "github_repository" {
  description = "GitHub repository allowed to deploy, in owner/name form (for example my-org/enterprise-travel-agent-platform)."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must look like owner/name."
  }
}

variable "deploy_branch" {
  description = "The only branch whose workflows may authenticate to GCP."
  type        = string
  default     = "productionize"
}

# -----------------------------------------------------------------------------
# Neon Postgres
# -----------------------------------------------------------------------------
variable "enable_neon" {
  description = "Create the Neon Postgres project and store its connection string in Secret Manager."
  type        = bool
  default     = true
}

variable "neon_api_key" {
  description = "Neon API key. Leave empty to use the NEON_API_KEY environment variable. Set via TF_VAR_neon_api_key, never in a committed file."
  type        = string
  default     = ""
  sensitive   = true
}

variable "neon_project_name" {
  description = "Name of the Neon project."
  type        = string
  default     = "enterprise-travel-agent"
}

variable "neon_region_id" {
  description = "Neon region (for example aws-us-east-2, aws-us-east-1, aws-eu-central-1, aws-ap-southeast-1)."
  type        = string
  default     = "aws-us-east-2"
}

variable "neon_pg_version" {
  description = "Postgres major version."
  type        = number
  default     = 16
}

variable "neon_database_name" {
  description = "Name of the application database."
  type        = string
  default     = "travel_agent"
}

variable "neon_role_name" {
  description = "Name of the application database role."
  type        = string
  default     = "travel_app"
}

# -----------------------------------------------------------------------------
# Upstash Redis
# -----------------------------------------------------------------------------
variable "enable_upstash" {
  description = "Create the Upstash Redis database and store its connection string in Secret Manager."
  type        = bool
  default     = true
}

variable "upstash_email" {
  description = "Upstash account email. Set via TF_VAR_upstash_email."
  type        = string
  default     = ""
}

variable "upstash_api_key" {
  description = "Upstash API key. Set via TF_VAR_upstash_api_key, never in a committed file."
  type        = string
  default     = ""
  sensitive   = true
}

variable "upstash_database_name" {
  description = "Name of the Upstash Redis database."
  type        = string
  default     = "enterprise-travel-agent"
}

variable "upstash_primary_region" {
  description = "Primary region of the global Upstash database (for example us-east-1, eu-west-1, ap-southeast-1)."
  type        = string
  default     = "us-east-1"
}

variable "project_slug" {
  type    = string
  default = "climate-risk"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "location" {
  type        = string
  description = "Azure region. uksouth by default -- see docs/finops.md region-selection note. No multi-region."
  default     = "uksouth"
}

variable "owner" {
  type    = string
  default = "varun"
}

variable "image_tag" {
  type        = string
  description = "Immutable git-SHA tag for the pipeline image. Required -- no default, so a plan never silently falls back to 'latest'."
}

variable "image_digest" {
  type        = string
  description = "sha256 digest of the pushed GHCR image, for provenance in the publish manifest. Empty string if not yet known (e.g. before the first push)."
  default     = ""
}

variable "ghcr_owner" {
  type        = string
  description = "GitHub user/org that owns the public GHCR image (ghcr.io/<ghcr_owner>/<ghcr_image_name>). Required -- no default, since guessing a GitHub username would bake a wrong owner into the image reference."
  validation {
    condition     = length(var.ghcr_owner) > 0
    error_message = "ghcr_owner must be set, e.g. -var=\"ghcr_owner=your-github-username\"."
  }
}

variable "ghcr_image_name" {
  type    = string
  default = "climate-risk-pipeline"
}

variable "job_trigger_type" {
  type = string
  # Two manual smoke tests succeeded end to end against real ADLS Gen2
  # storage (ADR 0005, ADR 0006) -- "Schedule" is now the steady baseline,
  # not an override. Weekly cadence, Monday 03:00 UTC: matches OWID's and
  # World Bank's own weekly/monthly refresh_check cadence
  # (config/sources.yaml) -- more frequent execution would only cost more
  # for no fresher data. NOTE: azurerm_container_app_job's trigger_type is
  # immutable -- changing this value forces destroy+recreate of the job
  # resource (no data loss: the job holds no state, everything lives in
  # the untouched storage account) rather than an in-place update.
  default = "Schedule"
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "log_daily_quota_gb" {
  type        = number
  description = "Hard daily Log Analytics ingestion cap in GB. 0.1GB (100MB) is already ~100x a weekly batch job's actual log volume (KB-scale structured JSON, INFO only, no DataFrame payloads) -- lowest sensible value that still leaves real headroom, not a value likely to clip legitimate logs."
  default     = 0.1
}

variable "monthly_budget_gbp" {
  type    = number
  default = 10
}

variable "github_repo" {
  type        = string
  description = "'owner/name' for GitHub OIDC federation. Empty skips it (e.g. before the repo has a GitHub remote)."
  default     = ""
}

variable "deploy_api" {
  type        = bool
  description = "Deploy the M10 read-only API Container App (docs/api/deployment.md). Off by default."
  default     = false
}

variable "api_image_tag" {
  type        = string
  description = "Immutable git-SHA tag for the API image. Only used when deploy_api = true."
  default     = ""
}

variable "api_ghcr_image_name" {
  type    = string
  default = "climate-risk-api"
}

variable "api_image_digest" {
  type        = string
  description = "Immutable digest (sha256:...) of the API image, exposed to the running API via CLIMATE_RISK_API_IMAGE_DIGEST for /api/v1/meta. Optional -- empty means the field stays null."
  default     = ""
}

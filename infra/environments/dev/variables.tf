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
  default = "climate-transition-risk"
}

variable "job_trigger_type" {
  type    = string
  default = "Manual" # switch to "Schedule" only after a successful manual smoke test
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

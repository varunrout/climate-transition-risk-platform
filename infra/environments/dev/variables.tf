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

variable "job_trigger_type" {
  type    = string
  default = "Manual" # switch to "Schedule" only after a successful manual smoke test
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "log_daily_quota_gb" {
  type    = number
  default = 0.5
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

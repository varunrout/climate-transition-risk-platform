variable "environment_name" {
  type = string
}

variable "job_name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "log_analytics_workspace_id" {
  type = string
}

variable "job_identity_id" {
  type = string
}

variable "image_ref" {
  type        = string
  description = "Full public GHCR image reference, e.g. ghcr.io/<owner>/climate-transition-risk:<git-sha>. Immutable git-SHA tag, never 'latest'. Public image -> no registry credentials needed to pull it."
}

variable "image_digest" {
  type        = string
  description = "sha256 digest of the pushed image, for provenance in the publish manifest. Empty string if not yet known (e.g. before the first push)."
  default     = ""
}

variable "trigger_type" {
  type        = string
  description = "Manual (default -- for the first observed smoke test) or Schedule (weekly, after that succeeds)."
  default     = "Manual"
  validation {
    condition     = contains(["Manual", "Schedule"], var.trigger_type)
    error_message = "trigger_type must be \"Manual\" or \"Schedule\"."
  }
}

variable "lake_root_url" {
  type        = string
  description = "abfss:// URL for the ADLS Gen2 lake root. See main.tf KNOWN GAP comment -- not yet consumable by the pipeline."
}

variable "tags" {
  type = map(string)
}

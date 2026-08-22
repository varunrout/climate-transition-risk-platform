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

variable "acr_login_server" {
  type = string
}

variable "image_tag" {
  type        = string
  description = "Immutable git-SHA tag, e.g. output of `git rev-parse --short HEAD`. Never 'latest'."
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

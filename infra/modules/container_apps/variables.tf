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

variable "job_identity_client_id" {
  type        = string
  description = "Client ID of the job's user-assigned managed identity -- passed through as AZURE_CLIENT_ID so azure.identity picks it unambiguously. Not a secret."
}

variable "storage_account_name" {
  type        = string
  description = "ADLS Gen2 storage account name, used to build the four abfss:// zone URIs (raw/bronze/silver/gold)."
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

variable "tags" {
  type = map(string)
}

variable "deploy_api" {
  type        = bool
  description = "Deploy the M10 read-only API Container App. Off by default so a plan against an environment without a built/pushed API image stays a no-op."
  default     = false
}

variable "api_app_name" {
  type        = string
  description = "Container App name for the read-only API."
  default     = ""
}

variable "api_identity_id" {
  type        = string
  description = "Resource ID of the API's read-only user-assigned managed identity."
  default     = ""
}

variable "api_identity_client_id" {
  type        = string
  description = "Client ID of the API's managed identity, passed as AZURE_CLIENT_ID."
  default     = ""
}

variable "api_image_ref" {
  type        = string
  description = "Full public GHCR image reference for the API, e.g. ghcr.io/<owner>/climate-risk-api:<git-sha>."
  default     = ""
}

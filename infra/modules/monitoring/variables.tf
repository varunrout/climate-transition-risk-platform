variable "workspace_name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "retention_in_days" {
  type    = number
  default = 30
}

variable "daily_quota_gb" {
  type        = number
  default     = 0.5
  description = "Hard daily ingestion cap in GB -- a runaway/looping job stops sending logs rather than running up an open-ended bill."
}

variable "tags" {
  type = map(string)
}

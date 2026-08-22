variable "resource_group_name" {
  type = string
}

variable "resource_group_id" {
  type = string
}

variable "location" {
  type = string
}

variable "storage_account_id" {
  type = string
}

variable "github_repo" {
  type        = string
  description = "GitHub repo as 'owner/name' for OIDC federation. Empty string skips creating the federated credential (e.g. before the repo is pushed to GitHub)."
  default     = ""
}

variable "tags" {
  type = map(string)
}

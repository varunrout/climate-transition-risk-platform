variable "registry_name" {
  type        = string
  description = "Globally-unique ACR name (alphanumeric only, <=50 chars)."
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "tags" {
  type = map(string)
}

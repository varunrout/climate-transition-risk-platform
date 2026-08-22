variable "storage_account_name" {
  type        = string
  description = "Globally-unique storage account name (lowercase letters/numbers only, <=24 chars)."
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

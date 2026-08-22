terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
  }

  # Remote state: a single small Standard_LRS storage account/container is
  # enough (section 20 -- no complex state platform). This is deliberately
  # commented out rather than wired to a placeholder, chicken-and-egg
  # reason: the state storage account doesn't exist until something applies
  # this config. Bootstrap sequence:
  #   1. First apply runs with local state (terraform.tfstate, gitignored,
  #      never committed) to create rg-climate-risk-dev + a small
  #      "sttfstateclimaterisk" storage account with a "tfstate" container.
  #   2. Uncomment the backend block below, fill in the real storage account
  #      name, run `terraform init -migrate-state` once to move local state
  #      into the remote backend.
  #   3. All subsequent applies (including from GitHub Actions via OIDC) use
  #      the remote backend.
  #
  # backend "azurerm" {
  #   resource_group_name  = "rg-climate-risk-dev"
  #   storage_account_name = "sttfstateclimaterisk" # <- fill in after step 1
  #   container_name       = "tfstate"
  #   key                  = "climate-risk-dev.tfstate"
  #   use_oidc             = true
  # }
}

provider "azurerm" {
  features {
    resource_group {
      # Never let `terraform destroy` proceed if the RG still has resources
      # this config doesn't know about -- protects any resource a human
      # created by hand inside rg-climate-risk-dev from being silently swept.
      prevent_deletion_if_contains_resources = true
    }
  }
  # No subscription_id / client credentials hard-coded here: resolved from
  # environment (az login locally, OIDC federated credential in CI).
}

provider "azuread" {}

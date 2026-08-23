locals {
  tags = {
    project     = "climate-transition-risk"
    environment = var.environment
    managed_by  = "terraform"
    owner       = var.owner
  }
  name_prefix   = "${var.project_slug}-${var.environment}"
  image_ref     = "ghcr.io/${var.ghcr_owner}/${var.ghcr_image_name}:${var.image_tag}"
  api_image_ref = "ghcr.io/${var.ghcr_owner}/${var.api_ghcr_image_name}:${var.api_image_tag}"
}

# Single resource group -- no separate dev/staging/prod/shared/networking/
# observability groups. This is a portfolio project's dev environment, not
# an enterprise landing zone; environment separation is modelled by having
# `environments/<name>/` directories in this repo, not by multiplying live
# resource groups before there is a second real environment to justify one.
resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name_prefix}"
  location = var.location
  tags     = local.tags
}

module "storage" {
  source = "../../modules/storage"

  # Storage account names are globally unique across all of Azure and must be
  # <=24 lowercase alphanumeric characters -- if this collides, override with
  # `-var storage_account_name=...` rather than editing this default.
  storage_account_name = "st${replace(var.project_slug, "-", "")}${var.environment}01"
  resource_group_name  = azurerm_resource_group.main.name
  location             = azurerm_resource_group.main.location
  tags                 = local.tags
}

module "monitoring" {
  source = "../../modules/monitoring"

  workspace_name      = "log-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  retention_in_days   = var.log_retention_days
  daily_quota_gb      = var.log_daily_quota_gb
  tags                = local.tags
}

module "identity" {
  source = "../../modules/identity"

  resource_group_name = azurerm_resource_group.main.name
  resource_group_id   = azurerm_resource_group.main.id
  location            = azurerm_resource_group.main.location
  storage_account_id  = module.storage.storage_account_id
  github_repo         = var.github_repo
  tags                = local.tags
}

module "container_apps" {
  source = "../../modules/container_apps"

  environment_name           = "cae-${local.name_prefix}"
  job_name                   = "job-${local.name_prefix}-pipeline"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = module.monitoring.workspace_id
  job_identity_id            = module.identity.job_identity_id
  job_identity_client_id     = module.identity.job_identity_client_id
  storage_account_name       = module.storage.storage_account_name
  image_ref                  = local.image_ref
  image_digest               = var.image_digest
  trigger_type               = var.job_trigger_type
  tags                       = local.tags

  deploy_api             = var.deploy_api
  api_app_name           = "ca-${local.name_prefix}-api"
  api_identity_id        = module.identity.api_identity_id
  api_identity_client_id = module.identity.api_identity_client_id
  api_image_ref          = local.api_image_ref
  api_image_digest       = var.api_image_digest
}

# Cost Management budget -- an ALERTING mechanism, not a spending cap. Azure
# does not automatically stop resources when this is crossed (see
# docs/finops.md). Alerts fire to the subscription's default contact at 50/80/100%.
resource "azurerm_consumption_budget_resource_group" "main" {
  name              = "budget-${local.name_prefix}"
  resource_group_id = azurerm_resource_group.main.id

  amount     = var.monthly_budget_gbp
  time_grain = "Monthly"

  time_period {
    start_date = "2026-09-01T00:00:00Z"
  }

  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_roles  = ["Owner"]
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_roles  = ["Owner"]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_roles  = ["Owner"]
  }
}

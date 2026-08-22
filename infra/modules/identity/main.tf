# Two identities, least-privilege, scoped to this resource group only:
#
# 1. id-climate-risk-job: the RUNTIME identity Container Apps Jobs run as.
#    Storage Blob Data Contributor on the lake storage account (read/write
#    its own raw/bronze/silver/gold containers). Nothing else -- no ACR
#    role (the pipeline image is a public GHCR image, pulled with no
#    credentials at all -- see infra/modules/container_apps), no Key Vault
#    access, since v1 has no secrets to read (docs/finops.md).
#
# 2. id-climate-risk-deploy: the DEPLOY identity GitHub Actions assumes via
#    OIDC federated credential (no client secret stored anywhere). Granted
#    Contributor at resource-group scope, not subscription scope, so a
#    compromised or misconfigured workflow cannot touch anything outside
#    rg-climate-risk-dev. It cannot see or modify unrelated resources like
#    the pre-existing Azure_Learning resource group.

resource "azurerm_user_assigned_identity" "job" {
  name                = "id-climate-risk-job"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
}

resource "azurerm_role_assignment" "job_storage_blob_data_contributor" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.job.principal_id
}

resource "azurerm_user_assigned_identity" "deploy" {
  name                = "id-climate-risk-deploy"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
}

resource "azurerm_role_assignment" "deploy_contributor_scoped_to_rg" {
  scope                = var.resource_group_id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.deploy.principal_id
}

# Contributor alone cannot create/manage role assignments (this Terraform
# config assigns Storage Blob Data Contributor to the job identity above),
# so the deploy identity also needs RBAC-administration -- scoped to
# this resource group only via the built-in "Role Based Access Control
# Administrator" role, which can manage role assignments but (unlike Owner)
# cannot itself manage other resource types. This is the narrowest built-in
# role that makes `terraform apply` actually work end to end for this config.
resource "azurerm_role_assignment" "deploy_rbac_admin_scoped_to_rg" {
  scope                = var.resource_group_id
  role_definition_name = "Role Based Access Control Administrator"
  principal_id         = azurerm_user_assigned_identity.deploy.principal_id
}

resource "azurerm_federated_identity_credential" "github_actions" {
  count               = var.github_repo != "" ? 1 : 0
  name                = "github-actions-oidc"
  resource_group_name = var.resource_group_name
  parent_id           = azurerm_user_assigned_identity.deploy.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  # Restrict to pushes/deploys from the main branch of this exact repo --
  # not every branch, not every repo the token issuer could vouch for.
  subject = "repo:${var.github_repo}:ref:refs/heads/main"
}

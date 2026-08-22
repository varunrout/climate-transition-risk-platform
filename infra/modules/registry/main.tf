# Azure Container Registry -- Basic SKU (cheapest tier, ~10GB included
# storage, no geo-replication, no Premium features this single-image
# project has no use for). Images are pushed with immutable git-SHA tags
# from CI; `latest` is a convenience alias only, never the deploy target.

resource "azurerm_container_registry" "acr" {
  name                = var.registry_name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "Basic"
  admin_enabled       = false # pull auth is via managed identity + AcrPull role, not admin credentials

  tags = var.tags
}

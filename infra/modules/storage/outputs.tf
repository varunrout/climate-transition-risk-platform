output "storage_account_id" {
  value = azurerm_storage_account.lake.id
}

output "storage_account_name" {
  value = azurerm_storage_account.lake.name
}

output "primary_dfs_endpoint" {
  value = azurerm_storage_account.lake.primary_dfs_endpoint
}

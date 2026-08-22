output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "storage_account_name" {
  value = module.storage.storage_account_name
}

output "acr_login_server" {
  value = module.registry.login_server
}

output "container_app_job_id" {
  value = module.container_apps.job_id
}

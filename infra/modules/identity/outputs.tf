output "job_identity_id" {
  value = azurerm_user_assigned_identity.job.id
}

output "job_identity_client_id" {
  value = azurerm_user_assigned_identity.job.client_id
}

output "deploy_identity_client_id" {
  value = azurerm_user_assigned_identity.deploy.client_id
}

output "api_identity_id" {
  value = azurerm_user_assigned_identity.api.id
}

output "api_identity_client_id" {
  value = azurerm_user_assigned_identity.api.client_id
}

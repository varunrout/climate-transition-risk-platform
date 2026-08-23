output "job_id" {
  value = azurerm_container_app_job.pipeline.id
}

output "environment_id" {
  value = azurerm_container_app_environment.main.id
}

output "api_url" {
  value       = var.deploy_api ? "https://${azurerm_container_app.api[0].ingress[0].fqdn}" : ""
  description = "Public HTTPS URL of the API Container App, empty string if not deployed."
}

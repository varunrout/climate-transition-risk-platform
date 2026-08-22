output "job_id" {
  value = azurerm_container_app_job.pipeline.id
}

output "environment_id" {
  value = azurerm_container_app_environment.main.id
}

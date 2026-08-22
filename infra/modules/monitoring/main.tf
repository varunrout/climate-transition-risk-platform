# Log Analytics only -- no Application Insights. App Insights adds request
# tracing/APM value for a live web app; this project's compute is finite
# batch jobs whose useful telemetry (run_id, stage, duration, row_count,
# quality_status -- see climate_risk.observability.logging) is already
# structured JSON on stdout, which Container Apps Jobs forwards to Log
# Analytics automatically. Adding App Insights here would be paying for a
# capability nothing in this project uses. Documented in docs/finops.md.
#
# Cost guardrails: PerGB2018 (pay-as-you-go, no fixed cost when idle),
# short 30-day retention, and a daily ingestion cap so a noisy/looping job
# can't run up an unbounded bill before anyone notices.

resource "azurerm_log_analytics_workspace" "main" {
  name                = var.workspace_name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = var.retention_in_days
  daily_quota_gb      = var.daily_quota_gb

  tags = var.tags
}

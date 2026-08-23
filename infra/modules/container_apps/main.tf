# Container Apps Environment + one Container Apps Job.
#
# Environment: Consumption-only (no dedicated workload profile), which
# means zero idle cost -- the environment itself is free; you pay only for
# job executions (vCPU-seconds / GiB-seconds while a job instance runs).
#
# Job: ONE job resource running the unified `climate-risk run` command
# (ingest -> build-silver -> backtest -> score -> publish), not five
# separate per-stage jobs. `run` already fails fast -- each stage raises
# typer.Exit(1) on failure and stops the chain -- so a single job gives an
# honest pass/fail per pipeline execution without duplicating job/schedule
# config five times. Documented tradeoff in docs/finops.md: this means a
# late-stage failure (e.g. scoring) re-runs cheap early stages (ingest) on
# retry rather than resuming mid-pipeline; acceptable given each full run
# costs well under a penny in Container Apps consumption pricing.
#
# Image: a PUBLIC GitHub Container Registry (ghcr.io) image, pulled with
# NO registry credentials and NO Azure Container Registry -- the pipeline
# image contains no secrets, no credentials, no proprietary data, and no
# private assets (it's the pipeline code + public config + third-party
# libraries; all real data is fetched at runtime from public OWID/World
# Bank endpoints and written to this project's own storage). Publishing it
# publicly costs nothing on either the GitHub or the Azure side and removes
# the ~£4.20/month ACR Basic fixed charge entirely -- see docs/finops.md.
# If a future milestone ever adds a genuine secret or proprietary asset to
# the image, this must be revisited (private GHCR + a pull secret, or ACR).
#
# trigger_type defaults to "Manual" (var.trigger_type) so the very first
# real execution is a deliberate, observed `az containerapp job start`, per
# the "manual smoke test before scheduling" sequencing this project follows.
# Switch to "Schedule" with a weekly cron only after that succeeds.

resource "azurerm_container_app_environment" "main" {
  name                       = var.environment_name
  resource_group_name        = var.resource_group_name
  location                   = var.location
  log_analytics_workspace_id = var.log_analytics_workspace_id

  tags = var.tags
}

resource "azurerm_container_app_job" "pipeline" {
  name                         = var.job_name
  resource_group_name          = var.resource_group_name
  location                     = var.location
  container_app_environment_id = azurerm_container_app_environment.main.id

  replica_timeout_in_seconds = 1800 # 30 min ceiling -- local run is ~30s end to end, generous buffer
  replica_retry_limit        = 1    # fail fast, don't retry-storm; a transient source outage should surface, not silently retry into a partial publish

  identity {
    type         = "UserAssigned"
    identity_ids = [var.job_identity_id]
  }

  # No `registry` block: var.image_ref is a public ghcr.io image, so no pull
  # credentials of any kind are needed (not even the job's own managed
  # identity) -- one fewer moving part and one fewer thing that can hold a
  # stale/broken credential.

  dynamic "manual_trigger_config" {
    for_each = var.trigger_type == "Manual" ? [1] : []
    content {
      parallelism              = 1
      replica_completion_count = 1
    }
  }

  dynamic "schedule_trigger_config" {
    for_each = var.trigger_type == "Schedule" ? [1] : []
    content {
      # Weekly, Monday 03:00 UTC -- matches OWID's weekly refresh_check cadence
      # (config/sources.yaml) and World Bank's; the public sources this project
      # reads do not update more often than that, so a daily/hourly schedule
      # would only add execution cost for no fresher data.
      cron_expression          = "0 3 * * 1"
      parallelism              = 1
      replica_completion_count = 1
    }
  }

  template {
    container {
      name   = "climate-risk-pipeline"
      image  = var.image_ref # full ghcr.io/<owner>/<image>:<git-sha> reference, never ":latest"
      cpu    = 0.5
      memory = "1Gi"
      # No args override -> runs the image's default ENTRYPOINT/CMD, i.e.
      # `climate-risk --help`. Terraform sets args explicitly so the job's
      # actual behaviour is declared in code, not left to the image default.
      args = ["run"]

      # Four independent zone URIs, not one lake-root parent -- ADLS Gen2
      # has no valid abfss://<account>/.. above four separate filesystems
      # (ADR 0003's root cause). climate_risk.storage.LakeStorage reads
      # each of these directly (ADR 0004); no local-path assumption is made
      # anywhere in that read path.
      env {
        name  = "CLIMATE_RISK_RAW_ROOT"
        value = "abfss://raw@${var.storage_account_name}.dfs.core.windows.net/"
      }
      env {
        name  = "CLIMATE_RISK_BRONZE_ROOT"
        value = "abfss://bronze@${var.storage_account_name}.dfs.core.windows.net/"
      }
      env {
        name  = "CLIMATE_RISK_SILVER_ROOT"
        value = "abfss://silver@${var.storage_account_name}.dfs.core.windows.net/"
      }
      env {
        name  = "CLIMATE_RISK_GOLD_ROOT"
        value = "abfss://gold@${var.storage_account_name}.dfs.core.windows.net/"
      }
      # Selects ManagedIdentityCredential(client_id=...) directly and
      # unambiguously in climate_risk.storage.azure.resolve_credential --
      # a user-assigned identity is otherwise ambiguous to
      # DefaultAzureCredential. Non-secret identifier, safe as a plain env var.
      env {
        name  = "AZURE_CLIENT_ID"
        value = var.job_identity_client_id
      }
      env {
        name  = "CLIMATE_RISK_CONFIG_DIR"
        value = "/app/config"
      }
      # Image provenance for the publish manifest (climate_risk.cli.publish
      # reads these and records them in gold/manifests/<run_id>.json as
      # container_image_ref / container_image_digest, rather than leaving
      # those fields permanently null).
      env {
        name  = "CLIMATE_RISK_IMAGE_REF"
        value = var.image_ref
      }
      env {
        name  = "CLIMATE_RISK_IMAGE_DIGEST"
        value = var.image_digest
      }
      # production INFO logging only -- no DEBUG telemetry, no raw
      # DataFrame payloads (climate_risk.observability.logging never logs
      # more than row counts / scalar metrics; see docs/finops.md).
      env {
        name  = "CLIMATE_RISK_LOG_LEVEL"
        value = "INFO"
      }
    }
  }

  tags = var.tags
}

# M10 read-only API: one Container App (not Job) in the SAME Consumption
# environment as the pipeline job above -- no second environment, no second
# Log Analytics workspace. Public HTTP ingress, min_replicas = 0 (true
# scale-to-zero -- Azure charges nothing while no request has arrived
# recently), 0.5 vCPU / 1Gi cap when it does run. Public GHCR image again,
# so no registry credentials. Deploy this only via `var.deploy_api = true`
# (see infra/environments/dev/variables.tf) so a plain `terraform plan`
# against an environment that hasn't built/pushed the API image yet stays
# a no-op for this resource.
resource "azurerm_container_app" "api" {
  count                        = var.deploy_api ? 1 : 0
  name                         = var.api_app_name
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [var.api_identity_id]
  }

  template {
    min_replicas = 0
    max_replicas = 1 # portfolio-scale traffic; raise only if genuinely needed

    container {
      name   = "climate-risk-api"
      image  = var.api_image_ref
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "CLIMATE_RISK_GOLD_ROOT"
        value = "abfss://gold@${var.storage_account_name}.dfs.core.windows.net/"
      }
      # Read-only endpoints never need raw/bronze/silver -- CLIMATE_RISK_GOLD_ROOT
      # alone is enough for climate_risk.storage.LakeStorage.from_env(); the
      # other three zones fall back to their local-path defaults, which is
      # harmless because this API never touches them.
      env {
        name  = "AZURE_CLIENT_ID"
        value = var.api_identity_client_id
      }
      env {
        name  = "CLIMATE_RISK_CONFIG_DIR"
        value = "/app/config"
      }
      env {
        name  = "CLIMATE_RISK_LOG_LEVEL"
        value = "INFO"
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 8000
      }
      readiness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 8000
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  tags = var.tags
}

# Deployment

## Local

```bash
uv sync --extra api
uv run climate-risk build-bi && uv run climate-risk build-web   # if not already published
uv run climate-risk api --host 127.0.0.1 --port 8000 [--reload]
```

Or directly: `uvicorn climate_risk.api.app:app --reload`.

## Docker

A **dedicated** image (`Dockerfile.api`), not the batch pipeline image
(`Dockerfile`): different entrypoint (`uvicorn`, not the CLI), different
runtime shape (long-lived HTTP server vs. a one-shot job command), and no
reason for either image to grow every time a batch-only or API-only
dependency is added.

```bash
docker build -f Dockerfile.api --build-arg GIT_SHA=$(git rev-parse HEAD) \
  -t climate-risk-api:local .

docker run -p 8000:8000 \
  -v "$(pwd)/data/lake:/data/lake:ro" \
  climate-risk-api:local
```

Verified locally: startup (bundle load + validation) in ~0.4s; warm
request latency ~7ms for a full country-profile response, on the real
19-country published bundle.

## Azure: Container Apps (scale-to-zero)

Reuses **all** existing infrastructure -- no new resource group, no new
Container Apps Environment, no new Log Analytics workspace, no new
storage account, no database, no API Management, no Application Gateway.

New resources (Terraform, `infra/modules/container_apps` +
`infra/modules/identity`), gated behind `var.deploy_api = true`:

| Resource | Detail |
|---|---|
| `azurerm_container_app.api` | Consumption, `min_replicas = 0` (true scale-to-zero), `max_replicas = 1`, 0.5 vCPU / 1Gi -- same shape as the existing pipeline job. Public HTTPS ingress, target port 8000. Liveness/readiness probes on `/health`. |
| `azurerm_user_assigned_identity.api` (`id-climate-risk-api`) | Dedicated runtime identity for the API -- **not** a reuse of the job's identity. |
| `azurerm_role_assignment.api_storage_blob_data_reader` | Storage Blob Data **Reader** only (not Contributor) -- see `security.md`. |

Verified plan (`terraform plan -var="deploy_api=true" -var="api_image_tag=<git-sha>" ...`
against the real `rg-climate-risk-dev` state): **3 to add, 0 to change,
0 to destroy.** The existing pipeline job, storage account, and
monitoring workspace are untouched.

```bash
cd infra/environments/dev
terraform plan \
  -var="image_tag=<pipeline-git-sha>" -var="ghcr_owner=<owner>" \
  -var="image_digest=<pipeline-sha256>" \
  -var="deploy_api=true" -var="api_image_tag=<api-git-sha>"
terraform apply "<saved-plan>"
```

### Image

```bash
docker build -f Dockerfile.api --build-arg GIT_SHA=$(git rev-parse HEAD) \
  -t ghcr.io/<owner>/climate-risk-api:$(git rev-parse HEAD) .
docker push ghcr.io/<owner>/climate-risk-api:$(git rev-parse HEAD)
```

Public GHCR, immutable Git-SHA tag, never `:latest` -- same convention as
the pipeline image (`docs/finops.md`). **The GHCR package visibility must
be set to Public** (Settings > Danger Zone on the package page) before
Azure can pull it anonymously -- Container Apps pulls public GHCR images
with no registry credentials configured, exactly like the pipeline job.

### Cost

Azure Container Apps Consumption plan includes a monthly free grant
(180,000 vCPU-seconds, 360,000 GiB-seconds, 2,000,000 requests) that
comfortably covers portfolio-level traffic; at `min_replicas = 0` there
is no idle charge between requests. Same cost model as the existing
pipeline job, which has run since M8 within the existing
`monthly_budget_gbp` alert (`docs/finops.md`) with no adjustment needed.

### Scale-to-zero behaviour

`min_replicas = 0`: Azure deallocates the last replica after the
Consumption plan's idle cooldown when no request has arrived. The next
request triggers a cold start (container pull if not cached + Python
process start + bundle load, ~0.4s locally for the bundle-load portion
alone). This is an accepted, documented tradeoff for a portfolio demo --
not kept warm with a minimum of one replica, per the brief's explicit
instruction not to do so without approval.

### Observability

Reuses the existing Log Analytics workspace (no new one). The API logs
one structured line per request (`climate_risk.api.app`'s
`log_requests` middleware): path, method, status code, duration, plus
the bundle's `source_run_id` at startup. No response payloads, no
personal data, no secrets are ever logged.

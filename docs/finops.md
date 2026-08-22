# FinOps: cost design, guardrails, and shutdown runbook

**Status: infra/ has been written, `terraform fmt`/`validate` pass, but
`terraform plan`/`apply` have not succeeded — the Azure subscription is
currently disabled for all write operations (see "Current blocker" below).
No Azure resource for this project has been created. Costs below are
estimates from the Terraform configuration and public Azure pricing, not
measured spend.**

## Current blocker

`az provider register -n Microsoft.App --wait` and `terraform plan` both
returned:

```
ReadOnlyDisabledSubscription: The subscription '480200f9-...bbc3' is
disabled and therefore marked as read only. You cannot perform any write
actions on this subscription until it is re-enabled.
```

This is a billing/reactivation issue on "Azure subscription 1", not a
permissions problem — the account already holds Owner at subscription
scope. Resolution: reactivate the subscription in the Azure portal (Cost
Management + Billing → Subscriptions → Reactivate, or add a valid payment
method), then re-run `terraform plan` from `infra/environments/dev/`.

## Target cost

| | |
|---|---|
| Ideal steady state | £0–5/month |
| Soft ceiling | £10/month |
| Treat the ceiling as | a design constraint, not a target |

## Resource-by-resource cost table

| Resource | SKU/tier | Idle cost? | Execution cost? | Necessary? | Cheaper alternative? |
|---|---|---|---|---|---|
| ADLS Gen2 storage account | Standard_LRS, Hot (raw→Cool after 30d) | Yes — pence/month for the data volume this project has (tens of MB) | Negligible (transaction cost per read/write, this project does thousands of ops/run, not millions) | Yes — the analytical source of truth | None cheaper that still gives durable, queryable Parquet storage |
| ACR | Basic | Yes — ~£4.20/month flat (Basic SKU has a fixed monthly charge, not consumption) | None beyond storage of image layers (~750MB, well under Basic's 10GB included) | Yes — Container Apps Jobs need to pull from somewhere | GitHub Container Registry (ghcr.io) is free for public images and would remove this entire line item — **candidate cost-cut if £4.20/month matters**; kept ACR for now because it keeps identity/RBAC in one place (managed identity + AcrPull vs. a GitHub PAT) |
| Container Apps Environment | Consumption | **No** — the environment itself has no idle charge | n/a (environment ≠ compute) | Yes | n/a, already the cheapest option |
| Container Apps Job | 0.5 vCPU / 1Gi, Manual→Schedule(weekly) | **No** — scale-to-zero; billed only for actual run duration | ~£0.0001–0.0005 per run (a run takes well under 60s locally; Container Apps consumption pricing is ~$0.000024/vCPU-s + ~$0.000003/GiB-s) at weekly cadence this is pennies per year | Yes | n/a |
| Log Analytics workspace | PerGB2018, 30-day retention, 0.5GB/day cap | **No** — PerGB2018 has no fixed monthly cost, pay only for ingested GB | A weekly job's structured JSON logs are KB, not GB — realistically £0/month | Yes — run status/failure visibility | Could omit entirely and rely on `az containerapp job logs` streaming instead; kept because 30-day history for a portfolio project is worth the near-zero cost |
| Application Insights | **Not deployed** | n/a | n/a | **No** | Structured stdout logs already carry run_id/stage/duration/quality_status; App Insights' value (distributed tracing, live web request metrics) doesn't apply to a finite batch job. Omitted by design. |
| Azure Key Vault | **Not deployed** | n/a | n/a | **No** | Every configured source (OWID, World Bank) is a public, unauthenticated URL. Managed identity handles storage/ACR auth. There is currently nothing to put in a vault — see `06_data_sources_and_licensing.md`. Add it only if/when Ember (or another source) requires an API key. |
| Synapse serverless SQL | **Not deployed** | n/a | n/a | **No** | Gold Parquet is small (thousands of rows) and directly readable by pandas/Power BI/DuckDB without a SQL-over-lake layer. Synapse would add zero query capability this project's data volume needs. Revisit only if Power BI DirectQuery over the lake becomes a real requirement. |
| Azure ML / MLflow | **Not deployed** | n/a | n/a | **No** | Run manifests (`gold/manifests/<run_id>.json`) already carry config hash, git SHA, source snapshots, and backtest metrics — the reproducibility/lineage value Azure ML would add is already covered by the manifest contract in `climate_risk.contracts.run` + `publishing/barrier.py`. |
| User-assigned managed identities (×2) | n/a | **No** — identities themselves are free | n/a | Yes | n/a |
| Cost Management budget | n/a | **No** — budgets are free | n/a | Yes | n/a |

**Estimated steady-state monthly cost once deployed: roughly £4–5/month**,
almost entirely the ACR Basic SKU's fixed charge. Everything else is
consumption-based and, at this project's data volume and weekly cadence,
effectively rounds to zero. This is within the £0–5 ideal band, comfortably
under the £10 ceiling — and the £4.20 ACR line is the one deliberate,
documented exception to "everything scales to zero," kept for identity
simplicity (see table).

## Idle-cost vs execution-cost services

- **Idle cost (accrues even with zero pipeline runs):** ADLS Gen2 storage
  (pence), ACR Basic (~£4.20/month fixed).
- **Execution cost (only while a job actually runs):** Container Apps Job
  compute, storage transactions, Log Analytics ingestion. At a weekly
  schedule this is a handful of pipeline runs per month, each lasting well
  under a minute.

## Region

`uksouth`, confirmed available on this subscription
(`az account list-locations`). Single region, no geo-redundancy, no
multi-region or active-active design — the raw snapshots + manifests +
committed pipeline code already provide the rebuild capability a portfolio
project needs (see "Recovery path" below); paying for GRS/ZRS storage or a
second region would buy durability this project doesn't need.

## Storage redundancy

`Standard_LRS` — locally redundant, cheapest tier Azure offers. Chosen
over ZRS/GRS because:
1. Raw snapshots are re-fetchable from the same public upstream sources as
   long as they remain available (the whole point of `01_data_ingestion.md`'s
   manifest contract).
2. Bronze/silver/gold are all deterministically rebuildable from raw +
   committed code (backtest reproduction in ADR 0002 demonstrates this
   determinism already, locally).
3. A single-region portfolio project doesn't have an SLA to defend that
   would justify GRS's ~2x storage cost.

## Cloud storage I/O — known gap

`climate_risk.config.loader.RunPaths` and every pipeline stage read/write
plain local filesystem paths via `pandas.to_parquet`/`read_parquet`. There
is **no `abfss://` support implemented or tested yet**. The Terraform
Container Apps Job template sets `CLIMATE_RISK_LAKE_ROOT` to an `abfss://`
URL so the resource shape is correct once this lands, but running the job
today would fail at the first file write.

To close this gap: add the `adlfs` package (fsspec-compatible ADLS Gen2
backend) as a dependency, verify `pandas.to_parquet("abfss://...", storage_options=...)`
works with the job's managed identity, and add an integration test against
a real (or Azurite-emulated) ADLS Gen2 account. This is blocked on having
an enabled subscription to test against, same as the rest of M8's cloud
verification steps.

## What survives destruction

- **Nothing in Azure is at risk of loss because nothing has been created.**
- Once deployed: `terraform destroy` would delete the storage account (and
  therefore raw/bronze/silver/gold Parquet + manifests) unless explicitly
  excluded. All of it is reproducible from: (a) the committed pipeline code
  and config, and (b) re-running `climate-risk ingest` against the same
  live public sources (OWID, World Bank) — the only genuinely
  non-reproducible content is a raw snapshot's *exact bytes* if an upstream
  source revises its data before a re-fetch, which is precisely why
  `01_data_ingestion.md`'s manifest/checksum discipline exists.

## Shutdown / cost-zero commands

Once resources exist (they do not yet):

```bash
# Stop paying for everything project-related, in one step:
cd infra/environments/dev
terraform destroy -var="image_tag=<last-deployed-sha>"

# Or, cheaper-than-destroy pause (keeps data, stops the ACR fixed charge only
# by deleting just the registry -- rebuild by re-running the image-push step):
az acr delete --name <acr-name> --resource-group rg-climate-risk-dev
```

`terraform destroy` is never run automatically by this project's CI or
agents — per this repo's operating rules, it requires explicit user
instruction every time.

## Recovery path

```bash
# 1. Recreate infrastructure from code
cd infra/environments/dev
terraform apply -var="image_tag=<git-sha>"

# 2. Rebuild and push the pipeline image
docker build -t <acr-login-server>/climate-risk-pipeline:<git-sha> .
az acr login --name <acr-name>
docker push <acr-login-server>/climate-risk-pipeline:<git-sha>

# 3. Manually trigger one smoke-test run
az containerapp job start --name job-climate-risk-dev-pipeline \
  --resource-group rg-climate-risk-dev

# 4. Once verified, switch trigger_type = "Schedule" and re-apply
```

Raw snapshots re-fetch from OWID/World Bank; bronze/silver/gold/scores/
backtests rebuild deterministically from raw + committed code (same
mechanism ADR 0002 uses to reproduce the 2015→2022 backtest locally).

## Guardrails encoded in Terraform (not just documented)

- ACR: Basic SKU, `admin_enabled = false` (no static admin credentials)
- Storage: `allow_nested_items_to_be_public = false`, HTTPS-only, 7-day
  soft-delete (not indefinite)
- Container Apps Job: `replica_retry_limit = 1` (no retry storms),
  0.5 vCPU / 1Gi (smallest sensible size for a pandas/numpy/scipy job),
  `Manual` trigger by default (a human decides when the first real run
  happens; `Schedule` is opt-in after that succeeds)
- Log Analytics: `daily_quota_gb = 0.5` hard cap — a looping/noisy job
  stops sending logs rather than running up an open-ended ingestion bill
- Managed identities scoped to exactly two role assignments each (storage
  + ACR for the job identity; Contributor + RBAC Administrator on the
  resource group only for the deploy identity) — neither ever touches
  subscription scope
- `prevent_deletion_if_contains_resources = true` on the resource-group
  provider feature — `terraform destroy` refuses to proceed if a human
  added something to `rg-climate-risk-dev` outside Terraform's knowledge
- Budget alerts at 50/80/100% of £10/month — **an alerting mechanism, not
  an enforced cap**; Azure does not stop resources automatically when a
  budget is exceeded, which is why the architectural guardrails above (not
  the budget) are the real cost control

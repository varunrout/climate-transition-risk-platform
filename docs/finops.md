# FinOps: cost design, guardrails, and shutdown runbook

**Status: DEPLOYED, VERIFIED, and RUNNING ON A RECURRING SCHEDULE
(2026-08-22).** 16 resources applied to `rg-climate-risk-dev` (`uksouth`).
Three real Container Apps Job executions have run the full pipeline end to
end against live ADLS Gen2 storage and produced correct output (ADR 0005,
ADR 0006), the last one confirming a real `git_sha` in the published
manifest. `trigger_type = "Schedule"`, weekly, **Monday 03:00 UTC**.
Costs below are estimates from the Terraform configuration and public
Azure pricing; Cost Management's `currentSpend` reports £0.00 so far
(billing data lags actual usage by hours).

## Target cost

| | |
|---|---|
| Ideal steady state | < £1/month |
| Soft ceiling | £10/month |
| Treat the ceiling as | a design constraint, not a target |

## Resource-by-resource cost table (current design, 16 resources)

| Resource | SKU/tier | Idle cost? | Execution cost? | Necessary? | Cheaper alternative? |
|---|---|---|---|---|---|
| ADLS Gen2 storage account | Standard_LRS, Hot (raw→Cool after 30d) | Yes — pence/month for the data volume this project has (tens of MB) | Negligible (thousands of ops/run, not millions) | Yes — the analytical source of truth | None cheaper that still gives durable, queryable Parquet storage |
| 4× ADLS Gen2 filesystems (raw/bronze/silver/gold) | — | No (not billed separately from the account) | — | Yes — the zone layout | — |
| Storage lifecycle policy | — | No | — | Yes — moves `raw/` to Cool after 30d | — |
| Container Apps Environment | Consumption | **No** — zero idle charge | n/a | Yes | Already cheapest |
| Container Apps Job | 0.5 vCPU / 1Gi, Manual→Schedule(weekly) | **No** — scale-to-zero | ~£0.0001–0.0005 per run (well under 60s locally; ~$0.000024/vCPU-s + ~$0.000003/GiB-s) — pennies per **year** at weekly cadence | Yes | n/a |
| Log Analytics workspace | PerGB2018, 30-day retention, **0.1GB/day cap** | **No** — pay only for ingested GB | A weekly job's structured JSON logs are KB, not GB — realistically £0/month | Yes — run status/failure visibility | Could omit and rely on `az containerapp job logs` streaming instead; kept for 30-day history at near-zero cost |
| 2× user-assigned managed identities | — | No — free | n/a | Yes — least-privilege auth | — |
| 3× role assignments | — | No — free | n/a | Yes — scope each identity to only what it needs | — |
| Cost Management budget | £10/month, 50/80/100% alerts | No — free | n/a | Yes — spend visibility | — |
| Resource group | — | No | — | Yes | — |
| **Container Registry (ACR)** | **removed** | — | — | **No** | **Replaced with a public GHCR image (§ below) — this was the one line item with a real idle cost (~£4.20/month Basic SKU fixed charge) and removing it is the whole point of this revision** |
| Application Insights | **Not deployed** | n/a | n/a | **No** | Structured stdout already carries run_id/stage/duration/quality_status; App Insights' distributed-tracing value doesn't apply to a finite batch job |
| Azure Key Vault | **Not deployed** | n/a | n/a | **No** | Every configured source (OWID, World Bank) is public/unauthenticated; managed identity handles storage auth. Add only if a future source needs an API key |
| Synapse serverless SQL | **Not deployed** | n/a | n/a | **No** | Gold Parquet (thousands of rows) is directly readable by pandas/Power BI/DuckDB; no SQL-over-lake layer needed at this volume |
| Azure ML / MLflow | **Not deployed** | n/a | n/a | **No** | `gold/manifests/<run_id>.json` already carries config hash, git SHA, image ref/digest, source snapshots, backtest metrics — the lineage value Azure ML would add is already covered |

**Estimated steady-state monthly cost once deployed: well under £1/month**
— every remaining resource is either free (identities, role assignments,
budget, resource group, filesystems, lifecycle policy) or pure consumption
at a data volume and weekly cadence that rounds to pence. This clears the
new "materially below £5" target and is comfortably under the £10 ceiling.

## Why GHCR instead of ACR

The pipeline image is pipeline code + public config (`config/*.yaml`) +
third-party libraries. It contains **no secrets, no credentials, no
proprietary data, and no private assets** — every data source it talks to
(OWID, World Bank) is a public unauthenticated URL, and the only outputs it
produces are written to this project's own storage at runtime. There is
nothing in the image that requires it to be private.

Publishing it as a **public** image on GitHub Container Registry
(`ghcr.io/<owner>/climate-transition-risk`) is free — no Azure resource, no
GitHub Packages storage cost for a public image — and removes the
Container Apps Job's `registry` block entirely: a public image needs **no
pull credentials at all**, not even the job's own managed identity, which
also removes the `AcrPull` role assignment that existed in the prior design.
One fewer resource, one fewer idle cost, one fewer credential surface.

If a future milestone ever puts something proprietary in the image (a
private data license, a paid API key baked into a layer — it shouldn't be,
secrets belong in Key Vault, but hypothetically), this decision must be
revisited: either a private GHCR repository (still free, but needs a pull
secret) or ACR.

**Image provenance is preserved** despite dropping the registry-managed
digest tracking ACR would have given "for free": the Container Apps Job
template sets `CLIMATE_RISK_IMAGE_REF` and `CLIMATE_RISK_IMAGE_DIGEST` env
vars (`infra/modules/container_apps/main.tf`), which `climate-risk publish`
reads and records as `container_image_ref`/`container_image_digest` in
`gold/manifests/<run_id>.json` — verified locally by setting those env vars
and confirming they land correctly in a real published manifest.

## Idle-cost vs execution-cost services

- **Idle cost (accrues even with zero pipeline runs):** ADLS Gen2 storage
  (pence/month). That's it — GHCR (public, free), Container Apps
  Environment (consumption), and everything else in the table above has
  zero idle cost.
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

## Observability cost controls

- **Log Analytics daily cap lowered to 0.1GB** (was 0.5GB) — still ~100x a
  weekly batch job's actual log volume, so real headroom remains; a
  runaway/looping job now hits the ceiling and stops ingesting sooner
  rather than later.
- **30-day retention**, unchanged — enough history for a portfolio project,
  not indefinite.
- **Production INFO logging only**: `climate_risk.observability.logging`
  defaults to INFO and now reads `CLIMATE_RISK_LOG_LEVEL` explicitly (the
  Container Apps Job template sets it to `INFO` in Terraform rather than
  leaving it to an implicit default) — DEBUG-level telemetry is never
  enabled in the deployed environment.
- **No large payload/DataFrame logging**: every pipeline stage logs scalar
  metrics (run_id, stage, duration_s, row_count, quality_status) via
  `structlog`, never a raw DataFrame. The CLI's summary tables printed to
  stdout at the end of `backtest`/`score` are small by construction (3 and
  19 rows respectively) — visibility, not a payload dump.

## Cloud storage I/O — resolved

**Status: implemented and verified against real ADLS Gen2 (ADR 0004, ADR 0005).**
`climate_risk.storage.LakeStorage` replaced the old `RunPaths` with four
independently-rooted zone backends (`CLIMATE_RISK_{RAW,BRONZE,SILVER,GOLD}_ROOT`),
each talking to storage through the `StorageBackend` protocol rather than
raw `pathlib`. `AzureStorageBackend` (fsspec + adlfs) authenticates via
`ManagedIdentityCredential(client_id=...)`, selected unambiguously via the
job's `AZURE_CLIENT_ID` env var — no account key, SAS, or connection
string anywhere.

A second Azure smoke test (ADR 0005, 2026-08-22) ran the full pipeline —
ingestion through publish — end to end against the real
`stclimateriskdev01` account and produced output identical to the local
baseline: same `snapshot_set_id`, same backtest metrics, same country
scores. `raw`/`bronze`/`silver`/`gold` all populated correctly; the fail-
closed publish barrier wrote `latest_successful_run.json` last, after
verifying its required artifacts existed.

**Known remaining gap, not related to storage:** the published manifest's
`git_sha` field is `null` when run in the container, because
`git rev-parse HEAD` has no `.git` directory to read from inside the
image (correctly excluded via `.dockerignore`). The image tag/digest
already carry the git SHA and remain the authoritative provenance record;
fixing the manifest field properly means baking the SHA in as a build-time
`ARG`/`ENV` instead of a runtime `git` subprocess call.

## What survives destruction

- `terraform destroy` would delete the storage account (and therefore
  raw/bronze/silver/gold Parquet + manifests currently sitting in
  `stclimateriskdev01`) unless explicitly excluded. All of it is
  reproducible from: (a) the committed pipeline code and config, and (b)
  re-running `climate-risk ingest` against the same live public sources
  (OWID, World Bank) — the only genuinely non-reproducible content is a
  raw snapshot's *exact bytes* if an upstream source revises its data
  before a re-fetch, which is precisely why `01_data_ingestion.md`'s
  manifest/checksum discipline exists.
- GHCR images are independent of the Azure resource group entirely —
  `terraform destroy` cannot touch them.

## Shutdown / cost-zero commands

```bash
# Stop paying for everything project-related, in one step:
cd infra/environments/dev
terraform destroy -var="image_tag=472fd07" -var="ghcr_owner=varunrout"
```

There is no per-resource "pause" step to document beyond this — every
remaining resource is either free or pure scale-to-zero consumption, so
there is no meaningful cost to pause short of full teardown.

`terraform destroy` is never run automatically by this project's CI or
agents — per this repo's operating rules, it requires explicit user
instruction every time.

## Recovery path

```bash
# 1. Push the pipeline image to GHCR (public, free). --build-arg GIT_SHA
# is what populates the manifest's git_sha field (ADR 0006) and the
# org.opencontainers.image.revision OCI label -- without it both fall back
# to empty/null, not an error, but worth not forgetting.
docker build --build-arg GIT_SHA=$(git rev-parse HEAD) -t ghcr.io/<owner>/climate-risk-pipeline:$(git rev-parse --short HEAD) .
echo "$GHCR_TOKEN" | docker login ghcr.io -u <owner> --password-stdin
docker push ghcr.io/<owner>/climate-risk-pipeline:<git-sha>
docker inspect --format='{{index .RepoDigests 0}}' ghcr.io/<owner>/climate-risk-pipeline:<git-sha>  # capture digest for provenance

# 2. Recreate infrastructure from code
cd infra/environments/dev
terraform apply -var="image_tag=<git-sha>" -var="ghcr_owner=<owner>" -var="image_digest=<sha256:...>"

# 3. The job is already on trigger_type = "Schedule" (weekly, Monday 03:00
# UTC) by default -- it will run automatically. To force one run sooner:
az containerapp job start --name job-climate-risk-dev-pipeline \
  --resource-group rg-climate-risk-dev
```

Raw snapshots re-fetch from OWID/World Bank; bronze/silver/gold/scores/
backtests rebuild deterministically from raw + committed code (same
mechanism ADR 0002 uses to reproduce the 2015→2022 backtest locally).

## Guardrails encoded in Terraform (not just documented)

- No registry credentials anywhere — the image is public GHCR, pulled with
  no `registry` block and no role assignment
- Storage: `allow_nested_items_to_be_public = false`, HTTPS-only, 7-day
  soft-delete (not indefinite)
- Container Apps Job: `replica_retry_limit = 1` (no retry storms),
  0.5 vCPU / 1Gi (smallest sensible size for a pandas/numpy/scipy job,
  unchanged since first deployment -- enabling the schedule did not
  increase compute size), `trigger_type = "Schedule"` (weekly, Monday
  03:00 UTC -- evaluated in UTC, Azure's fixed behaviour for Container
  Apps Jobs cron schedules, not configurable per-job). Reaching this state
  required two manual smoke tests to succeed first (ADR 0005, ADR 0006) --
  `trigger_type` is immutable in Azure's schema, so this change replaced
  the job resource (0 data loss: the job holds no state) rather than
  updating it in place.
- Log Analytics: `daily_quota_gb = 0.1` hard cap — a looping/noisy job
  stops sending logs rather than running up an open-ended ingestion bill
- Managed identities scoped narrowly: the job identity gets exactly one
  role (Storage Blob Data Contributor on its own storage account, nothing
  else — no ACR role to hold anymore); the deploy identity gets Contributor
  + RBAC Administrator on the resource group only, never subscription scope
- `prevent_deletion_if_contains_resources = true` on the resource-group
  provider feature — `terraform destroy` refuses to proceed if a human
  added something to `rg-climate-risk-dev` outside Terraform's knowledge
- Budget alerts at 50/80/100% of £10/month — **an alerting mechanism, not
  an enforced cap**; Azure does not stop resources automatically when a
  budget is exceeded, which is why the architectural guardrails above (not
  the budget) are the real cost control

# ADR 0006: Git provenance fix and recurring weekly schedule enabled

- Status: Accepted
- Date: 2026-08-22

## Context

ADR 0005 closed the Azure end-to-end gap but left one honest limitation:
the published manifest's `git_sha` field was `null` in the container,
because `git rev-parse HEAD` has no `.git` directory to read from (the
image deliberately doesn't ship repo history). This ADR closes that gap
without copying `.git` into the image, and records enabling the recurring
weekly schedule once a clean run confirmed the fix.

## Provenance fix

`climate_risk.contracts.run.resolve_git_sha()` replaces
`current_git_commit()` with an explicit precedence: `CLIMATE_RISK_GIT_SHA`
env var first, `git rev-parse HEAD` fallback for local-checkout runs, `None`
only if genuinely unavailable. The Dockerfile takes a `GIT_SHA` build arg
(empty default, never a placeholder string) and bakes it in as both the
`CLIMATE_RISK_GIT_SHA` env var and the standard
`org.opencontainers.image.revision` OCI label. Deliberately not inferred
from the GHCR tag: a tag is a label a deploy step chooses to apply, not
something the running process can attest to about itself.

## New image

Built at commit `6bafc0aae4e6854eb81122048d1c22dff273602d` with
`docker build --build-arg GIT_SHA=$(git rev-parse HEAD) ...`. Pushed to
`ghcr.io/varunrout/climate-risk-pipeline:6bafc0a`, digest
`sha256:bde8ac5408e3a129ceaf36fdedc01e533523499874fa8926ee3e7ae5914536e2`,
anonymous pull re-verified.

## Terraform: image update

`terraform plan` showed exactly **0 add, 1 change, 0 destroy** (the
Container Apps Job's image/digest env vars only) — applied cleanly.

## Third smoke test: SUCCEEDED, git_sha confirmed

Execution `job-climate-risk-dev-pipeline-4vypcbo` succeeded. Downloaded
manifest confirms every required field, including the one this ADR set
out to fix:

```json
"git_sha": "6bafc0aae4e6854eb81122048d1c22dff273602d",
"container_image_ref": "ghcr.io/varunrout/climate-risk-pipeline:6bafc0a",
"container_image_digest": "sha256:bde8ac5408e3a129ceaf36fdedc01e533523499874fa8926ee3e7ae5914536e2",
"azure_job_execution_id": "job-climate-risk-dev-pipeline-4vypcbo",
"publish_status": "PUBLISHED"
```

Analytical outputs identical to every prior run: same `source_snapshot_ids`
(upstream data unchanged), same `config_hash`, same backtest metrics, same
scores — expected and correct given identical inputs, not coincidence.

## Recurring weekly schedule enabled

With the git-provenance gap closed and a clean successful run confirming
it, `job_trigger_type` changed from `"Manual"` to `"Schedule"`
(`infra/environments/dev/variables.tf` default, no longer an override).

**Mechanism note:** `azurerm_container_app_job`'s `trigger_type` is an
immutable field in Azure's schema — `terraform plan` showed **1 to add,
0 to change, 1 to destroy**, a full replace of the job resource, not an
in-place update. This is unavoidable and was verified safe before
applying: the job resource holds no state (all data lives in the storage
account, confirmed untouched — 0 changes to `azurerm_storage_account`,
both managed identities, the Container Apps Environment, Log Analytics,
or the budget), so recreating it loses nothing. Applied: `1 added, 0
changed, 1 destroyed`.

## Post-enable verification

| Check | Result |
|---|---|
| Trigger type | `Schedule` (confirmed via `az containerapp job show`) |
| Schedule expression | `0 3 * * 1` — Monday 03:00 |
| Timezone semantics | Azure Container Apps Jobs cron schedules are evaluated in **UTC** (Azure's documented behaviour, not configurable per-job) |
| Retry policy | `replicaRetryLimit: 1`, unchanged |
| Timeout | `replicaTimeout: 1800` (30 min), unchanged |
| Scale-to-zero | Inherent to the Container Apps Jobs resource type — a Job has no `minReplicas`/always-on concept; it only runs when triggered, same as before |
| Compute size | `cpu: 0.5`, `memory: 1Gi` — unchanged, not increased |
| Budget | `budget-climate-risk-dev`, £10/month, still present and active |
| Resource count | 6 top-level resources in `rg-climate-risk-dev`, unchanged from before this change |
| New paid resources | None — `az group list` confirms `rg-climate-risk-dev` is still the only resource group in the subscription |
| `terraform plan` after apply | "No changes. Your infrastructure matches the configuration." — code and live state agree |

## Consequences

- The pipeline will now run automatically every Monday at 03:00 UTC
  against live OWID/World Bank data, with no manual trigger required.
- Cost posture unchanged from `docs/finops.md`'s estimate (well under
  £1/month) — nothing about enabling the schedule changes compute size,
  adds a service, or increases idle cost; it only changes *when* the
  existing scale-to-zero job runs.
- `git_sha` is now a reliably real field in every published manifest going
  forward, closing the last honest gap from ADR 0005.

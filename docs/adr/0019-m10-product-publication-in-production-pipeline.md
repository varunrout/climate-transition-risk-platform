# ADR 0019: Downstream product publication (gold/bi + gold/web) joins the scheduled production pipeline

- Status: Accepted.
- Date: 2026-08-23

## Context

M10 (ADR 0018) built a read-only API that serves the `gold/web` bundle. When
the API's Container App was first deployed to Azure it crash-looped. Two
distinct, real root causes were found by reading actual crash logs (Log
Analytics, after the streaming logs API returned intermittent 500s), not by
guessing:

1. `climate_risk.storage.runtime.validate_cloud_storage_invariant()` (the
   guard ADR 0010 added after the M6 silent-local-fallback incident)
   requires **all four** lake zones to resolve to ADLS/abfss whenever
   `CONTAINER_APP_NAME`-style environment markers are present -- and Azure
   sets those for Container **Apps**, not just Container Apps **Jobs**. The
   API's Terraform config had only ever set `CLIMATE_RISK_GOLD_ROOT`, on the
   (now-proven-wrong) assumption that a read-only, gold-only service didn't
   need the other three. Fixed in `infra/modules/container_apps/main.tf` by
   setting all four zone env vars on the API container, same as the pipeline
   job already does.
2. Once (1) was fixed, the API's fail-closed startup validation
   (`climate_risk.api.repository.load_bundle`) correctly refused to start,
   because **`gold/bi` and `gold/web` had never been published to the real
   Azure storage account at all.** `climate-risk build-bi` and
   `climate-risk build-web` had only ever been run locally, against a local
   filesystem lake. The scheduled production Container Apps Job's `args =
   ["run"]` chains `ingest -> build-silver -> backtest -> score -> publish`
   -- `build-bi`/`build-web` were added later (M9) as separate, standalone
   CLI commands and were never wired into the scheduled job.

## Decision considered and rejected: one-off job execution override

The immediate unblock would have been `az containerapp job start --command
... --args "climate-risk build-bi && climate-risk build-web"` -- a one-off
execution of the existing job with its command/args overridden for a single
run. This was explicitly rejected: it repeats the exact pattern (a
per-execution template/command override diverging from the
Terraform-declared, scheduled configuration) that caused the M6 storage
silent-fallback incident (ADR 0010) to go undetected for as long as it did --
whatever actually ran was not what the scheduled configuration says runs.
A one-off override would have unblocked the API once, invisibly, without
fixing anything the next scheduled Monday-03:00-UTC execution would do.

## Decision

Downstream product publication becomes a **persistent stage of the normal
production pipeline**, not a manual or one-off step:

- `climate_risk.publishing.product.publish_product()` (exposed as
  `climate-risk publish-product`, and invoked automatically by `climate-risk
  run` immediately after `publish()` succeeds) builds `gold/bi` then
  `gold/web` from the just-published core release, then **re-reads
  everything back from storage** to verify completeness and per-file
  integrity before declaring success -- the same "trust the backend read,
  not the in-process write" pattern `climate_risk.storage.runtime.
  verify_durable_success` already uses for the core release.
- **Core/product separation is preserved exactly as designed in ADR
  0016/0017**: `climate_risk.publishing.barrier` (the core fail-closed
  publish gate, `gold/latest_successful_run.json`) is untouched by this
  change. `publish_product()` requires a core release to already exist and
  never writes to or mutates the core pointer. A product-publication failure
  exits the `run` command non-zero (so Azure Container Apps Job monitoring
  sees the scheduled run failed) but leaves the previously valid core
  release, and any previously valid `gold/bi`/`gold/web` bundle, completely
  untouched -- there is no window where a partial/corrupt product bundle
  could pass the API's own startup validation, because the manifest (with
  its per-file SHA-256/row-count entries) is written last, after every data
  file, exactly as before (ADR 0017).
- Same code path locally and in Azure: `climate-risk run` behaves
  identically wherever it's invoked; no Azure-specific branch, no execution
  template override.

## Verification

Ran the complete production orchestration locally (`climate-risk run`
against a from-scratch local lake): ingest -> build-silver -> backtest ->
score -> publish -> **publish-product**, all in one process, all succeeding
in sequence. Confirmed independently (re-reading from disk, not trusting
log lines) that `gold/latest_successful_run.json`, `gold/bi/run_metadata.
parquet`, and `gold/web/manifest.json` all reference the exact same
`run_id`. New test coverage:
`tests/unit/test_publishing_product.py` (verification-layer unit tests --
missing manifest, run_id mismatch, tampered file hash, missing referenced
file, active-score/scenario-method mismatch, non-finite-literal detection,
unsafe run-metadata field leakage) and `tests/integration/
test_publish_product_cli.py` (full CLI-level: a real `publish()` followed
by a real `publish_product()` against a from-scratch fake local lake, plus
"no prior core release" and "a build failure never touches the core
pointer" cases). Full `ruff check`/`ruff format --check`/`mypy`/`pytest -q`
all pass.

## Production rollout

A new pipeline image is built from the commit that includes this change
and pushed to the same public GHCR repository the batch pipeline already
uses (`ghcr.io/varunrout/climate-risk-pipeline:<new-git-sha>`), and the
existing scheduled Container Apps Job (`job-climate-risk-dev-pipeline`) is
updated via Terraform to reference it -- an image/tag change only, not a
new resource. The job is then triggered once using its normal
Terraform-managed template (no command/args/image override, precisely to
prove the actual scheduled configuration works end to end), and `gold/bi`
+ `gold/web` are verified to exist in the real Azure storage account via
Entra-authenticated (no keys/SAS/connection-strings) reads before the API
Container App is expected to recover.

## Consequences

- The weekly scheduled run (Monday 03:00 UTC) now keeps `gold/web` current
  automatically; the API no longer depends on anyone remembering to run
  `build-bi`/`build-web` by hand.
- A product-publication failure is now operationally visible (non-zero job
  exit) rather than silently leaving a stale-but-undetected `gold/web`.
- No new Azure resources, no new schedule, no change to job CPU/memory/
  retry/timeout/identity -- only the container image reference changes.

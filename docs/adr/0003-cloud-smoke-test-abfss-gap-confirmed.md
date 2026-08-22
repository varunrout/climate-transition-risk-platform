# ADR 0003: First Azure smoke run confirmed the abfss:// gap for real

- Status: Accepted (failure confirmed, fix not yet implemented)
- Date: 2026-08-22

## Context

`docs/finops.md` and `infra/modules/container_apps/main.tf` both documented,
before any Azure deployment existed, that `climate_risk.config.loader.RunPaths`
only reads/writes local filesystem paths and has no `abfss://` support —
flagged as a known gap rather than tested. Once the subscription was
reactivated, the 16-resource dev environment was applied and one manual
`az containerapp job start` execution was run against it.

## What happened

Execution `job-climate-risk-dev-pipeline-ysfx443` pulled
`ghcr.io/varunrout/climate-risk-pipeline:3d88f88` successfully (public
image, no credentials, confirmed in `ContainerAppSystemLogs_CL`: "Pulling
image" → "Successfully pulled image ... in 300ms"), started the container,
and crashed within roughly a second with:

```
PermissionError: [Errno 13] Permission denied: 'abfss:'
```

Traceback shows `RunPaths.ensure_zones()` → `pathlib.Path.mkdir()` trying
to create a literal local directory named `abfss:` — `CLIMATE_RISK_LAKE_ROOT=
abfss://raw@stclimateriskdev01.dfs.core.windows.net/..` was interpreted as
a plain relative filesystem path, not a URL, exactly as predicted. This
happened inside the `ingest` stage of `climate-risk run`, before any
network call to OWID/World Bank and before any Azure Storage SDK call —
there is no Azure SDK code in the ingestion/silver/backtest/score/publish
path at all yet, so this is not a permissions or auth failure, it's a
missing capability.

`replica_retry_limit = 1` produced exactly one retry (`-r74lh`, then
`-msnsz`), both failing identically — confirming this is deterministic
code behaviour, not a transient fault, which is the correct signal for
`replica_retry_limit = 1` to have caught quickly rather than retry-storming
against a bug that retrying cannot fix.

Verified via account-key `az storage fs file list` that all four
containers (`raw`, `bronze`, `silver`, `gold`) are empty — no partial or
corrupt data reached storage, consistent with the crash happening before
any storage I/O was attempted.

## Consequences

- The Azure deployment itself is validated: image pull, managed identity,
  Container Apps Job scheduling, log delivery to Log Analytics, and the
  publish barrier's fail-closed design (nothing was published, nothing
  claims to have run) all worked exactly as designed.
- The pipeline cannot yet produce real cloud output. Closing this requires
  the work already scoped in `docs/finops.md`'s "Cloud storage I/O" section:
  add the `adlfs` package, make `RunPaths` fsspec-aware for `abfss://` roots
  (dispatching to local `pathlib` for local roots, unchanged), verify
  `pandas.to_parquet`/`read_parquet` against the real `stclimateriskdev01`
  account under the job's managed identity, then re-run this exact smoke
  test to confirm a real end-to-end cloud pass.
- Cost impact of this failed run: negligible — a few seconds of 0.5vCPU/1Gi
  Container Apps consumption compute across two attempts, well under the
  per-run estimate in `docs/finops.md`.

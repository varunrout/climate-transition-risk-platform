# ADR 0010: M6 Azure promotion blocked -- reproducible silent-write incident

- Status: Accepted (incident record preserved; root cause fixed; M6 Azure promotion complete).
- Date: 2026-08-22

## Context

ADR 0009 froze and locally verified the M6 phase-3 production score (v2,
`energy_component_v2.1`). Per the M6 phase-3 brief, the next steps were:
build/push the new image, apply the minimal Terraform image update, and
run one manual Azure execution to validate before relying on the weekly
schedule. This ADR records what was found when that validation was
actually attempted -- honestly, including a failure the brief did not
anticipate.

## What was done

1. Built and pushed `ghcr.io/varunrout/climate-risk-pipeline:7f11e31`
   (git SHA `7f11e31d27c558a2e0172c2cb1aed45eef7465f3`), digest
   `sha256:75dc6de8c9ad94e91b07f92d3e9014e50549a659cfa4ec7c38bb66b39d77e8b1`.
   Anonymous pull re-verified (`docker logout` + `rmi` + pull with zero
   cached credentials).
2. `terraform plan`/`apply` for the image update: **0 add, 1 change, 0
   destroy** (only the Container Apps Job's image/digest env vars), exactly
   the expected shape.
3. Ran one manual execution (`climate-risk run`, execution
   `job-climate-risk-dev-pipeline-8r4dvow`): Azure reported
   **`Succeeded`** (system logs: "successfully completed", no errors).
   Container console logs (Log Analytics) show a complete, ordinary-looking
   run: all three sources ingested `ACCEPTED`, silver panel and energy
   table built, backtest run, v1 *and* v2 scores computed, and
   `publish` logging `"published" ... active_score_version=v2_energy`
   with a real `run_id`.

## What verification found

Direct ADLS Gen2 verification (both the `az storage fs` DFS-specific
commands and the plain Blob API, cross-checked against a live
write/read/delete round trip against the same account to rule out a
verification-tooling problem) shows **none of that execution's output
actually reached storage**:

- No `raw/source=*/ingest_date=2026-08-22/run_id=9eddfb50-...` (or the
  earlier `run_id=6b3a5e8c-...`) directory exists.
- `gold/country_transition_risk_v2.parquet`: `exists() == false`
  (checked directly, not just via listing).
- Every gold file present is from an *earlier* run (job execution
  `job-climate-risk-dev-pipeline-4vypcbo`, image `6bafc0a`, the last
  execution recorded in ADR 0006) -- `lastModified` timestamps and manifest
  contents confirm this precisely, not a guess.

This was **reproduced on a second, minimal execution** (`climate-risk
ingest` only, execution `job-climate-risk-dev-pipeline-agnn6vw`, run_id
`9eddfb50-06d2-485d-ba6b-e3dce6da31ab`): console logs show `"status":
"ACCEPTED"` / `"event": "ingest complete"` for all three sources, but the
raw zone shows no trace of that run afterward either. Ruling out timing:
storage was checked repeatedly over several minutes with no change, and a
fresh, unrelated test blob (written directly via `az storage blob upload`)
was visible immediately -- the storage account itself has no propagation
delay.

## What this rules out

- **Not RBAC/identity**: the job's user-assigned identity
  (`id-climate-risk-job`) is intact and unchanged by this apply (Terraform
  plan showed only image/digest changing); its principal ID matches the
  `owner` field on the *existing* (older, correctly-written) gold files,
  confirming this identity has successfully written to this exact
  container before.
- **Not dependency drift**: `uv.lock` is unchanged since before ADR 0006's
  working run (`git diff 6bafc0a..7f11e31 -- uv.lock` is empty) -- the
  `--frozen` install in the Dockerfile guarantees identical
  fsspec/adlfs/pandas/pyarrow versions in both images.
- **Superseded inference about env-var loss**: the first investigation treated
  `validate-config` seeing `CLIMATE_RISK_CONFIG_DIR=/app/config` as evidence
  that the job-template env block survived the override. The follow-up proved
  that inference wrong: `CLIMATE_RISK_CONFIG_DIR=/app/config` is baked into the
  Dockerfile, while the four ADLS zone-root env vars were absent from the
  failed execution template.
- **Not the verification tooling**: a live write/read/delete round trip
  against the same storage account via the same account-key auth path
  succeeded instantly.
- **Not a pre-existing bug independent of this session's changes**: ADR
  0005/0006 proved the identical storage code path
  (`climate_risk.storage.azure`, untouched by any M6 work) worked
  end-to-end with real writes against this same account.

## Root cause (proven in follow-up)

The failed executions were started with a per-execution image/command/args
override. Azure execution metadata for the two reproduced failures shows:

- `job-climate-risk-dev-pipeline-8r4dvow`: image
  `ghcr.io/varunrout/climate-risk-pipeline:7f11e31`,
  `command=["climate-risk"]`, `args=["run"]`, status `Succeeded`.
- `job-climate-risk-dev-pipeline-agnn6vw`: image
  `ghcr.io/varunrout/climate-risk-pipeline:7f11e31`,
  `command=["climate-risk"]`, `args=["ingest"]`, status `Succeeded`.

Those execution templates do not contain the Terraform job-template env
block with `CLIMATE_RISK_RAW_ROOT`, `CLIMATE_RISK_BRONZE_ROOT`,
`CLIMATE_RISK_SILVER_ROOT`, and `CLIMATE_RISK_GOLD_ROOT`. The current live
job template, after rollback, does contain all four `abfss://...` roots and
the user-assigned managed identity `AZURE_CLIENT_ID`.

The earlier note that `validate-config` saw `CLIMATE_RISK_CONFIG_DIR=/app/config`
did **not** prove the Terraform env block survived the manual start
override: the Dockerfile itself also bakes `CLIMATE_RISK_CONFIG_DIR=/app/config`.
The same Dockerfile also bakes `CLIMATE_RISK_LAKE_ROOT=/data/lake`.

Therefore, when the failed override execution did not receive the four
per-zone ADLS roots, `LakeStorage.from_env()` used its designed local-dev
fallback: `/data/lake/{raw,bronze,silver,gold}` inside the container. The
pipeline wrote successfully to that ephemeral container filesystem, so
Python saw no error and Azure correctly reported exit code 0 / `Succeeded`.
After the container exited, the ephemeral files disappeared, leaving ADLS
unchanged.

This was not an `adlfs`/`fsspec` flush bug. The unchanged storage code path
worked in ADR 0005/0006 because those executions used the Terraform-backed
job template with explicit ADLS zone roots. The failed image changed M6
ingestion/scoring behavior but did not change `src/climate_risk/storage`;
the dangerous missing guard was that an Azure runtime could still legally
select `LocalStorageBackend`.


## Corrective fix implemented locally

`src/climate_risk/storage/runtime.py` now adds startup storage diagnostics
and runtime invariants:

- every CLI command logs `raw`, `bronze`, `silver`, and `gold` backend
  classes plus sanitized root locations;
- if Azure Container Apps runtime is detected and any zone resolves to
  `LocalStorageBackend`, the command fails immediately with a nonzero exit;
- local development remains unchanged: local roots are still allowed when
  not running in Azure;
- after a cloud `climate-risk run` publishes, `verify_durable_success()`
  re-reads durable artifacts through the configured storage backend before
  allowing success.

The durable check verifies raw snapshots/manifests, bronze artifacts,
silver transition and energy tables, required gold score artifacts,
`latest_successful_run.json`, the manifest referenced by that pointer, the
expected current run id, and the active production score artifact declared
by the manifest.

## Preventive tests added

`tests/unit/test_storage_runtime.py` covers the incident surface directly:

- Azure runtime + local RAW/BRONZE/SILVER/GOLD root fails;
- all Azure roots are allowed;
- local runtime + local roots are allowed;
- ephemeral-only cloud run fails;
- missing raw, silver, and gold artifacts fail durable verification;
- absent latest pointer fails;
- pointer referencing the wrong run fails;
- unreadable referenced manifest fails;
- full durable verification succeeds;
- backend diagnostic logs do not include credential-like env values.

Validation on 2026-08-22: `ruff check src tests` passed,
`ruff format --check src tests` passed (with a local cache-write warning
only), `mypy src` passed, and `pytest` passed: 178 tests. A clean local
`climate-risk run` against `artifacts/local_validation_runtime` completed
real ingestion, energy silver/features, backtest, v1/v2 scoring, and
publish. Durable verifier output: raw snapshots 3, raw manifests 3, bronze
artifacts 3, silver transition 1, silver energy 1, pointer run id
`a5569731-4f83-45c0-ad4f-65960029b834`, manifest path
`manifests/a5569731-4f83-45c0-ad4f-65960029b834.json`, score version
`v2_energy`.

Terraform CLI was not installed on the local machine used for this
follow-up, so `terraform fmt`/`terraform validate` could not be rerun here.
No Terraform files were changed by the corrective fix.

## Final Azure promotion and external verification

The corrected image was built from commit
`95b7fa4ef0a0af82f99818276865039ff54cb017`, pushed as
`ghcr.io/varunrout/climate-risk-pipeline:95b7fa4`, and anonymous-pull
verified at digest
`sha256:75a77ec0d6c02a28db1fb09e72be48caf9d8c269d63b2b56af33b59b29943dcd`.
Terraform plan/apply for promotion was exactly **0 add, 1 change, 0
destroy**: only the Container Apps Job image and provenance env vars
changed. A post-apply Terraform plan reported no changes.

Controlled Azure execution `job-climate-risk-dev-pipeline-xsjvjwd` ran the
Terraform-managed template (no per-execution image/command/env override)
with image `95b7fa4`, `args=["run"]`, 0.5 vCPU, 1Gi memory, retry limit 1,
and the existing user-assigned managed identity. Log Analytics confirms
all four zones selected `AzureStorageBackend`, all three sources ingested,
energy silver/features built, backtest completed, v1 and v2 scores wrote,
and publish completed with active score version `v2_energy`. The in-job
durable verifier then re-read required artifacts and reported pointer run
id `fad0a51c-280f-48b5-9f94-4cba6d05e9cb`, manifest path
`manifests/fad0a51c-280f-48b5-9f94-4cba6d05e9cb.json`, score version
`v2_energy`, raw snapshots 7, raw manifests 7, bronze artifacts 3, silver
transition 1, and silver energy 1.

After the signed-in Azure user was granted `Storage Blob Data Reader` on
`stclimateriskdev01`, independent Azure CLI verification using
`--auth-mode login` (Entra auth only; no storage keys, SAS, or connection
strings) listed and downloaded the production artifacts externally. ADLS
listing counts were raw 27, bronze 9, silver 8, gold 12. The externally
read `latest_successful_run.json` points to
`fad0a51c-280f-48b5-9f94-4cba6d05e9cb`; the referenced manifest is readable
and declares:

- `git_sha`: `95b7fa4ef0a0af82f99818276865039ff54cb017`
- image ref: `ghcr.io/varunrout/climate-risk-pipeline:95b7fa4`
- image digest:
  `sha256:75a77ec0d6c02a28db1fb09e72be48caf9d8c269d63b2b56af33b59b29943dcd`
- `score_version`: `v2_energy`
- `component_version`: `energy_component_v2.1`
- `weights_version`: `v2_weights_v1`
- source snapshot IDs: OWID CO2 `7f78e2b218ce4bb8`, World Bank WDI
  `21cb9294d95abbb2`, OWID Energy `77b3db513f02f5ff`
- `config_hash`: `ac4bfcb823d938d3`
- `azure_job_execution_id`: `job-climate-risk-dev-pipeline-xsjvjwd`
- `publish_status`: `PUBLISHED`

Because the source checksums matched the local validation baseline, strict
local/Azure parity was required and passed for the externally downloaded
Azure artifacts: silver transition table (3763 rows), silver energy table
(2307 rows), v1 score (19 rows), v2 score (19 rows), energy features (19
rows), and backtest summary (3 rows). Snapshot IDs, energy feature values,
v1/v2 scores and ranks, component contributions, weight coverage, data
confidence, backtest metrics, config hash, and score version all matched
the local baseline.

Fail-closed publication is externally verified: `latest_successful_run.json`
points to the current valid manifest, the required score artifacts
`country_transition_risk.parquet` and `country_transition_risk_v2.parquet`
exist, and v2 is the declared active production score. This remains
governance-consistent because ADR 0008's pre-registered rule was
permutation `p <= 0.10`, positive MAE improvement, and weight robustness;
ADR 0009's hardened result remains within that rule.

## Action taken

The failed `7f11e31` image was rolled back immediately to `6bafc0a` to
protect the weekly schedule while the incident was investigated. After the
root cause was proven, the storage invariant and durable verifier were
implemented, tested, built into image `95b7fa4`, deployed through Terraform,
and validated by the controlled Azure execution and external ADLS parity
checks above.

## Consequences

- **M6 is COMPLETE.** The final score decision is ACCEPT, the frozen
  `energy_component_v2.1` / `v2_energy` specification is active in Azure,
  v1 artifacts remain preserved as comparison outputs, and the silent-success
  incident now has a fail-fast preventive invariant plus durable success
  verification.
- No new Azure services were added. The live resource inventory remains the
  same low-cost set: storage account, two managed identities, Log Analytics,
  Container Apps Environment, and Container Apps Job. Compute remains 0.5
  vCPU / 1Gi memory, retry limit 1, timeout 30 minutes, weekly Monday 03:00
  UTC schedule.
- The exact next milestone is **M7 structural-break / regime research**.

# ADR 0005: Second Azure smoke test succeeded end to end

- Status: Accepted
- Date: 2026-08-22

## Context

ADR 0003 confirmed the `abfss://` bug for real. ADR 0004 fixed it with a
backend-neutral storage abstraction. This records the result of applying
that fix to the deployed Azure infrastructure and re-running the smoke
test.

## Terraform change

`terraform plan` against the corrected code (image `472fd07`, digest
`sha256:83812b229ffec707cab09ae1ca05b4dfb544e814c9f0a18f205b7aa8eddc09a9`,
`ghcr_owner=varunrout`) produced exactly **0 to add, 1 to change, 0 to
destroy** — an in-place update of only the Container Apps Job's image
reference and environment variables (four explicit
`CLIMATE_RISK_{RAW,BRONZE,SILVER,GOLD}_ROOT` values replacing the invalid
single `CLIMATE_RISK_LAKE_ROOT`, plus `AZURE_CLIENT_ID`). No storage
account, identity, or Container Apps Environment was touched. Applied
cleanly: `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`

## Smoke test result: SUCCEEDED

Execution `job-climate-risk-dev-pipeline-zpj4lut`, 2026-08-22T13:10:53Z →
13:11:51Z (58 seconds total, including image pull). Every stage ran and
is independently visible in `ContainerAppConsoleLogs_CL`:

1. OWID ingestion — 3,744 rows, ACCEPTED
2. World Bank ingestion — 494 rows, ACCEPTED
3. Raw snapshots persisted to ADLS (`raw` filesystem: `payload.bin` +
   `manifest.json` per source, verified via `az storage fs file list`)
4. Bronze outputs persisted (`bronze` filesystem: one `data.parquet` per
   source/snapshot_id)
5. Silver panel built — 3,763 rows, `snapshot_set_id=adfc6a067fe0cb04`
6. Backtest executed — 342 splits across 6 rolling origins
7. Scoring executed — 19/19 countries scored
8. Gold outputs written (`gold` filesystem: `backtest_country_origin.parquet`,
   `backtest_summary.parquet`, `country_transition_risk.parquet`,
   `rank_stability.json`)
9. Run manifest written (`gold/manifests/dcd89544-....json`)
10. `latest_successful_run.json` written last, confirmed present and
    matching the manifest's `run_id`/`status: SUCCEEDED`

## Managed identity, proven not assumed

`AZURE_CLIENT_ID` was set to the job's own user-assigned identity client
ID, so `climate_risk.storage.azure.resolve_credential()` constructed
`ManagedIdentityCredential(client_id=...)` directly — there is no other
credential code path in this codebase (no account key, SAS, or connection
string anywhere; enforced by
`test_azure_storage_backend_has_no_key_or_secret_attributes`). The write
succeeding is therefore direct proof the managed identity path worked,
not an inference from logs.

## Local vs Azure comparison

Every deterministic field matches the local baseline exactly:

| Field | Local | Azure | Match |
|---|---|---|---|
| `source_snapshot_ids` | `{owid_co2: 7f78e2b2..., world_bank_wdi: 21cb9294...}` | identical | ✅ |
| `source_checksums` | full sha256 | identical | ✅ |
| `config_hash` | `4ffdf579946d4fe6` | identical | ✅ |
| `snapshot_set_id` | `adfc6a067fe0cb04` | identical | ✅ |
| `country_scope` | 19 countries | identical | ✅ |
| `latest_model_eligible_year` | 2024 | identical | ✅ |
| `backtest_metrics` (all 3 variants, all fields) | — | identical | ✅ |
| `score_version` / `model_variant` | v1 / empirical_bootstrap_v1 | identical | ✅ |

This is exact-match, not "close enough": the upstream OWID/World Bank
snapshots were identical between the two runs (same source_snapshot_ids),
so deterministic outputs matching exactly is the expected and correct
result, not a coincidence requiring explanation.

## Manifest field checklist (spec section 17)

All present: `run_id`, `started_at`, `completed_at`, `container_image_ref`,
`container_image_digest`, `source_snapshot_ids`, `source_checksums`,
`config_hash`, `random_seed`, `country_scope`, `quality_status`,
`model_variant`, `backtest_metrics`, `score_version`, `publish_status`,
`azure_job_execution_id` (= `job-climate-risk-dev-pipeline-zpj4lut`,
sourced from the `CONTAINER_APP_JOB_EXECUTION_NAME` env var Azure injects
— confirmed real, not a guess, by this run).

**One field is null and that is reported honestly, not hidden:** `git_sha`.
`climate_risk.contracts.run.current_git_commit()` shells out to
`git rev-parse HEAD`, which fails inside the container because `.git` is
not copied into the image (correctly excluded via `.dockerignore` — it's
not needed for the app and would bloat the image). The function catches
that failure and returns `None` rather than crashing, which is why the
run still succeeded, but it means image provenance from git SHA is
currently only available via the immutable image *tag*
(`ghcr.io/varunrout/climate-risk-pipeline:472fd07`, itself a git SHA) and
digest, not from inside the manifest's `git_sha` field. Follow-up: bake
the git SHA in at build time as a `GIT_SHA` build-arg/env var (Docker
`ARG`/`ENV`) rather than relying on a runtime `git` subprocess call that
can never work in a container with no `.git` directory.

## Cost posture after this run

- Log footprint: 39 log lines, ~6.2KB total for the entire run — no
  secrets, no DataFrame payloads (confirmed by direct inspection), several
  orders of magnitude under the 0.1GB/day cap.
- ADLS data written: raw ~14.6MB (mostly the OWID CSV payload), bronze
  ~137KB, silver ~130KB, gold ~33KB. Total well under any meaningful
  storage cost threshold.
- Subscription-wide resource check: `rg-climate-risk-dev` is still the
  only resource group in the subscription; the 6 top-level resources
  (storage account, 2 managed identities, Log Analytics workspace,
  Container Apps environment, Container Apps job) plus their sub-resources
  are exactly what Terraform manages — nothing else was created.
- Cost Management reports `currentSpend: £0.00` against the £10 budget
  (billing data lags; this run's actual cost is a few pence of Container
  Apps consumption compute plus negligible storage/transaction cost, per
  `docs/finops.md`'s estimate).

## Consequences

- The pipeline now genuinely runs end-to-end in Azure, not just in a
  container against local/mounted storage. This is the first real cloud
  execution evidence for this project.
- Recurring weekly scheduling (`trigger_type = "Schedule"`) is now
  technically safe to enable on the next apply — this smoke test was the
  explicit precondition. Not yet enabled; that remains a separate,
  deliberate step per the project's operating rules.
- `git_sha` in the manifest is a known, documented gap (see above), not a
  new blocker for anything else.

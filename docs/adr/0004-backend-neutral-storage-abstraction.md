# ADR 0004: Backend-neutral storage abstraction (fix for ADR 0003)

- Status: Accepted
- Date: 2026-08-22

## Context

ADR 0003 confirmed the abfss:// bug for real: `RunPaths` was a thin
`pathlib.Path` wrapper, and pointing it at `CLIMATE_RISK_LAKE_ROOT=
abfss://raw@stclimateriskdev01.dfs.core.windows.net/..` made
`Path("abfss://...").mkdir()` try to create a literal local directory
named `abfss:` and crash with `PermissionError`. The fix needed to be a
real storage abstraction, not a string check bolted onto `pathlib`.

A second, more fundamental correction came before writing any code: the
Azure design has **four separate ADLS Gen2 filesystems** (raw, bronze,
silver, gold), each its own container. There is no valid
`abfss://<account>/..` "parent" above them — the original single
`CLIMATE_RISK_LAKE_ROOT` env var was conceptually wrong for Azure from the
start, not just wrongly consumed.

## Decision

**Four independently-rooted zones, one `StorageBackend` per zone.**
`climate_risk.storage.LakeStorage` replaces `RunPaths`: it resolves
`raw`/`bronze`/`silver`/`gold` each from their own env var
(`CLIMATE_RISK_RAW_ROOT` etc.), falling back to `<CLIMATE_RISK_LAKE_ROOT>/
<zone>` for local-dev convenience (unchanged default:
`data/lake/{raw,bronze,silver,gold}`).

**One coherent interface, two implementations, one branch point.**
`climate_risk.storage.base.StorageBackend` is a `Protocol` with primitive
operations (`exists`, `makedirs`, `write_bytes`, `read_bytes`, `glob`,
`remove`, `modified_at`); `write_parquet`/`read_parquet`/`write_json`/
`read_json` are free functions built once on top of those primitives, so
neither backend duplicates that logic. `LocalStorageBackend` uses
`pathlib` directly (unchanged semantics, unchanged Windows path handling,
zero regression risk versus the old code). `AzureStorageBackend` uses
fsspec + adlfs. `climate_risk.storage.lake.backend_for_uri` is the **only**
place that branches on URI scheme — no `if path.startswith("abfss://")`
anywhere else in the codebase.

**Adapters fetch bytes, never touch storage.** `SourceAdapter.fetch()` used
to accept a `dest_dir: Path` and write the raw payload itself — a second,
independent place a Path/URI confusion could have hidden. It now returns
`(RawArtifact, bytes)`; `climate_risk.ingestion.pipeline.run_ingest` is the
only thing that writes to storage, via `lake.raw`/`lake.bronze`. This also
simplified `RawArtifact`, which no longer carries a `payload_path` field
that never made sense for a remote object.

**Managed identity only, no secrets, provably.** `AzureStorageBackend`
authenticates via `azure.identity`. Because the job runs under a
*user-assigned* identity, `DefaultAzureCredential()` alone is ambiguous;
`AZURE_CLIENT_ID` (a non-secret identifier) selects
`ManagedIdentityCredential(client_id=...)` directly, so which credential
path is in use is provable by construction, not by log inspection. No
account key, SAS token, or connection string appears anywhere in this
module or in the Terraform/Container Apps config that feeds it — verified
by `test_azure_storage_backend_has_no_key_or_secret_attributes`.

**Atomicity claims match what each backend actually guarantees.**
`LocalStorageBackend.write_bytes` uses same-directory temp-file +
`Path.replace` (atomic on POSIX and NTFS). `AzureStorageBackend.write_bytes`
is a single blob PUT — Azure Blob Storage guarantees that's atomic at the
object level (no reader ever observes a torn blob), which is a real,
documented property, not an assumption. Neither backend claims POSIX
cross-path rename semantics it doesn't have. The publish barrier
(`climate_risk.publishing.barrier`) builds its fail-closed guarantee on
top of this correctly: it verifies every `required_artifacts` path
actually exists *before* writing the pointer, and writes the pointer last
and alone — no reliance on a multi-file transaction the storage layer
can't provide.

**"Latest" bronze/silver snapshot is picked by real backend metadata.**
`snapshot_id`/`snapshot_set_id` directories are content-hash-named, not
time-ordered, so picking "the latest one" when several exist needs actual
last-modified metadata. `StorageBackend.modified_at()` gives that
uniformly (`Path.stat().st_mtime` locally; blob `last_modified` from
`adlfs`'s `fs.info()` on Azure) instead of assuming path/glob order
correlates with recency.

## Consequences

- **Analytical outputs are unchanged.** A full local pipeline run
  post-refactor reproduced the pre-refactor baseline exactly:
  `snapshot_set_id`, silver row count (3,763), every backtest metric
  across all three model variants, and every country's score/rank matched
  byte-for-byte (`git log` shows the comparison; the storage refactor
  touched only I/O plumbing, never the ingestion/silver/backtest/score
  logic itself).
- 79 tests pass (up from 57), including a "remote-style" backend suite
  that exercises `AzureStorageBackend`'s real glob/path/read/write logic
  against fsspec's in-memory filesystem — no live Azure credentials needed
  to test the abstraction itself; Azure verification proper still comes
  from the real cloud smoke test.
- New dependencies: `fsspec`, `adlfs`, `azure-identity`.
- Known follow-up, not yet done: this ADR fixes the storage *interface*;
  the Terraform Container Apps Job template still needs updating from the
  single invalid `CLIMATE_RISK_LAKE_ROOT=abfss://raw@.../..` to four
  explicit `CLIMATE_RISK_{RAW,BRONZE,SILVER,GOLD}_ROOT` values, and
  `AZURE_CLIENT_ID` needs wiring to the job's managed identity client ID.

# ADR 0017: M9 Web Bundle Snapshot Strategy and Publication Boundary

## Status

Accepted.

## Context

The React dashboard (ADR 0016) must run as a static site with no backend
and no exposed Azure credentials. Two decisions were needed: (1) how the
static build gets its data snapshot, and (2) whether `build-web` is part
of the core fail-closed publication barrier or a downstream artifact.

## Decision 1: data snapshot strategy

**Chosen: Option A -- package a small, current public web snapshot into
the static site build**, committed at `web/public/data/*.json`.

Rationale:

- The underlying source data (OWID CO2 + energy-mix, World Bank WDI) is
  already public, openly licensed, and non-confidential -- there is no
  privacy reason to gate it behind CI-fetched credentials.
- `build_manifest`'s `RUN_METADATA_SAFE_FIELDS` safelist already excludes
  every field that would matter if it were secret (lake-relative source
  paths, the Azure job execution id); nothing in the bundle is sensitive.
- The full bundle is ~7.6 MB (`country-timeseries.json` and
  `energy-indicators.json` dominate at ~3.6-3.7 MB each; every other file
  is under 260 KB) -- small enough to commit directly without Git LFS or
  a separate artifact store.
- Option B (CI + Entra/OIDC fetching a published bundle at build time)
  would add a real operational dependency -- a live, reachable, credentialed
  publication endpoint -- for a portfolio site whose data changes at most
  weekly. That complexity is not justified here.

Consequence: **the committed snapshot is refreshed manually** by running
`climate-risk build-web` and copying `data/lake/gold/web/*.json` into
`web/public/data/` before a deploy, not automatically on every Azure
production run. `manifest.json`'s `generated_at`/`source_run_id`/
`source_git_sha` make it obvious, in the deployed Provenance page, exactly
which analytical run a given deployment reflects -- so a stale snapshot is
visible, not silently wrong.

## Decision 2: publication boundary

**Chosen: web bundle generation is a downstream, independently
recoverable product artifact -- not part of the core fail-closed
publication barrier** (`climate_risk.publishing.barrier`).

Rationale: a JSON serialization failure in the web layer is a product
concern, not evidence that the underlying `v2_energy` score or
`empirical_bootstrap_v1` scenario run was scientifically invalid. Gating
`latest_successful_run.json` on `build-web` succeeding would let a
trivial frontend-layer bug (e.g. a new dtype `Table.TransformColumnTypes`-style
edge case) block a valid core publish. `build-web` reads only from
already-published `gold/bi/*.parquet`, so it can be re-run at any time
without re-running or re-validating the core pipeline.

Consequence: **no change to `climate_risk.publishing.barrier` or the
`publish` CLI command.** `build-web` remains a separate, manually
(or later, CI-)invoked step, consistent with how `build-bi` and
`export-bi-preview` already work.

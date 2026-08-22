# ADR 0001: Repository foundation and first ingestion sources

- Status: Accepted
- Date: 2026-08-22

## Context

The spec (`24_repo_structure_and_implementation_roadmap.md`) calls for a
uv-managed Python 3.12 package with local filesystem raw/bronze/silver/gold
zones that later map to ADLS Gen2 unchanged, and a fail-closed publishing
barrier so a partial run can never overwrite the previous release.

## Decisions

1. **uv + hatchling**, not Poetry — `uv` was not preinstalled; installed via
   `pip install --user uv` and invoked as `python -m uv` for this
   environment. Hatchling as the build backend is uv's default and requires
   no extra config.
2. **Local lake root is a plain directory tree** (`data/lake/{raw,bronze,silver,gold}`)
   addressed via `RunPaths`, whose only environment-specific input is
   `CLIMATE_RISK_LAKE_ROOT`. Swapping this for an `abfss://` root is the only
   change needed to point at ADLS Gen2 — no pipeline code depends on the
   filesystem being local.
3. **OWID country identity uses the source's own `iso_code` column directly**
   rather than fuzzy name matching, since OWID already publishes ISO-3.
   World Bank's API is queried by ISO-3 country code directly. This satisfies
   the "controlled mapping, not fuzzy-matched in production" requirement in
   `07_data_model_and_contracts.md` without needing a reconciliation step in
   M1 — `config/countries.yaml` is still the single source of truth for which
   19 countries are in scope.
4. **World Bank adapter does not subclass `HttpSourceAdapter`** — it needs two
   indicator calls (GDP, population) combined into one raw artifact, which
   doesn't fit the "one URL in, one payload out" shape the base class assumes
   for OWID. It implements the same `SourceAdapter` protocol directly instead
   of forcing an awkward abstraction onto a two-call source.
5. **Ember is present in `config/sources.yaml` but `enabled: false` /
   `licence_review_status: pending_verification`** per
   `06_data_sources_and_licensing.md` section 4 — its exact licence terms and
   machine-readable access path have not been verified yet. The config loader
   and ingest CLI both refuse to run a non-`approved` source.
6. **CLI commands for unimplemented stages (`build-silver`, `features`,
   `model`, `backtest`, `score`, `publish`) exist and exit 2 with an explicit
   "not implemented" message** rather than being silently absent — this
   makes `climate-risk run` a truthful description of pipeline state instead
   of a partial pipeline pretending to be complete.

## Consequences

- M1 ingestion is real: `climate-risk ingest` downloads live OWID CO2 data
  (3,744 rows across the 19-country panel) and World Bank WDI GDP/population
  (494 rows), and both are covered by contract tests running against local
  CSV/JSON fixtures so CI never depends on network access.
- The missing-GDP-in-latest-year condition observed in the original scratch
  analysis reproduces here as a `DQ-GDP-020` WARN event, not a silent gap —
  confirmed against live data on 2026-08-22 (19/19 G20 countries missing 2024
  GDP in the OWID snapshot, consistent with known WDI reporting lag).

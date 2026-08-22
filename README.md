# Climate Transition Risk Intelligence Platform

Country-level analytics platform for historical decarbonisation, GDP/CO2
decoupling, forward transition uncertainty and an explainable transition-risk
score, built on public data (Our World in Data, World Bank) with an
Azure-native target architecture.

**This README states only what has actually been implemented and verified in
this repository.** The full design spec (25 documents) lives in the project's
Google Drive folder and describes the target end state; a capability listed
there is not claimed here until it is implemented, tested, and committed.

## Implementation status

| Milestone | Scope | Status |
|---|---|---|
| M0 | Repo foundation: package layout, config, logging, CLI, CI, tests | **Implemented** |
| M1 | OWID CO2 + World Bank WDI ingestion (real adapters, manifests, checksums) | **Implemented** |
| M2 | Silver country-year panel (dimension, unit normalisation, completeness) | Not implemented |
| M3 | Decoupling analytics, deterministic + bootstrap scenario engine | Not implemented |
| M4 | Rolling-origin backtesting harness | Not implemented |
| M5 | Transition risk scoring, country profiles | Not implemented |
| M6 | Ember energy-transition features | Not implemented (source gated `pending_verification`, disabled) |
| M7 | Regime/structural-break research | Not implemented |
| M8 | Azure infrastructure (Terraform) | Not implemented — see `infra/` for plan-only scaffolding once added |
| M9 | Power BI semantic layer | Not implemented |
| M10 | Read-only FastAPI serving layer | Not implemented |

Ember is disabled in `config/sources.yaml` (`licence_review_status:
pending_verification`) because its exact licence, attribution wording and
machine-readable access path have not yet been verified against
`06_data_sources_and_licensing.md`. The config loader and quality gate refuse
to let a non-`approved` source influence production output.

## What actually runs today

```bash
uv sync --all-extras
uv run climate-risk validate-config
uv run climate-risk ingest          # fetches real OWID + World Bank data
uv run pytest
uv run ruff check .
uv run mypy src
```

`ingest` downloads the live Our World in Data CO2 dataset and World Bank WDI
GDP/population indicators for the 19 sovereign G20 countries, writes an
immutable raw snapshot + `manifest.json` per run under
`data/lake/raw/source=<source>/ingest_date=.../run_id=.../`, and — only if no
FATAL data-quality event fired — promotes a standardised Parquet snapshot to
`data/lake/bronze/source=<source>/snapshot_id=<sha256-prefix>/data.parquet`.
A rejected snapshot stays quarantined under `raw/`; it never overwrites the
previously accepted bronze snapshot.

`build-silver`, `features`, `model`, `backtest`, `score` and `publish` are
CLI commands that exist but intentionally exit with `NotImplementedError`
rather than fabricate output — see `src/climate_risk/cli.py`.

The fail-closed **publishing barrier** (`src/climate_risk/publishing/barrier.py`)
is implemented and tested: `latest_successful_run.json` is only ever updated
by a `SUCCEEDED` run, so a failed or in-progress run can never overwrite the
previously published release. See `tests/unit/test_publishing_barrier.py`.

## Repository layout

```text
src/climate_risk/
  config/         typed config models + YAML loader (sources.yaml, countries.yaml, quality_rules.yaml)
  contracts/      pydantic domain models: manifests, validation events, run metadata
  ingestion/      source adapters (OWID, World Bank) + orchestration pipeline
  quality/        quality rule registry + publish-gate logic
  publishing/     fail-closed latest_successful_run barrier
  observability/  structured logging (structlog)
  transforms/ features/ regimes/ scenarios/ backtesting/ scoring/ api/  (scaffolded, not yet implemented)
config/           versioned YAML: sources, countries, quality rules
tests/
  unit/           pure logic
  contracts/      adapter standardisation + quality-check contracts, adversarial fixtures
  integration/    full ingest pipeline against local fixtures (no network required)
docs/adr/         architectural decision records
infra/            Terraform (Azure) — added incrementally, plan-reviewed before any apply
```

## Design source of truth

The full specification (`00_overview.md` through
`24_repo_structure_and_implementation_roadmap.md`) is maintained outside this
repo. Key precedence rules this build follows:

1. The specification's explicit architecture choices (Azure Container Apps
   Jobs, not AKS/Databricks; ADLS Gen2 raw→bronze→silver→gold; fail-closed
   publishing; GDP-lag handled explicitly, never silently imputed).
2. Honesty rule: scratch/feasibility analysis is not evidence the platform
   exists. A capability is claimable only after it runs from committed code
   with a passing test.

## License

MIT for this repository's code. Upstream data sources (OWID, World Bank) are
CC-BY-4.0 and require attribution — see `config/sources.yaml`.

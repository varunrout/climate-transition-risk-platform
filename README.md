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
| M2 | Silver country-year panel (dimension, unit normalisation, completeness) | **Implemented** |
| M3 | Decoupling analytics, deterministic + bootstrap scenario engine | **Implemented** (library only; not yet CLI-wired) |
| M4 | Rolling-origin backtesting harness | **Implemented** |
| M5 | Transition risk scoring v1 (4 of 5 components), rank stability | **Implemented** |
| M6 | Ember energy-transition features | Not implemented (source gated `pending_verification`, disabled) |
| M7 | Regime/structural-break research | Not implemented |
| M8 | Azure infrastructure (Terraform) | **Terraform written, `fmt`/`validate` pass; `plan`/`apply` blocked** — the Azure subscription is disabled for all write operations (billing issue, not a permissions gap). No Azure resource exists. See `docs/finops.md`. |
| M9 | Power BI semantic layer | Not implemented |
| M10 | Read-only FastAPI serving layer | Not implemented |
| M11 | End-to-end `publish` wiring | **Implemented** — fail-closed, verified on the real CLI path (see `docs/adr/`) |

Production container: **implemented and verified**. `docker build .` produces
a non-root, multi-stage image; the full `ingest → build-silver → backtest →
score → publish` chain has been run inside it against a mounted volume and
live network data, producing output bit-identical to the non-containerized
run. Not yet pushed to any registry (ACR doesn't exist — see M8).

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
uv run climate-risk build-silver    # joins into the country-year panel
uv run climate-risk backtest        # rolling-origin evaluation, 6 origins
uv run climate-risk score           # transition risk scoring v1
uv run climate-risk run             # chains all of the above
uv run pytest                       # 53 tests
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

`build-silver` joins the latest accepted OWID + World Bank bronze into
`dim_country` and `fact_country_year_transition` (World Bank GDP as the
primary constant-price series; OWID GDP kept only as a secondary column).

`backtest` runs 6 rolling origins (2010→2015 … 2017→2022) across all 19
countries against three candidate models (no-change, deterministic trend,
empirical bootstrap) and writes `gold/backtest_country_origin.parquet` +
`gold/backtest_summary.parquet`. See
[docs/adr/0002-backtest-reproduction-vs-scratch.md](docs/adr/0002-backtest-reproduction-vs-scratch.md)
for the reproduction of the documented 2015→2022 scratch experiment: the
bootstrap's median absolute error (0.0262) closely matches the scratch
figure (≈0.0263); 90% interval coverage (76.3% across 114 splits) does
**not** reproduce the scratch's ≈84.2% and is reported as a genuine,
unresolved undercoverage finding — not tuned away.

`score` computes transition risk scoring v1 — 4 of the 5 nominal components
(energy-system transition excluded because Ember is disabled) — with
weight-perturbation rank-stability analysis, and writes
`gold/country_transition_risk.parquet` + `gold/rank_stability.json`. Every
row carries `weight_coverage=0.8` so a partial score is never presented as
a complete one.

`features`/`model` exist as tested library functions
(`climate_risk.features.decoupling`, `climate_risk.scenarios.engine`) but
are not yet wired as standalone CLI commands (their logic runs inside
`backtest` and `score`).

`publish` checks the latest ingestion manifests are `ACCEPTED`, a silver
panel exists, and gold backtest/score outputs exist, then calls the
fail-closed **publishing barrier** (`src/climate_risk/publishing/barrier.py`):
`latest_successful_run.json` is only ever updated by a `SUCCEEDED` run, so a
failed or in-progress run can never overwrite the previously published
release. Verified on the real CLI path (not just unit tests): deleting
`gold/backtest_summary.parquet` and running `climate-risk publish` exits 1
and leaves the pointer file byte-for-byte unchanged. `publish` also writes a
full evidence manifest to `gold/manifests/<run_id>.json` (source snapshot
ids/checksums, config hash, country scope, backtest metrics, score version).

## Container image

```bash
docker build -t climate-risk-pipeline:$(git rev-parse --short HEAD) .
docker run --rm -v /path/to/lake:/data/lake climate-risk-pipeline:latest run
```

Multi-stage, non-root, `python:3.12-slim` base, locked production-only deps.
Verified: the full pipeline chain has been run inside the built image
against a mounted volume and live network data, producing output
bit-identical to the non-containerized run (same `snapshot_set_id`, same
scores). Not yet pushed to any registry — see `infra/` below.

## Azure infrastructure

`infra/` (Terraform) defines a deliberately minimal, low-cost dev
environment: one resource group, ADLS Gen2 (Standard_LRS), ACR (Basic),
one Container Apps Environment + one unified Container Apps Job
(Consumption, scale-to-zero), Log Analytics only, two least-privilege
managed identities, and a Cost Management budget with 50/80/100% alerts.
`terraform fmt`/`validate` pass. **`terraform plan`/`apply` are currently
blocked**: the Azure subscription returns `ReadOnlyDisabledSubscription` on
every write attempt (confirmed independently via `az provider register`) —
a billing/reactivation issue, not a permissions gap. No Azure resource for
this project exists. Full cost breakdown, guardrails, and the resume path
once the subscription is reactivated: [docs/finops.md](docs/finops.md).

## Repository layout

```text
src/climate_risk/
  config/         typed config models + YAML loader (sources.yaml, countries.yaml, quality_rules.yaml)
  contracts/      pydantic domain models: manifests, validation events, run metadata
  ingestion/      source adapters (OWID, World Bank) + orchestration pipeline
  transforms/     silver country-year panel builder + atomic writers
  features/       decoupling analytics (growth rates, correlation, elasticity)
  scenarios/      deterministic trend baseline + seeded bootstrap Monte Carlo
  backtesting/    rolling-origin harness (no_change / deterministic / bootstrap vs actuals)
  scoring/        transition risk scoring v1 + weight-perturbation sensitivity
  quality/        quality rule registry + publish-gate logic
  publishing/     fail-closed latest_successful_run barrier
  observability/  structured logging (structlog)
  regimes/ api/   scaffolded, not yet implemented
config/           versioned YAML: sources, countries, quality rules
tests/
  unit/           pure logic (config, quality, publishing, decoupling, scenarios, backtesting, scoring)
  contracts/      adapter standardisation + quality-check contracts, adversarial fixtures
  integration/    full ingest/silver pipelines against local fixtures (no network required)
docs/adr/         architectural decision records, including the backtest reproduction finding
docs/finops.md    Azure cost design, guardrails, shutdown/recovery runbook
infra/            Terraform (Azure) -- plan-validated, not yet applied (subscription blocked)
Dockerfile        production container image (built and smoke-tested locally)
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

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
| M6 | Energy-system transition features | **Locally complete and production-promoted; Azure promotion BLOCKED by an unresolved incident.** Phase 1 (ADR 0007): OWID `energy-data` verified and ingested. Phase 2 (ADR 0008) evaluated a 3-signal energy component and decided ACCEPT. Phase 3 (ADR 0009) strengthened the evidence (2000-permutation test), tested redundancy-reduced alternatives, and froze a leaner **2-signal** production spec (`energy_component_v2.1`). `cli.score()` computes **both v1 and v2**; `cli.publish()` **requires both** and declares v2 (`score_version=v2_energy`) active, v1 permanently preserved as comparison. Verified locally end-to-end (163 tests, fail-closed tested). **Azure validation (ADR 0010) found the new image's execution reports `Succeeded` and logs a normal-looking run, but a direct ADLS Gen2 check proves none of that run's output — not even the raw ingestion snapshot — actually persisted to storage; reproduced on a second, minimal execution.** Root cause not found (RBAC, dependency drift, and the verification tooling itself were all ruled out). The Azure job has been **rolled back to the last confirmed-working pre-M6 image** (`6bafc0a`) to protect the weekly schedule until this is root-caused. See ADR 0010 for the full incident record. |
| M7 | Regime/structural-break research | Not implemented |
| M8 | Azure runtime | **COMPLETE — production-verified.** 16 Terraform-managed resources (6 top-level Azure service resources plus their sub-resources: filesystems, role assignments, lifecycle policy, budget notifications) live in `rg-climate-risk-dev` (uksouth). Three real Container Apps Job executions have succeeded end to end against live ADLS Gen2, producing output identical to the local baseline and, since ADR 0006, a real `git_sha` in every published manifest. Weekly schedule: Monday 03:00 UTC. See `docs/finops.md`, ADR 0003–0006. |
| M9 | Power BI semantic layer | Not implemented |
| M10 | Read-only FastAPI serving layer | Not implemented |
| M11 | v1 release (data revision analysis, reproducibility test, evidence bundle, governance/hardening) | Not implemented. The fail-closed `publish` barrier itself is implemented and production-verified (a prerequisite for M11, not M11 itself) — see `docs/adr/`. |

Production container: **implemented, pushed, and running in production**.
`docker build .` produces a non-root, multi-stage image; the full
`ingest → build-silver → backtest → score → publish` chain has run inside
it — locally, and for real in Azure — producing identical output each
time. Published as a **public GitHub Container Registry** image (no Azure
Container Registry at all: the image has no secrets/proprietary content,
so a public image removes a real idle cost with no privacy tradeoff — see
`docs/finops.md`). Current production tag: see "Azure infrastructure"
below.

Ember (direct) is disabled in `config/sources.yaml` (`licence_review_status:
pending_verification`) — its licence is CC-BY-4.0, but no stable programmatic
access path could be verified from this environment (see
`docs/m6_source_feasibility.md`). The config loader and quality gate refuse to
let a non-`approved` source influence production output. `owid_energy` is
`approved` and enabled instead — same licence family, verified live access,
verified full 1985–2024/25 coverage for all 19 countries, and it already
re-publishes Ember's electricity-mix data.

## What actually runs today

```bash
uv sync --all-extras
uv run climate-risk validate-config
uv run climate-risk ingest          # fetches real OWID CO2 + energy-mix + World Bank data
uv run climate-risk build-silver    # joins into the country-year panel + raw energy-mix table
uv run climate-risk energy-features # diagnostic energy-transition features (M6, not score-wired)
uv run climate-risk backtest        # rolling-origin evaluation, 6 origins
uv run climate-risk score           # v1 (comparison) + v2 (production, energy-augmented, ADR 0009)
uv run climate-risk run             # chains all of the above, publish requires both v1 and v2
uv run climate-risk m6-evaluate     # M6 phase 2 research (ADR 0008): coverage/stability/redundancy/
                                     # incremental-information/backtest/score-v2 gate
uv run climate-risk m6-harden       # M6 phase 3 research (ADR 0009): strengthened permutation test,
                                     # redundancy-reduced component alternatives, lookback/origin robustness
uv run pytest                       # 163 tests
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

`score` computes **both** transition risk scores: v1 (4 of the 5 nominal
components, permanent comparison baseline, weight-perturbation
rank-stability analysis, `gold/country_transition_risk.parquet` +
`gold/rank_stability.json`, `weight_coverage=0.8`) and **v2** — the
default production score since ADR 0009, energy-augmented with the frozen
`energy_component_v2.1` spec (`gold/country_transition_risk_v2.parquet` +
`gold/rank_stability_v2.json`, per-country `weight_coverage` up to `1.0`).
v1's computation is completely unaffected by v2's presence; v2 is
best-effort inside `score` (skipped with a warning if the energy silver
table isn't available) but **required** by `publish` below.

`m6-evaluate` (M6 phase 2, ADR 0008) and `m6-harden` (M6 phase 3, ADR 0009)
are the research commands that produced the evidence behind v2: coverage
thresholds fixed before evaluation, feature stability (lookback-window,
one-year-revision, and — in `m6-harden` — per-feature/per-country/
Theil-Sen-vs-OLS drill-down), collinearity/VIF/redundancy clustering,
leave-one-country-out incremental-information tests with a
2000-permutation null distribution, per-origin and leave-one-origin-out
temporal robustness, redundancy-reduced component-formulation comparison,
and weight-robustness at ±10/20/30%. Every artifact is written under
`gold/research/m6/`; neither command touches `gold/country_transition_risk*.parquet`
directly — they inform the frozen spec in `climate_risk.scoring.energy_component`,
which `score`/`publish` consume like any other production code.

`features`/`model` exist as tested library functions
(`climate_risk.features.decoupling`, `climate_risk.scenarios.engine`) but
are not yet wired as standalone CLI commands (their logic runs inside
`backtest` and `score`).

`publish` checks the latest ingestion manifests (including `owid_energy`)
are `ACCEPTED`, a silver panel exists, and gold backtest + **both** v1 and
v2 score outputs exist, then calls the fail-closed **publishing barrier**
(`src/climate_risk/publishing/barrier.py`): `latest_successful_run.json` is
only ever updated by a `SUCCEEDED` run, so a failed or in-progress run —
including one where energy ingestion or v2 scoring failed upstream — can
never overwrite the previously published release. Verified on the real
CLI path (not just unit tests, `tests/integration/test_publish_cli_v2_gate.py`):
publish blocks and leaves the pointer byte-for-byte unchanged when v2 is
missing. `publish` writes a full evidence manifest to
`gold/manifests/<run_id>.json` declaring `score_version=v2_energy` as the
active production score, `comparison_score_version=v1`, `component_version`,
`weights_version`, and both artifacts' paths/country counts, alongside the
existing source-snapshot/config-hash/git-SHA provenance.

## Container image

```bash
docker build -t climate-risk-pipeline:$(git rev-parse --short HEAD) .
docker run --rm -v /path/to/lake:/data/lake climate-risk-pipeline:latest run
```

Multi-stage, non-root, `python:3.12-slim` base, locked production-only deps.
Public image on GitHub Container Registry:
`ghcr.io/varunrout/climate-risk-pipeline:6bafc0a` (immutable git-SHA tag,
anonymous-pull verified; the current Azure production tag — see ADR 0006).
Storage is backend-neutral
(`climate_risk.storage`, see ADR 0004) — the same image runs unchanged
against a local mounted volume or live Azure Data Lake Storage Gen2.

## Azure infrastructure

`infra/` (Terraform) defines a deliberately minimal, low-cost dev
environment, **deployed and verified**: one resource group
(`rg-climate-risk-dev`, `uksouth`), ADLS Gen2 (Standard_LRS, 4 filesystems),
one Container Apps Environment + one unified Container Apps Job
(Consumption, scale-to-zero) pulling the public GHCR image above (no
Azure Container Registry), Log Analytics only (0.1GB/day cap, 30-day
retention), two least-privilege managed identities (the job's identity
authenticates to ADLS via `ManagedIdentityCredential` only — no keys/SAS
anywhere), and a Cost Management budget with 50/80/100% alerts.

Three real Container Apps Job executions have run the full pipeline —
ingestion → silver → backtest → score → publish — end to end against live
ADLS Gen2 storage, each producing output identical to the local baseline
(same `snapshot_set_id`, same backtest metrics, same country scores; see
ADR 0005, ADR 0006). The published manifest now carries a real `git_sha`
(baked in at image build time via a `GIT_SHA` Docker build-arg — `.git`
itself is never copied into the image), alongside the image ref/digest and
`azure_job_execution_id`.

**Recurring execution is enabled**: `trigger_type = "Schedule"`, weekly,
**Monday 03:00 UTC** — matches OWID's and World Bank's own weekly/monthly
refresh cadence (`config/sources.yaml`), so more frequent runs would only
cost more for no fresher data. Compute size, retry limit (1), and timeout
(30 min) are unchanged from the manually-triggered configuration; enabling
the schedule changed *when* the job runs, not its size or cost profile.
Full cost breakdown, guardrails, and resume/shutdown commands:
[docs/finops.md](docs/finops.md).

## Repository layout

```text
src/climate_risk/
  config/         typed config models + YAML loader (sources.yaml, countries.yaml, quality_rules.yaml)
  contracts/      pydantic domain models: manifests, validation events, run metadata
  ingestion/      source adapters (OWID CO2, OWID energy-mix, World Bank) + orchestration pipeline
  transforms/     silver country-year panel + raw energy-mix table builders, atomic writers
  features/       decoupling analytics (growth rates, correlation, elasticity);
                  energy_transition.py: diagnostic M6 features (trend/momentum/velocity/
                  percentile), not yet wired into scoring/
  scenarios/      deterministic trend baseline + seeded bootstrap Monte Carlo
  backtesting/    rolling-origin harness (no_change / deterministic / bootstrap vs actuals)
  scoring/        transition risk scoring v1 (production) + weight-perturbation sensitivity;
                  energy_component.py + risk_score_v2_energy.py: experimental M6 v2, not
                  imported by v1 or by cli.score()/cli.publish()
  research/       M6 phase 2 evidence-gate modules (coverage/stability/redundancy/
                  incremental-information/temporal-backtest) -- research-only, one-way
                  dependency into the existing pipeline's outputs, never the reverse
  quality/        quality rule registry + publish-gate logic
  publishing/     fail-closed latest_successful_run barrier
  storage/        backend-neutral local/ADLS Gen2 storage abstraction (ADR 0004)
  observability/  structured logging (structlog)
  regimes/ api/   scaffolded, not yet implemented
config/           versioned YAML: sources, countries, quality rules
tests/
  unit/           pure logic (config, quality, publishing, decoupling, scenarios, backtesting,
                  scoring, M6 research modules)
  contracts/      adapter standardisation + quality-check contracts, adversarial fixtures
  integration/    full ingest/silver pipelines against local fixtures (no network required)
docs/adr/         architectural decision records, including the backtest reproduction finding
                  and the M6 phases 1-2 source verification / score-gating decision (0007, 0008)
docs/finops.md    Azure cost design, guardrails, shutdown/recovery runbook
docs/m6_source_feasibility.md  M6 phase 1 source licence/access/coverage verification + feature contract
infra/            Terraform (Azure) -- deployed and verified (rg-climate-risk-dev)
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

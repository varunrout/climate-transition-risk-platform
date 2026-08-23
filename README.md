# Climate Transition Risk Intelligence Platform

**v1.0.0** · A sovereign climate transition-risk intelligence platform:
converts public emissions, economic, and energy data for 19 G20 economies
into evidence-backed country risk profiles, rankings, and forward
scenarios — reproducible end to end, from ingestion to a live dashboard
and API.

**Live product**: [dashboard](https://varunrout.github.io/climate-transition-risk-platform/) · **Live API**: [Swagger/OpenAPI docs](https://ca-climate-risk-dev-api.ambitiousbush-97a2aedf.uksouth.azurecontainerapps.io/docs)

**Key engineering**: Azure (Container Apps, ADLS Gen2), Terraform,
managed identity (zero keys/SAS/connection strings), GitHub Actions
(CI + immutable-tag container builds + Pages deployment), FastAPI, React/
TypeScript, deterministic checksummed publication (`gold/web`).

**Key analytical evidence**: production risk score `v2_energy` combines
five components (including an energy-transition signal that only reached
production after clearing a pre-registered evidence gate — see
`docs/governance.md`); forward scenarios (`empirical_bootstrap_v1`)
validated by rolling-origin backtesting against two baseline models; a
research track (M7) evaluated two further candidates and explicitly did
**not** promote either — a negative result reported, not hidden.

This README works for three audiences: a **recruiter/hiring manager**
gets the summary above and `docs/portfolio-case-study.md`; a **data
scientist/analyst** should read `docs/model_cards/model-card.md` and
`docs/data_cards/data-card.md`; an **engineer reproducing this** should
jump straight to `docs/reproducibility.md`. Deeper technical detail below
links out to `docs/` rather than duplicating it here.

**This README states only what has actually been implemented and verified in
this repository.** The full design spec (25 documents) lives in the project's
Google Drive folder and describes the target end state; a capability listed
there is not claimed here until it is implemented, tested, and committed.
`docs/scope-v1.md` freezes exactly what v1.0.0 covers and what it
deliberately excludes.

## Implementation status

| Milestone | Scope | Status |
|---|---|---|
| M0 | Repo foundation: package layout, config, logging, CLI, CI, tests | **Implemented** |
| M1 | OWID CO2 + World Bank WDI ingestion (real adapters, manifests, checksums) | **Implemented** |
| M2 | Silver country-year panel (dimension, unit normalisation, completeness) | **Implemented** |
| M3 | Decoupling analytics, deterministic + bootstrap scenario engine | **Implemented** (library only; not yet CLI-wired) |
| M4 | Rolling-origin backtesting harness | **Implemented** |
| M5 | Transition risk scoring v1 (4 of 5 components), rank stability | **Implemented** |
| M6 | Energy-system transition features | **COMPLETE - production-verified in Azure.** Phase 1 (ADR 0007): OWID `energy-data` verified and ingested. Phase 2 (ADR 0008): pre-registered gate ACCEPTed the energy component (`p <= 0.10`, positive MAE improvement, weight robustness). Phase 3 (ADR 0009): 2000-permutation hardening, redundancy-reduced 2-signal spec frozen as `energy_component_v2.1`, `score_version=v2_energy`. `cli.score()` computes **both v1 and v2**; `cli.publish()` **requires both** and declares v2 active while preserving v1 as a comparison artifact. ADR 0010 records the failed `7f11e31` Azure promotion, the proven local-storage fallback root cause, the preventive invariant, the corrected `95b7fa4` image, external Entra-authenticated ADLS verification, manifest/pointer consistency, and local/Azure parity. |
| M7 | Regime/structural-break research | **Complete**. Structural-break diagnostics are retained for interpretation, but formal regime-aware forecasting is not promoted. Phase 3 decision: **RECENCY_WEIGHTING_ONLY**. Phase 4 decision: **KEEP_EXISTING_EMPIRICAL_BOOTSTRAP_IN_PRODUCTION** because recency gains were small, country robustness failed, and P5-P95 coverage remained below the nominal 90% target. No production score, scenario engine, Azure schedule, or publish contract change. See ADR 0011-0014 plus `docs/m7_phase3_report.md` and `docs/m7_phase4_report.md`. |
| M8 | Azure runtime | **COMPLETE - production-verified.** Terraform-managed resources live in `rg-climate-risk-dev` (uksouth): ADLS Gen2, four filesystems, Container Apps Environment + Job, two managed identities, RBAC, Log Analytics, lifecycle policy, and budget. Real Container Apps Job executions have succeeded end to end against live ADLS Gen2, including the M6 v2 production run `job-climate-risk-dev-pipeline-xsjvjwd`, with output identical to the local baseline and real Git/image provenance in the manifest. Weekly schedule: Monday 03:00 UTC. See `docs/finops.md`, ADR 0003-0010. |
| M9 | React web dashboard (canonical product) + superseded Power BI prototype | **COMPLETE — deployed, live, and verified with real portfolio screenshots.** ADR 0016: the canonical M9 product changed from a native Power BI report to a React/TypeScript web dashboard (`web/`) — a distribution/portability decision, not a claim Power BI is technically impossible. The Power BI work (`powerbi/`, `docs/powerbi/`) is preserved as engineering history and marked superseded, not deleted; it includes a real, live-debugged record of 9 Desktop bugs found and fixed, with one unresolved report-canvas defect that ended that route (`docs/powerbi/native_report_status.md`). A deterministic `gold/web/` JSON publication layer (`climate-risk build-web`, ADR 0017) sits downstream of `gold/bi/` with a versioned manifest (schema version, provenance, per-file row counts/SHA-256, bundle hash). The React app (Vite + TypeScript + React Router + TanStack Query + Zod-validated contracts + ECharts) implements all 7 canonical routes against real data, with production (`v2_energy`/`empirical_bootstrap_v1`) vs comparison (`v1`) vs research-only (M7 diagnostics) semantics enforced throughout. Live in-browser verification against the real 19-country bundle caught and fixed a real bug (`echarts-for-react` never called `setOption` under echarts v6; replaced with a direct ECharts binding, `web/src/lib/useEcharts.ts`). **Deployed to GitHub Pages** (zero cost, `.github/workflows/deploy-web.yml`): **https://varunrout.github.io/climate-transition-risk-platform/**. 8 real Playwright screenshots (7 routes + one mobile capture) taken directly against that live deployment, chart-paint-aware (not faked, not loading states) — see `docs/web/screenshots/`. **Executive Overview map regression fixed**: the ECharts `map` series (plain equirectangular projection, no antimeridian-aware clipping) drew a long horizontal streak connecting Russia's antimeridian-split geometry, plus a wide band across the bottom from Antarctica's full-longitude-span geometry at extreme southern latitude. Replaced with a static `d3-geo`/`geoPath` SVG renderer (sphere-aware clipping fixes the Russia streak) that also drops Antarctica from the rendered collection (zero analytical relevance for a G20 map) and removes `roam: true` (no more accidental free zoom/pan) in favour of keyboard-focusable/activatable country paths. See ADR 0016, ADR 0017. |
| M10 | Read-only FastAPI serving layer | **COMPLETE — deployed, healthy, and verified live.** Serves published `gold/web` output (never recomputes analytics), fails to start on an inconsistent bundle, versioned `/api/v1` contracts (Pydantic v2, no bare dicts), production/research semantics enforced in the response models. Root cause of the original CrashLoopBackOff: `gold/bi`/`gold/web` had only ever been published locally — the scheduled Container Apps Job's `run` chain never included the product-publication stage. Fixed with a persistent `climate-risk publish-product` stage invoked by `run()` right after core `publish()` succeeds (never a one-off `--command` override); core analytical publication stays the fail-closed barrier, product-publication failures are reported loudly but never corrupt or roll back a valid core release (ADR 0019). Container images are now built by **GitHub Actions**, not local Docker (`.github/workflows/build-containers.yml`): immutable full-Git-SHA GHCR tags, OCI revision labels, GHA build cache, machine-readable digest artifacts, anonymous-pull verified for both `climate-risk-pipeline` and `climate-risk-api`. Live API: **https://ca-climate-risk-dev-api.ambitiousbush-97a2aedf.uksouth.azurecontainerapps.io** (`/docs`, `/redoc`, `/openapi.json`), scale-to-zero (min replicas 0), `id-climate-risk-api` managed identity with **Storage Blob Data Reader only** (no keys/SAS/connection strings). `/api/v1/meta` exposes `data_git_sha` (the pipeline commit that produced the served bundle) and `api_git_sha`/`api_image_digest` (this API application's own build) as distinct fields, not one overloaded value. Local/Azure response parity verified byte-for-byte except 4/345 backtest rows differing at ~1e-13 relative floating-point precision (cross-platform BLAS/numpy noise, not a data or logic bug). Web dashboard (M9) unmodified and still fully independent. See ADR 0018, ADR 0019, `docs/api/`. |
| M11 | v1.0.0 release (data revision analysis, reproducibility test, evidence bundle, governance/hardening) | **COMPLETE — tagged and released.** Data revision analysis found zero drift (byte-identical snapshot hashes vs. a fresh live fetch); frozen-input reproducibility proven exact for every analytical field (only run-specific metadata legitimately differs); cross-environment (Windows/Linux) parity confirmed at ~5e-14 relative precision, not visible in any rounded output. Model/data cards, governance doc, reproducibility guide, and architecture diagrams added. Security review: zero secrets found (repo + full Git history + GitHub secret scanning), Dependabot alerts enabled. Machine-readable release evidence bundle at `release/v1.0.0/`, self-validated by `scripts/validate_release.py`. One stale documentation figure found and corrected during the model-evidence audit (a conflated backtest-reproduction claim — see the `backtest` section below). See `docs/scope-v1.md`, `docs/governance.md`, `docs/reproducibility.md`, `docs/model_cards/model-card.md`, `docs/data_cards/data-card.md`, `docs/architecture/`. |

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
uv run climate-risk m7-phase1       # M7 phase 1 research (ADR 0011): leakage-safe structural-break diagnostics
uv run climate-risk m7-phase2       # M7 phase 2 research (ADR 0012): historical-origin regime stability
uv run climate-risk m7-phase3       # M7 phase 3 research (ADR 0013): scenario experiment decision gate
uv run climate-risk m7-phase4       # M7 phase 4 research (ADR 0014): recency hardening and final M7 decision
uv run climate-risk build-bi        # M9 BI semantic publication tables under gold/bi/ (still used, feeds build-web)
uv run climate-risk export-bi-preview # superseded Power BI static portfolio preview from gold/bi/
uv run climate-risk build-web       # M9 web publication bundle (JSON) under gold/web/, downstream of gold/bi/
uv run climate-risk api             # M10 read-only API (requires `uv sync --extra api`); see "Read-only API" below
uv run pytest                       # 275 tests
uv run ruff check .
uv run mypy src
```

### Web dashboard (M9 canonical product)

**Live:** https://varunrout.github.io/climate-transition-risk-platform/

Portfolio screenshots (real, captured live from the deployed site with
Playwright — see `docs/web/screenshots/README.md`): `docs/web/screenshots/`.

```bash
uv run climate-risk build-bi
uv run climate-risk build-web
cp data/lake/gold/web/*.json web/public/data/   # portfolio data snapshot, see ADR 0017

cd web
npm install
npm run dev      # local dev server
npm run lint
npm run typecheck
npm run test      # 18 tests, Vitest + React Testing Library
npm run build     # production build to web/dist
npm run preview   # serve the production build locally
```

The app is a static single-page app: `web/public/data/*.json` is a committed,
public, non-sensitive data snapshot (ADR 0017 — Option A, no Azure
credentials in the frontend). Deploys to GitHub Pages at zero cost via
`.github/workflows/deploy-web.yml` on every push to `master` touching
`web/`. See `docs/adr/0016-m9-react-web-supersedes-power-bi.md` and
`docs/adr/0017-m9-web-bundle-snapshot-and-publication-boundary.md`.

### Read-only API (M10)

Programmatic access, API/portfolio demonstration, and future
integrations -- **not** required by the web dashboard above, which stays
fully independent. Read-only (`GET` only), serves already-published
`gold/web` output, fails to start rather than serve an inconsistent
bundle. See `docs/api/` (README, endpoints, contracts, deployment,
security) and ADR 0018.

```bash
uv sync --extra api
uv run climate-risk api        # http://127.0.0.1:8000, docs at /docs and /redoc

curl http://127.0.0.1:8000/api/v1/meta
curl http://127.0.0.1:8000/api/v1/countries/GBR
curl http://127.0.0.1:8000/api/v1/countries/IND/scenario
curl http://127.0.0.1:8000/api/v1/diagnostics/regimes/MEX
```

Architecture: `gold/bi` -> `gold/web` (JSON, same bundle the dashboard
reads) -> validated once at API startup -> served from memory. No model
recomputation in request handlers. Production score/scenario semantics
(`v2_energy` / `empirical_bootstrap_v1`) and research-only M7 diagnostics
(`production_use: false`) are enforced in the response contracts, not
just by convention.

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
`gold/backtest_summary.parquet`. Two distinct evidence claims here, kept
separate deliberately (conflating them was a documentation bug fixed at
the v1.0.0 release — see
[docs/adr/0002-backtest-reproduction-vs-scratch.md](docs/adr/0002-backtest-reproduction-vs-scratch.md)):

- **Single-origin scratch reproduction** (2015→2022 only, 19 splits): the
  bootstrap's median absolute error (0.0262) closely matched the original
  scratch-study figure (≈0.0263); interval coverage (63.2%) did **not**
  reproduce the scratch's ≈84.2%.
- **Full production backtest** (all 6 rolling origins, 114 splits per
  model — this is what `/api/v1/backtests` and the Model Evidence
  dashboard page actually serve): empirical bootstrap MAE 0.0363, median
  AE 0.0201, 90% interval coverage 76.3% (calibration gap 13.7 points
  below the nominal 90% target) — closer to but still short of the
  scratch's ≈84.2%. Reported as a genuine, unresolved undercoverage
  finding, not tuned away (see `docs/model_cards/model-card.md`'s Known
  limitations). Live figures always available at `/api/v1/backtests`;
  read them from the running system rather than this document, which will
  go stale.

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

**GitHub Actions is the canonical image builder** (`.github/workflows/build-containers.yml`)
— triggered on every push to `master` touching `src/**`/`Dockerfile*`/`pyproject.toml`, or
manually via `gh workflow run build-containers.yml --ref master -f image=all`. Local Docker
Desktop is never required to produce a production image; the Dockerfiles below remain useful
for local development/testing only.

```bash
docker build -t climate-risk-pipeline:$(git rev-parse --short HEAD) .
docker run --rm -v /path/to/lake:/data/lake climate-risk-pipeline:latest run
```

Multi-stage, non-root, `python:3.12-slim` base, locked production-only deps.
Public images on GitHub Container Registry, built on GitHub-hosted runners with
immutable full-Git-SHA tags, OCI revision labels, and anonymous-pull verification
in CI:
`ghcr.io/varunrout/climate-risk-pipeline:d4f105e29c40b2d996add8f2adc9481a9091d60b`
(digest `sha256:b6c85bbe522126b16a030c48ca519b96b33cb2b5d559c68c17043ed82ec5f95d`)
and `ghcr.io/varunrout/climate-risk-api:d4f105e29c40b2d996add8f2adc9481a9091d60b`
(digest `sha256:d813c7c03d46ad8c0ef0589b1a58b0c2302ffda077292aa767d00065cf2b1a11`)
— both the v1.0.0 release's Azure production tags (see ADR 0010, ADR 0019,
`release/v1.0.0/release-manifest.json`). Each build also
uploads a machine-readable `pipeline-image.json`/`api-image.json` artifact
(`git_sha`, `image`, `digest`) so a deploy step never has to copy text out of logs.
Storage is backend-neutral
(`climate_risk.storage`, see ADR 0004) — the same image runs unchanged
against a local mounted volume or live Azure Data Lake Storage Gen2.

## Azure infrastructure

`infra/` (Terraform) defines a deliberately minimal, low-cost dev
environment, **deployed and verified**: one resource group
(`rg-climate-risk-dev`, `uksouth`), ADLS Gen2 (Standard_LRS, 4 filesystems),
one Container Apps Environment + one unified Container Apps Job pulling the
pipeline image, plus one scale-to-zero API Container App pulling the API
image (both public GHCR images above, built by GitHub Actions, no Azure
Container Registry), Log Analytics only (0.1GB/day cap, 30-day retention),
three least-privilege managed identities (`id-climate-risk-job`:
Storage Blob Data Contributor; `id-climate-risk-api`: Storage Blob Data
Reader *only*; `id-climate-risk-deploy`: scoped Contributor/RBAC-admin for
CI — each authenticates via `ManagedIdentityCredential`/OIDC only, no
keys/SAS/connection strings anywhere), and a Cost Management budget with
50/80/100% alerts.

The scheduled Container Apps Job runs the full pipeline — ingestion →
silver → backtest → score → **core publish → product publication
(`gold/bi` + `gold/web`)** — end to end against live ADLS Gen2 storage
using its *normal* Terraform-managed template (no per-execution command/
image/env overrides), producing output identical to the local baseline
(same `snapshot_set_id`, same backtest metrics, same country scores; see
ADR 0005, ADR 0006, ADR 0019). The published manifest carries a real
`git_sha` (baked in at image build time via a `GIT_SHA` Docker build-arg —
`.git` itself is never copied into the image), alongside the image
ref/digest and `azure_job_execution_id`; the same `git_sha` is what the
live API's `/api/v1/meta` exposes as `data_git_sha`.

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
                  energy_transition.py: M6 energy features (trend/momentum/velocity/
                  percentile), consumed by v2 scoring and also written as diagnostics
  scenarios/      deterministic trend baseline + seeded bootstrap Monte Carlo
  backtesting/    rolling-origin harness (no_change / deterministic / bootstrap vs actuals)
  scoring/        transition risk scoring v1 (comparison baseline) + v2_energy production;
                  energy_component.py + risk_score_v2_energy.py preserve v1 semantics
                  while adding the M6 production energy component
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

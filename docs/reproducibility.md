# Reproducibility

This document distinguishes two different things that are easy to conflate,
and reports the actual tested result for each, not an aspirational claim.

- **Reproducing the release** — re-running the exact pipeline against the
  exact frozen inputs that produced a specific published bundle, and
  checking the output matches.
- **Running against latest live data** — re-running the pipeline against
  whatever the public sources currently serve, which may differ from the
  release's inputs if the sources have been revised since.

These are not equivalent, and this document tests both honestly.

## Supported environment

- Python 3.12, dependencies locked in `uv.lock` (`uv sync --all-extras`)
- `uv run climate-risk run` executes the full pipeline: ingest → build-silver
  → backtest → score → publish → publish-product (`gold/bi` + `gold/web`)
- `uv run climate-risk api` (requires `uv sync --extra api`) serves the
  published bundle locally
- `cd web && npm ci && npm run build` builds the frontend against the
  bundle in `web/public/data/`
- Production images are built by GitHub Actions
  (`.github/workflows/build-containers.yml`), not local Docker — see the
  Container image section of `README.md`

## Frozen-input reproducibility test (tested 2026-08-23)

Ran the full pipeline twice against the **same frozen source snapshots**
(`source_snapshot_ids`: `owid_co2=7f78e2b218ce4bb8`,
`world_bank_wdi=21cb9294d95abbb2`, `owid_energy=77b3db513f02f5ff`) and the
same commit (`90323b5`): once as the Azure production run
(`source_run_id=19923940-f6bf-43a1-a3c6-298d4af1769b`, Linux container), once
locally on Windows in an isolated temporary lake
(`source_run_id=320c5fa3-823a-4fd4-a426-ad4283a13f60`).

**Content determinism: exact.**

- `release_id` (deterministic hash of the silver panel content): identical
  across both runs — `adfc6a067fe0cb04`.
- `country-overview.json` field-by-field diff: every score, rank,
  `data_confidence_score`, and component value is byte-for-byte identical
  across the two runs (38 field diffs found, **all** of them
  `latest_successful_run_id`/`latest_successful_run_completed_at` — the
  two run-specific metadata fields documented as expected to differ below;
  zero diffs in any analytical field).
- `country-timeseries.json`, `energy-indicators.json`,
  `regime-diagnostics.json`, `risk-components.json`,
  `scenario-quantiles.json`, `countries.json`: SHA-256 hashes identical.
- `config_hash`: identical (`ac4bfcb823d938d3`).

**Not identical, and expected not to be** (run-specific metadata, not
content):

- `source_run_id`, `generated_at`, `web_bundle_hash` (the bundle hash
  covers `run-metadata.json`, which embeds the run ID/timestamp/Git SHA by
  design — see `docs/data-card.md`'s note on manifest provenance)
- `country-overview.json`'s per-country `latest_successful_run_id` /
  `latest_successful_run_completed_at` fields

This repository does **not** claim byte-for-byte reproducibility of the
entire bundle — that would require fabricating away genuinely meaningful
run provenance. It claims, and demonstrates, exact reproducibility of every
analytical value given the same inputs and code.

## Cross-environment (platform) reproducibility

The two runs compared above ran on different platforms: Azure's Linux
container (the production image) vs a local Windows checkout. One class of
difference survives even holding inputs and code identical:

- **`backtest-metrics.json`**: 4 of 345 rows differ, at a maximum relative
  difference of `5.2e-14` (`forecast_p95`, `interval_width_90`,
  `forecast_p50`, `absolute_error` on origin/target-year splits at rows
  155, 286, 298). This is floating-point non-associativity in the
  `empirical_bootstrap` Monte Carlo's summation order, arising from
  different BLAS/numpy builds across platforms — not a data difference,
  not a code difference, and not visible in any rounded/serialized score,
  rank, or confidence value the product surfaces to a reader.

This is the same class of noise M10 already documented for local/Azure API
parity; it is reported here again rather than hidden, and is not expected
to change in future runs unless the underlying numpy/BLAS build changes.

All values that reach a human reader (`score_total`, `rank`,
`data_confidence_score`, scenario quantiles as displayed, backtest MAE/RMSE
as displayed) are rounded/serialized identically across both platforms;
only unrounded internal float64 values at the ~15th significant digit can
differ.

## Data revision analysis

See `release/v1.0.0/data-revision-summary.json` for the machine-readable
result. Summary: a fresh fetch from all three live sources
(`owid_co2`, `world_bank_wdi`, `owid_energy`), performed ~55 minutes after
the production release run, produced **byte-identical** content —
`source_snapshot_id` (SHA-256 prefix of the raw fetched bytes) matched the
production run exactly for all three sources, and row counts matched
exactly (3744 / 494 / 2307). No revision was detected in this window, so
there is nothing to report a revision-impact analysis on; the release
proceeds unmodified. The snapshot-hash mechanism that would catch a real
revision (see `docs/data-card.md`) is exercised and working, even though it
found nothing to catch here — a short window between fetches is the honest
reason for that, not a claim that upstream sources never revise.

## Reproducing the release yourself

```bash
git clone https://github.com/varunrout/climate-transition-risk-platform
cd climate-transition-risk-platform/climate-transition-risk
git checkout v1.0.0

uv python install 3.12
uv sync --all-extras
uv run ruff check src tests
uv run mypy src
uv run pytest -q

uv run climate-risk run          # ingest -> ... -> publish -> publish-product
uv run climate-risk api          # serves the bundle just published, localhost:8000

cd web
npm ci
npm run build                    # builds against web/public/data/ (the committed M9/M10 snapshot)
```

Running `climate-risk run` fetches from the **live** sources at whatever
moment you run it — reproducing the release's exact historical values
requires the release's frozen source snapshots (see `docs/data-card.md`'s
raw-snapshot retention policy) rather than a fresh live fetch, per the
distinction at the top of this document.

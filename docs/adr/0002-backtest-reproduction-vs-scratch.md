# ADR 0002: Backtest reproduction vs. the 2026-08-21 scratch analysis

- Status: Accepted (finding documented, not resolved)
- Date: 2026-08-22

## Context

`04_results_and_evaluation.md` records scratch feasibility numbers from a
2026-08-21 uncommitted analysis using a fit-through-2015 / evaluate-2022
split: median forecast MAE ≈ 0.0263 vs ≈ 0.0266 for a naive baseline, and
≈84.2% empirical coverage of the nominal 90% interval. The spec requires
this be reproduced from committed code and any difference investigated.

## What was run

`climate_risk.backtesting.rolling_origin.run_backtest` against the real
silver panel (snapshot_set_id `adfc6a067fe0cb04`, built from live OWID +
World Bank data), origin=2015, target=2022, 19 countries, 10,000 bootstrap
simulations, seed 42.

## Result

| Metric | Scratch (2026-08-21) | This build (committed code) |
|---|---|---|
| Bootstrap median AE | ≈0.0263 | **0.02618** |
| No-change baseline (median AE proxy) | ≈0.0266 | 0.0547 (MAE), 0.0546 (median AE) |
| 90% interval coverage | ≈84.2% | **63.2%** (12/19 covered) |

The median absolute error for the empirical bootstrap reproduces the
scratch number almost exactly (0.02618 vs ≈0.0263) — strong evidence the
core bootstrap mechanism and the underlying carbon-intensity data are
consistent with the original feasibility check.

The **no-change baseline does not reproduce**: this build's naive MAE
(0.055) is roughly double the scratch's ≈0.0266. The scratch document does
not specify whether its "naive baseline" was no-change, a different
naive-trend definition, or computed on a differently-scoped country/year set,
so this is not resolvable from the spec text alone — it is recorded as an
open discrepancy rather than silently matched.

**Interval coverage does not reproduce**: 63.2% observed vs ≈84.2% scratch,
a materially large gap in the same direction (undercoverage) but of
different magnitude. Plausible contributors, none confirmed:
- Single-origin, 19-country sample is small (n=19); a coverage estimate at
  this sample size has wide binomial uncertainty (a 90%-nominal interval
  covering 12/19 vs 16/19 is only a few countries' difference).
- The scratch analysis's bootstrap implementation details (block bootstrap
  vs simple resampling, exact intensity transform, exact origin/target
  years used) are not fully specified in the preserved spec text.
- Silver panel construction differs: this build computes
  `carbon_intensity_gdp` from World-Bank-primary GDP; the scratch's exact
  GDP source pairing is not documented.

## Decision

Report both numbers as-is. Do not tune the bootstrap to hit the scratch
coverage figure — 13_backtesting_and_calibration.md section 15 explicitly
prohibits test-set-informed tuning, and the scratch figure is feasibility
evidence, not ground truth to calibrate against. `M4` proceeds to multiple
rolling-origin splits (not just 2015→2022) so coverage is evaluated on a
larger, less noise-dominated sample before any calibration-correction layer
(`13_backtesting_and_calibration.md` section 12) is considered.

## Multi-origin follow-up

Six rolling origins (2010→2015, 2012→2017, 2014→2019, 2015→2020, 2016→2021,
2017→2022) × 19 countries = 114 eligible bootstrap splits, 5,000 simulations
each, seed 42:

| Model | MAE | RMSE | Median AE | Coverage_90 |
|---|---|---|---|---|
| no_change | 0.0527 | 0.0710 | 0.0387 | n/a |
| deterministic_trend | 0.0469 | 0.0758 | 0.0242 | n/a |
| empirical_bootstrap | **0.0365** | **0.0603** | **0.0198** | **76.3%** |

On the larger sample the empirical bootstrap beats both mandatory baselines
on every point metric, and interval coverage rises from 63.2% (single
origin) to 76.3% — closer to, but still short of, both the nominal 90% and
the scratch's ≈84.2%. This is a genuine, moderate undercoverage finding
across 114 splits, not single-sample noise.

## Consequences

- Undercoverage persists at n=114 and is reported as-is, not hidden or
  tuned away — a calibration-correction layer
  (`13_backtesting_and_calibration.md` section 12, e.g. quantile scaling
  fit on training-only backtests) is a candidate for M7 but is not
  implemented here; implementing it now, informed by this same evaluation
  set, would risk the test-set-informed tuning the spec prohibits.
- The close median-AE match at the single 2015→2022 origin is the stronger
  of the two original reproduction results; the coverage figure should be
  cited as "76.3% across 114 rolling-origin splits," not as a reproduction
  of the scratch 84.2%.
- The bootstrap outperforming both mandatory baselines (no-change,
  deterministic trend) on every point metric across 114 splits is real
  evidence the added complexity earns its place, per
  `04_results_and_evaluation.md` section 2's evaluation objective.

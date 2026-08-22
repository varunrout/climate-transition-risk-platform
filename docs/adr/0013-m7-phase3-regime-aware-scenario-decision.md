# ADR 0013: M7 phase 3 regime-aware scenario experiments

- Status: Accepted as research evidence; production integration not justified
- Date: 2026-08-22

## Context

ADR 0011 and ADR 0012 showed that structural-break diagnostics can be computed
without future leakage, but exact break evidence is method-sensitive. Phase 3
therefore tests the forecasting question directly: whether conditioning
scenarios on current-regime information improves point forecasts, interval
calibration, sharpness, country robustness, and origin robustness versus the
existing production baselines and a simple recency-weighted control.

## Pre-registered rules

Frozen before evaluating Phase 3 performance:

- target: `carbon_intensity_gdp`
- origins: 2010->2015, 2012->2017, 2014->2019, 2015->2020, 2016->2021,
  2017->2022
- minimum post-break observations: 5
- break confidence threshold: 0.70
- minimum break strength: 1.25
- recency half-life: 5 years
- regime weight multiplier: 3.0
- maximum confidence-weighted multiplier: 5.0
- fallback: existing empirical bootstrap
- simulation count: 5,000
- seed: 42

The Phase 3 acceptance gate required a regime method to beat both the
production empirical bootstrap and the recency-weighted control, avoid material
coverage degradation, improve at least half of origins and countries, and pass
break-year sensitivity.

## Methods compared

- `deterministic_trend`: existing production deterministic baseline.
- `empirical_bootstrap`: existing production full-history bootstrap.
- `recency_weighted_bootstrap`: simple control, exponential five-year half-life,
  no break logic.
- `current_regime_only`: observations since the latest credible segmented
  break, otherwise fallback.
- `regime_weighted_bootstrap`: all history retained, current-regime observations
  upweighted.
- `break_confidence_weighted_bootstrap`: regime weighting scaled by break
  confidence.
- `conditional_regime_weighted_bootstrap`: regime weighting only when the
  activation rule passes, otherwise production fallback.

## Results

Local command:

```text
climate-risk --no-json-logs m7-phase3 --n-simulations 5000 --random-seed 42
```

Artifacts written under `gold/research/m7/phase3/`:

- `scenario_method_results.parquet`
- `origin_metrics.parquet`
- `country_metrics.parquet`
- `calibration_metrics.parquet`
- `break_sensitivity.parquet`
- `recency_vs_regime.parquet`
- `conditional_policy.parquet`
- `performance_uncertainty.parquet`
- `case_studies.json`
- `decision.json`

Overall performance, 114 country-origin splits:

| Method | MAE | Median AE | RMSE | Coverage 90 | Width 90 | Interval score |
|---|---:|---:|---:|---:|---:|---:|
| `recency_weighted_bootstrap` | 0.035150 | 0.017991 | 0.058410 | 0.798 | 0.132994 | 0.216704 |
| `empirical_bootstrap` | 0.036480 | 0.019825 | 0.060332 | 0.763 | 0.139659 | 0.227544 |
| `regime_weighted_bootstrap` | 0.036921 | 0.020381 | 0.059359 | 0.754 | 0.139556 | 0.222644 |
| `break_confidence_weighted_bootstrap` | 0.037070 | 0.020557 | 0.059360 | 0.746 | 0.139283 | 0.224602 |
| `conditional_regime_weighted_bootstrap` | 0.037110 | 0.020525 | 0.059284 | 0.746 | 0.139540 | 0.224787 |
| `current_regime_only` | 0.037803 | 0.020452 | 0.060594 | 0.746 | 0.138300 | 0.245149 |
| `deterministic_trend` | 0.046877 | 0.024161 | 0.075767 | 0.000 | 0.000000 | 0.937531 |

The recency-only control is best on MAE, median AE, coverage gap, interval
width, and interval score. Regime-aware methods do not beat it.

## Robustness and uncertainty

Country-level robustness:

- Recency weighting improves MAE for 6/19 countries versus empirical bootstrap.
- Conditional regime weighting improves MAE for 3/19 countries versus empirical
  bootstrap.

Origin-level robustness for conditional regime weighting:

- Improved 3/6 origins versus empirical bootstrap.
- Activated in 20/114 splits and fell back in 94/114 splits.
- Worst split degradation: +0.064941 absolute error.
- Largest split improvement: -0.086182 absolute error.

Break-year sensitivity:

- 80 perturbation rows.
- median absolute P50 shift: 0.002603.
- max absolute P50 shift: 0.030301.

Bootstrap uncertainty over country-origin splits, 1,000 iterations:

- Recency observed MAE delta vs empirical: -0.001330; 5-95% interval
  [-0.003979, +0.001471]; probability of MAE improvement 0.769.
- Best regime method (`regime_weighted_bootstrap`) observed MAE delta vs
  empirical: +0.000441; 5-95% interval [-0.001237, +0.001930]; probability
  of MAE improvement 0.310.

## Case studies

Mechanically selected examples:

- Regime-aware clearly helps: Russia, 2012->2017; conditional regime absolute
  error 0.056326 vs empirical 0.142508.
- Regime-aware clearly hurts: China, 2016->2021; conditional regime absolute
  error 0.065593 vs empirical 0.000652.
- Break-year perturbation robust: Australia, 2014->2019; +2 year perturbation
  changed P50 by 0.000002.
- Detector disagreement / fallback: Argentina examples fell back to empirical
  bootstrap when break evidence was weak or absent.

## Decision

Mechanical Phase 3 decision: **RECENCY_WEIGHTING_ONLY**.

Reason:

- Simple recency weighting beats empirical bootstrap on point accuracy and
  calibration gap.
- No regime-aware method beats the recency control.
- Best regime method does not improve MAE versus empirical bootstrap.
- Conditional regime policy is not country-robust.
- Break-year sensitivity is acceptable, but that alone is insufficient.

## Consequences

Phase 4 production integration of regime-aware scenarios is **not justified**.

The evidence supports keeping structural-break/regime outputs as diagnostics
and considering a separate, simpler recency-weighted scenario experiment if a
future production scenario change is desired.

No production changes are approved by this ADR:

- `risk_score_v2_energy` remains unchanged.
- `climate_risk.scenarios.engine` remains unchanged.
- `climate-risk run` does not call M7.
- Azure image, Terraform, and the Monday 03:00 UTC schedule remain unchanged.

M7 is still not marked complete until the roadmap/docs are reconciled with this
Phase 3 decision and the full quality gate remains green.

# M7 Phase 3 Report: Regime-Aware Scenario Experiments

Date: 2026-08-22

Status: Phase 3 complete. Production integration is not justified.

## 1. Methods compared

Frozen baselines:

- `deterministic_trend`
- `empirical_bootstrap`

Experimental controls and regime methods:

- `recency_weighted_bootstrap`
- `current_regime_only`
- `regime_weighted_bootstrap`
- `break_confidence_weighted_bootstrap`
- `conditional_regime_weighted_bootstrap`

## 2. Pre-registered rules

- Target: `carbon_intensity_gdp`
- Origins: 2010->2015, 2012->2017, 2014->2019, 2015->2020, 2016->2021,
  2017->2022
- Minimum post-break observations: 5
- Break confidence threshold: 0.70
- Minimum break strength: 1.25
- Recency half-life: 5 years
- Regime weight multiplier: 3.0
- Maximum confidence-weighted multiplier: 5.0
- Fallback: empirical bootstrap
- Simulations: 5,000
- Seed: 42

## 3-5. Point Forecasts, Calibration, Sharpness

| Method | MAE | Median AE | RMSE | Coverage 90 | Width 90 |
|---|---:|---:|---:|---:|---:|
| `recency_weighted_bootstrap` | 0.035150 | 0.017991 | 0.058410 | 0.798 | 0.132994 |
| `empirical_bootstrap` | 0.036480 | 0.019825 | 0.060332 | 0.763 | 0.139659 |
| `regime_weighted_bootstrap` | 0.036921 | 0.020381 | 0.059359 | 0.754 | 0.139556 |
| `break_confidence_weighted_bootstrap` | 0.037070 | 0.020557 | 0.059360 | 0.746 | 0.139283 |
| `conditional_regime_weighted_bootstrap` | 0.037110 | 0.020525 | 0.059284 | 0.746 | 0.139540 |
| `current_regime_only` | 0.037803 | 0.020452 | 0.060594 | 0.746 | 0.138300 |
| `deterministic_trend` | 0.046877 | 0.024161 | 0.075767 | 0.000 | 0.000000 |

Recency weighting is both sharper and better calibrated than the full-history
bootstrap. Regime-aware methods do not beat recency.

## 6. Regime vs Recency

The recency-only control is the best Phase 3 method:

- MAE delta vs empirical bootstrap: -0.001330.
- Coverage gap improves from 0.137 to 0.102.
- Mean interval width falls from 0.139659 to 0.132994.

Best regime method:

- `regime_weighted_bootstrap`
- MAE delta vs empirical bootstrap: +0.000441.
- MAE delta vs recency: +0.001771.

## 7-8. Country and Origin Robustness

- Recency weighting improves 6/19 countries versus empirical bootstrap.
- Conditional regime weighting improves 3/19 countries versus empirical
  bootstrap.
- Conditional regime weighting improves 3/6 origins.
- Conditional policy activated in 20/114 splits and fell back in 94/114.

## 9. Break-Year Sensitivity

- Perturbation rows: 80.
- Median absolute P50 shift: 0.002603.
- Max absolute P50 shift: 0.030301.

Break-year sensitivity is acceptable, but this does not rescue the regime
methods because their point and recency-control gates fail.

## 10. Detector-Agreement Conditioning

Method agreement was weak in Phase 1-2, and Phase 3 shows that conditioning on
the segmented break evidence does not outperform simple recency weighting.
The one robust method-agreement profile is not enough to justify global
scenario-engine changes.

## 11. Conditional Policy

Conditional regime weighting:

- 114 evaluated splits.
- 20 activated splits.
- 94 fallback splits.
- Worst error degradation: +0.064941.
- Largest error improvement: -0.086182.

The policy is interpretable, but not robust enough for production.

## 12. Case Studies

- Helps: Russia 2012->2017, conditional regime error 0.056326 vs empirical
  0.142508.
- Hurts: China 2016->2021, conditional regime error 0.065593 vs empirical
  0.000652.
- Robust to break-year perturbation: Australia 2014->2019, +2 year break
  perturbation moved P50 by 0.000002.
- Fallback/no break: Argentina examples fell back when evidence was weak or
  absent.

## 13. Uncertainty and Limitations

Bootstrap over 114 country-origin splits, 1,000 iterations:

- Recency MAE delta vs empirical: -0.001330; 5-95% interval
  [-0.003979, +0.001471]; probability of improvement 0.769.
- Best regime MAE delta vs empirical: +0.000441; 5-95% interval
  [-0.001237, +0.001930]; probability of improvement 0.310.

The sample is small. The result supports a cautious negative conclusion about
regime-aware scenario production, not a universal claim about structural breaks.

## 14. Tests

Focused Phase 3 tests: 12 passed.

Full quality gate: 206 passed.

## 15. Git SHA

Pending commit at this report-writing point; final SHA recorded in the chat report.

## 16. Final Phase 3 Decision

**RECENCY_WEIGHTING_ONLY**

Structural-break machinery does not add incremental forecasting value over the
simple recency control in this evaluation.

## 17. Phase 4

Phase 4 production integration of regime-aware scenarios is **not justified**.
Azure production remains untouched.

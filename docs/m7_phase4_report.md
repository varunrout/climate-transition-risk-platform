# M7 Phase 4 Report: Recency Scenario Hardening and M7 Closure

## Summary

M7 Phase 4 preserved the Phase 3 decision:

`RECENCY_WEIGHTING_ONLY`

Formal regime-aware forecasting is not promoted. Structural-break diagnostics
remain useful for interpretation, but exact break conditioning is too
method-sensitive for production scenario selection.

The final production decision is:

`KEEP_EXISTING_EMPIRICAL_BOOTSTRAP_IN_PRODUCTION`

M7 is complete. No Azure, Terraform, production score, or production scenario
change was made.

## Recency Weighting Specification

The canonical recency candidate is an exponential weighting over historical
annual log changes:

`weight = 0.5 ** (age_years / 5.0)`

where `age_years` is measured relative to the latest observation available at
the historical origin. Forecast paths resample observed annual log changes with
replacement using these weights, then compound them over the forecast horizon.

The small pre-declared family was:

| Scheme | Half-life |
| --- | ---: |
| weak_recency | 10 years |
| canonical_recency | 5 years |
| strong_recency | 3 years |

The 5-year half-life remained the primary candidate because it was the frozen
Phase 3 formulation.

## Leakage Safety

For each evaluation origin, only data available at or before that origin was
used to create forecasts. Nested recency parameter selection used only completed
prior-origin outcomes where `target_year < evaluation_origin`.

Calibration also used only prior-origin forecasts and outcomes. No interval
scale was estimated from the same origin being evaluated.

## Candidate Comparison

| Method | MAE | RMSE | Median AE | P5-P95 coverage | Gap vs 0.90 | Mean width | Interval score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deterministic_trend | 0.046877 | 0.075767 | 0.024161 | 0.000000 | 0.900000 | 0.000000 | 0.937531 |
| empirical_bootstrap | 0.036480 | 0.060332 | 0.019825 | 0.763158 | 0.136842 | 0.139659 | 0.227544 |
| recency_weighted_bootstrap | 0.035150 | 0.058410 | 0.017991 | 0.798246 | 0.101754 | 0.132994 | 0.216704 |
| nested_recency_weighted_bootstrap | 0.035868 | 0.059363 | 0.016633 | 0.789474 | 0.110526 | 0.129741 | 0.218508 |
| recency_weighted_calibrated | 0.035868 | 0.059363 | 0.016633 | 0.789474 | 0.110526 | 0.129741 | 0.218508 |

Recency weighting improves point accuracy and interval score versus the
production empirical bootstrap, but the P5-P95 interval remains under-calibrated
relative to the nominal 90% target.

## Calibration Gap

Observed P5-P95 coverage:

- empirical bootstrap: 0.763158
- canonical recency weighted: 0.798246
- nominal target: 0.900000

Recency improves coverage by 0.035088, but the remaining calibration gap is
0.101754. This is not well-calibrated.

Tail miss rates for canonical recency:

- lower-tail miss rate: 0.175439
- upper-tail miss rate: 0.026316

Undercoverage is mostly lower-tail miss risk, meaning actual carbon intensity
was often below the lower forecast bound. For transition-risk interpretation,
this implies the scenario distribution can understate faster-than-expected
improvement in some cases.

## Country and Origin Behaviour

Country-level coverage remains uneven. Examples:

- full coverage under recency: ARG, CAN, IDN, ITA, TUR, USA, ZAF
- low coverage under recency: BRA at 0.333333, AUS at 0.500000, KOR at 0.500000
- large-error countries remain material: CHN, RUS, SAU, IDN, IND, ZAF

Origin-level coverage improves most for 2015 and 2016, but early origins remain
under-calibrated:

| Origin | Empirical coverage | Recency coverage |
| ---: | ---: | ---: |
| 2010 | 0.631579 | 0.684211 |
| 2012 | 0.684211 | 0.736842 |
| 2014 | 0.736842 | 0.736842 |
| 2015 | 0.736842 | 0.842105 |
| 2016 | 0.894737 | 0.947368 |
| 2017 | 0.894737 | 0.842105 |

## Nested Weighting

Nested selection chose:

| Origin | Selected scheme | Half-life |
| ---: | --- | ---: |
| 2010 | canonical_recency | 5 |
| 2012 | canonical_recency | 5 |
| 2014 | canonical_recency | 5 |
| 2015 | canonical_recency | 5 |
| 2016 | strong_recency | 3 |
| 2017 | strong_recency | 3 |

The nested candidate did not outperform the canonical Phase 3 recency candidate.

## Robustness

Canonical recency versus empirical bootstrap:

- improved splits: 52
- degraded splits: 44
- tied splits: 18
- countries improved: 6
- countries degraded: 7
- countries tied: 6
- origins improved: 4
- origins degraded: 2
- median error delta: -0.000601
- mean error delta: -0.001330
- worst degradation: 0.052522
- largest improvement: 0.062902

The gain is not driven by a single split, but it is not broad enough across
countries to justify production replacement.

## Uncertainty

Country-cluster bootstrap for
`MAE(recency_weighted_bootstrap) - MAE(empirical_bootstrap)`:

- observed delta: -0.001330
- p05: -0.006569
- p50: -0.000979
- p95: 0.002368
- probability of MAE improvement: 0.6445

This supports a directional improvement, but with wide enough uncertainty that
the production change would be premature.

## Final Architecture

The post-M7 architecture is:

```text
TRANSITION + ENERGY DATA
        |
        +--> production risk score v2_energy
        |
        +--> production scenario engine
        |       existing empirical bootstrap
        |
        +--> structural-break diagnostics
                research/interpretation layer
                not a production forecast selector
```

## Final Decision

M7 final production decision:

`KEEP_EXISTING_EMPIRICAL_BOOTSTRAP_IN_PRODUCTION`

M7 final status:

`COMPLETE`

No production or Azure promotion is justified from M7 Phase 4 evidence.

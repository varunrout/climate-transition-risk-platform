# ADR 0014: M7 Phase 4 Recency Scenario Production Decision

## Status

Accepted.

## Context

M7 Phase 3 rejected formal regime-aware forecasting for production. The frozen
Phase 3 decision is `RECENCY_WEIGHTING_ONLY`: structural-break diagnostics have
interpretive value, but exact break conditioning is too method-sensitive, and a
simple recency-weighted bootstrap explains the useful forecast gain better than
formal regime detection.

Phase 4 therefore hardened only the recency-weighted scenario family. It did
not expand structural-break methods, modify `risk_score_v2_energy`, alter the
production scenario engine, touch Terraform, or change Azure production.

The evaluation reused the six historical origins from M7 Phase 3:

- 2010 -> 2015
- 2012 -> 2017
- 2014 -> 2019
- 2015 -> 2020
- 2016 -> 2021
- 2017 -> 2022

Across 19 countries this produces 114 country-origin splits.

## Pre-Registered Phase 4 Rules

The candidate family was frozen before final Phase 4 comparison:

- `weak_recency`: exponential half-life 10 years
- `canonical_recency`: exponential half-life 5 years
- `strong_recency`: exponential half-life 3 years

The primary candidate remained the Phase 3 canonical 5-year half-life. Nested
weight selection was allowed only when a later origin had enough completed
prior-origin evidence. For origin `t`, selection used only forecasts whose
target year was strictly before `t`. When fewer than 30 prior splits were
available, selection fell back to `canonical_recency`.

Interval calibration was tested with a simple prior-origin residual-to-half-
width scaling rule:

- use only completed prior origins with `target_year < evaluation_origin`
- estimate the 90th percentile of residual-to-half-width ratios
- require at least 30 prior splits
- constrain scale to `[1.0, 1.5]`

No calibration parameter was estimated from the evaluation origin's own
outcomes.

## Results

Overall candidate results:

| Method | MAE | RMSE | Median AE | P5-P95 coverage | Coverage gap | Mean width | Interval score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| deterministic_trend | 0.046877 | 0.075767 | 0.024161 | 0.000000 | 0.900000 | 0.000000 | 0.937531 |
| empirical_bootstrap | 0.036480 | 0.060332 | 0.019825 | 0.763158 | 0.136842 | 0.139659 | 0.227544 |
| nested_recency_weighted_bootstrap | 0.035868 | 0.059363 | 0.016633 | 0.789474 | 0.110526 | 0.129741 | 0.218508 |
| recency_weighted_bootstrap | 0.035150 | 0.058410 | 0.017991 | 0.798246 | 0.101754 | 0.132994 | 0.216704 |
| recency_weighted_calibrated | 0.035868 | 0.059363 | 0.016633 | 0.789474 | 0.110526 | 0.129741 | 0.218508 |

The canonical recency-weighted bootstrap improved MAE by 0.001330 versus the
production empirical bootstrap and improved P5-P95 coverage from 0.763158 to
0.798246. However, observed coverage remained materially below the nominal
0.900000 interval target.

The leakage-safe calibration candidate did not improve coverage enough to pass
the calibration gate. Mean calibration scale remained 1.0 because the early
historical origins did not provide enough prior evidence to justify a nontrivial
scale under the pre-registered minimum split rule.

Nested selection chose `canonical_recency` for origins 2010, 2012, 2014, and
2015, and `strong_recency` for 2016 and 2017. The nested candidate did not beat
the canonical Phase 3 recency candidate.

## Robustness

Canonical recency versus empirical bootstrap:

- 52 of 114 splits improved
- 44 of 114 splits degraded
- 18 of 114 splits were effectively tied
- 6 countries improved on mean error
- 7 countries degraded on mean error
- 6 countries were effectively tied
- 4 origins improved
- 2 origins degraded
- median error delta: -0.000601
- mean error delta: -0.001330
- worst degradation: 0.052522
- largest improvement: 0.062902

Country-cluster bootstrap uncertainty around
`MAE(recency_weighted_bootstrap) - MAE(empirical_bootstrap)`:

- observed delta: -0.001330
- p05: -0.006569
- p50: -0.000979
- p95: 0.002368
- probability of MAE improvement: 0.6445

The gain is directionally positive, but small and not robust enough across
countries to justify replacing the production scenario method.

## Decision

Final Phase 4 production decision:

`KEEP_EXISTING_EMPIRICAL_BOOTSTRAP_IN_PRODUCTION`

Rationale:

- Recency improves aggregate point accuracy, but the gain is small.
- Country robustness fails the pre-registered gate.
- P5-P95 intervals remain under-calibrated versus the nominal 90% target.
- Leakage-safe calibration does not materially close the calibration gap.
- The existing empirical bootstrap remains simpler, already productionized, and
  reproducible.

M7 is complete because the structural-break hypothesis, regime-aware scenario
experiment, recency control, calibration question, and final production decision
have all been evaluated without changing production scoring or Azure.

## Consequences

- Production scenario engine remains the existing empirical bootstrap.
- `risk_score_v2_energy` remains unchanged.
- Azure production remains unchanged.
- Structural-break outputs remain diagnostic/research artifacts for future
  interpretation and Power BI profile work.
- Structural-break outputs must not enter `risk_score_v2_energy`.
- Regime detection must not determine production scenario selection unless a
  future milestone reopens the question with new pre-registered evidence.

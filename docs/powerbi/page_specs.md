# Power BI Page Specifications

## Page 1: Executive Overview

Question: Which G20 sovereigns currently carry the highest transition risk,
and how confident are we?

Primary tables:

- `country_overview`
- `run_metadata`

Visuals:

- ranked table: country, active score, rank, rank band, data confidence
- filled or bubble map by `score_total`
- histogram or column distribution of `score_total`
- top risk drivers using `risk_components`
- recent mover cards using `score_delta_v2_minus_v1` and rank delta
- freshness strip: run ID, completed at, active score version, publish status

Required interaction:

- country selection cross-filters all summary visuals
- drill-through to Country Profile

## Page 2: Country Profile

Question: Why is this country risky?

Primary tables:

- `country_overview`
- `risk_components`
- `country_timeseries`
- `scenario_quantiles`
- `regime_diagnostics`

Visuals:

- score/rank/data-confidence cards
- component decomposition bar chart
- v1 vs v2 score comparison
- carbon intensity trend line
- latest energy component and energy confidence
- production scenario interval: P5/P50/P95 plus deterministic baseline
- diagnostic structural-change callout if a current profile exists

Required labels:

- active score is `v2_energy`
- data confidence is separate from transition risk
- structural-change diagnostics are not production forecast selectors

## Page 3: Energy Transition

Question: What is happening in the power system?

Primary tables:

- `energy_indicators`
- `risk_components`
- `country_overview`

Visuals:

- latest low-carbon, fossil, coal, and renewables shares by country
- country trend for low-carbon share
- country trend for fossil share
- transition velocity comparison
- energy component contribution by country

Keep raw indicators separate from transformed risk-score components.

## Page 4: Scenario Explorer

Question: What does the production scenario distribution imply?

Primary tables:

- `country_timeseries`
- `scenario_quantiles`
- `run_metadata`

Visuals:

- historical carbon intensity line
- production P5/P50/P95 forecast markers or interval band
- deterministic baseline marker
- country selector
- target-year selector if future scenario target years are added

Required label:

`Production forecast: empirical_bootstrap_v1`

Do not show recency-weighted or regime-aware forecasts as production forecasts.

## Page 5: Model Evidence

Question: How reliable is the modelling evidence?

Primary tables:

- `backtest_metrics`
- `run_metadata`

Visuals:

- MAE by model variant
- P5-P95 coverage by model variant
- calibration gap versus nominal 90%
- interval width by model variant
- country-origin error distribution
- origin-level coverage matrix

Required note:

Historical P5-P95 intervals under-cover the nominal 90% target. This limitation
must remain visible.

## Page 6: Structural Change Diagnostics

Question: Which transition trajectory changes are interesting diagnostics?

Primary tables:

- `regime_diagnostics`
- `country_timeseries`

Visuals:

- candidate break year by country and series
- pre/post slope comparison
- break confidence/evidence
- method/break labels
- country case-study table

Required banner:

`DIAGNOSTIC ONLY - not used to select the production forecast or score.`

## Page 7: Data Quality / Provenance

Question: Can this result be reproduced and trusted?

Primary tables:

- `run_metadata`
- `country_overview`
- `country_timeseries`
- `energy_indicators`

Visuals:

- run metadata table
- source snapshot IDs
- active score/component/weights versions
- Git SHA and image digest
- latest model eligible year
- country completeness and missing feature count
- data confidence by country

Refresh cadence:

- weekly, aligned to the Monday 03:00 UTC Azure pipeline
- not real-time

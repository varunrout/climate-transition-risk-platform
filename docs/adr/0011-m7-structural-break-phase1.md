# ADR 0011: M7 phase 1 structural-break / regime diagnostics

- Status: Accepted as research framework; not promoted to production
- Date: 2026-08-22

## Context

M6 is complete and production runs `v2_energy`
(`energy_component_v2.1`, `v2_weights_v1`). M7 asks whether structural-regime
information can improve forward-looking transition analysis. The first M7 step
must be research-only: prove usefulness, stability, interpretability, and
leakage safety before changing the scenario engine, risk score, publish
contract, Azure job, or weekly schedule.

Annual sovereign data is a small-sample setting. A method that labels every
local slope wiggle as a regime change would be misleading.

## Decision

Add a separate M7 research framework:

- `climate_risk.research.m7_regimes`
- CLI command `climate-risk m7-phase1`
- output path `gold/research/m7/`

The command reads the latest silver transition and energy tables, writes only
research artifacts, and is not called by `climate-risk run`.

Phase 1 pre-registers:

- minimum total observations: 12
- minimum segment length: 5
- recent/prior windows: 5 observations
- maximum breaks: 1
- breakpoint tolerance for method agreement: +/-1 year
- bounded bootstrap stability sample: 12 country-series profiles by default

The Phase 1 feature contract is:

- `latest_regime_start_year`
- `years_in_current_regime`
- `break_count`
- `strongest_break_year`
- `strongest_break_strength`
- `pre_break_slope`
- `post_break_slope`
- `slope_delta`
- `regime_direction`
- `regime_confidence`
- `current_regime_label`
- `break_method`
- `break_version`

## Methods included

1. `threshold_baseline`

Recent five-observation slope versus the prior five-observation slope. This is
the simplest interpretable baseline and a useful guardrail against a black-box
detector becoming the only source of evidence.

2. `rolling_slope_change`

Adjacent-window slope scan. This deliberately sensitive diagnostic identifies
where local slope changes are largest, but Phase 1 does not treat it as
sufficient alone for regime declaration.

3. `cusum_stability`

Single-trend residual cumulative deviation. This captures broad instability
without pretending to estimate a precise break date.

4. `segmented_regression`

A one-break piecewise linear scan with minimum segment length, fit-improvement,
robust slope-change strength, and economic-effect thresholds. This is the
Phase 1 profile method because it is the most interpretable constrained model
implemented here.

## Methods considered but excluded from Phase 1

PELT, binary segmentation, and Bai-Perron-style multiple-break logic were
considered. They are not included in Phase 1 because the annual country-level
panel is small and multiple-break selection would add degrees of freedom before
we have evidence that one-break regime information is stable or useful in
historical-origin scenario evaluation.

Phase 2 may revisit constrained multiple-break logic only if one-break
diagnostics pass stability and backtest gates.

## Candidate series

Implemented candidate series:

- `carbon_intensity_gdp`
- `carbon_intensity_log_change`
- `co2_gdp_decoupling_gap`
- `low_carbon_share_elec`
- `clean_power_momentum_pp_per_year`
- `fossil_share_elec`
- `coal_share_elec`

Level, trend/slope, and annual-change evidence are kept separate. No regime
feature enters `risk_score_v2_energy`.

## Leakage safety

Every detector accepts an `as_of_year` and filters to observations
`year <= as_of_year` before fitting. Unit tests corrupt future observations and
verify unchanged historical-origin outputs.

## Phase 1 evidence

Local run:

```text
climate-risk --no-json-logs m7-phase1 --bootstrap-iterations 30 --max-bootstrap-profiles 12 --random-seed 42
```

Input:

- `data/lake/silver/fact_country_year_transition/snapshot_set_id=adfc6a067fe0cb04/data.parquet`
- `data/lake/silver/fact_country_year_energy/snapshot_set_id=8be0ef0690ba3206/data.parquet`

Outputs:

- `gold/research/m7/candidate_series.parquet`
- `gold/research/m7/feature_catalog.parquet`
- `gold/research/m7/country_breaks.parquet`
- `gold/research/m7/method_comparison.parquet`
- `gold/research/m7/method_agreement.parquet`
- `gold/research/m7/regime_profiles.parquet`
- `gold/research/m7/break_stability.parquet`
- `gold/research/m7/country_case_studies.json`
- `gold/research/m7/decision.json`

Coverage:

- 7 candidate series
- 19/19 countries for every series
- 4,419 candidate-series rows
- 532 country-series-method break results
- 133 segmented-regression regime profiles

Segmented-regression detected breaks:

- `carbon_intensity_gdp`: 5/19
- `carbon_intensity_log_change`: 0/19
- `co2_gdp_decoupling_gap`: 0/19
- `low_carbon_share_elec`: 1/19
- `clean_power_momentum_pp_per_year`: 6/19
- `fossil_share_elec`: 2/19
- `coal_share_elec`: 3/19

Method agreement is limited: only one country-series profile is currently
robust across methods, Mexico `clean_power_momentum_pp_per_year` with modal
break year 2021.

## Consequences

M7 Phase 1 is implemented and Phase 2 is justified. M7 is not complete.

No production change is approved by this ADR:

- `risk_score_v2_energy` remains unchanged.
- v1 artifacts remain preserved.
- `climate-risk run` does not call M7.
- Azure infrastructure and the Monday 03:00 UTC schedule remain unchanged.

The next research gate is Phase 2: historical-origin recomputation, breakpoint
stability over time, method-agreement analysis, and regime-aware scenario
backtesting with both point forecast and interval calibration metrics.

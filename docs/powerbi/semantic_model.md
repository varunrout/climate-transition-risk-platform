# Power BI Semantic Model

## Purpose

The Power BI model presents G20 sovereign transition risk from curated
BI-facing tables in `gold/bi/`. Python remains the source of truth for scoring,
scenario generation, backtesting, energy components, and regime diagnostics.

## Tables

### country_overview

Grain: one row per country.

Primary key: `country_iso3`.

Purpose: executive overview, ranking, segmentation, latest score, confidence,
latest transition/energy readings, v1/v2 comparison, and run freshness.

Important fields:

- `country_iso3`
- `country_name`
- `region`
- `income_group`
- `score_version`
- `score_total`
- `rank`
- `rank_band`
- `risk_segment`
- `data_confidence_score`
- `weight_coverage`
- `score_total_v1`
- `rank_v1`
- `score_delta_v2_minus_v1`
- `rank_delta_v2_minus_v1`
- `score_energy`
- `energy_confidence`
- `latest_transition_year`
- `latest_energy_year`
- `latest_successful_run_id`
- `latest_successful_run_completed_at`
- `publish_status`

### country_timeseries

Grain: one row per country-year.

Primary key: `country_iso3`, `year`.

Purpose: historical transition and power-system trends for profile and explorer
pages.

Sources: silver transition fact plus silver energy fact.

### risk_components

Grain: one row per country, score version, and component.

Primary key: `country_iso3`, `score_version`, `component_name`.

Purpose: score decomposition and methodology comparison.

Important fields:

- `component_name`
- `component_score`
- `nominal_weight`
- `effective_weight`
- `is_active_score`
- `component_version`
- `weights_version`

### scenario_quantiles

Grain: one row per country and scenario target year.

Primary key: `country_iso3`, `target_year`, `scenario_method`.

Purpose: production scenario explorer.

Important fields:

- `scenario_method = empirical_bootstrap_v1`
- `scenario_status = production`
- `forecast_p05`
- `forecast_p50`
- `forecast_p95`
- `deterministic_baseline`
- `simulation_count`
- `random_seed`
- `experimental_variant = false`

Recency-weighted and regime-aware research variants are not production
forecasts and are not included in this production scenario table.

### backtest_metrics

Grain: mixed metric grain.

Keys:

- summary rows: `model_variant`, `metric_grain = summary`
- detail rows: `country_iso3`, `origin_year`, `target_year`, `model_variant`,
  `metric_grain = country_origin`

Purpose: model evidence page. This table deliberately surfaces
`calibration_gap_90`, because historical P5-P95 intervals under-cover the
nominal 90% target.

### energy_indicators

Grain: one row per country-year.

Primary key: `country_iso3`, `year`.

Purpose: energy transition page. Raw power-mix indicators are kept distinct
from latest derived energy features and score transformations.

### regime_diagnostics

Grain: one row per country, candidate series, and `as_of_year`.

Primary key: `country_iso3`, `series_name`, `as_of_year`.

Purpose: structural-change diagnostics page.

Required semantic labels:

- `diagnostic_status = diagnostic_only_not_production_forecast_selector`
- `used_in_production_score = false`
- `used_in_production_scenario = false`

### run_metadata

Grain: one row per published run represented by the BI export.

Primary key: `run_id`.

Purpose: provenance and refresh transparency.

Important fields:

- `run_id`
- `completed_at`
- `publish_status`
- `active_score_version`
- `component_version`
- `weights_version`
- `production_scenario_method`
- `git_sha`
- `image_ref`
- `image_digest`
- `config_hash`
- source snapshot IDs
- silver table paths
- `latest_model_eligible_year`

## Relationships

Recommended relationships:

| From | To | Cardinality | Filter |
| --- | --- | --- | --- |
| country_overview.country_iso3 | country_timeseries.country_iso3 | 1:* | single |
| country_overview.country_iso3 | risk_components.country_iso3 | 1:* | single |
| country_overview.country_iso3 | scenario_quantiles.country_iso3 | 1:* | single |
| country_overview.country_iso3 | energy_indicators.country_iso3 | 1:* | single |
| country_overview.country_iso3 | regime_diagnostics.country_iso3 | 1:* | single |
| country_overview.country_iso3 | backtest_metrics.country_iso3 | 1:* | single |

Create a calculated or imported `dim_year` table in Power BI if needed:

- `dim_year[year]` -> `country_timeseries[year]`
- `dim_year[year]` -> `energy_indicators[year]`
- `dim_year[year]` -> `regime_diagnostics[as_of_year]`

Avoid bidirectional filters unless a specific visual interaction requires it.

## Refresh Semantics

The report is weekly-refresh, not real-time. The report header should show
`run_metadata.completed_at`, `latest_model_eligible_year`, `active_score_version`,
and `publish_status`.

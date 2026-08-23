import { z } from 'zod'

/**
 * Zod schemas mirroring the gold/web/*.json contract produced by
 * `climate_risk.bi.web_publish` (see docs/adr/0016, docs/adr/0017).
 * Field names match the published JSON exactly -- do not rename fields
 * here to "improve" them; rename in the Python publisher instead so the
 * contract stays single-sourced.
 */

const nullableNumber = z.number().nullable()
const nullableString = z.string().nullable()

export const CountryOverviewSchema = z.object({
  country_iso3: z.string(),
  country_name: z.string(),
  g20_flag: z.boolean(),
  region: z.string(),
  income_group: z.string(),
  valid_from: nullableString,
  valid_to: nullableString,
  score_version: z.string(),
  component_version: nullableString,
  weights_version: nullableString,
  score_total: z.number(),
  score_pace: nullableNumber,
  score_coupling: nullableNumber,
  score_volatility: nullableNumber,
  score_forward_downside: nullableNumber,
  score_energy: nullableNumber,
  energy_confidence: nullableNumber,
  data_confidence_score: nullableNumber,
  weight_coverage: nullableNumber,
  rank: z.number(),
  rank_band: z.string(),
  score_total_v1: nullableNumber,
  rank_v1: z.number().nullable(),
  latest_transition_year: z.number().nullable(),
  carbon_intensity_gdp: nullableNumber,
  co2_per_capita: nullableNumber,
  energy_intensity_gdp: nullableNumber,
  is_core_complete: z.boolean(),
  missing_feature_count: z.number(),
  transition_snapshot_id: nullableString,
  latest_energy_year: z.number().nullable(),
  coal_share_elec: nullableNumber,
  fossil_share_elec: nullableNumber,
  low_carbon_share_elec: nullableNumber,
  renewables_share_elec: nullableNumber,
  transition_velocity: nullableNumber,
  stalled_transition_residual_pp: nullableNumber,
  active_score_version: z.string(),
  is_active_score: z.boolean(),
  score_delta_v2_minus_v1: nullableNumber,
  rank_delta_v2_minus_v1: z.number().nullable(),
  risk_segment: z.string(),
  latest_successful_run_id: nullableString,
  latest_successful_run_completed_at: nullableString,
  publish_status: nullableString,
  bi_version: z.string(),
})
export type CountryOverview = z.infer<typeof CountryOverviewSchema>

export const CountryTimeseriesSchema = z.object({
  country_iso3: z.string(),
  year: z.number(),
  co2_mt: nullableNumber,
  real_gdp: nullableNumber,
  secondary_gdp_owid: nullableNumber,
  population: nullableNumber,
  carbon_intensity_gdp: nullableNumber,
  co2_per_capita: nullableNumber,
  energy_intensity_gdp: nullableNumber,
  primary_energy_twh: nullableNumber,
  is_core_complete: z.boolean(),
  missing_feature_count: z.number(),
  imputation_mask: z.string().nullable().default(''),
  snapshot_set_id: nullableString,
  coal_share_elec: nullableNumber,
  gas_share_elec: nullableNumber,
  oil_share_elec: nullableNumber,
  fossil_share_elec: nullableNumber,
  renewables_share_elec: nullableNumber,
  low_carbon_share_elec: nullableNumber,
  nuclear_share_elec: nullableNumber,
  solar_share_elec: nullableNumber,
  wind_share_elec: nullableNumber,
  hydro_share_elec: nullableNumber,
  biofuel_share_elec: nullableNumber,
  snapshot_set_id_energy: nullableString,
  country_name: z.string(),
  region: z.string(),
  income_group: z.string(),
  bi_version: z.string(),
})
export type CountryTimeseries = z.infer<typeof CountryTimeseriesSchema>

export const RiskComponentSchema = z.object({
  country_iso3: z.string(),
  score_version: z.string(),
  component_name: z.string(),
  component_score: nullableNumber,
  nominal_weight: nullableNumber,
  effective_weight: nullableNumber,
  is_active_score: z.boolean(),
  component_version: nullableString,
  weights_version: nullableString,
  bi_version: z.string(),
})
export type RiskComponent = z.infer<typeof RiskComponentSchema>

export const ScenarioQuantileSchema = z.object({
  country_iso3: z.string(),
  origin_year: z.number(),
  target_year: z.number(),
  scenario_horizon_years: z.number(),
  scenario_method: z.string(),
  scenario_status: z.string(),
  forecast_p05: z.number(),
  forecast_p50: z.number(),
  forecast_p95: z.number(),
  deterministic_baseline: nullableNumber,
  prob_below_origin_value: nullableNumber,
  simulation_count: z.number(),
  random_seed: z.number(),
  experimental_variant: z.boolean(),
  bi_version: z.string(),
  country_name: z.string(),
  region: z.string(),
  income_group: z.string(),
})
export type ScenarioQuantile = z.infer<typeof ScenarioQuantileSchema>

export const BacktestMetricSchema = z.object({
  model_variant: z.string(),
  n_splits: nullableNumber,
  mae: nullableNumber,
  rmse: nullableNumber,
  median_ae: nullableNumber,
  coverage_90: nullableNumber,
  mean_interval_width_90: nullableNumber,
  metric_grain: z.string(),
  nominal_coverage_90: nullableNumber,
  calibration_gap_90: nullableNumber,
  absolute_error: nullableNumber,
  actual: nullableNumber,
  country_iso3: nullableString,
  covered_90: z.union([z.boolean(), z.string()]).nullable(),
  forecast_p05: nullableNumber,
  forecast_p50: nullableNumber,
  forecast_p95: nullableNumber,
  horizon_years: nullableNumber,
  interval_width_90: nullableNumber,
  origin_year: nullableNumber,
  target_year: nullableNumber,
  production_model_variant: z.string(),
  bi_version: z.string(),
})
export type BacktestMetric = z.infer<typeof BacktestMetricSchema>

export const EnergyIndicatorSchema = z
  .object({
    country_iso3: z.string(),
    year: z.number(),
    coal_share_elec: nullableNumber,
    gas_share_elec: nullableNumber,
    oil_share_elec: nullableNumber,
    fossil_share_elec: nullableNumber,
    renewables_share_elec: nullableNumber,
    low_carbon_share_elec: nullableNumber,
    nuclear_share_elec: nullableNumber,
    solar_share_elec: nullableNumber,
    wind_share_elec: nullableNumber,
    hydro_share_elec: nullableNumber,
    biofuel_share_elec: nullableNumber,
    snapshot_set_id: nullableString,
    country_name: z.string(),
    region: z.string(),
    income_group: z.string(),
    latest_feature_latest_year: z.number().nullable(),
    latest_feature_trailing_window_years: z.number().nullable(),
    latest_feature_sample_size: z.number().nullable(),
    latest_feature_coal_share_elec: nullableNumber,
    latest_feature_fossil_share_elec: nullableNumber,
    latest_feature_renewables_share_elec: nullableNumber,
    latest_feature_low_carbon_share_elec: nullableNumber,
    latest_feature_coal_trend_pp_per_year: nullableNumber,
    latest_feature_clean_power_momentum_pp_per_year: nullableNumber,
    latest_feature_renewable_buildout_rate_pp_per_year: nullableNumber,
    latest_feature_fossil_persistence_mean_pct: nullableNumber,
    latest_feature_transition_velocity: nullableNumber,
    latest_feature_stalled_transition_residual_pp: nullableNumber,
    latest_feature_coal_share_elec_percentile: nullableNumber,
    latest_feature_low_carbon_share_elec_percentile: nullableNumber,
    bi_version: z.string(),
  })
  .passthrough()
export type EnergyIndicator = z.infer<typeof EnergyIndicatorSchema>

export const RegimeDiagnosticSchema = z.object({
  country_iso3: z.string(),
  series_name: z.string(),
  as_of_year: z.number(),
  latest_regime_start_year: z.number().nullable(),
  years_in_current_regime: z.number().nullable(),
  break_count: z.number(),
  strongest_break_year: nullableNumber,
  strongest_break_strength: nullableNumber,
  pre_break_slope: nullableNumber,
  post_break_slope: nullableNumber,
  slope_delta: nullableNumber,
  regime_direction: nullableString,
  regime_confidence: nullableNumber,
  current_regime_label: nullableString,
  break_method: z.string(),
  break_version: z.string(),
  country_name: z.string(),
  region: z.string(),
  income_group: z.string(),
  diagnostic_status: z.string(),
  used_in_production_score: z.literal(false),
  used_in_production_scenario: z.literal(false),
  bi_version: z.string(),
})
export type RegimeDiagnostic = z.infer<typeof RegimeDiagnosticSchema>

export const RunMetadataSchema = z.object({
  run_id: nullableString,
  started_at: nullableString,
  completed_at: nullableString,
  generated_at: nullableString,
  publish_status: nullableString,
  active_score_version: nullableString,
  component_version: nullableString,
  weights_version: nullableString,
  production_scenario_method: nullableString,
  git_sha: nullableString,
  image_ref: nullableString,
  image_digest: nullableString,
  config_hash: nullableString,
  transition_snapshot_id: nullableString,
  owid_co2_snapshot_id: nullableString,
  world_bank_wdi_snapshot_id: nullableString,
  owid_energy_snapshot_id: nullableString,
  latest_model_eligible_year: z.number().nullable(),
  latest_model_eligible_year_completeness: nullableNumber,
  bi_version: z.string(),
})
export type RunMetadata = z.infer<typeof RunMetadataSchema>

export const CountryIndexEntrySchema = z.object({
  country_iso3: z.string(),
  country_name: z.string(),
  region: z.string(),
  income_group: z.string(),
})
export type CountryIndexEntry = z.infer<typeof CountryIndexEntrySchema>

export const WebManifestSchema = z.object({
  schema_version: z.string(),
  generated_at: z.string(),
  source_run_id: nullableString,
  source_git_sha: nullableString,
  active_score_version: nullableString,
  active_component_version: nullableString,
  active_scenario_method: nullableString,
  model_eligible_year: z.number().nullable(),
  country_count: z.number(),
  source_snapshot_ids: z.record(z.string(), nullableString),
  config_hash: nullableString,
  web_bundle_hash: z.string(),
  files: z.array(
    z.object({
      name: z.string(),
      row_count: z.number(),
      sha256: z.string(),
      schema_version: z.string(),
    }),
  ),
})
export type WebManifest = z.infer<typeof WebManifestSchema>

/** Frontend-supported bundle schema versions. Bump alongside the publisher. */
export const SUPPORTED_SCHEMA_VERSIONS = ['1.0.0']

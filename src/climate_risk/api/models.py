"""Stable, versioned response contracts for the read-only API.

These models are deliberately decoupled from the internal `gold/web`
column names where a friendlier public shape is clearer -- but the
*values* always come straight from the published bundle (see
`climate_risk.api.repository`), never recomputed here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

ACTIVE_SCORE_VERSION = "v2_energy"
COMPARISON_SCORE_VERSION = "v1"
PRODUCTION_SCENARIO_METHOD = "empirical_bootstrap_v1"


class ApiMetadata(BaseModel):
    api_version: str = Field(
        description="This API's semantic version, independent of the data schema version."
    )
    active_score_version: str = Field(description="The production transition risk score version.")
    component_version: str | None = Field(
        description="Version of the energy component used in the active score."
    )
    production_scenario_method: str | None = Field(
        description="The production forward-scenario method."
    )
    model_eligible_year: int | None = Field(
        description="Latest year with a complete-enough panel to score."
    )
    source_run_id: str | None = Field(
        description="Run ID of the analytical run this bundle was published from."
    )
    data_git_sha: str | None = Field(
        description=(
            "Git SHA of the *pipeline* commit that produced the served analytical data "
            "(gold/web bundle). Distinct from api_git_sha -- see that field's description."
        )
    )
    api_git_sha: str | None = Field(
        description=(
            "Git SHA baked into *this running API application's* own container image "
            "(CLIMATE_RISK_GIT_SHA). Distinct from data_git_sha: the API code and the "
            "analytical data it serves are built and deployed independently, so these "
            "two SHAs commonly differ and neither should be inferred from the other."
        )
    )
    api_image_digest: str | None = Field(
        default=None,
        description="Immutable digest of this API's own container image, if injected at deploy time.",
    )
    source_snapshot_ids: dict[str, str | None] = Field(
        description="Content-addressed snapshot IDs of each upstream data source."
    )
    generated_at: str = Field(
        description="When this web/API data bundle was generated (ISO 8601, UTC)."
    )
    data_schema_version: str = Field(
        description="Schema version of the underlying gold/web publication bundle."
    )
    country_count: int = Field(description="Number of sovereigns covered by this bundle.")


class CountrySummary(BaseModel):
    country_iso3: str
    country_name: str
    region: str
    income_group: str
    risk_score: float = Field(description="Active (v2_energy) transition risk score, 0-100.")
    rank: int = Field(description="Rank among covered countries, 1 = highest risk.")
    rank_band: str = Field(
        description="Qualitative risk band, e.g. 'high', 'elevated', 'moderate', 'low'."
    )
    data_confidence_score: float | None = Field(
        description="Data confidence, 0-100. Reported separately from risk -- low confidence never implies higher risk."
    )


class ScoreComparison(BaseModel):
    country_iso3: str
    score_v1: float | None = Field(description=f"Comparison score ({COMPARISON_SCORE_VERSION}).")
    score_v2_energy: float = Field(description=f"Production score ({ACTIVE_SCORE_VERSION}).")
    score_delta: float | None = Field(description="score_v2_energy - score_v1.")
    rank_v1: int | None = None
    rank_v2_energy: int = Field(description="Rank on the production score.")
    rank_delta: int | None = Field(description="rank_v2_energy - rank_v1.")


class RiskComponent(BaseModel):
    component_name: str
    component_score: float | None
    nominal_weight: float | None
    effective_weight: float | None = Field(
        description="Weight actually applied after missing-data renormalisation."
    )
    is_active_score: bool = Field(
        description="True if this row belongs to the active (v2_energy) score decomposition."
    )
    score_version: str


class LatestTransitionSnapshot(BaseModel):
    latest_transition_year: int | None
    carbon_intensity_gdp: float | None
    co2_per_capita: float | None
    energy_intensity_gdp: float | None
    is_core_complete: bool
    missing_feature_count: int


class LatestEnergySnapshot(BaseModel):
    latest_energy_year: int | None
    coal_share_elec: float | None
    fossil_share_elec: float | None
    low_carbon_share_elec: float | None
    renewables_share_elec: float | None
    transition_velocity: float | None = Field(
        description="Signed rate of low-carbon share change, pp/year."
    )
    stalled_transition_residual_pp: float | None


class ScenarioSummary(BaseModel):
    country_iso3: str
    scenario_method: str = Field(
        description=f"Always '{PRODUCTION_SCENARIO_METHOD}' -- the production method."
    )
    scenario_status: str
    origin_year: int
    target_year: int
    scenario_horizon_years: int
    forecast_p05: float
    forecast_p50: float = Field(description="Median forecast.")
    forecast_p95: float
    deterministic_baseline: float | None
    prob_below_origin_value: float | None
    simulation_count: int
    random_seed: int


class ProvenanceRef(BaseModel):
    run_id: str | None
    completed_at: str | None
    publish_status: str | None
    active_score_version: str | None
    production_scenario_method: str | None


class CountryProfile(BaseModel):
    country_iso3: str
    country_name: str
    region: str
    income_group: str
    risk_score: float = Field(description="Active (v2_energy) score.")
    rank: int
    rank_band: str
    data_confidence_score: float | None
    weight_coverage: float | None = Field(
        description="Fraction of nominal component weight actually applied, 0-1."
    )
    score_comparison: ScoreComparison
    risk_components: list[RiskComponent]
    latest_transition: LatestTransitionSnapshot
    latest_energy: LatestEnergySnapshot
    scenario: ScenarioSummary | None = Field(
        description="Production scenario summary, if available for this country."
    )
    provenance: ProvenanceRef


class CountryTimeseriesPoint(BaseModel):
    country_iso3: str
    year: int
    co2_mt: float | None
    real_gdp: float | None
    population: float | None
    carbon_intensity_gdp: float | None
    co2_per_capita: float | None
    energy_intensity_gdp: float | None
    primary_energy_twh: float | None
    is_core_complete: bool
    missing_feature_count: int


class EnergyTimeseriesPoint(BaseModel):
    country_iso3: str
    year: int
    coal_share_elec: float | None
    gas_share_elec: float | None
    oil_share_elec: float | None
    fossil_share_elec: float | None
    renewables_share_elec: float | None
    low_carbon_share_elec: float | None
    nuclear_share_elec: float | None
    solar_share_elec: float | None
    wind_share_elec: float | None
    hydro_share_elec: float | None
    biofuel_share_elec: float | None


class BacktestRecord(BaseModel):
    model_variant: str
    production_model_variant: str
    metric_grain: str = Field(
        description="'summary' (aggregate) or 'country_origin' (individual split)."
    )
    country_iso3: str | None
    origin_year: float | None
    target_year: float | None
    horizon_years: float | None
    actual: float | None
    forecast_p50: float | None
    forecast_p05: float | None
    forecast_p95: float | None
    absolute_error: float | None
    covered_90: bool | None
    interval_width_90: float | None
    n_splits: float | None
    mae: float | None
    rmse: float | None
    coverage_90: float | None = Field(
        description="Realised 90% interval coverage, summary rows only."
    )
    nominal_coverage_90: float | None
    calibration_gap_90: float | None = Field(description="abs(coverage_90 - nominal_coverage_90).")


class RegimeDiagnostic(BaseModel):
    country_iso3: str
    series_name: str
    as_of_year: int
    current_regime_label: str | None
    regime_direction: str | None
    regime_confidence: float | None
    break_count: int
    strongest_break_year: float | None
    strongest_break_strength: float | None
    pre_break_slope: float | None
    post_break_slope: float | None
    slope_delta: float | None
    break_method: str
    break_version: str
    diagnostic_status: str
    production_use: bool = Field(
        description="Always false -- M7 diagnostics never select the production forecast."
    )
    status: str = Field(default="research_diagnostic", description="Always 'research_diagnostic'.")


class RankingEntry(BaseModel):
    rank: int
    country_iso3: str
    country_name: str
    risk_score: float
    data_confidence_score: float | None


class RankingResponse(BaseModel):
    active_score_version: str
    total_count: int
    entries: list[RankingEntry]


class ErrorResponse(BaseModel):
    detail: str

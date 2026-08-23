from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from climate_risk.api.app import get_bundle
from climate_risk.api.models import (
    ACTIVE_SCORE_VERSION,
    CountryProfile,
    CountrySummary,
    CountryTimeseriesPoint,
    EnergyTimeseriesPoint,
    LatestEnergySnapshot,
    LatestTransitionSnapshot,
    ProvenanceRef,
    RiskComponent,
    ScenarioSummary,
    ScoreComparison,
)
from climate_risk.api.repository import Bundle, Record, normalize_iso3

router = APIRouter()

MAX_LIMIT = 100


def _require_country(bundle: Bundle, iso3: str) -> Record:
    row = bundle.country(iso3)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown country ISO3 code: {iso3!r}")
    return row


@router.get(
    "/countries",
    response_model=list[CountrySummary],
    summary="Country catalogue",
    description="Lightweight per-country summary: ISO3, name, active (v2_energy) risk score, rank, confidence.",
)
def list_countries(
    bundle: Bundle = Depends(get_bundle),
    region: str | None = Query(default=None, description="Filter by exact region name."),
    min_risk_score: float | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=MAX_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[CountrySummary]:
    rows = bundle.country_overview
    if region is not None:
        rows = [r for r in rows if r["region"] == region]
    if min_risk_score is not None:
        rows = [r for r in rows if r["score_total"] >= min_risk_score]
    rows = sorted(rows, key=lambda r: r["rank"])[offset : offset + limit]
    return [
        CountrySummary(
            country_iso3=r["country_iso3"],
            country_name=r["country_name"],
            region=r["region"],
            income_group=r["income_group"],
            risk_score=r["score_total"],
            rank=r["rank"],
            rank_band=r["rank_band"],
            data_confidence_score=r["data_confidence_score"],
        )
        for r in rows
    ]


@router.get(
    "/countries/{iso3}",
    response_model=CountryProfile,
    responses={404: {"description": "Unknown ISO3 code"}},
    summary="Country profile",
    description="Full country profile: active score, comparison to v1, component decomposition, "
    "latest transition/energy snapshot, production scenario summary, and provenance.",
)
def get_country(iso3: str, bundle: Bundle = Depends(get_bundle)) -> CountryProfile:
    iso3 = normalize_iso3(iso3)
    row = _require_country(bundle, iso3)

    components = [
        RiskComponent(
            component_name=c["component_name"],
            component_score=c["component_score"],
            nominal_weight=c["nominal_weight"],
            effective_weight=c["effective_weight"],
            is_active_score=c["is_active_score"],
            score_version=c["score_version"],
        )
        for c in bundle.risk_components
        if c["country_iso3"] == iso3
    ]

    scenario_row = next((s for s in bundle.scenario_quantiles if s["country_iso3"] == iso3), None)
    scenario = (
        ScenarioSummary(
            country_iso3=iso3,
            scenario_method=scenario_row["scenario_method"],
            scenario_status=scenario_row["scenario_status"],
            origin_year=scenario_row["origin_year"],
            target_year=scenario_row["target_year"],
            scenario_horizon_years=scenario_row["scenario_horizon_years"],
            forecast_p05=scenario_row["forecast_p05"],
            forecast_p50=scenario_row["forecast_p50"],
            forecast_p95=scenario_row["forecast_p95"],
            deterministic_baseline=scenario_row["deterministic_baseline"],
            prob_below_origin_value=scenario_row["prob_below_origin_value"],
            simulation_count=scenario_row["simulation_count"],
            random_seed=scenario_row["random_seed"],
        )
        if scenario_row
        else None
    )

    return CountryProfile(
        country_iso3=row["country_iso3"],
        country_name=row["country_name"],
        region=row["region"],
        income_group=row["income_group"],
        risk_score=row["score_total"],
        rank=row["rank"],
        rank_band=row["rank_band"],
        data_confidence_score=row["data_confidence_score"],
        weight_coverage=row["weight_coverage"],
        score_comparison=ScoreComparison(
            country_iso3=iso3,
            score_v1=row["score_total_v1"],
            score_v2_energy=row["score_total"],
            score_delta=row["score_delta_v2_minus_v1"],
            rank_v1=row["rank_v1"],
            rank_v2_energy=row["rank"],
            rank_delta=row["rank_delta_v2_minus_v1"],
        ),
        risk_components=components,
        latest_transition=LatestTransitionSnapshot(
            latest_transition_year=row["latest_transition_year"],
            carbon_intensity_gdp=row["carbon_intensity_gdp"],
            co2_per_capita=row["co2_per_capita"],
            energy_intensity_gdp=row["energy_intensity_gdp"],
            is_core_complete=row["is_core_complete"],
            missing_feature_count=row["missing_feature_count"],
        ),
        latest_energy=LatestEnergySnapshot(
            latest_energy_year=row["latest_energy_year"],
            coal_share_elec=row["coal_share_elec"],
            fossil_share_elec=row["fossil_share_elec"],
            low_carbon_share_elec=row["low_carbon_share_elec"],
            renewables_share_elec=row["renewables_share_elec"],
            transition_velocity=row["transition_velocity"],
            stalled_transition_residual_pp=row["stalled_transition_residual_pp"],
        ),
        scenario=scenario,
        provenance=ProvenanceRef(
            run_id=row["latest_successful_run_id"],
            completed_at=row["latest_successful_run_completed_at"],
            publish_status=row["publish_status"],
            active_score_version=row["active_score_version"],
            production_scenario_method=scenario_row["scenario_method"] if scenario_row else None,
        ),
    )


@router.get(
    "/countries/{iso3}/timeseries",
    response_model=list[CountryTimeseriesPoint],
    responses={
        404: {"description": "Unknown ISO3 code"},
        422: {"description": "Invalid year range"},
    },
    summary="Historical transition indicators",
)
def get_country_timeseries(
    iso3: str,
    bundle: Bundle = Depends(get_bundle),
    start_year: int | None = Query(default=None),
    end_year: int | None = Query(default=None),
) -> list[CountryTimeseriesPoint]:
    iso3 = normalize_iso3(iso3)
    _require_country(bundle, iso3)
    if start_year is not None and end_year is not None and start_year > end_year:
        raise HTTPException(status_code=422, detail="start_year must be <= end_year")

    rows = [r for r in bundle.country_timeseries if r["country_iso3"] == iso3]
    if start_year is not None:
        rows = [r for r in rows if r["year"] >= start_year]
    if end_year is not None:
        rows = [r for r in rows if r["year"] <= end_year]
    rows = sorted(rows, key=lambda r: r["year"])
    return [
        CountryTimeseriesPoint(
            country_iso3=r["country_iso3"],
            year=r["year"],
            co2_mt=r["co2_mt"],
            real_gdp=r["real_gdp"],
            population=r["population"],
            carbon_intensity_gdp=r["carbon_intensity_gdp"],
            co2_per_capita=r["co2_per_capita"],
            energy_intensity_gdp=r["energy_intensity_gdp"],
            primary_energy_twh=r["primary_energy_twh"],
            is_core_complete=r["is_core_complete"],
            missing_feature_count=r["missing_feature_count"],
        )
        for r in rows
    ]


@router.get(
    "/countries/{iso3}/energy",
    response_model=list[EnergyTimeseriesPoint],
    responses={
        404: {"description": "Unknown ISO3 code"},
        422: {"description": "Invalid year range"},
    },
    summary="Historical energy-transition indicators",
)
def get_country_energy(
    iso3: str,
    bundle: Bundle = Depends(get_bundle),
    start_year: int | None = Query(default=None),
    end_year: int | None = Query(default=None),
) -> list[EnergyTimeseriesPoint]:
    iso3 = normalize_iso3(iso3)
    _require_country(bundle, iso3)
    if start_year is not None and end_year is not None and start_year > end_year:
        raise HTTPException(status_code=422, detail="start_year must be <= end_year")

    rows = [r for r in bundle.energy_indicators if r["country_iso3"] == iso3]
    if start_year is not None:
        rows = [r for r in rows if r["year"] >= start_year]
    if end_year is not None:
        rows = [r for r in rows if r["year"] <= end_year]
    rows = sorted(rows, key=lambda r: r["year"])
    return [
        EnergyTimeseriesPoint(
            country_iso3=r["country_iso3"],
            year=r["year"],
            coal_share_elec=r["coal_share_elec"],
            gas_share_elec=r["gas_share_elec"],
            oil_share_elec=r["oil_share_elec"],
            fossil_share_elec=r["fossil_share_elec"],
            renewables_share_elec=r["renewables_share_elec"],
            low_carbon_share_elec=r["low_carbon_share_elec"],
            nuclear_share_elec=r["nuclear_share_elec"],
            solar_share_elec=r["solar_share_elec"],
            wind_share_elec=r["wind_share_elec"],
            hydro_share_elec=r["hydro_share_elec"],
            biofuel_share_elec=r["biofuel_share_elec"],
        )
        for r in rows
    ]


@router.get(
    "/countries/{iso3}/scenario",
    response_model=ScenarioSummary,
    responses={404: {"description": "Unknown ISO3 code, or no scenario available"}},
    summary="Production forward scenario",
    description=f"Returns ONLY the production scenario method ({ACTIVE_SCORE_VERSION!r} score's paired "
    "method, empirical_bootstrap_v1). Experimental scenario variants are never exposed here.",
)
def get_country_scenario(iso3: str, bundle: Bundle = Depends(get_bundle)) -> ScenarioSummary:
    iso3 = normalize_iso3(iso3)
    _require_country(bundle, iso3)
    scenario_row = next((s for s in bundle.scenario_quantiles if s["country_iso3"] == iso3), None)
    if scenario_row is None:
        raise HTTPException(
            status_code=404, detail=f"No production scenario available for {iso3!r}"
        )
    return ScenarioSummary(
        country_iso3=iso3,
        scenario_method=scenario_row["scenario_method"],
        scenario_status=scenario_row["scenario_status"],
        origin_year=scenario_row["origin_year"],
        target_year=scenario_row["target_year"],
        scenario_horizon_years=scenario_row["scenario_horizon_years"],
        forecast_p05=scenario_row["forecast_p05"],
        forecast_p50=scenario_row["forecast_p50"],
        forecast_p95=scenario_row["forecast_p95"],
        deterministic_baseline=scenario_row["deterministic_baseline"],
        prob_below_origin_value=scenario_row["prob_below_origin_value"],
        simulation_count=scenario_row["simulation_count"],
        random_seed=scenario_row["random_seed"],
    )


@router.get(
    "/countries/{iso3}/risk-components",
    response_model=list[RiskComponent],
    responses={404: {"description": "Unknown ISO3 code"}},
    summary="Score decomposition",
)
def get_country_risk_components(
    iso3: str, bundle: Bundle = Depends(get_bundle)
) -> list[RiskComponent]:
    iso3 = normalize_iso3(iso3)
    _require_country(bundle, iso3)
    return [
        RiskComponent(
            component_name=c["component_name"],
            component_score=c["component_score"],
            nominal_weight=c["nominal_weight"],
            effective_weight=c["effective_weight"],
            is_active_score=c["is_active_score"],
            score_version=c["score_version"],
        )
        for c in bundle.risk_components
        if c["country_iso3"] == iso3
    ]


@router.get(
    "/countries/{iso3}/score-comparison",
    response_model=ScoreComparison,
    responses={404: {"description": "Unknown ISO3 code"}},
    summary="v1 vs v2_energy score comparison",
    description="Compares the comparison score (v1) against the production score (v2_energy). "
    "No new scoring logic -- both values come directly from the published bundle.",
)
def get_country_score_comparison(
    iso3: str, bundle: Bundle = Depends(get_bundle)
) -> ScoreComparison:
    iso3 = normalize_iso3(iso3)
    row = _require_country(bundle, iso3)
    return ScoreComparison(
        country_iso3=iso3,
        score_v1=row["score_total_v1"],
        score_v2_energy=row["score_total"],
        score_delta=row["score_delta_v2_minus_v1"],
        rank_v1=row["rank_v1"],
        rank_v2_energy=row["rank"],
        rank_delta=row["rank_delta_v2_minus_v1"],
    )

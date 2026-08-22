"""M6 evaluation panel: candidate feature catalog + the joined cross-sectional
dataset every other m6_* module operates on.

Cross-sectional, one row per country, because every candidate energy feature
(and the existing v1 raw metrics they're being tested against) is itself a
per-country "latest available" or "trailing-window" summary, not a
year-indexed series -- this matches how `climate_risk.scoring.risk_score`
already consumes `CountryRawMetrics`. Temporal (rolling-origin) evaluation
of these same features lives in `m6_incremental`, which recomputes them at
each historical origin rather than reusing this latest-only panel.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict

from climate_risk.config.loader import load_countries
from climate_risk.features.decoupling import compute_decoupling_for_panel
from climate_risk.features.energy_transition import (
    DEFAULT_TRAILING_WINDOW_YEARS,
    compute_energy_features_for_panel,
)
from climate_risk.scenarios.engine import run_country_scenario
from climate_risk.scoring.risk_score import compute_raw_metrics
from climate_risk.storage import LakeStorage
from climate_risk.transforms.silver import latest_silver_energy_panel, latest_silver_panel

Directionality = Literal["higher_is_higher_risk", "higher_is_lower_risk"]


class FeatureProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    feature_name: str
    family: str
    source_columns: list[str]
    unit: str
    transformation: str
    directionality: Directionality
    lookback_period_years: int | None
    notes: str


# Static catalog entries -- everything computable at load time, independent
# of any run's actual data. Coverage fields (country_coverage_pct etc.) are
# NOT part of this catalog; they're measured separately in m6_coverage and
# joined on afterwards, so a catalog entry never silently encodes a
# favourable-looking number that was actually measured after the fact.
FEATURE_CATALOG: list[FeatureProvenance] = [
    FeatureProvenance(
        feature_name="carbon_intensity_trend",
        family="carbon_intensity",
        source_columns=["co2_mt", "real_gdp"],
        unit="log-change per year",
        transformation="OLS slope of log(carbon_intensity_gdp) vs year, trailing <=5yr",
        directionality="higher_is_higher_risk",
        lookback_period_years=5,
        notes="Existing v1 'pace' component raw ingredient -- the baseline this evaluation tests against.",
    ),
    FeatureProvenance(
        feature_name="coupling_elasticity",
        family="decoupling",
        source_columns=["co2_mt", "real_gdp"],
        unit="dimensionless (d ln CO2 / d ln GDP)",
        transformation="OLS slope of log(CO2) vs log(GDP), full available history",
        directionality="higher_is_higher_risk",
        lookback_period_years=None,
        notes="Existing v1 'coupling' component raw ingredient. >=1 = no decoupling, <=0 = absolute decoupling.",
    ),
    FeatureProvenance(
        feature_name="coal_share_elec",
        family="power_mix_level",
        source_columns=["coal_share_elec"],
        unit="% of electricity generation",
        transformation="latest available year, no smoothing",
        directionality="higher_is_higher_risk",
        lookback_period_years=1,
        notes="OWID energy-data, verified docs/m6_source_feasibility.md.",
    ),
    FeatureProvenance(
        feature_name="fossil_share_elec",
        family="power_mix_level",
        source_columns=["fossil_share_elec"],
        unit="% of electricity generation",
        transformation="latest available year, no smoothing",
        directionality="higher_is_higher_risk",
        lookback_period_years=1,
        notes="coal + gas + oil combined; mechanically overlaps coal_share_elec.",
    ),
    FeatureProvenance(
        feature_name="renewables_share_elec",
        family="power_mix_level",
        source_columns=["renewables_share_elec"],
        unit="% of electricity generation",
        transformation="latest available year, no smoothing",
        directionality="higher_is_lower_risk",
        lookback_period_years=1,
        notes="Excludes nuclear; mechanically close to low_carbon_share_elec (differs only by nuclear).",
    ),
    FeatureProvenance(
        feature_name="low_carbon_share_elec",
        family="power_mix_level",
        source_columns=["low_carbon_share_elec"],
        unit="% of electricity generation",
        transformation="latest available year, no smoothing",
        directionality="higher_is_lower_risk",
        lookback_period_years=1,
        notes="renewables + nuclear; mechanically ~= 100 - fossil_share_elec.",
    ),
    FeatureProvenance(
        feature_name="coal_trend_pp_per_year",
        family="power_mix_momentum",
        source_columns=["coal_share_elec"],
        unit="percentage points per year",
        transformation=f"OLS slope of coal_share_elec vs year, trailing {DEFAULT_TRAILING_WINDOW_YEARS}yr",
        directionality="higher_is_higher_risk",
        lookback_period_years=DEFAULT_TRAILING_WINDOW_YEARS,
        notes="Positive = coal share rising = worse.",
    ),
    FeatureProvenance(
        feature_name="clean_power_momentum_pp_per_year",
        family="power_mix_momentum",
        source_columns=["low_carbon_share_elec"],
        unit="percentage points per year",
        transformation=f"OLS slope of low_carbon_share_elec vs year, trailing {DEFAULT_TRAILING_WINDOW_YEARS}yr",
        directionality="higher_is_lower_risk",
        lookback_period_years=DEFAULT_TRAILING_WINDOW_YEARS,
        notes="Near-mechanical inverse of coal_trend_pp_per_year at the aggregate level.",
    ),
    FeatureProvenance(
        feature_name="renewable_buildout_rate_pp_per_year",
        family="power_mix_momentum",
        source_columns=["renewables_share_elec"],
        unit="percentage points per year",
        transformation=f"mean YoY change in renewables_share_elec, trailing {DEFAULT_TRAILING_WINDOW_YEARS}yr",
        directionality="higher_is_lower_risk",
        lookback_period_years=DEFAULT_TRAILING_WINDOW_YEARS,
        notes="Overlaps clean_power_momentum_pp_per_year except for the nuclear component.",
    ),
    FeatureProvenance(
        feature_name="fossil_persistence_mean_pct",
        family="power_mix_level",
        source_columns=["fossil_share_elec"],
        unit="% of electricity generation",
        transformation=f"mean fossil_share_elec, trailing {DEFAULT_TRAILING_WINDOW_YEARS}yr",
        directionality="higher_is_higher_risk",
        lookback_period_years=DEFAULT_TRAILING_WINDOW_YEARS,
        notes="Smoothed version of fossil_share_elec -- expected high correlation with the latest-year level.",
    ),
    FeatureProvenance(
        feature_name="transition_velocity",
        family="power_mix_momentum",
        source_columns=["low_carbon_share_elec"],
        unit="pp/year, normalised by (100 - latest low_carbon_share_elec)",
        transformation="clean_power_momentum_pp_per_year / headroom_to_100pct",
        directionality="higher_is_lower_risk",
        lookback_period_years=DEFAULT_TRAILING_WINDOW_YEARS,
        notes="None when headroom <=1pp (near-saturated countries) -- not a fabricated value.",
    ),
    FeatureProvenance(
        feature_name="stalled_transition_residual_pp",
        family="power_mix_momentum",
        source_columns=["low_carbon_share_elec"],
        unit="percentage points",
        transformation="actual latest low_carbon_share_elec minus trailing-window trend-predicted value",
        directionality="higher_is_lower_risk",
        lookback_period_years=DEFAULT_TRAILING_WINDOW_YEARS,
        notes="Negative = below own recent trend = stalling.",
    ),
]


def feature_catalog() -> list[FeatureProvenance]:
    return list(FEATURE_CATALOG)


def build_evaluation_panel(
    lake: LakeStorage,
    *,
    target_year: int = 2050,
    random_seed: int = 42,
    trailing_window_years: int = DEFAULT_TRAILING_WINDOW_YEARS,
) -> pd.DataFrame:
    """One row per country: existing v1 raw metrics joined with the M6
    candidate energy features. Countries missing from either side keep
    their NaNs -- no imputation, no dropping.
    """
    transition = latest_silver_panel(lake)
    if transition is None:
        raise FileNotFoundError(
            "no fact_country_year_transition silver table; run build-silver first"
        )
    panel, _ = transition

    energy = latest_silver_energy_panel(lake)
    if energy is None:
        raise FileNotFoundError("no fact_country_year_energy silver table; run build-silver first")
    energy_panel, _ = energy

    countries = sorted(load_countries().keys())

    decoupling = {
        r.country_iso3: r for r in compute_decoupling_for_panel(panel, min_observations=5)
    }
    scenarios = {}
    for country_iso3 in countries:
        result = run_country_scenario(
            panel, country_iso3=country_iso3, target_year=target_year, random_seed=random_seed
        )
        if result is not None:
            scenarios[country_iso3] = result

    raw_metrics = compute_raw_metrics(
        panel, decoupling=decoupling, scenarios=scenarios, countries=countries
    )
    v1_frame = pd.DataFrame([m.model_dump() for m in raw_metrics]).rename(
        columns={"pace_recent_trend": "carbon_intensity_trend"}
    )[["country_iso3", "carbon_intensity_trend", "coupling_elasticity"]]

    energy_features = compute_energy_features_for_panel(
        energy_panel, trailing_window_years=trailing_window_years
    )
    energy_cols = [
        "country_iso3",
        "coal_share_elec",
        "fossil_share_elec",
        "renewables_share_elec",
        "low_carbon_share_elec",
        "coal_trend_pp_per_year",
        "clean_power_momentum_pp_per_year",
        "renewable_buildout_rate_pp_per_year",
        "fossil_persistence_mean_pct",
        "transition_velocity",
        "stalled_transition_residual_pp",
        "latest_year",
    ]
    energy_slim = (
        energy_features[energy_cols].rename(columns={"latest_year": "energy_latest_year"})
        if not energy_features.empty
        else pd.DataFrame(columns=energy_cols).rename(columns={"latest_year": "energy_latest_year"})
    )

    merged = pd.DataFrame({"country_iso3": countries}).merge(
        v1_frame, on="country_iso3", how="left"
    )
    merged = merged.merge(energy_slim, on="country_iso3", how="left")
    return merged.sort_values("country_iso3").reset_index(drop=True)

"""GDP/CO2 decoupling analytics (09_feature_engineering.md, 02_methodology.md).

Reproduces the scratch feasibility idea from committed code: annual GDP and
CO2 growth rates, Pearson/Spearman correlation between them, and an
emissions/GDP elasticity (the OLS slope of log CO2 on log GDP — the
standard decoupling-elasticity definition: elasticity < 1 indicates relative
decoupling, elasticity <= 0 indicates absolute decoupling).

Every result reports its own sample size and year window explicitly rather
than a single number with no stated support, per 04_results_and_evaluation.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict
from scipy import stats


class DecouplingResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_iso3: str
    year_start: int
    year_end: int
    sample_size: int
    pearson_r: float | None
    pearson_p_value: float | None
    spearman_r: float | None
    spearman_p_value: float | None
    elasticity: float | None  # d(ln CO2) / d(ln GDP), OLS slope
    elasticity_r_squared: float | None


def add_growth_rates(panel: pd.DataFrame) -> pd.DataFrame:
    """Adds gdp_growth_yoy and co2_growth_yoy (fractional YoY change) per country.

    Requires the panel sorted by (country_iso3, year); growth for a
    country's first observed year is NaN by construction (no prior year).
    """
    panel = panel.sort_values(["country_iso3", "year"]).copy()
    panel["gdp_growth_yoy"] = panel.groupby("country_iso3")["real_gdp"].pct_change()
    panel["co2_growth_yoy"] = panel.groupby("country_iso3")["co2_mt"].pct_change()
    return panel


def compute_decoupling(
    panel: pd.DataFrame, *, country_iso3: str, min_observations: int = 5
) -> DecouplingResult | None:
    """Decoupling metrics for one country over every year with both GDP and CO2 present.

    Returns None (not a fabricated zero) when fewer than `min_observations`
    complete (co2_mt, real_gdp) rows exist for the country.
    """
    rows = panel[panel["country_iso3"] == country_iso3].dropna(subset=["co2_mt", "real_gdp"])
    rows = rows[(rows["co2_mt"] > 0) & (rows["real_gdp"] > 0)]
    if len(rows) < min_observations:
        return None

    log_co2 = np.log(rows["co2_mt"].to_numpy())
    log_gdp = np.log(rows["real_gdp"].to_numpy())

    pearson_r: float | None
    pearson_p: float | None
    spearman_r: float | None
    spearman_p: float | None
    elasticity: float | None
    r_squared: float | None

    if len(rows) >= 2 and log_co2.std() > 0 and log_gdp.std() > 0:
        pearson_r, pearson_p = stats.pearsonr(log_gdp, log_co2)
        spearman_r, spearman_p = stats.spearmanr(log_gdp, log_co2)
        regression = stats.linregress(log_gdp, log_co2)
        elasticity = float(regression.slope)
        r_squared = float(regression.rvalue**2)
    else:
        pearson_r = pearson_p = spearman_r = spearman_p = elasticity = r_squared = None

    return DecouplingResult(
        country_iso3=country_iso3,
        year_start=int(rows["year"].min()),
        year_end=int(rows["year"].max()),
        sample_size=len(rows),
        pearson_r=pearson_r,
        pearson_p_value=pearson_p,
        spearman_r=spearman_r,
        spearman_p_value=spearman_p,
        elasticity=elasticity,
        elasticity_r_squared=r_squared,
    )


def compute_decoupling_for_panel(
    panel: pd.DataFrame, *, min_observations: int = 5
) -> list[DecouplingResult]:
    results = []
    for country_iso3 in sorted(panel["country_iso3"].unique()):
        result = compute_decoupling(
            panel, country_iso3=country_iso3, min_observations=min_observations
        )
        if result is not None:
            results.append(result)
    return results

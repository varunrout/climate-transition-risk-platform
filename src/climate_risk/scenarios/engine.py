"""Deterministic + bootstrap Monte Carlo scenario engine (11_scenario_engine.md).

Two baselines are always computed together — a Monte Carlo distribution is
never reported without the deterministic trend baseline alongside it, per
the spec's explicit requirement ("Never report Monte Carlo output without
the baseline").

Both operate on log(carbon_intensity_gdp) so that (a) the deterministic
trend is a constant proportional rate of change rather than an unbounded
linear extrapolation that can cross zero, and (b) the bootstrap resamples
YoY log-changes, which compose additively and keep the simulated series
strictly positive by construction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict
from scipy import stats


class DeterministicBaseline(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_iso3: str
    origin_year: int
    origin_value: float
    target_year: int
    trend_annual_log_change: float
    forecast_value: float
    sample_size: int
    r_squared: float | None


class ScenarioQuantiles(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_iso3: str
    origin_year: int
    target_year: int
    model_variant: str
    p05: float
    p25: float
    p50: float
    p75: float
    p95: float
    prob_below_baseline: float
    simulation_count: int
    random_seed: int


def deterministic_trend_baseline(
    series: pd.Series, *, years: pd.Series, target_year: int
) -> DeterministicBaseline | None:
    """Fit a linear trend to log(series) vs year and extrapolate to target_year.

    `series` must be a positive-valued metric (e.g. carbon_intensity_gdp)
    indexed the same as `years`. Returns None if fewer than 5 valid
    (year, value) pairs are available — refuses to extrapolate a trend from
    an inadequate sample rather than fabricating one from 1-2 points.
    """
    mask = series.notna() & (series > 0)
    if mask.sum() < 5:
        return None

    log_values = np.log(series[mask].to_numpy())
    year_values = years[mask].to_numpy()

    regression = stats.linregress(year_values, log_values)
    origin_year = int(year_values.max())
    origin_value = float(series[mask].loc[years[mask] == origin_year].iloc[0])

    horizon = target_year - origin_year
    forecast_log = regression.intercept + regression.slope * target_year
    forecast_value = float(np.exp(forecast_log))

    return DeterministicBaseline(
        country_iso3="",  # filled by caller
        origin_year=origin_year,
        origin_value=origin_value,
        target_year=target_year,
        trend_annual_log_change=float(regression.slope),
        forecast_value=forecast_value,
        sample_size=int(mask.sum()),
        r_squared=float(regression.rvalue**2) if horizon else None,
    )


def bootstrap_monte_carlo(
    series: pd.Series,
    *,
    years: pd.Series,
    target_year: int,
    n_simulations: int = 10_000,
    random_seed: int = 42,
) -> tuple[ScenarioQuantiles, np.ndarray] | None:
    """Empirical bootstrap: resample historical YoY log-changes with
    replacement, sum `horizon` draws per simulated path, apply to the origin
    value. Deterministic given (series, target_year, n_simulations, random_seed).

    Returns None if fewer than 5 YoY log-changes are available.
    """
    mask = series.notna() & (series > 0)
    if mask.sum() < 6:  # need >= 5 changes, i.e. >= 6 levels
        return None

    ordered = series[mask].to_numpy()
    order_idx = np.argsort(years[mask].to_numpy())
    ordered = ordered[order_idx]
    ordered_years = years[mask].to_numpy()[order_idx]

    log_changes = np.diff(np.log(ordered))
    if len(log_changes) < 5:
        return None

    origin_year = int(ordered_years[-1])
    origin_value = float(ordered[-1])
    horizon = target_year - origin_year
    if horizon <= 0:
        return None

    rng = np.random.default_rng(random_seed)
    draws = rng.choice(log_changes, size=(n_simulations, horizon), replace=True)
    cumulative_log_change = draws.sum(axis=1)
    simulated_values = origin_value * np.exp(cumulative_log_change)

    p05, p25, p50, p75, p95 = np.percentile(simulated_values, [5, 25, 50, 75, 95])
    prob_below_baseline = float(np.mean(simulated_values < origin_value))

    quantiles = ScenarioQuantiles(
        country_iso3="",  # filled by caller
        origin_year=origin_year,
        target_year=target_year,
        model_variant="empirical_bootstrap_v1",
        p05=float(p05),
        p25=float(p25),
        p50=float(p50),
        p75=float(p75),
        p95=float(p95),
        prob_below_baseline=prob_below_baseline,
        simulation_count=n_simulations,
        random_seed=random_seed,
    )
    return quantiles, simulated_values


class CountryScenario(BaseModel):
    """Bundled result — deterministic baseline and bootstrap distribution together."""

    model_config = ConfigDict(frozen=True)

    country_iso3: str
    deterministic: DeterministicBaseline
    bootstrap: ScenarioQuantiles


def run_country_scenario(
    panel: pd.DataFrame,
    *,
    country_iso3: str,
    target_year: int,
    n_simulations: int = 10_000,
    random_seed: int = 42,
) -> CountryScenario | None:
    rows = panel[panel["country_iso3"] == country_iso3].sort_values("year")
    series = rows["carbon_intensity_gdp"]
    years = rows["year"]

    deterministic = deterministic_trend_baseline(series, years=years, target_year=target_year)
    bootstrap_result = bootstrap_monte_carlo(
        series,
        years=years,
        target_year=target_year,
        n_simulations=n_simulations,
        random_seed=random_seed,
    )
    if deterministic is None or bootstrap_result is None:
        return None
    quantiles, _paths = bootstrap_result

    deterministic = deterministic.model_copy(update={"country_iso3": country_iso3})
    quantiles = quantiles.model_copy(update={"country_iso3": country_iso3})
    return CountryScenario(
        country_iso3=country_iso3, deterministic=deterministic, bootstrap=quantiles
    )

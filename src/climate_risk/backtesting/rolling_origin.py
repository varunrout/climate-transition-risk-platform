"""Rolling-origin backtesting harness (13_backtesting_and_calibration.md).

For each (country, origin_year, target_year): freeze data at or before
origin_year, fit each candidate model on that frozen slice only, forecast
target_year, and compare against the value actually observed there. No
target-period data reaches model fitting — `_history_at_or_before` is the
single place that enforces the cutoff, and the leakage test in
tests/unit/test_backtesting.py checks it directly.

Candidate models (mandatory baselines per 04_results_and_evaluation.md
section 3, never comparing the bootstrap only against a strawman):
  - no_change: forecast(target) = last observed value at origin
  - deterministic: log-linear trend baseline (climate_risk.scenarios.engine)
  - bootstrap: empirical bootstrap Monte Carlo (climate_risk.scenarios.engine)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from climate_risk.scenarios.engine import bootstrap_monte_carlo, deterministic_trend_baseline


class OriginResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_iso3: str
    origin_year: int
    target_year: int
    horizon_years: int
    model_variant: str
    actual: float
    forecast_p50: float
    forecast_p05: float | None
    forecast_p95: float | None
    absolute_error: float
    covered_90: bool | None
    interval_width_90: float | None


def _history_at_or_before(
    panel: pd.DataFrame, *, country_iso3: str, origin_year: int
) -> pd.DataFrame:
    """The only place the origin cutoff is enforced — every model variant is
    fit exclusively on what this returns, so no target-period value can leak
    into a forecast."""
    rows = panel[(panel["country_iso3"] == country_iso3) & (panel["year"] <= origin_year)]
    return rows.sort_values("year")


def evaluate_origin(
    panel: pd.DataFrame,
    *,
    country_iso3: str,
    origin_year: int,
    target_year: int,
    n_simulations: int = 10_000,
    random_seed: int = 42,
    min_observations: int = 5,
) -> list[OriginResult]:
    """Evaluate every candidate model for one (country, origin, target) split.

    Returns an empty list if the split is ineligible (13_backtesting_and_calibration.md
    section 4): insufficient training history, or the target year's actual is
    missing.
    """
    history = _history_at_or_before(panel, country_iso3=country_iso3, origin_year=origin_year)
    series = history["carbon_intensity_gdp"]
    years = history["year"]
    if series.notna().sum() < min_observations:
        return []

    actual_rows = panel[(panel["country_iso3"] == country_iso3) & (panel["year"] == target_year)]
    if actual_rows.empty or pd.isna(actual_rows.iloc[0]["carbon_intensity_gdp"]):
        return []
    actual = float(actual_rows.iloc[0]["carbon_intensity_gdp"])
    horizon = target_year - origin_year

    results: list[OriginResult] = []

    origin_value = float(series.dropna().iloc[-1])
    results.append(
        OriginResult(
            country_iso3=country_iso3,
            origin_year=origin_year,
            target_year=target_year,
            horizon_years=horizon,
            model_variant="no_change",
            actual=actual,
            forecast_p50=origin_value,
            forecast_p05=None,
            forecast_p95=None,
            absolute_error=abs(origin_value - actual),
            covered_90=None,
            interval_width_90=None,
        )
    )

    deterministic = deterministic_trend_baseline(series, years=years, target_year=target_year)
    if deterministic is not None:
        results.append(
            OriginResult(
                country_iso3=country_iso3,
                origin_year=origin_year,
                target_year=target_year,
                horizon_years=horizon,
                model_variant="deterministic_trend",
                actual=actual,
                forecast_p50=deterministic.forecast_value,
                forecast_p05=None,
                forecast_p95=None,
                absolute_error=abs(deterministic.forecast_value - actual),
                covered_90=None,
                interval_width_90=None,
            )
        )

    bootstrap_result = bootstrap_monte_carlo(
        series,
        years=years,
        target_year=target_year,
        n_simulations=n_simulations,
        random_seed=random_seed,
    )
    if bootstrap_result is not None:
        quantiles, _paths = bootstrap_result
        covered = quantiles.p05 <= actual <= quantiles.p95
        results.append(
            OriginResult(
                country_iso3=country_iso3,
                origin_year=origin_year,
                target_year=target_year,
                horizon_years=horizon,
                model_variant="empirical_bootstrap",
                actual=actual,
                forecast_p50=quantiles.p50,
                forecast_p05=quantiles.p05,
                forecast_p95=quantiles.p95,
                absolute_error=abs(quantiles.p50 - actual),
                covered_90=covered,
                interval_width_90=quantiles.p95 - quantiles.p05,
            )
        )

    return results


def run_backtest(
    panel: pd.DataFrame,
    *,
    origins: list[tuple[int, int]],
    countries: list[str] | None = None,
    n_simulations: int = 10_000,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Run every (origin_year, target_year) split in `origins` for every country.

    Returns a flat DataFrame — one row per (country, origin, model_variant) —
    matching the backtest_country_origin contract in 07_data_model_and_contracts.md.
    """
    countries = countries or sorted(panel["country_iso3"].unique())
    rows: list[dict[str, object]] = []
    for country_iso3 in countries:
        for origin_year, target_year in origins:
            for result in evaluate_origin(
                panel,
                country_iso3=country_iso3,
                origin_year=origin_year,
                target_year=target_year,
                n_simulations=n_simulations,
                random_seed=random_seed,
            ):
                rows.append(result.model_dump())
    return pd.DataFrame(rows)


def summarise_metrics(results: pd.DataFrame) -> pd.DataFrame:
    """Aggregate MAE / RMSE / median AE / P5-P95 coverage / interval width per model_variant.

    Country-unweighted by construction (13_backtesting_and_calibration.md
    section 5: don't hide weak small-economy performance behind a weighted
    average alone).
    """
    if results.empty:
        return pd.DataFrame(
            columns=[
                "model_variant",
                "n_splits",
                "mae",
                "rmse",
                "median_ae",
                "coverage_90",
                "mean_interval_width_90",
            ]
        )

    summary_rows: list[dict[str, object]] = []
    for model_variant, group in results.groupby("model_variant"):
        errors = group["absolute_error"].to_numpy()
        with_interval = group.dropna(subset=["covered_90"])
        summary_rows.append(
            {
                "model_variant": model_variant,
                "n_splits": len(group),
                "mae": float(np.mean(errors)),
                "rmse": float(np.sqrt(np.mean(errors**2))),
                "median_ae": float(np.median(errors)),
                "coverage_90": (
                    float(with_interval["covered_90"].mean()) if len(with_interval) else np.nan
                ),
                "mean_interval_width_90": (
                    float(with_interval["interval_width_90"].mean())
                    if len(with_interval)
                    else np.nan
                ),
            }
        )
    return pd.DataFrame(summary_rows)

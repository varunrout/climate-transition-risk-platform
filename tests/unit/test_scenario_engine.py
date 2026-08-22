from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from climate_risk.scenarios.engine import (
    bootstrap_monte_carlo,
    deterministic_trend_baseline,
    run_country_scenario,
)


@pytest.fixture
def declining_intensity_panel() -> pd.DataFrame:
    years = list(range(2000, 2021))
    rng = np.random.default_rng(7)
    intensity = 0.5 * (0.97 ** np.arange(len(years))) * (1 + rng.normal(0, 0.01, len(years)))
    return pd.DataFrame(
        {
            "country_iso3": ["ZZZ"] * len(years),
            "year": years,
            "carbon_intensity_gdp": intensity,
        }
    )


def test_deterministic_baseline_extrapolates_declining_trend(
    declining_intensity_panel: pd.DataFrame,
) -> None:
    baseline = deterministic_trend_baseline(
        declining_intensity_panel["carbon_intensity_gdp"],
        years=declining_intensity_panel["year"],
        target_year=2050,
    )
    assert baseline is not None
    assert baseline.trend_annual_log_change < 0  # intensity is declining
    assert baseline.forecast_value < baseline.origin_value
    assert baseline.sample_size == 21


def test_bootstrap_quantiles_are_monotonic(declining_intensity_panel: pd.DataFrame) -> None:
    result = bootstrap_monte_carlo(
        declining_intensity_panel["carbon_intensity_gdp"],
        years=declining_intensity_panel["year"],
        target_year=2030,
        n_simulations=2000,
        random_seed=42,
    )
    assert result is not None
    quantiles, _paths = result
    assert quantiles.p05 <= quantiles.p25 <= quantiles.p50 <= quantiles.p75 <= quantiles.p95


def test_bootstrap_is_deterministic_given_same_seed(
    declining_intensity_panel: pd.DataFrame,
) -> None:
    result_a = bootstrap_monte_carlo(
        declining_intensity_panel["carbon_intensity_gdp"],
        years=declining_intensity_panel["year"],
        target_year=2030,
        n_simulations=1000,
        random_seed=123,
    )
    result_b = bootstrap_monte_carlo(
        declining_intensity_panel["carbon_intensity_gdp"],
        years=declining_intensity_panel["year"],
        target_year=2030,
        n_simulations=1000,
        random_seed=123,
    )
    assert result_a is not None and result_b is not None
    assert result_a[0] == result_b[0]  # identical seed + data -> identical quantiles


def test_different_seeds_give_different_paths(declining_intensity_panel: pd.DataFrame) -> None:
    result_a = bootstrap_monte_carlo(
        declining_intensity_panel["carbon_intensity_gdp"],
        years=declining_intensity_panel["year"],
        target_year=2030,
        n_simulations=1000,
        random_seed=1,
    )
    result_b = bootstrap_monte_carlo(
        declining_intensity_panel["carbon_intensity_gdp"],
        years=declining_intensity_panel["year"],
        target_year=2030,
        n_simulations=1000,
        random_seed=2,
    )
    assert result_a is not None and result_b is not None
    assert result_a[0].p50 != result_b[0].p50


def test_run_country_scenario_always_includes_both_baseline_and_bootstrap(
    declining_intensity_panel: pd.DataFrame,
) -> None:
    scenario = run_country_scenario(
        declining_intensity_panel, country_iso3="ZZZ", target_year=2050, n_simulations=1000
    )
    assert scenario is not None
    assert scenario.deterministic is not None
    assert scenario.bootstrap is not None
    assert scenario.bootstrap.p05 <= scenario.bootstrap.p50 <= scenario.bootstrap.p95


def test_none_when_insufficient_history() -> None:
    tiny = pd.DataFrame(
        {
            "country_iso3": ["ZZZ"] * 3,
            "year": [2020, 2021, 2022],
            "carbon_intensity_gdp": [0.5, 0.49, 0.48],
        }
    )
    assert run_country_scenario(tiny, country_iso3="ZZZ", target_year=2050) is None

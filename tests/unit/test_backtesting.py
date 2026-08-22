from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from climate_risk.backtesting.rolling_origin import evaluate_origin, run_backtest, summarise_metrics


@pytest.fixture
def synthetic_panel() -> pd.DataFrame:
    years = list(range(2000, 2023))
    rng = np.random.default_rng(3)
    intensity = 0.6 * (0.96 ** np.arange(len(years))) * (1 + rng.normal(0, 0.015, len(years)))
    return pd.DataFrame(
        {
            "country_iso3": ["ZZZ"] * len(years),
            "year": years,
            "carbon_intensity_gdp": intensity,
        }
    )


def test_no_future_information_enters_training_split(synthetic_panel: pd.DataFrame) -> None:
    """Corrupt every year after the origin with an obviously-wrong value; if
    any model's forecast changes, future data leaked into fitting."""
    from climate_risk.backtesting.rolling_origin import _history_at_or_before

    origin_year = 2015
    clean_history = _history_at_or_before(
        synthetic_panel, country_iso3="ZZZ", origin_year=origin_year
    )

    corrupted = synthetic_panel.copy()
    corrupted.loc[corrupted["year"] > origin_year, "carbon_intensity_gdp"] = 999_999.0
    corrupted_history = _history_at_or_before(
        corrupted, country_iso3="ZZZ", origin_year=origin_year
    )

    pd.testing.assert_frame_equal(
        clean_history.reset_index(drop=True), corrupted_history.reset_index(drop=True)
    )


def test_evaluate_origin_returns_all_three_variants(synthetic_panel: pd.DataFrame) -> None:
    results = evaluate_origin(
        synthetic_panel,
        country_iso3="ZZZ",
        origin_year=2015,
        target_year=2022,
        n_simulations=2000,
        random_seed=42,
    )
    variants = {r.model_variant for r in results}
    assert variants == {"no_change", "deterministic_trend", "empirical_bootstrap"}


def test_bootstrap_interval_is_monotonic_in_backtest(synthetic_panel: pd.DataFrame) -> None:
    results = evaluate_origin(
        synthetic_panel,
        country_iso3="ZZZ",
        origin_year=2015,
        target_year=2022,
        n_simulations=2000,
        random_seed=42,
    )
    bootstrap = next(r for r in results if r.model_variant == "empirical_bootstrap")
    assert bootstrap.forecast_p05 <= bootstrap.forecast_p50 <= bootstrap.forecast_p95


def test_ineligible_split_returns_empty_when_target_missing(synthetic_panel: pd.DataFrame) -> None:
    results = evaluate_origin(
        synthetic_panel, country_iso3="ZZZ", origin_year=2015, target_year=2099
    )
    assert results == []


def test_run_backtest_and_summarise_metrics(synthetic_panel: pd.DataFrame) -> None:
    results = run_backtest(
        synthetic_panel, origins=[(2015, 2020), (2016, 2021), (2017, 2022)], n_simulations=1000
    )
    assert not results.empty
    summary = summarise_metrics(results)
    assert set(summary["model_variant"]) == {
        "no_change",
        "deterministic_trend",
        "empirical_bootstrap",
    }
    assert (summary["mae"] >= 0).all()
    bootstrap_row = summary[summary["model_variant"] == "empirical_bootstrap"].iloc[0]
    assert 0.0 <= bootstrap_row["coverage_90"] <= 1.0

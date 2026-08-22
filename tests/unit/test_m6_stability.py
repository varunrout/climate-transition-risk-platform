from __future__ import annotations

import pandas as pd

from climate_risk.research.m6_stability import (
    lookback_window_sensitivity,
    one_year_revision_sensitivity,
    summarise_stability,
    yoy_volatility,
)


def _energy_panel(
    countries: list[str], years: list[int], *, low_carbon_by_country: dict[str, list[float]]
) -> pd.DataFrame:
    rows = []
    for country in countries:
        for year, value in zip(years, low_carbon_by_country[country], strict=True):
            rows.append(
                {
                    "country_iso3": country,
                    "year": year,
                    "low_carbon_share_elec": value,
                    "fossil_share_elec": 100.0 - value,
                    "coal_share_elec": (100.0 - value) * 0.6,
                    "renewables_share_elec": value * 0.8,
                }
            )
    return pd.DataFrame(rows)


YEARS = list(range(2013, 2021))  # 8 years


def test_yoy_volatility_zero_for_perfectly_linear_series() -> None:
    values = [20.0 + 2.0 * i for i in range(len(YEARS))]  # constant +2pp/yr, no noise
    panel = _energy_panel(["AAA"], YEARS, low_carbon_by_country={"AAA": values})
    result = yoy_volatility(panel, column="low_carbon_share_elec")
    row = result[result["country_iso3"] == "AAA"].iloc[0]
    assert row["yoy_std_pp"] == 0.0
    assert row["yoy_mean_abs_pp"] == 2.0


def test_yoy_volatility_none_when_insufficient_history() -> None:
    panel = _energy_panel(["AAA"], YEARS[:1], low_carbon_by_country={"AAA": [30.0]})
    result = yoy_volatility(panel, column="low_carbon_share_elec")
    row = result[result["country_iso3"] == "AAA"].iloc[0]
    assert row["yoy_std_pp"] is None


def test_lookback_window_sensitivity_perfect_agreement_on_linear_trend() -> None:
    """A perfectly linear trend must produce identical slopes regardless of
    which trailing window is used -- Spearman correlation across windows
    should be 1.0 (or undefined if there's only one country, which is
    excluded from the pairwise comparison by construction)."""
    countries = ["AAA", "BBB", "CCC"]
    low_carbon = {
        "AAA": [20.0 + 2.0 * i for i in range(len(YEARS))],
        "BBB": [30.0 + 1.0 * i for i in range(len(YEARS))],
        "CCC": [10.0 + 3.0 * i for i in range(len(YEARS))],
    }
    panel = _energy_panel(countries, YEARS, low_carbon_by_country=low_carbon)
    result = lookback_window_sensitivity(panel, windows=(3, 5, 7))
    pairwise = result["pairwise_comparisons"]
    assert isinstance(pairwise, pd.DataFrame)
    valid = pairwise.dropna(subset=["spearman_rank_correlation"])
    assert (valid["spearman_rank_correlation"] > 0.99).all()


def test_one_year_revision_sensitivity_small_for_stable_trend() -> None:
    countries = ["AAA", "BBB", "CCC"]
    low_carbon = {
        "AAA": [20.0 + 2.0 * i for i in range(len(YEARS))],
        "BBB": [30.0 + 1.0 * i for i in range(len(YEARS))],
        "CCC": [10.0 + 3.0 * i for i in range(len(YEARS))],
    }
    panel = _energy_panel(countries, YEARS, low_carbon_by_country=low_carbon)
    result = one_year_revision_sensitivity(panel, trailing_window_years=5)
    assert not result.empty
    assert (result["dropped_from_panel_when_year_removed"] == False).all()  # noqa: E712


def test_summarise_stability_returns_scalar_summary() -> None:
    countries = ["AAA", "BBB", "CCC"]
    low_carbon = {
        "AAA": [20.0 + 2.0 * i for i in range(len(YEARS))],
        "BBB": [30.0 + 1.0 * i for i in range(len(YEARS))],
        "CCC": [10.0 + 3.0 * i for i in range(len(YEARS))],
    }
    panel = _energy_panel(countries, YEARS, low_carbon_by_country=low_carbon)
    lookback = lookback_window_sensitivity(panel)
    revision = one_year_revision_sensitivity(panel)
    summary = summarise_stability(lookback, revision)
    assert summary["mean_lookback_spearman_correlation"] is not None
    assert summary["countries_dropped_from_panel_by_one_year_revision"] == 0

from __future__ import annotations

import pandas as pd
import pytest

from climate_risk.features.energy_transition import (
    compute_energy_features,
    compute_energy_features_for_panel,
)


def _country_rows(
    country_iso3: str, years: list[int], *, coal: list[float], low_carbon: list[float]
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_iso3": [country_iso3] * len(years),
            "year": years,
            "coal_share_elec": coal,
            "gas_share_elec": [10.0] * len(years),
            "oil_share_elec": [1.0] * len(years),
            "fossil_share_elec": [c + 11.0 for c in coal],
            "renewables_share_elec": [
                lc - 5.0 for lc in low_carbon
            ],  # low_carbon minus the fixed 5.0 nuclear share below
            "low_carbon_share_elec": low_carbon,
            "nuclear_share_elec": [5.0] * len(years),
        }
    )


@pytest.fixture
def energy_panel() -> pd.DataFrame:
    # USA: coal declining ~2pp/yr, low-carbon rising ~2pp/yr over 6 years -- a clean trend.
    usa = _country_rows(
        "USA",
        [2015, 2016, 2017, 2018, 2019, 2020],
        coal=[38.0, 36.0, 34.0, 32.0, 30.0, 28.0],
        low_carbon=[33.0, 35.0, 37.0, 39.0, 41.0, 43.0],
    )
    # CHN: only two years of history -- below MIN_TRAILING_OBSERVATIONS, must yield None.
    chn = _country_rows("CHN", [2019, 2020], coal=[65.0, 63.0], low_carbon=[32.0, 33.7])
    return pd.concat([usa, chn], ignore_index=True)


def test_insufficient_history_returns_none(energy_panel: pd.DataFrame) -> None:
    result = compute_energy_features(energy_panel, country_iso3="CHN", trailing_window_years=5)
    assert result is None


def test_unknown_country_returns_none(energy_panel: pd.DataFrame) -> None:
    assert (
        compute_energy_features(energy_panel, country_iso3="ZZZ", trailing_window_years=5) is None
    )


def test_coal_trend_is_negative_and_clean_power_momentum_is_positive(
    energy_panel: pd.DataFrame,
) -> None:
    result = compute_energy_features(energy_panel, country_iso3="USA", trailing_window_years=5)
    assert result is not None
    assert result.coal_trend_pp_per_year is not None
    assert result.coal_trend_pp_per_year < 0
    assert result.clean_power_momentum_pp_per_year is not None
    assert result.clean_power_momentum_pp_per_year > 0
    assert result.latest_year == 2020
    assert result.low_carbon_share_elec == pytest.approx(43.0)


def test_transition_velocity_is_momentum_over_headroom(energy_panel: pd.DataFrame) -> None:
    result = compute_energy_features(energy_panel, country_iso3="USA", trailing_window_years=5)
    assert result is not None
    assert result.transition_velocity is not None
    expected = result.clean_power_momentum_pp_per_year / (100.0 - result.low_carbon_share_elec)
    assert result.transition_velocity == pytest.approx(expected)


def test_panel_features_skip_countries_with_no_result_and_add_percentiles(
    energy_panel: pd.DataFrame,
) -> None:
    features = compute_energy_features_for_panel(energy_panel, trailing_window_years=5)
    assert set(features["country_iso3"]) == {"USA"}  # CHN dropped: insufficient history
    assert "coal_share_elec_percentile" in features.columns
    assert "low_carbon_share_elec_percentile" in features.columns


def test_empty_panel_returns_empty_frame() -> None:
    empty = pd.DataFrame(
        columns=["country_iso3", "year", "fossil_share_elec", "low_carbon_share_elec"]
    )
    result = compute_energy_features_for_panel(empty, trailing_window_years=5)
    assert result.empty

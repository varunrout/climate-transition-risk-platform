from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from climate_risk.research.m6_incremental import (
    ENERGY_CANDIDATE_FEATURES,
    ablation_comparison,
    build_incremental_dataset,
    leave_one_country_out_comparison,
    permutation_test,
)


def _synthetic_transition_panel(
    countries: list[str], years: list[int], *, seed: int
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for country in countries:
        base = rng.uniform(0.3, 0.9)
        decay = rng.uniform(0.94, 0.99)
        for i, year in enumerate(years):
            intensity = base * (decay**i) * (1 + rng.normal(0, 0.01))
            rows.append({"country_iso3": country, "year": year, "carbon_intensity_gdp": intensity})
    return pd.DataFrame(rows)


def _synthetic_energy_panel(countries: list[str], years: list[int], *, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for country in countries:
        low_carbon_start = rng.uniform(10, 40)
        growth = rng.uniform(0.5, 2.5)
        for i, year in enumerate(years):
            low_carbon = min(95.0, low_carbon_start + growth * i + rng.normal(0, 1.0))
            fossil = 100.0 - low_carbon
            rows.append(
                {
                    "country_iso3": country,
                    "year": year,
                    "low_carbon_share_elec": low_carbon,
                    "fossil_share_elec": fossil,
                    "coal_share_elec": fossil * 0.5,
                    "gas_share_elec": fossil * 0.3,
                    "oil_share_elec": fossil * 0.2,
                    "renewables_share_elec": low_carbon * 0.8,
                    "nuclear_share_elec": low_carbon * 0.2,
                    "solar_share_elec": low_carbon * 0.3,
                    "wind_share_elec": low_carbon * 0.3,
                    "hydro_share_elec": low_carbon * 0.2,
                    "biofuel_share_elec": low_carbon * 0.0,
                }
            )
    return pd.DataFrame(rows)


COUNTRIES = [f"C{i:02d}" for i in range(12)]
YEARS = list(range(2000, 2023))
ORIGINS = [(2015, 2020), (2016, 2021), (2017, 2022)]


@pytest.fixture
def transition_panel() -> pd.DataFrame:
    return _synthetic_transition_panel(COUNTRIES, YEARS, seed=1)


@pytest.fixture
def energy_panel() -> pd.DataFrame:
    return _synthetic_energy_panel(COUNTRIES, YEARS, seed=2)


def test_no_future_leakage_in_energy_features(
    transition_panel: pd.DataFrame, energy_panel: pd.DataFrame
) -> None:
    """Corrupting every energy observation after an origin year must not
    change that origin's computed dataset row -- mirrors
    tests/unit/test_backtesting.py's leakage test, applied to the M6
    temporal-evaluation path."""
    origin_year = 2018
    clean_dataset = build_incremental_dataset(
        transition_panel, energy_panel, countries=COUNTRIES, origins=[(origin_year, 2022)]
    )

    corrupted_energy = energy_panel.copy()
    future_mask = corrupted_energy["year"] > origin_year
    corrupted_energy.loc[future_mask, "low_carbon_share_elec"] = 999.0
    corrupted_energy.loc[future_mask, "fossil_share_elec"] = -999.0

    corrupted_dataset = build_incremental_dataset(
        transition_panel, corrupted_energy, countries=COUNTRIES, origins=[(origin_year, 2022)]
    )

    pd.testing.assert_frame_equal(
        clean_dataset.sort_values("country_iso3").reset_index(drop=True),
        corrupted_dataset.sort_values("country_iso3").reset_index(drop=True),
    )


def test_incremental_dataset_has_expected_columns(
    transition_panel: pd.DataFrame, energy_panel: pd.DataFrame
) -> None:
    dataset = build_incremental_dataset(
        transition_panel, energy_panel, countries=COUNTRIES, origins=ORIGINS
    )
    assert not dataset.empty
    for column in [*ENERGY_CANDIDATE_FEATURES, "residual", "actual", "baseline_forecast"]:
        assert column in dataset.columns


def test_leave_one_country_out_reports_error_with_too_few_countries(
    transition_panel: pd.DataFrame, energy_panel: pd.DataFrame
) -> None:
    small = COUNTRIES[:3]
    dataset = build_incremental_dataset(
        transition_panel, energy_panel, countries=small, origins=ORIGINS
    )
    result = leave_one_country_out_comparison(dataset)
    assert "error" in result


def test_leave_one_country_out_runs_with_enough_countries(
    transition_panel: pd.DataFrame, energy_panel: pd.DataFrame
) -> None:
    dataset = build_incremental_dataset(
        transition_panel, energy_panel, countries=COUNTRIES, origins=ORIGINS
    )
    result = leave_one_country_out_comparison(dataset)
    assert "error" not in result
    assert result["baseline_mae"] >= 0
    assert result["augmented_mae"] >= 0
    assert result["n_splits"] > 0


def test_permutation_test_is_deterministic_given_same_seed(
    transition_panel: pd.DataFrame, energy_panel: pd.DataFrame
) -> None:
    dataset = build_incremental_dataset(
        transition_panel, energy_panel, countries=COUNTRIES, origins=ORIGINS
    )
    first = permutation_test(dataset, n_permutations=20, random_seed=7)
    second = permutation_test(dataset, n_permutations=20, random_seed=7)
    assert first == second


def test_permutation_p_value_is_a_valid_probability(
    transition_panel: pd.DataFrame, energy_panel: pd.DataFrame
) -> None:
    dataset = build_incremental_dataset(
        transition_panel, energy_panel, countries=COUNTRIES, origins=ORIGINS
    )
    result = permutation_test(dataset, n_permutations=30, random_seed=3)
    p_value = result["permutation_p_value"]
    if p_value is not None:
        assert 0.0 <= p_value <= 1.0


def test_ablation_comparison_covers_each_feature_and_the_combination(
    transition_panel: pd.DataFrame, energy_panel: pd.DataFrame
) -> None:
    dataset = build_incremental_dataset(
        transition_panel, energy_panel, countries=COUNTRIES, origins=ORIGINS
    )
    ablation = ablation_comparison(dataset)
    feature_sets = set(ablation["feature_set"])
    assert feature_sets == {*ENERGY_CANDIDATE_FEATURES, "all_three_combined"}

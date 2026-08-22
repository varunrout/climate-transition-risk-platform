from __future__ import annotations

import pandas as pd
import pytest

from climate_risk.scoring.energy_component import compute_energy_component


def _panel(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_higher_low_carbon_share_scores_lower_risk() -> None:
    panel = _panel(
        [
            {
                "country_iso3": "HIGH",
                "low_carbon_share_elec": 90.0,
                "clean_power_momentum_pp_per_year": 0.0,
                "fossil_persistence_mean_pct": 10.0,
            },
            {
                "country_iso3": "LOW",
                "low_carbon_share_elec": 10.0,
                "clean_power_momentum_pp_per_year": 0.0,
                "fossil_persistence_mean_pct": 10.0,
            },
        ]
    )
    result = compute_energy_component(panel).set_index("country_iso3")
    # HIGH has more low-carbon electricity -> should score as LOWER risk than LOW.
    assert (
        result.loc["HIGH", "sub_score_power_system_dependence"]
        < result.loc["LOW", "sub_score_power_system_dependence"]
    )


def test_higher_fossil_persistence_scores_higher_risk() -> None:
    panel = _panel(
        [
            {
                "country_iso3": "PERSISTENT",
                "low_carbon_share_elec": 50.0,
                "clean_power_momentum_pp_per_year": 0.0,
                "fossil_persistence_mean_pct": 90.0,
            },
            {
                "country_iso3": "TRANSITIONING",
                "low_carbon_share_elec": 50.0,
                "clean_power_momentum_pp_per_year": 0.0,
                "fossil_persistence_mean_pct": 10.0,
            },
        ]
    )
    result = compute_energy_component(panel).set_index("country_iso3")
    assert (
        result.loc["PERSISTENT", "sub_score_fossil_persistence"]
        > result.loc["TRANSITIONING", "sub_score_fossil_persistence"]
    )


def test_higher_momentum_scores_lower_risk() -> None:
    panel = _panel(
        [
            {
                "country_iso3": "IMPROVING",
                "low_carbon_share_elec": 50.0,
                "clean_power_momentum_pp_per_year": 3.0,
                "fossil_persistence_mean_pct": 50.0,
            },
            {
                "country_iso3": "STAGNANT",
                "low_carbon_share_elec": 50.0,
                "clean_power_momentum_pp_per_year": -1.0,
                "fossil_persistence_mean_pct": 50.0,
            },
        ]
    )
    result = compute_energy_component(panel).set_index("country_iso3")
    assert (
        result.loc["IMPROVING", "sub_score_transition_momentum"]
        < result.loc["STAGNANT", "sub_score_transition_momentum"]
    )


def test_component_score_is_within_0_100() -> None:
    panel = _panel(
        [
            {
                "country_iso3": f"C{i}",
                "low_carbon_share_elec": float(i * 5),
                "clean_power_momentum_pp_per_year": float(i - 5),
                "fossil_persistence_mean_pct": float(100 - i * 5),
            }
            for i in range(19)
        ]
    )
    result = compute_energy_component(panel)
    scored = result.dropna(subset=["energy_component_score"])
    assert (scored["energy_component_score"] >= 0).all()
    assert (scored["energy_component_score"] <= 100).all()


def test_missing_sub_signal_lowers_confidence_not_dropped() -> None:
    panel = _panel(
        [
            {
                "country_iso3": "PARTIAL",
                "low_carbon_share_elec": 50.0,
                "clean_power_momentum_pp_per_year": None,
                "fossil_persistence_mean_pct": 50.0,
            },
            {
                "country_iso3": "FULL",
                "low_carbon_share_elec": 50.0,
                "clean_power_momentum_pp_per_year": 1.0,
                "fossil_persistence_mean_pct": 50.0,
            },
        ]
    )
    result = compute_energy_component(panel).set_index("country_iso3")
    assert result.loc["PARTIAL", "n_sub_signals_available"] == 2
    assert result.loc["PARTIAL", "energy_confidence"] == pytest.approx(200 / 3)
    assert pd.notna(result.loc["PARTIAL", "energy_component_score"])  # still scored, not dropped
    assert result.loc["FULL", "energy_confidence"] == 100.0


def test_all_sub_signals_missing_yields_null_score_not_fabricated() -> None:
    panel = _panel(
        [
            {
                "country_iso3": "NODATA",
                "low_carbon_share_elec": None,
                "clean_power_momentum_pp_per_year": None,
                "fossil_persistence_mean_pct": None,
            },
            {
                "country_iso3": "OTHER",
                "low_carbon_share_elec": 40.0,
                "clean_power_momentum_pp_per_year": 1.0,
                "fossil_persistence_mean_pct": 60.0,
            },
        ]
    )
    result = compute_energy_component(panel).set_index("country_iso3")
    assert pd.isna(result.loc["NODATA", "energy_component_score"])
    assert result.loc["NODATA", "energy_confidence"] == 0.0


def test_deterministic_given_same_input() -> None:
    panel = _panel(
        [
            {
                "country_iso3": f"C{i}",
                "low_carbon_share_elec": float(i * 4),
                "clean_power_momentum_pp_per_year": float(i % 3 - 1),
                "fossil_persistence_mean_pct": float(80 - i * 3),
            }
            for i in range(10)
        ]
    )
    first = compute_energy_component(panel)
    second = compute_energy_component(panel)
    pd.testing.assert_frame_equal(first, second)

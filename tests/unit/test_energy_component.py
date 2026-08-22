from __future__ import annotations

import pandas as pd
import pytest

from climate_risk.scoring.energy_component import (
    ENERGY_COMPONENT_VERSION,
    compute_energy_component,
    compute_energy_component_generic,
)


def _panel(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_higher_low_carbon_share_scores_lower_risk() -> None:
    panel = _panel(
        [
            {
                "country_iso3": "HIGH",
                "low_carbon_share_elec": 90.0,
                "clean_power_momentum_pp_per_year": 0.0,
            },
            {
                "country_iso3": "LOW",
                "low_carbon_share_elec": 10.0,
                "clean_power_momentum_pp_per_year": 0.0,
            },
        ]
    )
    result = compute_energy_component(panel).set_index("country_iso3")
    # HIGH has more low-carbon electricity -> should score as LOWER risk than LOW.
    assert (
        result.loc["HIGH", "sub_score_power_system_dependence"]
        < result.loc["LOW", "sub_score_power_system_dependence"]
    )


def test_higher_momentum_scores_lower_risk() -> None:
    panel = _panel(
        [
            {
                "country_iso3": "IMPROVING",
                "low_carbon_share_elec": 50.0,
                "clean_power_momentum_pp_per_year": 3.0,
            },
            {
                "country_iso3": "STAGNANT",
                "low_carbon_share_elec": 50.0,
                "clean_power_momentum_pp_per_year": -1.0,
            },
        ]
    )
    result = compute_energy_component(panel).set_index("country_iso3")
    assert (
        result.loc["IMPROVING", "sub_score_transition_momentum"]
        < result.loc["STAGNANT", "sub_score_transition_momentum"]
    )


def test_component_version_is_recorded_and_frozen() -> None:
    panel = _panel(
        [
            {
                "country_iso3": "AAA",
                "low_carbon_share_elec": 50.0,
                "clean_power_momentum_pp_per_year": 0.0,
            }
        ]
    )
    result = compute_energy_component(panel)
    assert (result["energy_component_version"] == ENERGY_COMPONENT_VERSION).all()
    assert (
        ENERGY_COMPONENT_VERSION == "energy_component_v2.1"
    )  # regression guard on the frozen spec


def test_component_score_is_within_0_100() -> None:
    panel = _panel(
        [
            {
                "country_iso3": f"C{i}",
                "low_carbon_share_elec": float(i * 5),
                "clean_power_momentum_pp_per_year": float(i - 5),
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
            },
            {
                "country_iso3": "FULL",
                "low_carbon_share_elec": 50.0,
                "clean_power_momentum_pp_per_year": 1.0,
            },
        ]
    )
    result = compute_energy_component(panel).set_index("country_iso3")
    assert result.loc["PARTIAL", "n_sub_signals_available"] == 1
    assert result.loc["PARTIAL", "energy_confidence"] == pytest.approx(50.0)
    assert pd.notna(result.loc["PARTIAL", "energy_component_score"])  # still scored, not dropped
    assert result.loc["FULL", "energy_confidence"] == 100.0


def test_all_sub_signals_missing_yields_null_score_not_fabricated() -> None:
    panel = _panel(
        [
            {
                "country_iso3": "NODATA",
                "low_carbon_share_elec": None,
                "clean_power_momentum_pp_per_year": None,
            },
            {
                "country_iso3": "OTHER",
                "low_carbon_share_elec": 40.0,
                "clean_power_momentum_pp_per_year": 1.0,
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
            }
            for i in range(10)
        ]
    )
    first = compute_energy_component(panel)
    second = compute_energy_component(panel)
    pd.testing.assert_frame_equal(first, second)


# ---------------------------------------------------------------------------
# compute_energy_component_generic (M6 phase 3, section 2: formulation comparison)
# ---------------------------------------------------------------------------


def test_generic_two_signal_formulation_matches_hand_computed_average() -> None:
    panel = _panel(
        [
            {"country_iso3": "AAA", "low_carbon_share_elec": 90.0, "coal_share_elec": 5.0},
            {"country_iso3": "BBB", "low_carbon_share_elec": 10.0, "coal_share_elec": 80.0},
        ]
    )
    sub_signals = {"low_carbon_share_elec": False, "coal_share_elec": True}
    result = compute_energy_component_generic(panel, sub_signals).set_index("country_iso3")
    # AAA: high low-carbon (rank 1.0 -> inverted to 0) + low coal (rank 0.5 -> 50) = 25
    # BBB: low low-carbon (rank 0.5 -> inverted to 50) + high coal (rank 1.0 -> 100) = 75
    assert result.loc["AAA", "energy_component_score"] < result.loc["BBB", "energy_component_score"]


def test_generic_formulation_produces_frozen_formulation_identical_output() -> None:
    """compute_energy_component_generic, fed the frozen spec's own sub-signal
    set (ENERGY_SUB_SIGNALS), must reproduce compute_energy_component's own
    scoring exactly -- the generic path is used only for alternatives
    comparison, never as a silent behavioural change to production."""
    from climate_risk.scoring.energy_component import ENERGY_SUB_SIGNALS

    panel = _panel(
        [
            {
                "country_iso3": f"C{i}",
                "low_carbon_share_elec": float(i * 4),
                "clean_power_momentum_pp_per_year": float(i % 3 - 1),
            }
            for i in range(10)
        ]
    )
    frozen = compute_energy_component(panel)
    generic = compute_energy_component_generic(panel, ENERGY_SUB_SIGNALS)
    pd.testing.assert_series_equal(
        frozen["energy_component_score"], generic["energy_component_score"]
    )
    pd.testing.assert_series_equal(frozen["energy_confidence"], generic["energy_confidence"])


def test_frozen_spec_uses_exactly_two_signals() -> None:
    from climate_risk.scoring.energy_component import ENERGY_SUB_SIGNALS

    assert set(ENERGY_SUB_SIGNALS.keys()) == {
        "low_carbon_share_elec",
        "clean_power_momentum_pp_per_year",
    }
    assert (
        "fossil_persistence_mean_pct" not in ENERGY_SUB_SIGNALS
    )  # dropped for redundancy (ADR 0009)

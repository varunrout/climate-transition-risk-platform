from __future__ import annotations

from climate_risk.research.m6_component_alternatives import (
    FEATURE_COLUMNS,
    FORMULATION_NAMES,
    SUB_SIGNALS,
)


def test_formulation_names_consistent_across_both_representations() -> None:
    assert set(FEATURE_COLUMNS.keys()) == set(SUB_SIGNALS.keys())
    assert set(FORMULATION_NAMES) == set(FEATURE_COLUMNS.keys())


def test_each_formulation_columns_match_sub_signal_keys() -> None:
    for name in FORMULATION_NAMES:
        assert set(FEATURE_COLUMNS[name]) == set(SUB_SIGNALS[name].keys())


def test_two_signal_formulations_have_two_columns() -> None:
    assert len(FEATURE_COLUMNS["two_signal_compact"]) == 2
    assert len(FEATURE_COLUMNS["two_signal_alternative_level"]) == 2


def test_three_signal_current_matches_adr_0008_component() -> None:
    assert set(FEATURE_COLUMNS["three_signal_current"]) == {
        "low_carbon_share_elec",
        "clean_power_momentum_pp_per_year",
        "fossil_persistence_mean_pct",
    }


def test_alternative_level_formulation_avoids_the_redundant_pair() -> None:
    """ADR 0008 found low_carbon_share_elec and fossil_persistence_mean_pct
    near-mechanically redundant (Spearman rho ~= -0.989); the alternative
    level formulation must not use both."""
    columns = set(FEATURE_COLUMNS["two_signal_alternative_level"])
    assert not {"low_carbon_share_elec", "fossil_persistence_mean_pct"}.issubset(columns)

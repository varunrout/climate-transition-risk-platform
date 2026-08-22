"""M6 phase 3, section 2: candidate energy-component formulations compared
against each other before freezing one as `risk_score_v2_energy`'s
production component.

ADR 0008 found `low_carbon_share_elec` and `fossil_persistence_mean_pct`
(the two "level" signals in the original 3-signal component) in the same
redundancy cluster (Spearman rho ~= -0.989, near-mechanical) -- so the
3-signal component has closer to 2 independent degrees of freedom than 3.
These formulations test whether that redundancy actually costs anything
and whether a cleaner 2-signal design does just as well:

- `three_signal_current`: the ADR 0008 component, unchanged, as the
  incumbent to beat.
- `two_signal_compact`: drop fossil_persistence_mean_pct, keep the level
  (low_carbon_share_elec) + momentum (clean_power_momentum_pp_per_year)
  pair -- the simplest fix for the redundancy finding.
- `two_signal_alternative_level`: swap the level signal for
  coal_share_elec, which stood in its OWN redundancy cluster in ADR 0008
  (unlike low_carbon_share_elec) -- tests whether a genuinely
  less-redundant level signal changes the picture, at the cost of losing
  the "share of clean generation" framing for a "share of coal" one.

Both a feature-column form (for `m6_incremental`'s dataset-based tests) and
a sub-signal-direction form (for `energy_component.compute_energy_component_generic`)
are defined per formulation so the same names mean the same thing across
every comparison in this evaluation.
"""

from __future__ import annotations

FEATURE_COLUMNS: dict[str, list[str]] = {
    "three_signal_current": [
        "low_carbon_share_elec",
        "clean_power_momentum_pp_per_year",
        "fossil_persistence_mean_pct",
    ],
    "two_signal_compact": [
        "low_carbon_share_elec",
        "clean_power_momentum_pp_per_year",
    ],
    "two_signal_alternative_level": [
        "coal_share_elec",
        "clean_power_momentum_pp_per_year",
    ],
}

# column -> higher_is_higher_risk, per formulation (for energy_component.compute_energy_component_generic)
SUB_SIGNALS: dict[str, dict[str, bool]] = {
    "three_signal_current": {
        "low_carbon_share_elec": False,
        "clean_power_momentum_pp_per_year": False,
        "fossil_persistence_mean_pct": True,
    },
    "two_signal_compact": {
        "low_carbon_share_elec": False,
        "clean_power_momentum_pp_per_year": False,
    },
    "two_signal_alternative_level": {
        "coal_share_elec": True,
        "clean_power_momentum_pp_per_year": False,
    },
}

FORMULATION_NAMES: list[str] = list(FEATURE_COLUMNS.keys())

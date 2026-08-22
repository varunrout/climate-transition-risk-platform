"""M6 FROZEN production energy-transition component (risk_score_v2_energy).

Status: FROZEN spec `energy_component_v2.1` (M6 phase 3, ADR 0009). Not
imported by `climate_risk.scoring.risk_score` (v1); v1 is untouched by this
module's existence. `climate_risk.scoring.risk_score_v2_energy` is the only
production caller.

## Why 2 signals, not the original 3 (ADR 0008)

ADR 0008's original 3-signal component (power_system_dependence +
transition_momentum + fossil_persistence) found `low_carbon_share_elec` and
`fossil_persistence_mean_pct` in the SAME redundancy cluster (Spearman rho
~= -0.989, near-mechanical -- fossil_persistence is essentially a smoothed
`100 - low_carbon_share_elec`). M6 phase 3 (`climate_risk.research.m6_component_alternatives`,
`climate_risk.research.m6_phase3_harden`) compared the 3-signal component
against a 2-signal formulation that drops the redundant fossil-persistence
signal, and against an alternative level signal (`coal_share_elec`, which
stood in its own redundancy cluster). Real leave-one-country-out results
against live data (2000-permutation null test):

| Formulation | LOCO MAE improvement | permutation p |
|---|---|---|
| 3-signal (low_carbon + momentum + fossil_persistence) | 10.21% | 0.052 |
| **2-signal (low_carbon + momentum) -- FROZEN** | 10.06% | 0.0545 |
| 2-signal alternative (coal_share + momentum) | 4.90% | 0.987 (no signal) |

The 2-signal formulation performs within measurement noise of the 3-signal
one (and is actually slightly *better* on leave-one-origin-out CV: 13.1%
vs 12.4%), while directly resolving the redundancy finding and being
simpler -- the coal-share alternative was tested and rejected outright
(effectively indistinguishable from a random relationship). Per the M6
phase-3 brief's explicit instruction ("prefer the simpler formulation if
performance is statistically indistinguishable"), the 2-signal formulation
is frozen as production.

## The two sub-signals

- **power_system_dependence**: `low_carbon_share_elec` (latest year, %
  of electricity generation from renewables + nuclear). Higher share =
  lower risk.
- **transition_momentum**: `clean_power_momentum_pp_per_year` (trailing
  5yr OLS slope of `low_carbon_share_elec` vs year, percentage points per
  year). Higher (rising) momentum = lower risk. Known caveat, carried
  forward rather than resolved: this feature's trailing-window sensitivity
  is real (mean pairwise Spearman rho 0.59 across 3/5/7yr windows in phase
  3's lookback analysis) -- a Theil-Sen robust-slope alternative was tested
  and did NOT improve stability (0.577 vs 0.591 OLS), so the 5-year OLS
  window remains the canonical choice (also consistent with v1's own
  `pace_recent_trend` convention), not because instability was resolved.

Each is converted to a 0-100 cross-sectional percentile score (same
`rank(pct=True)*100` convention as `risk_score._percentile_score`, NaN
stays NaN), sign-flipped when higher-raw-value means lower risk, then
combined with equal 1/2 weights -- a documented, non-fitted choice. A
country missing one sub-signal still gets a score from the other:
`energy_confidence` records what fraction of the sub-signals were actually
observed, so missing energy data lowers confidence, never the score
itself (M6 missing-data requirement).
"""

from __future__ import annotations

import pandas as pd

ENERGY_COMPONENT_VERSION = "energy_component_v2.1"
"""Bumped from the ADR 0008 3-signal spec (implicitly v2.0) to this frozen
2-signal spec (ADR 0009) -- any future change to ENERGY_SUB_SIGNALS,
directionality, or the combination rule must bump this again."""

ENERGY_SUB_SIGNALS: dict[str, bool] = {
    # column -> higher_is_higher_risk
    "low_carbon_share_elec": False,
    "clean_power_momentum_pp_per_year": False,
}

MINIMUM_HISTORY_YEARS = 5
"""Matches `climate_risk.features.energy_transition.DEFAULT_TRAILING_WINDOW_YEARS`
-- the trailing window `clean_power_momentum_pp_per_year` is computed over.
Documented here because it's part of the frozen component's specification,
not just an implementation detail of the upstream feature module."""


def _direction_adjusted_percentile(values: pd.Series, *, higher_is_higher_risk: bool) -> pd.Series:
    ranked = values.rank(pct=True, na_option="keep") * 100.0
    return ranked if higher_is_higher_risk else (100.0 - ranked)


def compute_energy_component_generic(
    evaluation_panel: pd.DataFrame, sub_signals: dict[str, bool]
) -> pd.DataFrame:
    """Generic version of `compute_energy_component`, parameterised by an
    arbitrary `{column: higher_is_higher_risk}` sub-signal set -- used only
    by `climate_risk.research.m6_component_alternatives` to compare
    candidate formulations. The frozen production formulation is
    `compute_energy_component` below, which is NOT implemented in terms of
    this function's default so that changing this generic helper can never
    silently change production behaviour.
    """
    frame = evaluation_panel.set_index("country_iso3")
    sub_scores = pd.DataFrame(
        {
            column: _direction_adjusted_percentile(
                frame[column], higher_is_higher_risk=higher_is_higher_risk
            )
            for column, higher_is_higher_risk in sub_signals.items()
        }
    )

    n_available = sub_scores.notna().sum(axis=1)
    energy_component_score = sub_scores.mean(axis=1, skipna=True)
    energy_component_score = energy_component_score.mask(n_available == 0)
    energy_confidence = (n_available / len(sub_signals)) * 100.0

    out = pd.DataFrame(
        {
            "country_iso3": sub_scores.index,
            "energy_component_score": energy_component_score.to_numpy(),
            "energy_confidence": energy_confidence.to_numpy(),
            "n_sub_signals_available": n_available.to_numpy(),
        }
    )
    for column in sub_signals:
        out[f"sub_score_{column}"] = sub_scores[column].to_numpy()
    return out.reset_index(drop=True)


def compute_energy_component(evaluation_panel: pd.DataFrame) -> pd.DataFrame:
    """FROZEN production formulation (`ENERGY_COMPONENT_VERSION`). Input:
    a frame with one row per country carrying `low_carbon_share_elec` and
    `clean_power_momentum_pp_per_year` -- either the full M6 evaluation
    panel (`climate_risk.research.m6_panel.build_evaluation_panel`) or the
    slimmer `compute_energy_features_for_panel` output consumed directly by
    `cli.score()`. Output: one row per country with `energy_component_score`
    (0-100, NaN only if both sub-signals are missing), `energy_confidence`
    (0-100), and the two sub-scores for audit.
    """
    frame = evaluation_panel.set_index("country_iso3")
    sub_scores = pd.DataFrame(
        {
            column: _direction_adjusted_percentile(
                frame[column], higher_is_higher_risk=higher_is_higher_risk
            )
            for column, higher_is_higher_risk in ENERGY_SUB_SIGNALS.items()
        }
    )

    n_available = sub_scores.notna().sum(axis=1)
    energy_component_score = sub_scores.mean(axis=1, skipna=True)
    energy_component_score = energy_component_score.mask(n_available == 0)
    energy_confidence = (n_available / len(ENERGY_SUB_SIGNALS)) * 100.0

    out = pd.DataFrame(
        {
            "country_iso3": sub_scores.index,
            "energy_component_version": ENERGY_COMPONENT_VERSION,
            "energy_component_score": energy_component_score.to_numpy(),
            "energy_confidence": energy_confidence.to_numpy(),
            "sub_score_power_system_dependence": sub_scores["low_carbon_share_elec"].to_numpy(),
            "sub_score_transition_momentum": sub_scores[
                "clean_power_momentum_pp_per_year"
            ].to_numpy(),
            "n_sub_signals_available": n_available.to_numpy(),
        }
    )
    return out.reset_index(drop=True)

"""M6 candidate energy-transition component (EXPERIMENTAL -- score v2 only).

Not imported by `climate_risk.scoring.risk_score` (v1) or by `cli.score()`.
This module exists purely to let `risk_score_v2_energy` build an
experimental 5th component; it has no effect on any v1 output.

Three non-redundant sub-signals, one representative per redundancy family
identified in `climate_risk.research.m6_redundancy` (power-mix *level*,
*momentum*, and *persistence*) rather than every correlated share/trend
variable:

- power_system_dependence: low_carbon_share_elec (latest year). Higher
  share = lower risk.
- transition_momentum: clean_power_momentum_pp_per_year (trailing-window
  OLS slope). Higher (rising) momentum = lower risk.
- fossil_persistence: fossil_persistence_mean_pct (trailing-window mean
  fossil share). Higher = higher risk.

Each is converted to a 0-100 cross-sectional percentile score (same
`rank(pct=True)*100` convention as `risk_score._percentile_score`, NaN
stays NaN), sign-flipped first when higher-raw-value means lower risk, then
combined with equal 1/3 weights -- a documented, non-fitted choice (matches
how v1's own component list carries equal conceptual standing rather than
evaluation-fitted weights). A country missing one sub-signal still gets a
score from the other two: `energy_confidence` records what fraction of the
three sub-signals were actually observed, so missing energy data lowers
confidence, not the score itself, per the M6 missing-data requirement.
"""

from __future__ import annotations

import pandas as pd

ENERGY_SUB_SIGNALS: dict[str, bool] = {
    # column -> higher_is_higher_risk
    "low_carbon_share_elec": False,
    "clean_power_momentum_pp_per_year": False,
    "fossil_persistence_mean_pct": True,
}


def _direction_adjusted_percentile(values: pd.Series, *, higher_is_higher_risk: bool) -> pd.Series:
    ranked = values.rank(pct=True, na_option="keep") * 100.0
    return ranked if higher_is_higher_risk else (100.0 - ranked)


def compute_energy_component(evaluation_panel: pd.DataFrame) -> pd.DataFrame:
    """Input: the M6 evaluation panel (one row per country, from
    `climate_risk.research.m6_panel.build_evaluation_panel`). Output: one
    row per country with `energy_component_score` (0-100, NaN only if all
    three sub-signals are missing), `energy_confidence` (0-100), and the
    three sub-scores for audit.
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
            "energy_component_score": energy_component_score.to_numpy(),
            "energy_confidence": energy_confidence.to_numpy(),
            "sub_score_power_system_dependence": sub_scores["low_carbon_share_elec"].to_numpy(),
            "sub_score_transition_momentum": sub_scores[
                "clean_power_momentum_pp_per_year"
            ].to_numpy(),
            "sub_score_fossil_persistence": sub_scores["fossil_persistence_mean_pct"].to_numpy(),
            "n_sub_signals_available": n_available.to_numpy(),
        }
    )
    return out.reset_index(drop=True)

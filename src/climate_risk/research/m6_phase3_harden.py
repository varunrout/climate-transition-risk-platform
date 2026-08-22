"""M6 phase 3, sections 1-4: strengthen the phase-2 evidence before freezing
a production energy-component specification.

Orchestrates (does not redefine) the phase-2 building blocks
(`m6_panel`, `m6_incremental`, `m6_stability`, `m6_redundancy`,
`energy_component`, `risk_score_v2_energy`) against:

1. a stronger permutation test (>=2000 permutations, deterministic seed,
   reporting the percentile of the observed improvement within the null),
2. redundancy-reduced component formulations
   (`m6_component_alternatives`) compared on out-of-sample MAE, rank
   stability, weight sensitivity, missing-data behaviour and collinearity,
3. a deeper look at lookback-window instability (per-feature, per-country,
   plus a Theil-Sen-vs-OLS comparison), and
4. per-origin and leave-one-origin-out temporal robustness for every
   formulation.

Returns a plain dict of DataFrames/dicts; the CLI command
(`climate-risk m6-harden`) is the only thing that touches storage.
"""

from __future__ import annotations

from typing import TypedDict

import pandas as pd

from climate_risk.research import m6_component_alternatives as alternatives
from climate_risk.research import m6_incremental as incr
from climate_risk.research import m6_redundancy
from climate_risk.research import m6_stability as stability
from climate_risk.scoring.energy_component import compute_energy_component_generic
from climate_risk.scoring.risk_score import CountryRawMetrics
from climate_risk.scoring.risk_score_v2_energy import (
    weight_perturbation_analysis_v2,
)


class HardeningResult(TypedDict):
    incremental_dataset: pd.DataFrame
    permutation_result_incumbent: dict[str, object]
    formulation_incremental: pd.DataFrame
    formulation_permutations: dict[str, dict[str, object]]
    formulation_lookback: dict[str, pd.DataFrame]
    formulation_weight_sensitivity: dict[str, dict[str, float]]
    formulation_missing_data: dict[str, dict[str, object]]
    formulation_collinearity: dict[str, pd.DataFrame]
    full_lookback_pairwise: pd.DataFrame
    lookback_instability_by_feature: pd.DataFrame
    lookback_country_deltas: pd.DataFrame
    theil_sen_comparison: dict[str, dict[str, object]]
    formulation_by_origin: dict[str, pd.DataFrame]
    formulation_leave_one_origin_out: dict[str, dict[str, object]]


def run_hardening(
    transition_panel: pd.DataFrame,
    energy_panel: pd.DataFrame,
    evaluation_panel: pd.DataFrame,
    raw_metrics: list[CountryRawMetrics],
    *,
    countries: list[str],
    n_permutations: int,
    random_seed: int,
) -> HardeningResult:
    incremental_dataset = incr.build_incremental_dataset(
        transition_panel, energy_panel, countries=countries
    )

    # -----------------------------------------------------------------
    # 1. Strengthened permutation test (incumbent 3-signal formulation)
    # -----------------------------------------------------------------
    permutation_result = incr.permutation_test(
        incremental_dataset, n_permutations=n_permutations, random_seed=random_seed
    )

    # -----------------------------------------------------------------
    # 2. Redundancy-reduced component formulations
    # -----------------------------------------------------------------
    formulation_incremental = incr.compare_feature_sets(
        incremental_dataset, alternatives.FEATURE_COLUMNS
    )

    formulation_permutations = {
        name: incr.permutation_test(
            incremental_dataset,
            feature_columns=columns,
            n_permutations=n_permutations,
            random_seed=random_seed,
        )
        for name, columns in alternatives.FEATURE_COLUMNS.items()
    }

    formulation_lookback_columns = {
        "three_signal_current": [
            "clean_power_momentum_pp_per_year",
            "fossil_persistence_mean_pct",
        ],
        "two_signal_compact": ["clean_power_momentum_pp_per_year"],
        "two_signal_alternative_level": ["clean_power_momentum_pp_per_year"],
    }
    formulation_lookback: dict[str, pd.DataFrame] = {}
    for name, columns in formulation_lookback_columns.items():
        pairwise = stability.lookback_window_sensitivity(energy_panel, target_columns=columns)[
            "pairwise_comparisons"
        ]
        assert isinstance(pairwise, pd.DataFrame)
        formulation_lookback[name] = pairwise

    formulation_components = {
        name: compute_energy_component_generic(evaluation_panel, sub_signals)
        for name, sub_signals in alternatives.SUB_SIGNALS.items()
    }
    formulation_weight_sensitivity = {
        name: weight_perturbation_analysis_v2(
            raw_metrics,
            energy_component=component,
            perturbation_fraction=0.3,
            n_perturbations=200,
            random_seed=random_seed,
        )
        for name, component in formulation_components.items()
    }
    formulation_missing_data: dict[str, dict[str, object]] = {
        name: {
            "countries_with_full_component": int(
                (component["n_sub_signals_available"] == len(alternatives.SUB_SIGNALS[name])).sum()
            ),
            "countries_total": len(component),
            "mean_energy_confidence": float(component["energy_confidence"].mean()),
        }
        for name, component in formulation_components.items()
    }
    formulation_collinearity = {
        name: m6_redundancy.variance_inflation_factors(evaluation_panel, columns=columns)
        for name, columns in alternatives.FEATURE_COLUMNS.items()
    }

    # -----------------------------------------------------------------
    # 3. Lookback robustness detail
    # -----------------------------------------------------------------
    full_lookback = stability.lookback_window_sensitivity(energy_panel)
    pairwise = full_lookback["pairwise_comparisons"]
    assert isinstance(pairwise, pd.DataFrame)
    instability_by_feature = stability.lookback_instability_by_feature(pairwise)
    country_deltas = stability.lookback_window_country_deltas(energy_panel)
    # clean_power_momentum_pp_per_year is itself an OLS slope, not a raw
    # column in energy_panel -- the Theil-Sen comparison operates on the raw
    # series (low_carbon_share_elec, fossil_share_elec), the columns an
    # alternative estimator would actually be fit against.
    theil_sen_comparison = {
        "low_carbon_share_elec": stability.theil_sen_vs_ols_lookback_stability(
            energy_panel, column="low_carbon_share_elec"
        ),
        "fossil_share_elec": stability.theil_sen_vs_ols_lookback_stability(
            energy_panel, column="fossil_share_elec"
        ),
    }

    # -----------------------------------------------------------------
    # 4. Temporal / origin robustness, per formulation
    # -----------------------------------------------------------------
    formulation_by_origin = {
        name: incr.leave_one_country_out_comparison_by_origin(
            incremental_dataset, feature_columns=columns
        )
        for name, columns in alternatives.FEATURE_COLUMNS.items()
    }
    formulation_leave_one_origin_out = {
        name: incr.leave_one_origin_out_comparison(incremental_dataset, feature_columns=columns)
        for name, columns in alternatives.FEATURE_COLUMNS.items()
    }

    return {
        "incremental_dataset": incremental_dataset,
        "permutation_result_incumbent": permutation_result,
        "formulation_incremental": formulation_incremental,
        "formulation_permutations": formulation_permutations,
        "formulation_lookback": formulation_lookback,
        "formulation_weight_sensitivity": formulation_weight_sensitivity,
        "formulation_missing_data": formulation_missing_data,
        "formulation_collinearity": formulation_collinearity,
        "full_lookback_pairwise": pairwise,
        "lookback_instability_by_feature": instability_by_feature,
        "lookback_country_deltas": country_deltas,
        "theil_sen_comparison": theil_sen_comparison,
        "formulation_by_origin": formulation_by_origin,
        "formulation_leave_one_origin_out": formulation_leave_one_origin_out,
    }

"""Transition risk scoring v2, energy-augmented -- FROZEN production spec
(M6 phase 3, ADR 0009).

This module NEVER touches `climate_risk.scoring.risk_score` (v1): it is
additive, importing v1's `CountryRawMetrics` and `_percentile_score`
convention rather than modifying them. v1's own output
(`gold/country_transition_risk.parquet`, `compute_risk_scores`) is byte-for-byte
unchanged by this module's existence or by v2's promotion to production --
see `tests/unit/test_risk_score_v2_energy.py::test_v1_available_components_still_exclude_energy`.

v2 adds a 5th component (`energy`, `climate_risk.scoring.energy_component`,
frozen spec `energy_component_v2.1`) to v1's four, using the SAME nominal
weight scheme already declared in v1 (`NOMINAL_WEIGHTS["energy"] = 0.20`
was always reserved, just never computed) -- so v2's five nominal weights
already sum to 1.0 and don't need rescaling globally. Per-country
missing-data handling reuses v1's weighted_sum/weight_present
renormalisation loop unchanged: a country missing the energy component
still gets a score from its other four components, with a correspondingly
lower per-country `weight_coverage` (this differs from v1, where
`weight_coverage` was a single global constant because energy was
structurally 100% absent for every country -- v2 tracks it per-country
because energy coverage varies by country).

Promoted from ADR 0008's experimental status to the default production
score by ADR 0009, after the phase-3 evidence-hardening pass (2000-permutation
test, redundancy-reduced 2-signal component, per-origin/leave-one-origin-out
temporal checks) confirmed the ACCEPT decision holds under stronger scrutiny.
`cli.score()` now computes both v1 and v2; `cli.publish()` declares v2 as
the active production score while preserving v1 as a permanent comparison
artifact -- see `climate_risk.cli.score` / `climate_risk.cli.publish`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from climate_risk.scoring.energy_component import ENERGY_COMPONENT_VERSION
from climate_risk.scoring.risk_score import (
    BANDS,
    NOMINAL_WEIGHTS,
    CountryRawMetrics,
    _percentile_score,
)

SCORE_VERSION = "v2_energy"
COMPONENT_VERSION = ENERGY_COMPONENT_VERSION
WEIGHTS_VERSION = "v2_weights_v1"
"""Identifies the *weight scheme* (which nominal weights, which components
are available) separately from the *component formula* (COMPONENT_VERSION)
-- a future weight-only change (e.g. re-deriving the energy weight from a
fitted model) would bump WEIGHTS_VERSION without needing a new
COMPONENT_VERSION, and vice versa."""

AVAILABLE_COMPONENTS_V2 = ("pace", "coupling", "volatility", "forward_downside", "energy")
_available_weight_sum_v2 = sum(NOMINAL_WEIGHTS[c] for c in AVAILABLE_COMPONENTS_V2)
EFFECTIVE_WEIGHTS_V2: dict[str, float] = {
    c: NOMINAL_WEIGHTS[c] / _available_weight_sum_v2 for c in AVAILABLE_COMPONENTS_V2
}
NOMINAL_WEIGHT_SCHEME_COVERAGE_V2 = (
    _available_weight_sum_v2  # 1.0 -- all 5 nominal components now computed
)


def compute_risk_scores_v2(
    raw_metrics: list[CountryRawMetrics],
    *,
    energy_component: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Score every country in `raw_metrics`, joined with
    `energy_component` (from `climate_risk.scoring.energy_component.compute_energy_component`,
    already a 0-100 per-country score plus `energy_confidence`).

    `weights` defaults to EFFECTIVE_WEIGHTS_V2; pass an alternative for
    weight-perturbation sensitivity analysis without mutating shared state
    (same pattern as v1's `compute_risk_scores`).
    """
    weights = weights or EFFECTIVE_WEIGHTS_V2
    frame = pd.DataFrame([m.model_dump() for m in raw_metrics]).set_index("country_iso3")
    energy = energy_component.set_index("country_iso3")

    score_pace = _percentile_score(frame["pace_recent_trend"])
    score_coupling = _percentile_score(
        frame[["coupling_elasticity", "coupling_pearson_r"]].mean(axis=1, skipna=True)
    )
    score_volatility = _percentile_score(frame["volatility_std_log_change"])

    forward_both_missing = (
        frame[["forward_prob_worse_than_baseline", "forward_interval_width_ratio"]]
        .isna()
        .all(axis=1)
    )
    normalised_width = _percentile_score(frame["forward_interval_width_ratio"]).fillna(0) / 100.0
    combined_forward = (
        frame["forward_prob_worse_than_baseline"].fillna(0) * 0.7 + normalised_width * 0.3
    )
    combined_forward = combined_forward.mask(forward_both_missing)
    score_forward = _percentile_score(combined_forward)

    score_energy = energy["energy_component_score"].reindex(frame.index)
    energy_confidence = energy["energy_confidence"].reindex(frame.index).fillna(0.0)

    component_scores = pd.DataFrame(
        {
            "pace": score_pace,
            "coupling": score_coupling,
            "volatility": score_volatility,
            "forward_downside": score_forward,
            "energy": score_energy,
        }
    )

    weighted_sum = pd.Series(0.0, index=component_scores.index)
    weight_present = pd.Series(0.0, index=component_scores.index)
    for component, weight in weights.items():
        col = component_scores[component]
        present = col.notna()
        weighted_sum += col.fillna(0) * weight * present
        weight_present += weight * present

    score_total = weighted_sum / weight_present.replace(0, np.nan)
    per_country_weight_coverage = (
        weight_present  # already 0-1, sums the *nominal* v2 weight actually scored
    )

    history_score = (frame["history_years"] / frame["history_years"].max()).clip(upper=1.0)
    # Per-country now (v1 used a single global constant, since energy was
    # 0% covered for everyone); a country missing energy gets a lower
    # weight_coverage and thus lower confidence, without score_total itself
    # being pushed toward "higher risk" by the absence -- see
    # tests/unit/test_risk_score_v2_energy.py::test_missing_energy_does_not_inflate_risk.
    confidence = (
        (0.6 * frame["completeness_fraction"] + 0.4 * history_score)
        * 100.0
        * per_country_weight_coverage
    )

    out = pd.DataFrame(
        {
            "country_iso3": component_scores.index,
            "score_version": SCORE_VERSION,
            "component_version": COMPONENT_VERSION,
            "weights_version": WEIGHTS_VERSION,
            "score_total": score_total.to_numpy(),
            "score_pace": component_scores["pace"].to_numpy(),
            "score_coupling": component_scores["coupling"].to_numpy(),
            "score_volatility": component_scores["volatility"].to_numpy(),
            "score_forward_downside": component_scores["forward_downside"].to_numpy(),
            "score_energy": component_scores["energy"].to_numpy(),
            "energy_confidence": energy_confidence.to_numpy(),
            "data_confidence_score": confidence.to_numpy(),
            "weight_coverage": per_country_weight_coverage.to_numpy(),
        }
    )
    out = out.dropna(subset=["score_total"]).sort_values("score_total", ascending=False)
    out["rank"] = range(1, len(out) + 1)
    out["rank_band"] = out["score_total"].apply(_band)
    return out.reset_index(drop=True)


def _band(score: float) -> str:
    for upper, label in BANDS:
        if score <= upper:
            return label
    return BANDS[-1][1]


def weight_perturbation_analysis_v2(
    raw_metrics: list[CountryRawMetrics],
    *,
    energy_component: pd.DataFrame,
    perturbation_fraction: float = 0.3,
    n_perturbations: int = 200,
    random_seed: int = 42,
) -> dict[str, float]:
    """Same methodology as v1's `weight_perturbation_analysis`, generalised
    to a caller-supplied `perturbation_fraction` (v1 was hardcoded to 0.3 /
    +-30%; the M6 brief also asks for +-10% and +-20%)."""
    base_scores = compute_risk_scores_v2(raw_metrics, energy_component=energy_component)
    base_rank = base_scores.set_index("country_iso3")["rank"]

    rng = np.random.default_rng(random_seed)
    spearman_correlations = []
    max_movements = []
    moved_more_than_3 = []

    low = 1.0 - perturbation_fraction
    high = 1.0 + perturbation_fraction
    for _ in range(n_perturbations):
        perturbed = {c: w * rng.uniform(low, high) for c, w in EFFECTIVE_WEIGHTS_V2.items()}
        total = sum(perturbed.values())
        perturbed = {c: w / total for c, w in perturbed.items()}

        alt_scores = compute_risk_scores_v2(
            raw_metrics, energy_component=energy_component, weights=perturbed
        )
        alt_rank = alt_scores.set_index("country_iso3")["rank"]

        common = base_rank.index.intersection(alt_rank.index)
        if len(common) < 3:
            continue
        correlation = stats.spearmanr(base_rank[common], alt_rank[common]).correlation
        spearman_correlations.append(correlation)
        movement = (base_rank[common] - alt_rank[common]).abs()
        max_movements.append(int(movement.max()))
        moved_more_than_3.append(int((movement > 3).sum()))

    return {
        "perturbation_fraction": perturbation_fraction,
        "n_perturbations": len(spearman_correlations),
        "mean_spearman_correlation": float(np.mean(spearman_correlations)),
        "min_spearman_correlation": float(np.min(spearman_correlations)),
        "median_max_rank_movement": float(np.median(max_movements)),
        "mean_max_rank_movement": float(np.mean(max_movements)),
        "mean_countries_moved_gt_3_ranks": float(np.mean(moved_more_than_3)),
    }

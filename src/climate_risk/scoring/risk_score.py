"""Transition risk scoring v1 (10_transition_risk_taxonomy.md, 14_risk_scoring_and_country_profiles.md).

Score direction: 0 = lower observed transition risk, 100 = higher observed
transition risk — a relative analytical scale across the current country
set, not a probability of policy failure or a credit-risk equivalent
(10_transition_risk_taxonomy.md section 6 lists banned terminology this
module and its callers must not use).

v1 implements 4 of the 5 nominal components. The energy-system transition
component is **not computed** because its only planned data source (Ember)
is disabled pending licence verification (config/sources.yaml,
06_data_sources_and_licensing.md). Per section 5's missing-component
policy ("do not silently reweight unless explicitly defined"), the
remaining four weights are proportionally renormalised to sum to 1.0 and
`weight_coverage` on every row records that only 80% of the nominal weight
scheme was scored — this is not hidden inside a normal-looking 0-100 number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict
from scipy import stats

from climate_risk.features.decoupling import DecouplingResult
from climate_risk.scenarios.engine import CountryScenario

NOMINAL_WEIGHTS: dict[str, float] = {
    "pace": 0.25,
    "coupling": 0.20,
    "volatility": 0.15,
    "energy": 0.20,  # not computed in v1 -- see module docstring
    "forward_downside": 0.20,
}
AVAILABLE_COMPONENTS = ("pace", "coupling", "volatility", "forward_downside")
_available_weight_sum = sum(NOMINAL_WEIGHTS[c] for c in AVAILABLE_COMPONENTS)
EFFECTIVE_WEIGHTS: dict[str, float] = {
    c: NOMINAL_WEIGHTS[c] / _available_weight_sum for c in AVAILABLE_COMPONENTS
}
WEIGHT_COVERAGE = _available_weight_sum  # fraction of nominal v1 weight scheme actually scored

BANDS = [(20, "lower"), (40, "moderate-low"), (60, "moderate"), (80, "elevated"), (100, "high")]


class CountryRawMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_iso3: str
    pace_recent_trend: float | None  # annual log-change of intensity, last <=5yr; positive = worse
    coupling_elasticity: float | None
    coupling_pearson_r: float | None
    volatility_std_log_change: float | None
    forward_prob_worse_than_baseline: float | None
    forward_interval_width_ratio: float | None  # (p95-p05)/p50, normalised sharpness penalty
    history_years: int
    completeness_fraction: float


def _recent_trend(series: pd.Series, years: pd.Series, *, window: int = 5) -> float | None:
    rows = pd.DataFrame({"year": years, "value": series}).dropna()
    rows = rows[rows["value"] > 0].sort_values("year").tail(window)
    if len(rows) < 3:
        return None
    slope = stats.linregress(rows["year"], np.log(rows["value"])).slope
    return float(slope)


def _volatility(series: pd.Series, years: pd.Series) -> float | None:
    rows = pd.DataFrame({"year": years, "value": series}).dropna()
    rows = rows[rows["value"] > 0].sort_values("year")
    if len(rows) < 6:
        return None
    log_changes = np.diff(np.log(rows["value"].to_numpy()))
    return float(np.std(log_changes, ddof=1))


def compute_raw_metrics(
    panel: pd.DataFrame,
    *,
    decoupling: dict[str, DecouplingResult],
    scenarios: dict[str, CountryScenario],
    countries: list[str],
) -> list[CountryRawMetrics]:
    results = []
    for country_iso3 in countries:
        rows = panel[panel["country_iso3"] == country_iso3].sort_values("year")
        series = rows["carbon_intensity_gdp"]
        years = rows["year"]

        decoupling_result = decoupling.get(country_iso3)
        scenario_result = scenarios.get(country_iso3)

        interval_width_ratio = None
        prob_worse = None
        if scenario_result is not None:
            b = scenario_result.bootstrap
            prob_worse = 1.0 - b.prob_below_baseline
            if b.p50 != 0:
                interval_width_ratio = (b.p95 - b.p05) / abs(b.p50)

        results.append(
            CountryRawMetrics(
                country_iso3=country_iso3,
                pace_recent_trend=_recent_trend(series, years),
                coupling_elasticity=decoupling_result.elasticity if decoupling_result else None,
                coupling_pearson_r=decoupling_result.pearson_r if decoupling_result else None,
                volatility_std_log_change=_volatility(series, years),
                forward_prob_worse_than_baseline=prob_worse,
                forward_interval_width_ratio=interval_width_ratio,
                history_years=int(rows["year"].nunique()),
                completeness_fraction=(
                    float(rows["is_core_complete"].mean()) if len(rows) else 0.0
                ),
            )
        )
    return results


def _percentile_score(values: pd.Series) -> pd.Series:
    """Cross-sectional percentile rank -> 0-100, higher input value = higher score.

    NaNs stay NaN (missing metric, not a fabricated middle-of-pack score).
    """
    return values.rank(pct=True, na_option="keep") * 100.0


def compute_risk_scores(
    raw_metrics: list[CountryRawMetrics], *, weights: dict[str, float] | None = None
) -> pd.DataFrame:
    """Score every country in `raw_metrics`. `weights` defaults to EFFECTIVE_WEIGHTS
    (module-level v1 weights); pass an alternative weight dict for sensitivity analysis
    without mutating any shared state."""
    weights = weights or EFFECTIVE_WEIGHTS
    frame = pd.DataFrame([m.model_dump() for m in raw_metrics]).set_index("country_iso3")

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

    component_scores = pd.DataFrame(
        {
            "pace": score_pace,
            "coupling": score_coupling,
            "volatility": score_volatility,
            "forward_downside": score_forward,
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

    history_score = (frame["history_years"] / frame["history_years"].max()).clip(upper=1.0)
    # Confidence reflects completeness + history length, scaled down by weight_coverage so a
    # country is never shown as fully confident when a whole component (energy) is structurally
    # absent for every country in this release.
    confidence = (
        (0.6 * frame["completeness_fraction"] + 0.4 * history_score) * 100.0 * WEIGHT_COVERAGE
    )

    out = pd.DataFrame(
        {
            "country_iso3": component_scores.index,
            "score_total": score_total.to_numpy(),
            "score_pace": component_scores["pace"].to_numpy(),
            "score_coupling": component_scores["coupling"].to_numpy(),
            "score_volatility": component_scores["volatility"].to_numpy(),
            "score_forward_downside": component_scores["forward_downside"].to_numpy(),
            "data_confidence_score": confidence.to_numpy(),
            "weight_coverage": WEIGHT_COVERAGE,
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


def weight_perturbation_analysis(
    raw_metrics: list[CountryRawMetrics], *, n_perturbations: int = 200, random_seed: int = 42
) -> dict[str, float]:
    """Rank-stability under randomly perturbed component weights
    (10_transition_risk_taxonomy.md section 9 / 14_..._profiles.md section 8).

    Each perturbation draws new weights uniformly within +/-30% of the
    effective v1 weights (renormalised to sum to 1), rescores the same raw
    metrics with `weights=` (no shared/global state touched), and compares
    the resulting rank order to the base v1 ranking via Spearman correlation
    and rank-movement counts.
    """
    base_scores = compute_risk_scores(raw_metrics)
    base_rank = base_scores.set_index("country_iso3")["rank"]

    rng = np.random.default_rng(random_seed)
    spearman_correlations = []
    max_movements = []
    moved_more_than_3 = []

    for _ in range(n_perturbations):
        perturbed = {c: w * rng.uniform(0.7, 1.3) for c, w in EFFECTIVE_WEIGHTS.items()}
        total = sum(perturbed.values())
        perturbed = {c: w / total for c, w in perturbed.items()}

        alt_scores = compute_risk_scores(raw_metrics, weights=perturbed)
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
        "n_perturbations": len(spearman_correlations),
        "mean_spearman_correlation": float(np.mean(spearman_correlations)),
        "min_spearman_correlation": float(np.min(spearman_correlations)),
        "mean_max_rank_movement": float(np.mean(max_movements)),
        "mean_countries_moved_gt_3_ranks": float(np.mean(moved_more_than_3)),
    }

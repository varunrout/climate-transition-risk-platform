from __future__ import annotations

import numpy as np
import pytest

from climate_risk.scoring.risk_score import (
    AVAILABLE_COMPONENTS,
    NOMINAL_WEIGHTS,
    WEIGHT_COVERAGE,
    CountryRawMetrics,
    compute_risk_scores,
    weight_perturbation_analysis,
)


def make_metrics(n: int = 10) -> list[CountryRawMetrics]:
    rng = np.random.default_rng(0)
    return [
        CountryRawMetrics(
            country_iso3=f"C{i:02d}",
            pace_recent_trend=float(rng.normal(-0.02, 0.03)),
            coupling_elasticity=float(rng.uniform(-1.0, 1.2)),
            coupling_pearson_r=float(rng.uniform(-1, 1)),
            volatility_std_log_change=float(abs(rng.normal(0.05, 0.02))),
            forward_prob_worse_than_baseline=float(rng.uniform(0, 1)),
            forward_interval_width_ratio=float(abs(rng.normal(0.5, 0.2))),
            history_years=rng.integers(10, 25),
            completeness_fraction=float(rng.uniform(0.7, 1.0)),
        )
        for i in range(n)
    ]


def test_weight_coverage_reflects_missing_energy_component() -> None:
    assert "energy" not in AVAILABLE_COMPONENTS
    assert pytest.approx(1 - NOMINAL_WEIGHTS["energy"]) == WEIGHT_COVERAGE


def test_scores_are_in_0_100_range() -> None:
    scores = compute_risk_scores(make_metrics())
    assert (scores["score_total"] >= 0).all()
    assert (scores["score_total"] <= 100).all()
    assert (scores["data_confidence_score"] >= 0).all()
    assert (scores["data_confidence_score"] <= 100).all()


def test_data_confidence_never_exceeds_weight_coverage_ceiling() -> None:
    scores = compute_risk_scores(make_metrics())
    # completeness=1, history at max -> confidence approaches 100 * WEIGHT_COVERAGE, never 100
    assert (scores["data_confidence_score"] <= 100 * WEIGHT_COVERAGE + 1e-9).all()


def test_rank_is_dense_and_sorted_by_score_descending() -> None:
    scores = compute_risk_scores(make_metrics())
    assert list(scores["rank"]) == list(range(1, len(scores) + 1))
    assert scores["score_total"].is_monotonic_decreasing


def test_missing_metric_country_excluded_not_fabricated() -> None:
    metrics = make_metrics(5)
    # blank out every raw signal for one country
    blanked = metrics[0].model_copy(
        update={
            "pace_recent_trend": None,
            "coupling_elasticity": None,
            "coupling_pearson_r": None,
            "volatility_std_log_change": None,
            "forward_prob_worse_than_baseline": None,
            "forward_interval_width_ratio": None,
        }
    )
    metrics[0] = blanked
    scores = compute_risk_scores(metrics)
    assert blanked.country_iso3 not in set(scores["country_iso3"])


def test_weight_perturbation_analysis_reports_rank_stability() -> None:
    result = weight_perturbation_analysis(make_metrics(15), n_perturbations=50, random_seed=1)
    assert result["n_perturbations"] > 0
    assert -1.0 <= result["mean_spearman_correlation"] <= 1.0
    assert result["mean_max_rank_movement"] >= 0


def test_compute_risk_scores_does_not_mutate_global_weights() -> None:
    from climate_risk.scoring.risk_score import EFFECTIVE_WEIGHTS

    before = dict(EFFECTIVE_WEIGHTS)
    compute_risk_scores(make_metrics(), weights={"pace": 1.0})
    assert before == EFFECTIVE_WEIGHTS

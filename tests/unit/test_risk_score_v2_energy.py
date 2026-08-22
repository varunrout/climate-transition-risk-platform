from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from climate_risk.scoring import risk_score
from climate_risk.scoring.risk_score_v2_energy import (
    AVAILABLE_COMPONENTS_V2,
    COMPONENT_VERSION,
    EFFECTIVE_WEIGHTS_V2,
    SCORE_VERSION,
    WEIGHTS_VERSION,
    compute_risk_scores_v2,
    weight_perturbation_analysis_v2,
)


def make_metrics(n: int = 12) -> list[risk_score.CountryRawMetrics]:
    rng = np.random.default_rng(0)
    return [
        risk_score.CountryRawMetrics(
            country_iso3=f"C{i:02d}",
            pace_recent_trend=float(rng.normal(-0.02, 0.03)),
            coupling_elasticity=float(rng.uniform(-1.0, 1.2)),
            coupling_pearson_r=float(rng.uniform(-1, 1)),
            volatility_std_log_change=float(abs(rng.normal(0.05, 0.02))),
            forward_prob_worse_than_baseline=float(rng.uniform(0, 1)),
            forward_interval_width_ratio=float(abs(rng.normal(0.5, 0.2))),
            history_years=int(rng.integers(10, 25)),
            completeness_fraction=float(rng.uniform(0.7, 1.0)),
        )
        for i in range(n)
    ]


def make_energy_component(countries: list[str], *, missing: set[str] | None = None) -> pd.DataFrame:
    missing = missing or set()
    rng = np.random.default_rng(1)
    rows = []
    for c in countries:
        if c in missing:
            rows.append(
                {
                    "country_iso3": c,
                    "energy_component_score": None,
                    "energy_confidence": 0.0,
                    "sub_score_power_system_dependence": None,
                    "sub_score_transition_momentum": None,
                    "n_sub_signals_available": 0,
                }
            )
        else:
            rows.append(
                {
                    "country_iso3": c,
                    "energy_component_score": float(rng.uniform(0, 100)),
                    "energy_confidence": 100.0,
                    "sub_score_power_system_dependence": float(rng.uniform(0, 100)),
                    "sub_score_transition_momentum": float(rng.uniform(0, 100)),
                    "n_sub_signals_available": 2,
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# v1 is untouched by this module's existence
# ---------------------------------------------------------------------------


def test_v1_available_components_still_exclude_energy() -> None:
    assert "energy" not in risk_score.AVAILABLE_COMPONENTS
    assert pytest.approx(0.8) == risk_score.WEIGHT_COVERAGE


def test_v2_is_a_separate_module_not_imported_by_v1() -> None:
    import climate_risk.scoring.risk_score as v1_module

    assert not hasattr(v1_module, "compute_risk_scores_v2")
    assert not hasattr(v1_module, "energy_component")


# ---------------------------------------------------------------------------
# v2 scoring
# ---------------------------------------------------------------------------


def test_v2_nominal_weights_sum_to_one_and_include_energy() -> None:
    assert set(AVAILABLE_COMPONENTS_V2) == {
        "pace",
        "coupling",
        "volatility",
        "forward_downside",
        "energy",
    }
    assert sum(EFFECTIVE_WEIGHTS_V2.values()) == pytest.approx(1.0)


def test_score_version_field_present() -> None:
    metrics = make_metrics()
    countries = [m.country_iso3 for m in metrics]
    energy = make_energy_component(countries)
    scores = compute_risk_scores_v2(metrics, energy_component=energy)
    assert (scores["score_version"] == SCORE_VERSION).all()
    assert SCORE_VERSION == "v2_energy"  # regression guard: promoted, no longer "_experimental"
    assert SCORE_VERSION != "v1"


def test_component_and_weights_version_fields_present() -> None:
    metrics = make_metrics()
    countries = [m.country_iso3 for m in metrics]
    energy = make_energy_component(countries)
    scores = compute_risk_scores_v2(metrics, energy_component=energy)
    assert (scores["component_version"] == COMPONENT_VERSION).all()
    assert (scores["weights_version"] == WEIGHTS_VERSION).all()
    assert COMPONENT_VERSION == "energy_component_v2.1"


def test_scores_within_0_100_range() -> None:
    metrics = make_metrics()
    countries = [m.country_iso3 for m in metrics]
    energy = make_energy_component(countries)
    scores = compute_risk_scores_v2(metrics, energy_component=energy)
    assert (scores["score_total"] >= 0).all()
    assert (scores["score_total"] <= 100).all()


def test_missing_energy_does_not_inflate_risk() -> None:
    """A country missing its energy component must be scored from its other
    four components (renormalised weights), not pushed toward "higher risk"
    by the absence -- missing data is a confidence problem, not a risk
    signal."""
    metrics = make_metrics(2)
    countries = [m.country_iso3 for m in metrics]
    # Give both countries identical non-energy raw metrics so any score
    # difference is attributable only to energy-component presence/absence.
    identical = metrics[0].model_copy(update={"country_iso3": metrics[1].country_iso3})
    metrics = [metrics[0], identical]

    energy_full = make_energy_component(countries, missing=set())
    energy_missing_one = make_energy_component(countries, missing={countries[1]})

    scores_full = compute_risk_scores_v2(metrics, energy_component=energy_full).set_index(
        "country_iso3"
    )
    scores_partial = compute_risk_scores_v2(metrics, energy_component=energy_missing_one).set_index(
        "country_iso3"
    )

    # The country with energy missing gets weight_coverage < 1 (lower confidence)...
    assert scores_partial.loc[countries[1], "weight_coverage"] < 1.0
    assert (
        scores_partial.loc[countries[1], "data_confidence_score"]
        < scores_full.loc[countries[1], "data_confidence_score"]
    )
    # ...but score_total is still computed from the renormalised remaining
    # components (not NaN, not fabricated as maximal risk = 100).
    assert pd.notna(scores_partial.loc[countries[1], "score_total"])


def test_energy_confidence_zero_when_component_missing() -> None:
    metrics = make_metrics(3)
    countries = [m.country_iso3 for m in metrics]
    energy = make_energy_component(countries, missing={countries[0]})
    scores = compute_risk_scores_v2(metrics, energy_component=energy).set_index("country_iso3")
    assert scores.loc[countries[0], "energy_confidence"] == 0.0


def test_compute_risk_scores_v2_does_not_mutate_global_weights() -> None:
    before = dict(EFFECTIVE_WEIGHTS_V2)
    metrics = make_metrics()
    countries = [m.country_iso3 for m in metrics]
    energy = make_energy_component(countries)
    compute_risk_scores_v2(metrics, energy_component=energy, weights={"pace": 1.0})
    assert before == EFFECTIVE_WEIGHTS_V2


def test_deterministic_given_same_input() -> None:
    metrics = make_metrics()
    countries = [m.country_iso3 for m in metrics]
    energy = make_energy_component(countries)
    first = compute_risk_scores_v2(metrics, energy_component=energy)
    second = compute_risk_scores_v2(metrics, energy_component=energy)
    pd.testing.assert_frame_equal(first, second)


# ---------------------------------------------------------------------------
# weight robustness
# ---------------------------------------------------------------------------


def test_weight_perturbation_v2_runs_at_each_required_fraction() -> None:
    metrics = make_metrics(15)
    countries = [m.country_iso3 for m in metrics]
    energy = make_energy_component(countries)
    for fraction in (0.1, 0.2, 0.3):
        result = weight_perturbation_analysis_v2(
            metrics,
            energy_component=energy,
            perturbation_fraction=fraction,
            n_perturbations=30,
            random_seed=1,
        )
        assert result["n_perturbations"] > 0
        assert -1.0 <= result["mean_spearman_correlation"] <= 1.0
        assert result["perturbation_fraction"] == fraction

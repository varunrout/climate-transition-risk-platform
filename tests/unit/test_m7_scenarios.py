from __future__ import annotations

import inspect

import pandas as pd

from climate_risk import cli
from climate_risk.research.m7_scenarios import (
    BREAK_CONFIDENCE_THRESHOLD,
    MIN_POST_BREAK_OBSERVATIONS,
    break_year_sensitivity,
    confidence_weight_multiplier,
    forecast_scenario,
    interval_score,
    performance_delta_uncertainty,
    regime_activation,
    run_regime_scenario_backtest,
)
from climate_risk.scenarios import engine
from climate_risk.scoring.risk_score_v2_energy import (
    COMPONENT_VERSION,
    SCORE_VERSION,
    WEIGHTS_VERSION,
)


def _panel() -> pd.DataFrame:
    years = list(range(2000, 2023))
    values = [1.0 * (0.98**i) if i < 12 else 0.78 * (0.92 ** (i - 12)) for i in range(len(years))]
    return pd.DataFrame(
        {
            "country_iso3": ["ZZZ"] * len(years),
            "year": years,
            "carbon_intensity_gdp": values,
        }
    )


def _strong_regime() -> dict[str, object]:
    return {
        "strongest_break_year": 2012,
        "regime_confidence": BREAK_CONFIDENCE_THRESHOLD + 0.1,
        "strongest_break_strength": 2.0,
        "break_index": 12,
    }


def test_regime_activation_requires_minimum_post_break_history() -> None:
    regime = _strong_regime()

    assert regime_activation(regime, history_rows=12 + MIN_POST_BREAK_OBSERVATIONS)
    assert not regime_activation(regime, history_rows=12 + MIN_POST_BREAK_OBSERVATIONS - 1)


def test_current_regime_only_falls_back_when_break_is_weak() -> None:
    history = _panel()[_panel()["year"] <= 2017]
    weak = dict(_strong_regime())
    weak["regime_confidence"] = BREAK_CONFIDENCE_THRESHOLD - 0.01

    fallback = forecast_scenario(
        history,
        method="current_regime_only",
        target_year=2022,
        regime=weak,
        n_simulations=500,
        random_seed=7,
    )
    production = forecast_scenario(
        history,
        method="empirical_bootstrap",
        target_year=2022,
        regime=weak,
        n_simulations=500,
        random_seed=7,
    )

    assert fallback is not None
    assert production is not None
    assert fallback["fallback_used"] is True
    assert fallback["forecast_p50"] == production["forecast_p50"]


def test_seeded_simulation_is_deterministic() -> None:
    history = _panel()[_panel()["year"] <= 2017]
    kwargs = {
        "method": "regime_weighted_bootstrap",
        "target_year": 2022,
        "regime": _strong_regime(),
        "n_simulations": 500,
        "random_seed": 11,
    }

    first = forecast_scenario(history, **kwargs)
    second = forecast_scenario(history, **kwargs)

    assert first == second


def test_confidence_weight_multiplier_is_bounded() -> None:
    assert confidence_weight_multiplier({"regime_confidence": None}) == 1.0
    assert confidence_weight_multiplier({"regime_confidence": 0.0}) == 1.0
    assert confidence_weight_multiplier({"regime_confidence": 99.0}) == 5.0


def test_recency_control_runs_without_regime_evidence() -> None:
    history = _panel()[_panel()["year"] <= 2017]

    result = forecast_scenario(
        history,
        method="recency_weighted_bootstrap",
        target_year=2022,
        regime={},
        n_simulations=500,
        random_seed=42,
    )

    assert result is not None
    assert result["regime_activated"] is False
    assert result["forecast_p05"] <= result["forecast_p50"] <= result["forecast_p95"]


def test_break_year_perturbation_reports_forecast_sensitivity() -> None:
    panel = _panel()

    sensitivity = break_year_sensitivity(
        panel,
        countries=["ZZZ"],
        origins=((2017, 2022),),
        n_simulations=200,
        random_seed=42,
    )

    assert set(sensitivity["offset_years"]) <= {-2, -1, 1, 2}
    assert (sensitivity["abs_p50_delta"] >= 0).all()


def test_interval_score_penalises_misses() -> None:
    covered = interval_score(10.0, 5.0, 15.0, alpha=0.10)
    missed = interval_score(20.0, 5.0, 15.0, alpha=0.10)

    assert covered == 10.0
    assert missed > covered


def test_phase3_backtest_has_no_future_leakage() -> None:
    base = _panel()
    corrupted = base.copy()
    corrupted.loc[corrupted["year"] > 2017, "carbon_intensity_gdp"] = 999_999.0

    clean = run_regime_scenario_backtest(
        base,
        countries=["ZZZ"],
        origins=((2017, 2022),),
        n_simulations=200,
        random_seed=5,
    )
    dirty = run_regime_scenario_backtest(
        corrupted,
        countries=["ZZZ"],
        origins=((2017, 2022),),
        n_simulations=200,
        random_seed=5,
    )

    comparable_cols = [
        "model_variant",
        "forecast_p50",
        "forecast_p05",
        "forecast_p95",
        "regime_break_year",
        "regime_confidence",
    ]
    pd.testing.assert_frame_equal(clean[comparable_cols], dirty[comparable_cols])


def test_production_scenario_engine_is_unchanged() -> None:
    assert "recency_weighted" not in inspect.getsource(engine.bootstrap_monte_carlo)
    assert "regime_weighted" not in inspect.getsource(engine.run_country_scenario)


def test_score_v2_contract_remains_unchanged_by_phase3() -> None:
    assert SCORE_VERSION == "v2_energy"
    assert COMPONENT_VERSION == "energy_component_v2.1"
    assert WEIGHTS_VERSION == "v2_weights_v1"


def test_production_run_does_not_call_m7_phase3() -> None:
    assert "m7_phase3" not in inspect.getsource(cli.run)
    assert "phase3" not in inspect.getsource(cli.run).lower()


def test_performance_delta_uncertainty_is_seeded() -> None:
    results = pd.DataFrame(
        {
            "country_iso3": ["A", "A", "B", "B"],
            "origin_year": [2010, 2010, 2010, 2010],
            "target_year": [2015, 2015, 2015, 2015],
            "model_variant": [
                "empirical_bootstrap",
                "recency_weighted_bootstrap",
                "empirical_bootstrap",
                "recency_weighted_bootstrap",
            ],
            "absolute_error": [2.0, 1.0, 4.0, 5.0],
        }
    )

    first = performance_delta_uncertainty(results, n_iterations=50, random_seed=9)
    second = performance_delta_uncertainty(results, n_iterations=50, random_seed=9)

    pd.testing.assert_frame_equal(first, second)
    assert first.iloc[0]["observed_delta_mae"] == 0.0

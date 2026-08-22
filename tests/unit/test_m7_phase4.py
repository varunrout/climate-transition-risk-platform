from __future__ import annotations

import inspect

import numpy as np
import pandas as pd

from climate_risk.research import m7_phase4
from climate_risk.scenarios import engine as production_scenarios
from climate_risk.scoring.risk_score_v2_energy import SCORE_VERSION


def _panel() -> pd.DataFrame:
    rows = []
    for country in ("AAA", "BBB", "CCC"):
        base = {"AAA": 1.0, "BBB": 1.2, "CCC": 0.8}[country]
        for year in range(2000, 2024):
            rows.append(
                {
                    "country_iso3": country,
                    "year": year,
                    "carbon_intensity_gdp": base * np.exp(-0.025 * (year - 2000)),
                }
            )
    return pd.DataFrame(rows)


def test_recency_weights_are_deterministic_and_prioritise_recent_years() -> None:
    years = pd.Series([2000, 2001, 2002, 2003, 2004])

    first = m7_phase4.recency_weights(years, half_life_years=5.0)
    second = m7_phase4.recency_weights(years, half_life_years=5.0)

    assert np.array_equal(first, second)
    assert first[-1] > first[0]
    assert first[-1] == 1.0


def test_nested_parameter_selection_uses_only_prior_completed_origins() -> None:
    selected = m7_phase4.select_nested_recency_schemes(
        _panel(),
        countries=["AAA", "BBB", "CCC"],
        origins=((2010, 2015), (2012, 2017), (2017, 2022)),
        n_simulations=100,
        random_seed=7,
    )

    assert selected[2010].scheme == "canonical_recency"
    assert selected[2012].scheme == "canonical_recency"
    assert selected[2017].scheme in {"weak_recency", "canonical_recency", "strong_recency"}


def test_interval_calibration_uses_only_prior_origins_and_is_bounded() -> None:
    panel = _panel()
    origins = ((2010, 2015), (2012, 2017), (2017, 2022))
    selected = {origin: m7_phase4.RECENCY_CANDIDATES[1] for origin, _target in origins}

    scales = m7_phase4.prior_origin_interval_scales(
        panel,
        countries=["AAA", "BBB", "CCC"],
        origins=origins,
        selected_by_origin=selected,
        n_simulations=100,
        random_seed=7,
    )

    assert scales[2010] == 1.0
    assert scales[2012] == 1.0
    assert 1.0 <= scales[2017] <= m7_phase4.MAX_INTERVAL_SCALE


def test_apply_interval_scale_preserves_point_forecast_and_expands_interval() -> None:
    forecast = {
        "forecast_p05": 8.0,
        "forecast_p50": 10.0,
        "forecast_p95": 13.0,
        "model_variant": "recency_weighted_bootstrap",
    }

    scaled = m7_phase4.apply_interval_scale(forecast, scale=1.5)

    assert scaled["forecast_p50"] == 10.0
    assert scaled["forecast_p05"] == 7.0
    assert scaled["forecast_p95"] == 14.5
    assert scaled["calibration_scale"] == 1.5


def test_coverage_and_interval_width_metrics() -> None:
    rows = pd.DataFrame(
        {
            "actual": [10.0, 12.0],
            "forecast_p05": [9.0, 13.0],
            "forecast_p95": [11.0, 14.0],
            "covered_90": [True, False],
            "interval_width_90": [2.0, 1.0],
        }
    )

    assert m7_phase4.coverage_rate(rows) == 0.5
    assert m7_phase4.mean_interval_width(rows) == 1.5


def test_phase4_fallback_behaviour_for_insufficient_history() -> None:
    short = pd.DataFrame(
        {
            "country_iso3": ["AAA"] * 4,
            "year": [2010, 2011, 2012, 2013],
            "carbon_intensity_gdp": [1.0, 0.9, 0.85, 0.8],
        }
    )

    results = m7_phase4.run_phase4_backtest(
        short,
        countries=["AAA"],
        origins=((2013, 2018),),
        n_simulations=50,
        random_seed=7,
    )

    assert results.empty


def test_phase4_backtest_is_seeded_and_deterministic() -> None:
    first = m7_phase4.run_phase4_backtest(
        _panel(), countries=["AAA"], origins=((2017, 2022),), n_simulations=100, random_seed=7
    )
    second = m7_phase4.run_phase4_backtest(
        _panel(), countries=["AAA"], origins=((2017, 2022),), n_simulations=100, random_seed=7
    )

    pd.testing.assert_frame_equal(first, second)


def test_phase4_decision_preserves_frozen_phase3_result() -> None:
    artifacts = m7_phase4.run_phase4_hardening(
        _panel(), countries=["AAA", "BBB", "CCC"], n_simulations=100, random_seed=7
    )

    decision = artifacts["decision"]

    assert decision["phase3_decision_frozen"] == "RECENCY_WEIGHTING_ONLY"
    assert decision["structural_break_diagnostic_status"] == "retained_as_research_diagnostics"
    assert decision["risk_score_v2_energy_changed"] is False
    assert decision["azure_changed"] is False


def test_production_score_v2_remains_unchanged() -> None:
    assert SCORE_VERSION == "v2_energy"


def test_structural_break_diagnostics_do_not_enter_production_scenario_engine() -> None:
    source = inspect.getsource(production_scenarios)

    assert "detect_break" not in source
    assert "m7_phase4" not in source


def test_regime_detector_does_not_influence_phase4_candidates() -> None:
    source = inspect.getsource(m7_phase4)

    assert "detect_break" not in source
    assert "regime" not in m7_phase4.preregistered_phase4_rules()["primary_candidate"]

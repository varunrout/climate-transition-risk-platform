from __future__ import annotations

import inspect

import pandas as pd

from climate_risk import cli
from climate_risk.research.m7_regimes import (
    BREAK_VERSION,
    MIN_SEGMENT_LENGTH,
    MIN_TOTAL_OBSERVATIONS,
    bootstrap_break_stability,
    build_candidate_series_panel,
    candidate_series_catalog,
    compare_methods,
    detect_break,
    detect_breaks_by_origin,
    method_agreement,
    run_phase2_diagnostics,
    temporal_regime_stability,
)
from climate_risk.scoring.risk_score_v2_energy import (
    COMPONENT_VERSION,
    SCORE_VERSION,
    WEIGHTS_VERSION,
)


def _series(values: list[float], *, start_year: int = 2000) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_iso3": ["ZZ"] * len(values),
            "year": list(range(start_year, start_year + len(values))),
            "value": values,
        }
    )


def _obvious_break() -> pd.DataFrame:
    years = list(range(2000, 2020))
    values = [100 - (i * 0.2) if i < 10 else 98 - ((i - 10) * 3.0) for i in range(len(years))]
    return _series(values)


def test_insufficient_history_returns_insufficient_evidence() -> None:
    result = detect_break(
        _series([1.0] * (MIN_TOTAL_OBSERVATIONS - 1)),
        country_iso3="ZZ",
        series_name="x",
        directionality="higher_is_higher_risk",
        method="segmented_regression",
        minimum_economic_slope_delta=0.5,
    )

    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.current_regime_label == "INSUFFICIENT_EVIDENCE"


def test_minimum_segment_length_blocks_too_short_segments() -> None:
    assert MIN_SEGMENT_LENGTH == 5
    result = detect_break(
        _series([10, 9, 8, 7, 6, 1, 0, -1, -2]),
        country_iso3="ZZ",
        series_name="x",
        directionality="higher_is_higher_risk",
        method="threshold_baseline",
        minimum_economic_slope_delta=0.5,
    )

    assert result.status == "INSUFFICIENT_EVIDENCE"


def test_no_break_series_is_not_over_labelled() -> None:
    result = detect_break(
        _series([100 - i for i in range(20)]),
        country_iso3="ZZ",
        series_name="x",
        directionality="higher_is_higher_risk",
        method="segmented_regression",
        minimum_economic_slope_delta=0.5,
    )

    assert result.break_count == 0
    assert result.status == "NO_CREDIBLE_BREAK"
    assert result.current_regime_label == "STEADY_IMPROVEMENT"


def test_obvious_synthetic_break_is_detected_deterministically() -> None:
    first = detect_break(
        _obvious_break(),
        country_iso3="ZZ",
        series_name="x",
        directionality="higher_is_higher_risk",
        method="segmented_regression",
        minimum_economic_slope_delta=0.5,
    )
    second = detect_break(
        _obvious_break(),
        country_iso3="ZZ",
        series_name="x",
        directionality="higher_is_higher_risk",
        method="segmented_regression",
        minimum_economic_slope_delta=0.5,
    )

    assert first == second
    assert first.break_count == 1
    assert first.strongest_break_year == 2010
    assert first.slope_delta is not None and first.slope_delta < 0
    assert first.current_regime_label == "ACCELERATING_TRANSITION"
    assert first.break_version == BREAK_VERSION


def test_slope_direction_respects_series_directionality() -> None:
    improving_low_carbon = detect_break(
        _series([10 + i for i in range(20)]),
        country_iso3="ZZ",
        series_name="low_carbon_share_elec",
        directionality="higher_is_lower_risk",
        method="segmented_regression",
        minimum_economic_slope_delta=0.5,
    )
    worsening_fossil = detect_break(
        _series([10 + i for i in range(20)]),
        country_iso3="ZZ",
        series_name="fossil_share_elec",
        directionality="higher_is_higher_risk",
        method="segmented_regression",
        minimum_economic_slope_delta=0.5,
    )

    assert improving_low_carbon.regime_direction == "IMPROVING"
    assert worsening_fossil.regime_direction == "DETERIORATING"


def test_break_strength_and_confidence_are_defined_for_detected_break() -> None:
    result = detect_break(
        _obvious_break(),
        country_iso3="ZZ",
        series_name="x",
        directionality="higher_is_higher_risk",
        method="rolling_slope_change",
        minimum_economic_slope_delta=0.5,
    )

    assert result.break_count == 1
    assert result.strongest_break_strength is not None
    assert result.strongest_break_strength > 1
    assert result.regime_confidence is not None
    assert 0 <= result.regime_confidence <= 1


def test_no_future_leakage_in_as_of_detection() -> None:
    clean = _series([100 - i for i in range(16)])
    corrupted_future = pd.concat(
        [
            clean,
            _series([1_000_000, -1_000_000, 1_000_000, -1_000_000], start_year=2016),
        ],
        ignore_index=True,
    )

    clean_result = detect_break(
        clean,
        country_iso3="ZZ",
        series_name="x",
        directionality="higher_is_higher_risk",
        method="segmented_regression",
        minimum_economic_slope_delta=0.5,
        as_of_year=2015,
    )
    corrupted_result = detect_break(
        corrupted_future,
        country_iso3="ZZ",
        series_name="x",
        directionality="higher_is_higher_risk",
        method="segmented_regression",
        minimum_economic_slope_delta=0.5,
        as_of_year=2015,
    )

    assert clean_result == corrupted_result


def test_method_agreement_logic_marks_robust_when_break_years_align() -> None:
    rows = []
    for method in [
        "threshold_baseline",
        "rolling_slope_change",
        "cusum_stability",
        "segmented_regression",
    ]:
        rows.append(
            {
                "country_iso3": "ZZ",
                "series_name": "x",
                "break_method": method,
                "status": "BREAK_DETECTED",
                "break_count": 1,
                "strongest_break_year": 2010,
                "regime_direction": "IMPROVING",
                "regime_confidence": 0.8,
            }
        )

    agreement = method_agreement(pd.DataFrame(rows)).iloc[0]

    assert agreement["break_detection_agreement"] == 1.0
    assert agreement["break_year_agreement_within_1yr"] == 1.0
    assert agreement["method_sensitivity"] == "ROBUST_ACROSS_METHODS"


def test_compare_methods_counts_detected_breaks() -> None:
    frame = pd.DataFrame(
        [
            {
                "country_iso3": "AA",
                "series_name": "x",
                "break_method": "segmented_regression",
                "status": "BREAK_DETECTED",
                "break_count": 1,
                "strongest_break_strength": 2.0,
                "regime_confidence": 0.7,
                "current_regime_label": "ACCELERATING_TRANSITION",
            },
            {
                "country_iso3": "BB",
                "series_name": "x",
                "break_method": "segmented_regression",
                "status": "NO_CREDIBLE_BREAK",
                "break_count": 0,
                "strongest_break_strength": None,
                "regime_confidence": 0.0,
                "current_regime_label": "STEADY_IMPROVEMENT",
            },
        ]
    )

    comparison = compare_methods(frame).iloc[0]

    assert comparison["eligible_country_count"] == 2
    assert comparison["detected_break_count"] == 1
    assert comparison["accelerating_count"] == 1


def test_bootstrap_stability_is_deterministic_with_seed() -> None:
    kwargs = {
        "country_iso3": "ZZ",
        "series_name": "x",
        "directionality": "higher_is_higher_risk",
        "method": "segmented_regression",
        "minimum_economic_slope_delta": 0.5,
        "n_iterations": 20,
        "random_seed": 7,
    }

    first = bootstrap_break_stability(_obvious_break(), **kwargs)
    second = bootstrap_break_stability(_obvious_break(), **kwargs)

    assert first == second
    assert first["n_iterations"] == 20


def test_candidate_series_panel_contains_pre_registered_variables() -> None:
    transition = pd.DataFrame(
        {
            "country_iso3": ["ZZ"] * 14,
            "year": list(range(2000, 2014)),
            "carbon_intensity_gdp": [1.0 - i * 0.01 for i in range(14)],
            "co2_mt": [100.0 - i for i in range(14)],
            "real_gdp": [1000.0 + i * 10 for i in range(14)],
        }
    )
    energy = pd.DataFrame(
        {
            "country_iso3": ["ZZ"] * 14,
            "year": list(range(2000, 2014)),
            "low_carbon_share_elec": [20.0 + i for i in range(14)],
            "fossil_share_elec": [80.0 - i for i in range(14)],
            "coal_share_elec": [50.0 - i * 0.5 for i in range(14)],
        }
    )

    panel = build_candidate_series_panel(transition, energy)
    names = set(panel["series_name"])
    catalog_names = {spec.series_name for spec in candidate_series_catalog()}

    assert catalog_names <= names


def test_score_v2_contract_remains_unchanged() -> None:
    assert SCORE_VERSION == "v2_energy"
    assert COMPONENT_VERSION == "energy_component_v2.1"
    assert WEIGHTS_VERSION == "v2_weights_v1"


def test_production_run_does_not_call_m7_research() -> None:
    run_source = inspect.getsource(cli.run)

    assert "m7" not in run_source.lower()
    assert "research/m7" not in run_source


def test_historical_origin_recomputation_ignores_future_values() -> None:
    base = _obvious_break()
    base["series_name"] = "carbon_intensity_gdp"
    corrupted = base.copy()
    corrupted.loc[corrupted["year"] > 2012, "value"] = 99999.0

    clean_results = detect_breaks_by_origin(base, origins=(2012,))
    corrupted_results = detect_breaks_by_origin(corrupted, origins=(2012,))

    pd.testing.assert_frame_equal(clean_results, corrupted_results)


def test_temporal_regime_stability_counts_label_switches() -> None:
    origin_results = pd.DataFrame(
        [
            {
                "origin_year": 2010,
                "country_iso3": "ZZ",
                "series_name": "x",
                "break_method": "segmented_regression",
                "status": "NO_CREDIBLE_BREAK",
                "break_count": 0,
                "strongest_break_year": None,
                "current_regime_label": "STEADY_IMPROVEMENT",
            },
            {
                "origin_year": 2012,
                "country_iso3": "ZZ",
                "series_name": "x",
                "break_method": "segmented_regression",
                "status": "BREAK_DETECTED",
                "break_count": 1,
                "strongest_break_year": 2011,
                "current_regime_label": "DETERIORATING_TRANSITION",
            },
        ]
    )

    stability = temporal_regime_stability(origin_results).iloc[0]

    assert stability["eligible_origins"] == 2
    assert stability["break_detection_rate"] == 0.5
    assert stability["label_switch_count"] == 1
    assert stability["modal_break_year"] == 2011


def test_phase2_diagnostics_are_research_only_contract() -> None:
    transition = pd.DataFrame(
        {
            "country_iso3": ["ZZ"] * 18,
            "year": list(range(2000, 2018)),
            "carbon_intensity_gdp": [1.0 - i * 0.01 for i in range(18)],
            "co2_mt": [100.0 - i for i in range(18)],
            "real_gdp": [1000.0 + i * 10 for i in range(18)],
        }
    )
    energy = pd.DataFrame(
        {
            "country_iso3": ["ZZ"] * 18,
            "year": list(range(2000, 2018)),
            "low_carbon_share_elec": [20.0 + i for i in range(18)],
            "fossil_share_elec": [80.0 - i for i in range(18)],
            "coal_share_elec": [50.0 - i * 0.5 for i in range(18)],
        }
    )

    artifacts = run_phase2_diagnostics(transition, energy, origins=(2012, 2014))

    assert set(artifacts) == {
        "origin_regime_results",
        "origin_method_agreement",
        "temporal_stability",
        "decision",
    }
    decision = artifacts["decision"]
    assert isinstance(decision, dict)
    assert decision["decision"] == "PHASE3_JUSTIFIED"
    assert decision["decision_is_not_production_promotion"] is True

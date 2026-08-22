from __future__ import annotations

from pathlib import Path

import pandas as pd

from climate_risk.bi.publish import (
    ACTIVE_SCORE_VERSION,
    BI_PREFIX,
    build_backtest_metrics,
    build_country_overview,
    build_country_timeseries,
    build_energy_indicators,
    build_regime_diagnostics,
    build_risk_components,
    build_run_metadata,
    build_scenario_quantiles,
    write_bi_artifacts,
)
from climate_risk.storage import LakeStorage, LocalStorageBackend


def _dim_country() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_iso3": ["AAA", "BBB"],
            "country_name": ["Alpha", "Beta"],
            "g20_flag": [True, True],
            "region": ["R1", "R2"],
            "income_group": ["High income", "Upper middle income"],
            "valid_from": ["2000-01-01", "2000-01-01"],
            "valid_to": [None, None],
        }
    )


def _transition() -> pd.DataFrame:
    rows = []
    for country, base in (("AAA", 1.0), ("BBB", 1.2)):
        for year in range(2015, 2025):
            rows.append(
                {
                    "country_iso3": country,
                    "year": year,
                    "co2_mt": base * 100,
                    "real_gdp": base * 1000,
                    "secondary_gdp_owid": base * 900,
                    "population": base * 10,
                    "carbon_intensity_gdp": base * (0.97 ** (year - 2015)),
                    "co2_per_capita": base * 5,
                    "energy_intensity_gdp": base * 2,
                    "primary_energy_twh": base * 30,
                    "is_core_complete": True,
                    "missing_feature_count": 0,
                    "imputation_mask": "",
                    "snapshot_set_id": "transition-snap",
                }
            )
    return pd.DataFrame(rows)


def _energy() -> pd.DataFrame:
    rows = []
    for country in ("AAA", "BBB"):
        for year in range(2018, 2025):
            rows.append(
                {
                    "country_iso3": country,
                    "year": year,
                    "coal_share_elec": 20.0,
                    "gas_share_elec": 30.0,
                    "oil_share_elec": 5.0,
                    "fossil_share_elec": 55.0,
                    "renewables_share_elec": 30.0,
                    "low_carbon_share_elec": 45.0,
                    "nuclear_share_elec": 15.0,
                    "solar_share_elec": 7.0,
                    "wind_share_elec": 8.0,
                    "hydro_share_elec": 10.0,
                    "biofuel_share_elec": 5.0,
                    "snapshot_set_id": "energy-snap",
                }
            )
    return pd.DataFrame(rows)


def _risk_v1() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_iso3": ["AAA", "BBB"],
            "score_total": [40.0, 70.0],
            "score_pace": [30.0, 80.0],
            "score_coupling": [40.0, 75.0],
            "score_volatility": [50.0, 60.0],
            "score_forward_downside": [35.0, 85.0],
            "data_confidence_score": [80.0, 78.0],
            "weight_coverage": [0.8, 0.8],
            "rank": [2, 1],
            "rank_band": ["moderate", "elevated"],
        }
    )


def _risk_v2() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_iso3": ["AAA", "BBB"],
            "score_version": [ACTIVE_SCORE_VERSION, ACTIVE_SCORE_VERSION],
            "component_version": ["energy_component_v2.1", "energy_component_v2.1"],
            "weights_version": ["v2_weights_v1", "v2_weights_v1"],
            "score_total": [35.0, 75.0],
            "score_pace": [30.0, 80.0],
            "score_coupling": [40.0, 75.0],
            "score_volatility": [50.0, 60.0],
            "score_forward_downside": [35.0, 85.0],
            "score_energy": [20.0, 90.0],
            "energy_confidence": [100.0, 95.0],
            "data_confidence_score": [98.0, 92.0],
            "weight_coverage": [1.0, 1.0],
            "rank": [2, 1],
            "rank_band": ["moderate", "elevated"],
        }
    )


def _energy_features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_iso3": ["AAA", "BBB"],
            "latest_year": [2024, 2024],
            "trailing_window_years": [5, 5],
            "sample_size": [7, 7],
            "coal_share_elec": [20.0, 20.0],
            "fossil_share_elec": [55.0, 55.0],
            "renewables_share_elec": [30.0, 30.0],
            "low_carbon_share_elec": [45.0, 45.0],
            "transition_velocity": [1.1, -0.2],
            "stalled_transition_residual_pp": [0.0, 2.0],
            "coal_trend_pp_per_year": [-0.5, 0.2],
            "clean_power_momentum_pp_per_year": [1.0, -0.1],
            "renewable_buildout_rate_pp_per_year": [0.8, 0.0],
            "fossil_persistence_mean_pct": [55.0, 55.0],
            "coal_share_elec_percentile": [50.0, 50.0],
            "low_carbon_share_elec_percentile": [50.0, 50.0],
        }
    )


def test_country_overview_preserves_active_score_and_v1_comparison() -> None:
    overview = build_country_overview(
        _dim_country(),
        _transition(),
        _risk_v1(),
        _risk_v2(),
        _energy_features(),
        {"run_id": "run-1", "completed_at": "2026-01-01T00:00:00Z"},
        {"publish_status": "PUBLISHED"},
    )

    assert overview["country_iso3"].is_unique
    assert set(overview["active_score_version"]) == {ACTIVE_SCORE_VERSION}
    assert set(overview["is_active_score"]) == {True}
    assert "score_total_v1" in overview.columns
    assert "score_delta_v2_minus_v1" in overview.columns
    assert set(overview["publish_status"]) == {"PUBLISHED"}


def test_risk_components_are_long_form_and_preserve_v1_v2() -> None:
    components = build_risk_components(_risk_v1(), _risk_v2())

    assert {ACTIVE_SCORE_VERSION, "v1"} == set(components["score_version"])
    assert {"pace", "coupling", "volatility", "forward_downside", "energy"}.issuperset(
        set(components["component_name"])
    )
    assert not components.duplicated(["country_iso3", "score_version", "component_name"]).any()
    assert (
        components.loc[components["component_name"] == "energy", "score_version"]
        .eq(ACTIVE_SCORE_VERSION)
        .all()
    )


def test_country_timeseries_has_unique_country_year_keys() -> None:
    timeseries = build_country_timeseries(_dim_country(), _transition(), _energy())

    assert not timeseries.duplicated(["country_iso3", "year"]).any()
    assert len(timeseries) == len(_transition())
    assert "low_carbon_share_elec" in timeseries.columns


def test_scenario_quantiles_are_ordered_and_labelled_production() -> None:
    scenarios = build_scenario_quantiles(
        _dim_country(), _transition(), countries=["AAA", "BBB"], target_year=2030, n_simulations=200
    )

    assert set(scenarios["scenario_status"]) == {"production"}
    assert set(scenarios["experimental_variant"]) == {False}
    assert (scenarios["forecast_p05"] <= scenarios["forecast_p50"]).all()
    assert (scenarios["forecast_p50"] <= scenarios["forecast_p95"]).all()
    assert scenarios["scenario_method"].eq("empirical_bootstrap_v1").all()


def test_backtest_metrics_surface_calibration_gap() -> None:
    country_origin = pd.DataFrame(
        {
            "country_iso3": ["AAA"],
            "origin_year": [2015],
            "target_year": [2020],
            "horizon_years": [5],
            "model_variant": ["empirical_bootstrap"],
            "actual": [0.8],
            "forecast_p50": [0.85],
            "forecast_p05": [0.75],
            "forecast_p95": [0.95],
            "absolute_error": [0.05],
            "covered_90": [True],
            "interval_width_90": [0.20],
        }
    )
    summary = pd.DataFrame(
        {
            "model_variant": ["empirical_bootstrap"],
            "n_splits": [1],
            "mae": [0.05],
            "rmse": [0.05],
            "median_ae": [0.05],
            "coverage_90": [0.76],
            "mean_interval_width_90": [0.20],
        }
    )

    metrics = build_backtest_metrics(country_origin, summary)

    assert {"country_origin", "summary"} == set(metrics["metric_grain"])
    assert "calibration_gap_90" in metrics.columns
    assert metrics["production_model_variant"].eq("empirical_bootstrap").all()


def test_energy_indicators_keep_raw_indicators_separate_from_latest_features() -> None:
    energy = build_energy_indicators(_dim_country(), _energy(), _energy_features())

    assert "low_carbon_share_elec" in energy.columns
    assert "latest_feature_transition_velocity" in energy.columns
    assert not energy.duplicated(["country_iso3", "year"]).any()


def test_regime_diagnostics_are_clearly_non_production() -> None:
    profiles = pd.DataFrame(
        {
            "country_iso3": ["AAA"],
            "series_name": ["carbon_intensity_gdp"],
            "as_of_year": [2024],
            "latest_regime_start_year": [2018],
            "years_in_current_regime": [7],
            "break_count": [1],
            "strongest_break_year": [2018],
            "strongest_break_strength": [2.0],
            "pre_break_slope": [-0.01],
            "post_break_slope": [-0.03],
            "slope_delta": [-0.02],
            "regime_direction": ["IMPROVING"],
            "regime_confidence": [0.8],
            "current_regime_label": ["ACCELERATING_TRANSITION"],
            "break_method": ["segmented_regression"],
            "break_version": ["m7_structural_break_v0.1"],
        }
    )

    diagnostics = build_regime_diagnostics(_dim_country(), profiles)

    assert diagnostics["used_in_production_score"].eq(False).all()
    assert diagnostics["used_in_production_scenario"].eq(False).all()
    assert diagnostics["diagnostic_status"].str.contains("diagnostic_only").all()


def test_run_metadata_contains_provenance_fields() -> None:
    metadata = build_run_metadata(
        {"run_id": "run-1", "completed_at": "done", "snapshot_set_id": "transition-snap"},
        {
            "git_sha": "abc",
            "config_hash": "cfg",
            "publish_status": "PUBLISHED",
            "source_snapshot_ids": {"owid_energy": "energy-snap"},
        },
        "transition/path.parquet",
        "energy/path.parquet",
    )

    assert metadata.loc[0, "run_id"] == "run-1"
    assert metadata.loc[0, "git_sha"] == "abc"
    assert metadata.loc[0, "owid_energy_snapshot_id"] == "energy-snap"
    assert metadata.loc[0, "active_score_version"] == ACTIVE_SCORE_VERSION


def test_write_bi_artifacts_is_deterministic(tmp_path: Path) -> None:
    from climate_risk.bi.publish import BiArtifacts

    lake = LakeStorage(
        raw=LocalStorageBackend(tmp_path / "raw"),
        bronze=LocalStorageBackend(tmp_path / "bronze"),
        silver=LocalStorageBackend(tmp_path / "silver"),
        gold=LocalStorageBackend(tmp_path / "gold"),
    )
    artifacts = BiArtifacts(
        country_overview=pd.DataFrame({"country_iso3": ["AAA"]}),
        country_timeseries=pd.DataFrame({"country_iso3": ["AAA"], "year": [2024]}),
        risk_components=pd.DataFrame({"country_iso3": ["AAA"], "component_name": ["pace"]}),
        scenario_quantiles=pd.DataFrame({"country_iso3": ["AAA"], "forecast_p50": [1.0]}),
        backtest_metrics=pd.DataFrame({"model_variant": ["empirical_bootstrap"]}),
        energy_indicators=pd.DataFrame({"country_iso3": ["AAA"], "year": [2024]}),
        regime_diagnostics=pd.DataFrame({"country_iso3": ["AAA"]}),
        run_metadata=pd.DataFrame({"run_id": ["run-1"]}),
    )

    write_bi_artifacts(lake, artifacts)

    for name in artifacts.as_dict():
        assert lake.gold.exists(f"{BI_PREFIX}/{name}.parquet")

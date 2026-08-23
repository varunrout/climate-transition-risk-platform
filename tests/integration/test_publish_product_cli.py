"""End-to-end coverage for the downstream product-publication stage.

`climate-risk publish-product` (and the `run()` chain that calls it after
`publish()`) builds gold/bi + gold/web from an already-published core
release and re-verifies the result against real storage reads. This
exercises the real CLI functions against a from-scratch fake local lake --
not a Power BI/web-layer unit test (that's tests/unit/test_bi_publish.py
and tests/unit/test_web_publish.py) -- to prove the two layers actually
compose end to end, matching what runs in production (ADR 0019).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import typer

from climate_risk.storage import LakeStorage, backend_for_uri, read_text, write_json, write_parquet


def _make_lake(root: Path) -> LakeStorage:
    lake = LakeStorage(
        raw=backend_for_uri(str(root / "raw")),
        bronze=backend_for_uri(str(root / "bronze")),
        silver=backend_for_uri(str(root / "silver")),
        gold=backend_for_uri(str(root / "gold")),
    )
    lake.ensure_zones()
    return lake


def _write_accepted_manifest(lake: LakeStorage, *, source_name: str) -> None:
    write_json(
        lake.raw,
        f"source={source_name}/ingest_date=2026-08-23/run_id=test-run/manifest.json",
        {
            "status": "ACCEPTED",
            "sha256": f"deadbeef{source_name}",
            "retrieved_at_utc": "2026-08-23T00:00:00+00:00",
        },
    )


def _write_full_core_release(lake: LakeStorage) -> None:
    for source_name in ("owid_co2", "world_bank_wdi", "owid_energy"):
        _write_accepted_manifest(lake, source_name=source_name)

    dim_country = pd.DataFrame(
        {
            "country_iso3": ["USA", "CHN"],
            "country_name": ["United States", "China"],
            "g20_flag": [True, True],
            "region": ["North America", "East Asia and Pacific"],
            "income_group": ["High income", "Upper middle income"],
            "valid_from": ["2000-01-01", "2000-01-01"],
            "valid_to": [None, None],
        }
    )
    write_parquet(lake.silver, "dim_country/data.parquet", dim_country)

    transition_rows = [
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
        for country, base in (("USA", 1.0), ("CHN", 1.2))
        for year in range(2015, 2025)
    ]
    write_parquet(
        lake.silver,
        "fact_country_year_transition/snapshot_set_id=abc123/data.parquet",
        pd.DataFrame(transition_rows),
    )

    energy_rows = [
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
        for country in ("USA", "CHN")
        for year in range(2018, 2025)
    ]
    write_parquet(
        lake.silver,
        "fact_country_year_energy/snapshot_set_id=xyz789/data.parquet",
        pd.DataFrame(energy_rows),
    )

    write_parquet(
        lake.gold,
        "backtest_summary.parquet",
        pd.DataFrame(
            {
                "model_variant": ["empirical_bootstrap"],
                "n_splits": [1],
                "mae": [0.05],
                "rmse": [0.05],
                "median_ae": [0.05],
                "coverage_90": [0.76],
                "mean_interval_width_90": [0.20],
            }
        ),
    )
    write_parquet(
        lake.gold,
        "backtest_country_origin.parquet",
        pd.DataFrame(
            {
                "country_iso3": ["USA"],
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
        ),
    )
    write_parquet(
        lake.gold,
        "country_transition_risk.parquet",
        pd.DataFrame(
            {
                "country_iso3": ["USA", "CHN"],
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
        ),
    )
    from climate_risk.scoring.risk_score_v2_energy import SCORE_VERSION as V2_SCORE_VERSION

    write_parquet(
        lake.gold,
        "country_transition_risk_v2.parquet",
        pd.DataFrame(
            {
                "country_iso3": ["USA", "CHN"],
                "score_version": [V2_SCORE_VERSION, V2_SCORE_VERSION],
                "component_version": ["energy_component_v2.1", "energy_component_v2.1"],
                "weights_version": ["v2_weights_v1", "v2_weights_v1"],
                "score_total": [38.0, 68.0],
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
        ),
    )
    write_parquet(
        lake.gold,
        "energy_transition_features.parquet",
        pd.DataFrame(
            {
                "country_iso3": ["USA", "CHN"],
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
        ),
    )


@pytest.fixture
def published_lake_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real published core release (via the actual `publish()` CLI function)
    against a from-scratch fake local lake, with `CLIMATE_RISK_LAKE_ROOT`
    pointed at it -- so `prepare_lake_from_env()` inside `publish_product`
    resolves the same lake."""
    from climate_risk.cli import publish

    root = tmp_path / "lake"
    lake = _make_lake(root)
    _write_full_core_release(lake)

    monkeypatch.setenv("CLIMATE_RISK_LAKE_ROOT", str(root))
    for zone in ("RAW", "BRONZE", "SILVER", "GOLD"):
        monkeypatch.delenv(f"CLIMATE_RISK_{zone}_ROOT", raising=False)

    published_run_id = publish()
    assert lake.gold.exists("latest_successful_run.json")
    return root, published_run_id  # type: ignore[return-value]


def test_publish_product_builds_verified_gold_bi_and_gold_web(
    published_lake_env: tuple[Path, str],
) -> None:
    from climate_risk.cli import publish_product

    root, published_run_id = published_lake_env
    lake = _make_lake(root)

    publish_product(scenario_target_year=2030)

    for table in (
        "country_overview",
        "country_timeseries",
        "risk_components",
        "scenario_quantiles",
        "backtest_metrics",
        "energy_indicators",
        "regime_diagnostics",
        "run_metadata",
    ):
        assert lake.gold.exists(f"bi/{table}.parquet")

    for stem in (
        "countries",
        "country-overview",
        "country-timeseries",
        "risk-components",
        "scenario-quantiles",
        "backtest-metrics",
        "energy-indicators",
        "regime-diagnostics",
        "run-metadata",
    ):
        assert lake.gold.exists(f"web/{stem}.json")
    assert lake.gold.exists("web/manifest.json")

    manifest = json.loads(read_text(lake.gold, "web/manifest.json"))
    assert manifest["source_run_id"] == published_run_id
    from climate_risk.bi.publish import PRODUCTION_SCENARIO_METHOD
    from climate_risk.scoring.risk_score_v2_energy import SCORE_VERSION as V2_SCORE_VERSION

    assert manifest["active_score_version"] == V2_SCORE_VERSION
    assert manifest["active_scenario_method"] == PRODUCTION_SCENARIO_METHOD

    # gold/bi run_metadata carries the same run_id as the core pointer --
    # i.e. gold/bi, gold/web, and the core release all correspond to the
    # same published analytical run.
    run_metadata = pd.read_parquet((root / "gold" / "bi" / "run_metadata.parquet").as_posix())
    assert run_metadata.loc[0, "run_id"] == published_run_id


def test_publish_product_requires_a_prior_core_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from climate_risk.cli import publish_product

    root = tmp_path / "lake"
    lake = _make_lake(root)
    monkeypatch.setenv("CLIMATE_RISK_LAKE_ROOT", str(root))
    for zone in ("RAW", "BRONZE", "SILVER", "GOLD"):
        monkeypatch.delenv(f"CLIMATE_RISK_{zone}_ROOT", raising=False)

    with pytest.raises(typer.Exit) as exc_info:
        publish_product(scenario_target_year=2030)
    assert exc_info.value.exit_code == 1
    assert not lake.gold.exists("web/manifest.json")


def test_publish_product_failure_never_touches_core_pointer(
    published_lake_env: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """If gold/bi or gold/web building blows up partway, the core release
    pointer (`latest_successful_run.json`) must be left completely
    untouched -- product publication is purely additive/downstream."""
    from climate_risk.cli import publish_product

    root, published_run_id = published_lake_env
    lake = _make_lake(root)
    before_pointer = lake.gold.read_bytes("latest_successful_run.json")

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated build-web failure")

    import climate_risk.publishing.product as product_module

    monkeypatch.setattr(product_module, "build_web_bundle", _boom)

    with pytest.raises(typer.Exit) as exc_info:
        publish_product(scenario_target_year=2030)
    assert exc_info.value.exit_code == 1

    after_pointer = lake.gold.read_bytes("latest_successful_run.json")
    assert after_pointer == before_pointer
    # gold/bi was written before the simulated failure in build_web_bundle,
    # but gold/web must never have been written at all.
    assert not lake.gold.exists("web/manifest.json")

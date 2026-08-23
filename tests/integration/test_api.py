"""M10: end-to-end tests for the read-only API against a real, from-scratch
published gold/web bundle (built via the actual `climate_risk.bi.publish`
and `climate_risk.bi.web_publish` code paths, not hand-crafted JSON) --
this is real contract testing: if the bi->web transformation drifts from
what the API expects, these tests catch it, not just a mocked shape.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from climate_risk.api.repository import StartupValidationError, load_bundle
from climate_risk.bi.publish import ACTIVE_SCORE_VERSION as BI_ACTIVE_SCORE_VERSION
from climate_risk.bi.publish import BI_PREFIX
from climate_risk.bi.web_publish import build_manifest, build_web_bundle, write_web_bundle
from climate_risk.storage import LakeStorage, LocalStorageBackend, write_parquet, write_text

COUNTRIES = ["AAA", "BBB", "CCC"]


def _dim_labels() -> dict[str, dict[str, str]]:
    return {
        "AAA": {"country_name": "Alphaland", "region": "R1", "income_group": "High income"},
        "BBB": {"country_name": "Betaland", "region": "R2", "income_group": "Upper middle income"},
        "CCC": {"country_name": "Gammaland", "region": "R1", "income_group": "High income"},
    }


def _write_bi_tables(lake: LakeStorage) -> None:
    labels = _dim_labels()
    scores = {"AAA": 35.0, "BBB": 75.0, "CCC": 55.0}
    scores_v1 = {"AAA": 40.0, "BBB": 70.0, "CCC": 55.0}
    ranks = {"AAA": 3, "BBB": 1, "CCC": 2}
    ranks_v1 = {"AAA": 3, "BBB": 1, "CCC": 2}

    country_overview = pd.DataFrame(
        [
            {
                "country_iso3": iso3,
                "country_name": labels[iso3]["country_name"],
                "g20_flag": True,
                "region": labels[iso3]["region"],
                "income_group": labels[iso3]["income_group"],
                "valid_from": "2000-01-01",
                "valid_to": None,
                "score_version": BI_ACTIVE_SCORE_VERSION,
                "component_version": "energy_component_v2.1",
                "weights_version": "v2_weights_v1",
                "score_total": scores[iso3],
                "score_pace": 50.0,
                "score_coupling": 50.0,
                "score_volatility": 50.0,
                "score_forward_downside": 50.0,
                "score_energy": 50.0,
                "energy_confidence": 90.0,
                "data_confidence_score": 80.0,
                "weight_coverage": 1.0,
                "rank": ranks[iso3],
                "rank_band": "high"
                if scores[iso3] >= 70
                else "moderate"
                if scores[iso3] >= 45
                else "low",
                "score_total_v1": scores_v1[iso3],
                "rank_v1": ranks_v1[iso3],
                "latest_transition_year": 2024,
                "carbon_intensity_gdp": 0.9,
                "co2_per_capita": 5.0,
                "energy_intensity_gdp": 2.0,
                "is_core_complete": True,
                "missing_feature_count": 0,
                "transition_snapshot_id": "snap-transition",
                "latest_energy_year": 2024,
                "coal_share_elec": 20.0,
                "fossil_share_elec": 50.0,
                "low_carbon_share_elec": 50.0,
                "renewables_share_elec": 30.0,
                "transition_velocity": 1.0,
                "stalled_transition_residual_pp": 0.0,
                "active_score_version": BI_ACTIVE_SCORE_VERSION,
                "is_active_score": True,
                "score_delta_v2_minus_v1": scores[iso3] - scores_v1[iso3],
                "rank_delta_v2_minus_v1": ranks[iso3] - ranks_v1[iso3],
                "risk_segment": "Medium transition risk",
                "latest_successful_run_id": "run-test-1",
                "latest_successful_run_completed_at": "2026-01-01T00:05:00Z",
                "publish_status": "PUBLISHED",
                "bi_version": "bi_semantic_v1",
            }
            for iso3 in COUNTRIES
        ]
    )

    country_timeseries = pd.DataFrame(
        [
            {
                "country_iso3": iso3,
                "year": year,
                "co2_mt": 100.0,
                "real_gdp": 1000.0,
                "secondary_gdp_owid": 900.0,
                "population": 10.0,
                "carbon_intensity_gdp": 1.0 - (year - 2020) * 0.01,
                "co2_per_capita": 5.0,
                "energy_intensity_gdp": 2.0,
                "primary_energy_twh": 30.0,
                "is_core_complete": True,
                "missing_feature_count": 0,
                "imputation_mask": "",
                "snapshot_set_id": "snap-transition",
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
                "snapshot_set_id_energy": "snap-energy",
                "country_name": labels[iso3]["country_name"],
                "region": labels[iso3]["region"],
                "income_group": labels[iso3]["income_group"],
                "bi_version": "bi_semantic_v1",
            }
            for iso3 in COUNTRIES
            for year in range(2020, 2025)
        ]
    )

    risk_components = pd.DataFrame(
        [
            {
                "country_iso3": iso3,
                "score_version": version,
                "component_name": name,
                "component_score": 50.0,
                "nominal_weight": 0.2,
                "effective_weight": 0.2,
                "is_active_score": version == BI_ACTIVE_SCORE_VERSION,
                "component_version": "energy_component_v2.1"
                if version == BI_ACTIVE_SCORE_VERSION
                else None,
                "weights_version": "v2_weights_v1" if version == BI_ACTIVE_SCORE_VERSION else None,
                "bi_version": "bi_semantic_v1",
            }
            for iso3 in COUNTRIES
            for version in ("v1", BI_ACTIVE_SCORE_VERSION)
            for name in ("pace", "coupling", "volatility", "forward_downside", "energy")
            if not (version == "v1" and name == "energy")
        ]
    )

    scenario_quantiles = pd.DataFrame(
        [
            {
                "country_iso3": iso3,
                "origin_year": 2024,
                "target_year": 2030,
                "scenario_horizon_years": 6,
                "scenario_method": "empirical_bootstrap_v1",
                "scenario_status": "production",
                "forecast_p05": 0.5,
                "forecast_p50": 0.8,
                "forecast_p95": 1.2,
                "deterministic_baseline": 0.85,
                "prob_below_origin_value": 0.6,
                "simulation_count": 10000,
                "random_seed": 42,
                "experimental_variant": False,
                "bi_version": "bi_semantic_v1",
                "country_name": labels[iso3]["country_name"],
                "region": labels[iso3]["region"],
                "income_group": labels[iso3]["income_group"],
            }
            for iso3 in COUNTRIES
        ]
    )

    backtest_metrics = pd.DataFrame(
        [
            {
                "model_variant": "empirical_bootstrap",
                "n_splits": 6.0,
                "mae": 0.05,
                "rmse": 0.06,
                "median_ae": 0.04,
                "coverage_90": 0.76,
                "mean_interval_width_90": 0.2,
                "metric_grain": "summary",
                "nominal_coverage_90": 0.9,
                "calibration_gap_90": 0.14,
                "absolute_error": None,
                "actual": None,
                "country_iso3": None,
                "covered_90": None,
                "forecast_p05": None,
                "forecast_p50": None,
                "forecast_p95": None,
                "horizon_years": None,
                "interval_width_90": None,
                "origin_year": None,
                "target_year": None,
                "production_model_variant": "empirical_bootstrap",
                "bi_version": "bi_semantic_v1",
            },
            {
                "model_variant": "empirical_bootstrap",
                "n_splits": None,
                "mae": None,
                "rmse": None,
                "median_ae": None,
                "coverage_90": None,
                "mean_interval_width_90": None,
                "metric_grain": "country_origin",
                "nominal_coverage_90": 0.9,
                "calibration_gap_90": None,
                "absolute_error": 0.02,
                "actual": 0.8,
                "country_iso3": "AAA",
                "covered_90": True,
                "forecast_p05": 0.7,
                "forecast_p50": 0.82,
                "forecast_p95": 0.95,
                "horizon_years": 5.0,
                "interval_width_90": 0.25,
                "origin_year": 2015.0,
                "target_year": 2020.0,
                "production_model_variant": "empirical_bootstrap",
                "bi_version": "bi_semantic_v1",
            },
        ]
    )

    energy_indicators = pd.DataFrame(
        [
            {
                "country_iso3": iso3,
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
                "snapshot_set_id": "snap-energy",
                "country_name": labels[iso3]["country_name"],
                "region": labels[iso3]["region"],
                "income_group": labels[iso3]["income_group"],
                "latest_feature_latest_year": 2024,
                "latest_feature_trailing_window_years": 5,
                "latest_feature_sample_size": 5,
                "latest_feature_coal_share_elec": 20.0,
                "latest_feature_fossil_share_elec": 55.0,
                "latest_feature_renewables_share_elec": 30.0,
                "latest_feature_low_carbon_share_elec": 45.0,
                "latest_feature_coal_trend_pp_per_year": -0.5,
                "latest_feature_clean_power_momentum_pp_per_year": 1.0,
                "latest_feature_renewable_buildout_rate_pp_per_year": 0.8,
                "latest_feature_fossil_persistence_mean_pct": 55.0,
                "latest_feature_transition_velocity": 1.0,
                "latest_feature_stalled_transition_residual_pp": 0.0,
                "latest_feature_coal_share_elec_percentile": 50.0,
                "latest_feature_low_carbon_share_elec_percentile": 50.0,
                "bi_version": "bi_semantic_v1",
            }
            for iso3 in COUNTRIES
            for year in range(2020, 2025)
        ]
    )

    regime_diagnostics = pd.DataFrame(
        [
            {
                "country_iso3": iso3,
                "series_name": "carbon_intensity_gdp",
                "as_of_year": 2024,
                "latest_regime_start_year": 2018,
                "years_in_current_regime": 6,
                "break_count": 1,
                "strongest_break_year": 2018.0,
                "strongest_break_strength": 2.0,
                "pre_break_slope": -0.01,
                "post_break_slope": -0.03,
                "slope_delta": -0.02,
                "regime_direction": "IMPROVING",
                "regime_confidence": 0.8,
                "current_regime_label": "ACCELERATING_TRANSITION",
                "break_method": "segmented_regression",
                "break_version": "m7_regime_break_v0.1",
                "country_name": labels[iso3]["country_name"],
                "region": labels[iso3]["region"],
                "income_group": labels[iso3]["income_group"],
                "diagnostic_status": "diagnostic_only_not_production_forecast_selector",
                "used_in_production_score": False,
                "used_in_production_scenario": False,
                "bi_version": "bi_semantic_v1",
            }
            for iso3 in COUNTRIES
        ]
    )

    run_metadata = pd.DataFrame(
        [
            {
                "run_id": "run-test-1",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:05:00Z",
                "generated_at": "2026-01-01T00:05:00Z",
                "publish_status": "PUBLISHED",
                "active_score_version": BI_ACTIVE_SCORE_VERSION,
                "component_version": "energy_component_v2.1",
                "weights_version": "v2_weights_v1",
                "production_scenario_method": "empirical_bootstrap_v1",
                "git_sha": "abc123def456",
                "image_ref": None,
                "image_digest": None,
                "config_hash": "cfg-hash",
                "azure_job_execution_id": None,
                "transition_silver_path": "source=x/data.parquet",
                "energy_silver_path": "source=y/data.parquet",
                "transition_snapshot_id": "snap-transition",
                "owid_co2_snapshot_id": "co2-snap",
                "world_bank_wdi_snapshot_id": "wdi-snap",
                "owid_energy_snapshot_id": "energy-snap",
                "latest_model_eligible_year": 2024,
                "latest_model_eligible_year_completeness": 1.0,
                "bi_version": "bi_semantic_v1",
            }
        ]
    )

    tables = {
        "country_overview": country_overview,
        "country_timeseries": country_timeseries,
        "risk_components": risk_components,
        "scenario_quantiles": scenario_quantiles,
        "backtest_metrics": backtest_metrics,
        "energy_indicators": energy_indicators,
        "regime_diagnostics": regime_diagnostics,
        "run_metadata": run_metadata,
    }
    for name, frame in tables.items():
        write_parquet(lake.gold, f"{BI_PREFIX}/{name}.parquet", frame)


@pytest.fixture
def published_lake_root(tmp_path: Path) -> Path:
    lake = LakeStorage(
        raw=LocalStorageBackend(tmp_path / "raw"),
        bronze=LocalStorageBackend(tmp_path / "bronze"),
        silver=LocalStorageBackend(tmp_path / "silver"),
        gold=LocalStorageBackend(tmp_path / "gold"),
    )
    _write_bi_tables(lake)
    bundle = build_web_bundle(lake)
    manifest = build_manifest(bundle, generated_at="2026-01-02T00:00:00+00:00")
    write_web_bundle(lake, bundle, manifest)
    return tmp_path


@pytest.fixture
def client(published_lake_root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CLIMATE_RISK_LAKE_ROOT", str(published_lake_root))
    from climate_risk.api.app import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_meta(client: TestClient) -> None:
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    body = response.json()
    assert body["active_score_version"] == "v2_energy"
    assert body["production_scenario_method"] == "empirical_bootstrap_v1"
    assert body["source_run_id"] == "run-test-1"
    assert body["country_count"] == 3
    assert body["data_schema_version"] == "1.0.0"
    # data provenance and API application provenance are distinct concepts
    # that must never be collapsed into one overloaded field (ADR 0018/0019).
    assert "source_git_sha" not in body
    assert body["data_git_sha"] == "abc123def456"  # baked into the published bundle's manifest
    assert body["api_git_sha"]  # this test process's own resolvable git SHA (repo checkout)


def test_meta_api_image_digest_reflects_env_when_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLIMATE_RISK_API_IMAGE_DIGEST", "sha256:deadbeefcafe")
    body = client.get("/api/v1/meta").json()
    assert body["api_image_digest"] == "sha256:deadbeefcafe"


def test_openapi_and_docs_available(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    openapi = client.get("/openapi.json").json()
    assert openapi["info"]["title"] == "Climate Transition Risk Intelligence API"


def test_list_countries(client: TestClient) -> None:
    response = client.get("/api/v1/countries")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    assert {c["country_iso3"] for c in body} == set(COUNTRIES)
    # sorted by rank
    assert [c["rank"] for c in body] == sorted(c["rank"] for c in body)


def test_list_countries_region_filter(client: TestClient) -> None:
    response = client.get("/api/v1/countries", params={"region": "R1"})
    assert response.status_code == 200
    body = response.json()
    assert {c["country_iso3"] for c in body} == {"AAA", "CCC"}


def test_list_countries_limit(client: TestClient) -> None:
    response = client.get("/api/v1/countries", params={"limit": 1})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_country_profile(client: TestClient) -> None:
    response = client.get("/api/v1/countries/BBB")
    assert response.status_code == 200
    body = response.json()
    assert body["country_iso3"] == "BBB"
    assert body["country_name"] == "Betaland"
    assert body["score_comparison"]["score_v2_energy"] == pytest.approx(75.0)
    assert body["score_comparison"]["score_v1"] == pytest.approx(70.0)
    assert body["provenance"]["run_id"] == "run-test-1"
    assert len(body["risk_components"]) > 0
    assert body["scenario"]["scenario_method"] == "empirical_bootstrap_v1"


def test_country_profile_lowercase_iso3(client: TestClient) -> None:
    response = client.get("/api/v1/countries/bbb")
    assert response.status_code == 200
    assert response.json()["country_iso3"] == "BBB"

    response = client.get("/api/v1/countries/Bbb")
    assert response.status_code == 200
    assert response.json()["country_iso3"] == "BBB"


def test_country_profile_unknown_iso3(client: TestClient) -> None:
    response = client.get("/api/v1/countries/ZZZ")
    assert response.status_code == 404
    assert "ZZZ" in response.json()["detail"]


def test_country_timeseries(client: TestClient) -> None:
    response = client.get("/api/v1/countries/AAA/timeseries")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    assert [p["year"] for p in body] == sorted(p["year"] for p in body)


def test_country_timeseries_year_filter(client: TestClient) -> None:
    response = client.get(
        "/api/v1/countries/AAA/timeseries", params={"start_year": 2022, "end_year": 2023}
    )
    assert response.status_code == 200
    body = response.json()
    assert {p["year"] for p in body} == {2022, 2023}


def test_country_timeseries_invalid_year_range(client: TestClient) -> None:
    response = client.get(
        "/api/v1/countries/AAA/timeseries", params={"start_year": 2023, "end_year": 2020}
    )
    assert response.status_code == 422


def test_country_timeseries_unknown_country(client: TestClient) -> None:
    response = client.get("/api/v1/countries/ZZZ/timeseries")
    assert response.status_code == 404


def test_country_energy(client: TestClient) -> None:
    response = client.get("/api/v1/countries/AAA/energy")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    assert all(p["country_iso3"] == "AAA" for p in body)


def test_country_scenario_production_only(client: TestClient) -> None:
    response = client.get("/api/v1/countries/AAA/scenario")
    assert response.status_code == 200
    body = response.json()
    assert body["scenario_method"] == "empirical_bootstrap_v1"
    assert body["forecast_p05"] <= body["forecast_p50"] <= body["forecast_p95"]


def test_country_risk_components(client: TestClient) -> None:
    response = client.get("/api/v1/countries/AAA/risk-components")
    assert response.status_code == 200
    body = response.json()
    assert {c["score_version"] for c in body} == {"v1", "v2_energy"}
    active = [c for c in body if c["is_active_score"]]
    assert {c["component_name"] for c in active} == {
        "pace",
        "coupling",
        "volatility",
        "forward_downside",
        "energy",
    }


def test_score_comparison_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/countries/CCC/score-comparison")
    assert response.status_code == 200
    body = response.json()
    assert body["score_v1"] == pytest.approx(55.0)
    assert body["score_v2_energy"] == pytest.approx(55.0)
    assert body["score_delta"] == pytest.approx(0.0)


def test_rankings(client: TestClient) -> None:
    response = client.get("/api/v1/rankings")
    assert response.status_code == 200
    body = response.json()
    assert body["active_score_version"] == "v2_energy"
    assert body["total_count"] == 3
    scores = [e["risk_score"] for e in body["entries"]]
    assert scores == sorted(scores, reverse=True)


def test_rankings_sort_ascending(client: TestClient) -> None:
    response = client.get("/api/v1/rankings", params={"sort": "risk_asc"})
    scores = [e["risk_score"] for e in response.json()["entries"]]
    assert scores == sorted(scores)


def test_backtests_summary_and_detail(client: TestClient) -> None:
    response = client.get("/api/v1/backtests")
    assert response.status_code == 200
    body = response.json()
    grains = {r["metric_grain"] for r in body}
    assert grains == {"summary", "country_origin"}
    summary = next(r for r in body if r["metric_grain"] == "summary")
    assert summary["coverage_90"] == pytest.approx(0.76)
    assert summary["nominal_coverage_90"] == pytest.approx(0.9)
    # historical undercoverage must be visible, not hidden
    assert summary["coverage_90"] < summary["nominal_coverage_90"]


def test_backtests_country_filter(client: TestClient) -> None:
    response = client.get("/api/v1/backtests", params={"country": "aaa"})
    assert response.status_code == 200
    body = response.json()
    assert all(r["country_iso3"] in (None, "AAA") for r in body)


def test_regime_diagnostics_are_research_only(client: TestClient) -> None:
    response = client.get("/api/v1/diagnostics/regimes/AAA")
    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    for entry in body:
        assert entry["production_use"] is False
        assert entry["status"] == "research_diagnostic"


def test_regime_diagnostics_unknown_country(client: TestClient) -> None:
    response = client.get("/api/v1/diagnostics/regimes/ZZZ")
    assert response.status_code == 404


def test_no_mutation_routes(client: TestClient) -> None:
    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)("/api/v1/countries/AAA")
        assert response.status_code in (404, 405), f"{method} unexpectedly allowed"
    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)("/api/v1/rankings")
        assert response.status_code in (404, 405), f"{method} unexpectedly allowed"


def test_responses_are_deterministic(client: TestClient) -> None:
    first = client.get("/api/v1/countries/AAA").json()
    second = client.get("/api/v1/countries/AAA").json()
    assert first == second

    first_rankings = client.get("/api/v1/rankings").json()
    second_rankings = client.get("/api/v1/rankings").json()
    assert first_rankings == second_rankings


def test_no_secret_like_fields_anywhere_in_meta(client: TestClient) -> None:
    body = client.get("/api/v1/meta").json()
    forbidden = (
        "key",
        "secret",
        "sas",
        "token",
        "connectionstring",
        "password",
        "tenant",
        "subscription",
    )
    payload = json.dumps(body).lower()
    for word in forbidden:
        assert word not in payload, (
            f"potential secret-like field leaked: {word!r} found in /meta response"
        )


class TestContractAgainstPublishedArtifacts:
    """Verify representative API fields exactly match the underlying
    gold/web source (spec section 21: the API must not become a second
    analytical implementation)."""

    def test_country_overview_matches_source(
        self, client: TestClient, published_lake_root: Path
    ) -> None:
        source = json.loads(
            (published_lake_root / "gold" / "web" / "country-overview.json").read_text()
        )
        source_row = next(r for r in source if r["country_iso3"] == "BBB")

        api_row = client.get("/api/v1/countries/BBB").json()

        assert api_row["risk_score"] == source_row["score_total"]
        assert api_row["rank"] == source_row["rank"]
        assert api_row["data_confidence_score"] == source_row["data_confidence_score"]
        assert api_row["score_comparison"]["score_v1"] == source_row["score_total_v1"]

    def test_scenario_matches_source(self, client: TestClient, published_lake_root: Path) -> None:
        source = json.loads(
            (published_lake_root / "gold" / "web" / "scenario-quantiles.json").read_text()
        )
        source_row = next(r for r in source if r["country_iso3"] == "AAA")

        api_row = client.get("/api/v1/countries/AAA/scenario").json()

        assert api_row["forecast_p05"] == source_row["forecast_p05"]
        assert api_row["forecast_p50"] == source_row["forecast_p50"]
        assert api_row["forecast_p95"] == source_row["forecast_p95"]

    def test_energy_matches_source(self, client: TestClient, published_lake_root: Path) -> None:
        source = json.loads(
            (published_lake_root / "gold" / "web" / "energy-indicators.json").read_text()
        )
        source_rows = sorted(
            (r for r in source if r["country_iso3"] == "AAA"), key=lambda r: r["year"]
        )

        api_rows = client.get("/api/v1/countries/AAA/energy").json()

        assert [r["low_carbon_share_elec"] for r in api_rows] == [
            r["low_carbon_share_elec"] for r in source_rows
        ]

    def test_component_scores_match_source(
        self, client: TestClient, published_lake_root: Path
    ) -> None:
        source = json.loads(
            (published_lake_root / "gold" / "web" / "risk-components.json").read_text()
        )
        source_rows = [r for r in source if r["country_iso3"] == "CCC" and r["is_active_score"]]

        api_rows = [
            r
            for r in client.get("/api/v1/countries/CCC/risk-components").json()
            if r["is_active_score"]
        ]

        assert {r["component_name"]: r["component_score"] for r in api_rows} == {
            r["component_name"]: r["component_score"] for r in source_rows
        }


class TestStartupValidation:
    """M10 section 11: the API must fail to start rather than serve
    partially invalid analytics."""

    def _lake(self, root: Path) -> LakeStorage:
        return LakeStorage(
            raw=LocalStorageBackend(root / "raw"),
            bronze=LocalStorageBackend(root / "bronze"),
            silver=LocalStorageBackend(root / "silver"),
            gold=LocalStorageBackend(root / "gold"),
        )

    def test_fails_when_bundle_missing_entirely(self, tmp_path: Path) -> None:
        lake = self._lake(tmp_path)
        with pytest.raises(StartupValidationError, match="missing required file"):
            load_bundle(lake)

    def test_fails_on_schema_version_mismatch(self, tmp_path: Path) -> None:
        lake = self._lake(tmp_path)
        _write_bi_tables(lake)
        bundle = build_web_bundle(lake)
        manifest = build_manifest(bundle, generated_at="2026-01-02T00:00:00+00:00")
        manifest["schema_version"] = "99.0.0"
        write_web_bundle(lake, bundle, manifest)

        with pytest.raises(StartupValidationError, match="schema version"):
            load_bundle(lake)

    def test_fails_on_unexpected_active_score_version(self, tmp_path: Path) -> None:
        lake = self._lake(tmp_path)
        _write_bi_tables(lake)
        bundle = build_web_bundle(lake)
        manifest = build_manifest(bundle, generated_at="2026-01-02T00:00:00+00:00")
        manifest["active_score_version"] = "v1"
        write_web_bundle(lake, bundle, manifest)

        with pytest.raises(StartupValidationError, match="active_score_version"):
            load_bundle(lake)

    def test_fails_on_unexpected_scenario_method(self, tmp_path: Path) -> None:
        lake = self._lake(tmp_path)
        _write_bi_tables(lake)
        bundle = build_web_bundle(lake)
        manifest = build_manifest(bundle, generated_at="2026-01-02T00:00:00+00:00")
        manifest["active_scenario_method"] = "recency_weighted_bootstrap"
        write_web_bundle(lake, bundle, manifest)

        with pytest.raises(StartupValidationError, match="active_scenario_method"):
            load_bundle(lake)

    def test_fails_on_corrupted_file_hash_mismatch(self, tmp_path: Path) -> None:
        lake = self._lake(tmp_path)
        _write_bi_tables(lake)
        bundle = build_web_bundle(lake)
        manifest = build_manifest(bundle, generated_at="2026-01-02T00:00:00+00:00")
        write_web_bundle(lake, bundle, manifest)
        # Corrupt one published file after the manifest was written.
        write_text(lake.gold, "web/country-overview.json", "[]")

        with pytest.raises(
            StartupValidationError, match="does not match its manifest SHA-256|row count"
        ):
            load_bundle(lake)

    def test_app_fails_to_start_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CLIMATE_RISK_LAKE_ROOT", str(tmp_path))
        from climate_risk.api.app import create_app

        with pytest.raises(StartupValidationError), TestClient(create_app()):
            pass

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from climate_risk.bi.publish import BI_PREFIX
from climate_risk.bi.web_publish import (
    RUN_METADATA_SAFE_FIELDS,
    TABLE_TO_WEB_FILE,
    WEB_PREFIX,
    WEB_SCHEMA_VERSION,
    build_manifest,
    build_web_bundle,
    json_safe,
    write_web_bundle,
)
from climate_risk.storage import LakeStorage, LocalStorageBackend, read_text, write_parquet


def _lake(tmp_path: Path) -> LakeStorage:
    return LakeStorage(
        raw=LocalStorageBackend(tmp_path / "raw"),
        bronze=LocalStorageBackend(tmp_path / "bronze"),
        silver=LocalStorageBackend(tmp_path / "silver"),
        gold=LocalStorageBackend(tmp_path / "gold"),
    )


def _write_bi_tables(lake: LakeStorage) -> None:
    country_overview = pd.DataFrame(
        {
            "country_iso3": ["AAA", "BBB"],
            "country_name": ["Alpha", "Beta"],
            "region": ["R1", "R2"],
            "income_group": ["High income", "Upper middle income"],
            "score_total": [35.0, 75.0],
            "rank": [2, 1],
            "active_score_version": ["v2_energy", "v2_energy"],
            "score_total_v1": [40.0, 70.0],
            "weight_coverage": [1.0, np.nan],
        }
    )
    country_timeseries = pd.DataFrame(
        {
            "country_iso3": ["AAA", "AAA"],
            "year": [2023, 2024],
            "carbon_intensity_gdp": [1.0, 0.97],
        }
    )
    risk_components = pd.DataFrame(
        {
            "country_iso3": ["AAA", "BBB"],
            "score_version": ["v2_energy", "v2_energy"],
            "component_name": ["pace", "pace"],
            "component_score": [30.0, 80.0],
        }
    )
    scenario_quantiles = pd.DataFrame(
        {
            "country_iso3": ["AAA", "BBB"],
            "forecast_p05": [0.5, 0.6],
            "forecast_p50": [0.8, 0.9],
            "forecast_p95": [1.2, 1.4],
            "scenario_method": ["empirical_bootstrap_v1", "empirical_bootstrap_v1"],
        }
    )
    backtest_metrics = pd.DataFrame(
        {
            "model_variant": ["empirical_bootstrap"],
            "mae": [0.05],
            "coverage_90": [0.76],
        }
    )
    energy_indicators = pd.DataFrame(
        {
            "country_iso3": ["AAA", "BBB"],
            "year": [2024, 2024],
            "low_carbon_share_elec": [45.0, np.inf],
        }
    )
    regime_diagnostics = pd.DataFrame(
        {
            "country_iso3": ["AAA"],
            "series_name": ["carbon_intensity_gdp"],
            "used_in_production_score": [False],
            "used_in_production_scenario": [False],
            "diagnostic_status": ["diagnostic_only_not_production_forecast_selector"],
        }
    )
    run_metadata = pd.DataFrame(
        [
            {
                "run_id": "run-1",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:05:00Z",
                "generated_at": "2026-01-01T00:05:00Z",
                "publish_status": "PUBLISHED",
                "active_score_version": "v2_energy",
                "component_version": "energy_component_v2.1",
                "weights_version": "v2_weights_v1",
                "production_scenario_method": "empirical_bootstrap_v1",
                "git_sha": "abc123",
                "image_ref": "ghcr.io/example/climate-risk:abc123",
                "image_digest": "sha256:deadbeef",
                "config_hash": "cfg-hash",
                "azure_job_execution_id": "job-exec-secret-ish",
                "transition_silver_path": "source=owid_co2/snapshot_id=x/data.parquet",
                "energy_silver_path": "source=owid_energy/snapshot_id=y/data.parquet",
                "transition_snapshot_id": "transition-snap",
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


def test_json_safe_handles_nan_inf_numpy_and_timestamps() -> None:
    assert json_safe(float("nan")) is None
    assert json_safe(float("inf")) is None
    assert json_safe(float("-inf")) is None
    assert json_safe(np.nan) is None
    assert json_safe(np.float64(1.5)) == 1.5
    assert json_safe(np.int64(7)) == 7
    assert isinstance(json_safe(np.int64(7)), int)
    assert json_safe(pd.NA) is None
    assert json_safe(None) is None
    assert json_safe(True) is True
    ts = pd.Timestamp("2026-01-01T00:00:00Z")
    assert json_safe(ts) == ts.isoformat()
    assert json_safe(pd.NaT) is None
    assert json_safe("plain-string") == "plain-string"


def test_build_web_bundle_produces_every_expected_file(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_bi_tables(lake)

    bundle = build_web_bundle(lake)

    for file_stem in TABLE_TO_WEB_FILE.values():
        assert file_stem in bundle
    assert "countries" in bundle
    assert len(bundle["countries"]) == 2
    assert {"country_iso3", "country_name", "region", "income_group"} == set(
        bundle["countries"][0].keys()
    )


def test_bundle_json_is_valid_and_has_no_nan_or_infinity(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_bi_tables(lake)
    bundle = build_web_bundle(lake)

    for records in bundle.values():
        payload = json.dumps(records)
        assert "NaN" not in payload
        assert "Infinity" not in payload
        reparsed = json.loads(payload)
        assert reparsed == records
        for record in records:
            for value in record.values():
                if isinstance(value, float):
                    assert math.isfinite(value)


def test_country_overview_row_count_matches_source(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_bi_tables(lake)
    bundle = build_web_bundle(lake)

    assert len(bundle["country-overview"]) == 2
    isos = {row["country_iso3"] for row in bundle["country-overview"]}
    assert isos == {"AAA", "BBB"}
    assert len(isos) == len(bundle["country-overview"])  # unique country keys


def test_scenario_quantiles_preserve_p5_p50_p95_ordering(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_bi_tables(lake)
    bundle = build_web_bundle(lake)

    for row in bundle["scenario-quantiles"]:
        assert row["forecast_p05"] <= row["forecast_p50"] <= row["forecast_p95"]
        assert row["scenario_method"] == "empirical_bootstrap_v1"


def test_active_score_and_production_scenario_labels_preserved(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_bi_tables(lake)
    bundle = build_web_bundle(lake)

    assert all(row["active_score_version"] == "v2_energy" for row in bundle["country-overview"])
    assert all("score_total_v1" in row for row in bundle["country-overview"])  # v1 retained
    manifest = build_manifest(bundle)
    assert manifest["active_score_version"] == "v2_energy"
    assert manifest["active_scenario_method"] == "empirical_bootstrap_v1"


def test_regime_diagnostics_labelled_non_production(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_bi_tables(lake)
    bundle = build_web_bundle(lake)

    for row in bundle["regime-diagnostics"]:
        assert row["used_in_production_score"] is False
        assert row["used_in_production_scenario"] is False
        assert "diagnostic_only" in row["diagnostic_status"]


def test_run_metadata_excludes_secret_like_and_private_path_fields(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_bi_tables(lake)
    bundle = build_web_bundle(lake)

    run_metadata = bundle["run-metadata"][0]
    assert set(run_metadata.keys()) == set(RUN_METADATA_SAFE_FIELDS)
    assert "transition_silver_path" not in run_metadata
    assert "energy_silver_path" not in run_metadata
    assert "azure_job_execution_id" not in run_metadata
    # Acceptable provenance fields ARE present.
    assert run_metadata["git_sha"] == "abc123"
    assert run_metadata["image_digest"] == "sha256:deadbeef"
    assert run_metadata["run_id"] == "run-1"
    forbidden_substrings = ("key", "secret", "sas", "token", "connectionstring", "password")
    for key in run_metadata:
        lowered = key.lower()
        assert not any(bad in lowered for bad in forbidden_substrings), key


def test_manifest_contains_required_provenance_fields(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_bi_tables(lake)
    bundle = build_web_bundle(lake)
    manifest = build_manifest(bundle, generated_at="2026-01-02T00:00:00+00:00")

    required = {
        "schema_version",
        "generated_at",
        "source_run_id",
        "source_git_sha",
        "active_score_version",
        "active_component_version",
        "active_scenario_method",
        "model_eligible_year",
        "country_count",
        "source_snapshot_ids",
        "config_hash",
        "web_bundle_hash",
        "files",
    }
    assert required.issubset(manifest.keys())
    assert manifest["schema_version"] == WEB_SCHEMA_VERSION
    assert manifest["country_count"] == 2
    assert manifest["source_run_id"] == "run-1"
    assert manifest["source_snapshot_ids"] == {
        "owid_co2": "co2-snap",
        "world_bank_wdi": "wdi-snap",
        "owid_energy": "energy-snap",
    }
    file_names = {f["name"] for f in manifest["files"]}
    assert file_names == {f"{stem}.json" for stem in bundle}
    for entry in manifest["files"]:
        assert entry["row_count"] >= 0
        assert len(entry["sha256"]) == 64
        assert entry["schema_version"] == WEB_SCHEMA_VERSION


def test_bundle_hash_is_deterministic(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_bi_tables(lake)
    bundle = build_web_bundle(lake)

    manifest_a = build_manifest(bundle, generated_at="2026-01-01T00:00:00+00:00")
    manifest_b = build_manifest(bundle, generated_at="2026-01-02T00:00:00+00:00")

    assert manifest_a["web_bundle_hash"] == manifest_b["web_bundle_hash"]


def test_write_web_bundle_writes_every_file_and_manifest(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_bi_tables(lake)
    bundle = build_web_bundle(lake)
    manifest = build_manifest(bundle)

    write_web_bundle(lake, bundle, manifest)

    for file_stem in bundle:
        assert lake.gold.exists(f"{WEB_PREFIX}/{file_stem}.json")
        parsed = json.loads(read_text(lake.gold, f"{WEB_PREFIX}/{file_stem}.json"))
        assert parsed == bundle[file_stem]
    assert lake.gold.exists(f"{WEB_PREFIX}/manifest.json")
    parsed_manifest = json.loads(read_text(lake.gold, f"{WEB_PREFIX}/manifest.json"))
    assert parsed_manifest["web_bundle_hash"] == manifest["web_bundle_hash"]


def test_source_bi_tables_are_not_modified_by_web_publication(tmp_path: Path) -> None:
    from climate_risk.storage import read_parquet as _read_parquet

    lake = _lake(tmp_path)
    _write_bi_tables(lake)
    before_frames = {
        name: _read_parquet(lake.gold, f"{BI_PREFIX}/{name}.parquet") for name in TABLE_TO_WEB_FILE
    }

    bundle = build_web_bundle(lake)
    manifest = build_manifest(bundle)
    write_web_bundle(lake, bundle, manifest)

    after_frames = {
        name: _read_parquet(lake.gold, f"{BI_PREFIX}/{name}.parquet") for name in TABLE_TO_WEB_FILE
    }
    for name in TABLE_TO_WEB_FILE:
        pd.testing.assert_frame_equal(before_frames[name], after_frames[name])

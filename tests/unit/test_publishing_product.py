"""Unit tests for `climate_risk.publishing.product`'s post-write verification.

These operate directly on a hand-built gold/bi + gold/web bundle (like
tests/unit/test_web_publish.py) rather than a full pipeline run -- the
full end-to-end path (core publish -> publish_product -> verify) is
covered by tests/integration/test_publish_product_cli.py. This file
focuses on proving `verify_product_publication` actually catches
corruption/mismatch rather than rubber-stamping whatever was written.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from climate_risk.bi.publish import BI_PREFIX, PRODUCTION_SCENARIO_METHOD
from climate_risk.bi.web_publish import (
    WEB_PREFIX,
    build_manifest,
    build_web_bundle,
    write_web_bundle,
)
from climate_risk.publishing.product import ProductPublicationError, verify_product_publication
from climate_risk.scoring.risk_score_v2_energy import SCORE_VERSION as V2_SCORE_VERSION
from climate_risk.storage import (
    LakeStorage,
    LocalStorageBackend,
    read_text,
    write_parquet,
    write_text,
)


def _lake(tmp_path: Path) -> LakeStorage:
    return LakeStorage(
        raw=LocalStorageBackend(tmp_path / "raw"),
        bronze=LocalStorageBackend(tmp_path / "bronze"),
        silver=LocalStorageBackend(tmp_path / "silver"),
        gold=LocalStorageBackend(tmp_path / "gold"),
    )


def _write_bi_tables(lake: LakeStorage, *, run_id: str = "run-1") -> None:
    country_overview = pd.DataFrame(
        {
            "country_iso3": ["AAA", "BBB"],
            "country_name": ["Alpha", "Beta"],
            "region": ["R1", "R2"],
            "income_group": ["High income", "Upper middle income"],
        }
    )
    run_metadata = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:05:00Z",
                "generated_at": "2026-01-01T00:05:00Z",
                "publish_status": "PUBLISHED",
                "active_score_version": V2_SCORE_VERSION,
                "component_version": "energy_component_v2.1",
                "weights_version": "v2_weights_v1",
                "production_scenario_method": PRODUCTION_SCENARIO_METHOD,
                "git_sha": "abc123",
                "image_ref": "ghcr.io/example/climate-risk:abc123",
                "image_digest": "sha256:deadbeef",
                "config_hash": "cfg-hash",
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
        "country_timeseries": pd.DataFrame({"country_iso3": ["AAA"], "year": [2024]}),
        "risk_components": pd.DataFrame(
            {
                "country_iso3": ["AAA"],
                "score_version": [V2_SCORE_VERSION],
                "component_name": ["pace"],
            }
        ),
        "scenario_quantiles": pd.DataFrame(
            {"country_iso3": ["AAA"], "scenario_method": [PRODUCTION_SCENARIO_METHOD]}
        ),
        "backtest_metrics": pd.DataFrame({"model_variant": ["empirical_bootstrap"]}),
        "energy_indicators": pd.DataFrame({"country_iso3": ["AAA"], "year": [2024]}),
        "regime_diagnostics": pd.DataFrame({"country_iso3": ["AAA"]}),
        "run_metadata": run_metadata,
    }
    for name, frame in tables.items():
        write_parquet(lake.gold, f"{BI_PREFIX}/{name}.parquet", frame)


def _write_valid_web_bundle(lake: LakeStorage, *, run_id: str = "run-1") -> None:
    _write_bi_tables(lake, run_id=run_id)
    bundle = build_web_bundle(lake)
    manifest = build_manifest(bundle)
    write_web_bundle(lake, bundle, manifest)


def test_verify_passes_for_a_freshly_written_consistent_bundle(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_valid_web_bundle(lake, run_id="run-1")

    result = verify_product_publication(lake, expected_run_id="run-1")

    assert result["source_run_id"] == "run-1"
    assert result["country_count"] == 2


def test_verify_fails_when_manifest_missing(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_valid_web_bundle(lake, run_id="run-1")
    lake.gold.remove(f"{WEB_PREFIX}/manifest.json")

    with pytest.raises(ProductPublicationError, match="missing"):
        verify_product_publication(lake, expected_run_id="run-1")


def test_verify_fails_on_run_id_mismatch(tmp_path: Path) -> None:
    """A bundle built for a stale run must never verify as belonging to the
    latest core release."""
    lake = _lake(tmp_path)
    _write_valid_web_bundle(lake, run_id="run-stale")

    with pytest.raises(ProductPublicationError, match="source_run_id_mismatch"):
        verify_product_publication(lake, expected_run_id="run-current")


def test_verify_fails_on_tampered_file_sha256(tmp_path: Path) -> None:
    """A file whose bytes were overwritten after the manifest was built
    (e.g. an interrupted/partial write) must be caught, not silently
    accepted -- this is exactly the failure mode that must never leave a
    bundle that passes API startup validation."""
    lake = _lake(tmp_path)
    _write_valid_web_bundle(lake, run_id="run-1")
    write_text(lake.gold, f"{WEB_PREFIX}/country-overview.json", "[]")

    with pytest.raises(ProductPublicationError, match="sha256_mismatch"):
        verify_product_publication(lake, expected_run_id="run-1")


def test_verify_fails_when_a_web_file_is_missing_but_manifest_still_references_it(
    tmp_path: Path,
) -> None:
    lake = _lake(tmp_path)
    _write_valid_web_bundle(lake, run_id="run-1")
    lake.gold.remove(f"{WEB_PREFIX}/backtest-metrics.json")

    with pytest.raises(ProductPublicationError, match="backtest-metrics.json"):
        verify_product_publication(lake, expected_run_id="run-1")


def test_verify_fails_on_active_score_version_mismatch(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_valid_web_bundle(lake, run_id="run-1")
    manifest = json.loads(read_text(lake.gold, f"{WEB_PREFIX}/manifest.json"))
    manifest["active_score_version"] = "v1"
    write_text(lake.gold, f"{WEB_PREFIX}/manifest.json", json.dumps(manifest, indent=2))

    with pytest.raises(ProductPublicationError, match="active_score_version_mismatch"):
        verify_product_publication(lake, expected_run_id="run-1")


def test_verify_fails_on_non_finite_literal_smuggled_into_a_file(tmp_path: Path) -> None:
    """Belt-and-braces: even though `json_safe` prevents NaN/Infinity from
    ever being serialized, verification independently re-scans the raw
    bytes for the literal tokens so a future regression upstream would
    still be caught here."""
    lake = _lake(tmp_path)
    _write_valid_web_bundle(lake, run_id="run-1")
    # Overwrite with content that keeps the *original* sha256 out of reach
    # deliberately -- this must fail on sha256_mismatch OR the NaN check,
    # either is an acceptable, loud failure.
    write_text(lake.gold, f"{WEB_PREFIX}/country-overview.json", '[{"x": NaN}]')

    with pytest.raises(ProductPublicationError):
        verify_product_publication(lake, expected_run_id="run-1")


def test_verify_fails_on_run_metadata_leaking_unsafe_field(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _write_valid_web_bundle(lake, run_id="run-1")
    run_metadata = json.loads(read_text(lake.gold, f"{WEB_PREFIX}/run-metadata.json"))
    run_metadata[0]["azure_job_execution_id"] = "should-not-be-here"
    payload = json.dumps(run_metadata, indent=2)
    write_text(lake.gold, f"{WEB_PREFIX}/run-metadata.json", payload)
    # Re-point the manifest's sha256/row_count at the tampered payload so
    # this test isolates the unsafe-field check from the sha256 check.
    import hashlib

    manifest = json.loads(read_text(lake.gold, f"{WEB_PREFIX}/manifest.json"))
    compact_payload = json.dumps(run_metadata, sort_keys=True, separators=(",", ":"))
    for entry in manifest["files"]:
        if entry["name"] == "run-metadata.json":
            entry["sha256"] = hashlib.sha256(compact_payload.encode("utf-8")).hexdigest()
    write_text(lake.gold, f"{WEB_PREFIX}/manifest.json", json.dumps(manifest, indent=2))
    write_text(lake.gold, f"{WEB_PREFIX}/run-metadata.json", compact_payload)

    with pytest.raises(ProductPublicationError, match="unsafe_fields"):
        verify_product_publication(lake, expected_run_id="run-1")

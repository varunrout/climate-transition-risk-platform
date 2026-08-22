"""M6 phase 3, section 15: publish() must fail-closed if v2 (the ADR 0009
production score) wasn't computed -- energy ingestion, energy feature
construction, or v2 scoring failing upstream must never result in a
partial/v1-only release becoming the new latest_successful_run pointer.

Exercises the real `climate_risk.cli.publish` command function directly
(not a subprocess) against a from-scratch fake local lake, so this is a
genuine end-to-end check of the CLI wiring added in M6 phase 3 -- not just
the already-covered `publishing.barrier` unit tests.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import typer

from climate_risk.storage import LakeStorage, backend_for_uri, write_json, write_parquet


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
    manifest = {
        "status": "ACCEPTED",
        "sha256": f"deadbeef{source_name}",
        "retrieved_at_utc": "2026-08-22T00:00:00+00:00",
    }
    write_json(
        lake.raw,
        f"source={source_name}/ingest_date=2026-08-22/run_id=test-run/manifest.json",
        manifest,
    )


def _write_minimal_silver_and_backtest(lake: LakeStorage) -> None:
    panel = pd.DataFrame(
        {
            "country_iso3": ["USA", "CHN"],
            "year": [2022, 2022],
            "is_core_complete": [True, True],
        }
    )
    write_parquet(
        lake.silver, "fact_country_year_transition/snapshot_set_id=abc123/data.parquet", panel
    )
    write_parquet(
        lake.gold,
        "backtest_summary.parquet",
        pd.DataFrame({"model_variant": ["empirical_bootstrap"], "mae": [0.05]}),
    )


def _write_v1_score(lake: LakeStorage) -> None:
    write_parquet(
        lake.gold,
        "country_transition_risk.parquet",
        pd.DataFrame({"country_iso3": ["USA", "CHN"], "score_total": [50.0, 60.0]}),
    )


def _write_v2_score(lake: LakeStorage) -> None:
    write_parquet(
        lake.gold,
        "country_transition_risk_v2.parquet",
        pd.DataFrame({"country_iso3": ["USA", "CHN"], "score_total": [48.0, 58.0]}),
    )


@pytest.fixture
def fake_lake_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "lake"
    lake = _make_lake(root)
    for source_name in ("owid_co2", "world_bank_wdi", "owid_energy"):
        _write_accepted_manifest(lake, source_name=source_name)
    _write_minimal_silver_and_backtest(lake)
    _write_v1_score(lake)

    monkeypatch.setenv("CLIMATE_RISK_LAKE_ROOT", str(root))
    monkeypatch.delenv("CLIMATE_RISK_RAW_ROOT", raising=False)
    monkeypatch.delenv("CLIMATE_RISK_BRONZE_ROOT", raising=False)
    monkeypatch.delenv("CLIMATE_RISK_SILVER_ROOT", raising=False)
    monkeypatch.delenv("CLIMATE_RISK_GOLD_ROOT", raising=False)
    return root


def test_publish_blocked_when_v2_score_missing(fake_lake_env: Path) -> None:
    """v1 exists, v2 does not (simulates an upstream energy/v2 failure) --
    publish must exit non-zero and must NOT write a pointer file."""
    from climate_risk.cli import publish

    lake = _make_lake(fake_lake_env)
    assert not lake.gold.exists("latest_successful_run.json")

    with pytest.raises(typer.Exit) as exc_info:
        publish()
    assert exc_info.value.exit_code == 1
    assert not lake.gold.exists("latest_successful_run.json")


def test_publish_leaves_previous_pointer_untouched_when_v2_missing(fake_lake_env: Path) -> None:
    """A prior successful release (v1+v2 both present) must survive a
    later run where v2 goes missing -- the pointer must not be touched."""
    from climate_risk.cli import publish

    lake = _make_lake(fake_lake_env)
    _write_v2_score(lake)
    publish()  # first run: succeeds, writes the pointer
    assert lake.gold.exists("latest_successful_run.json")
    first_pointer = lake.gold.read_bytes("latest_successful_run.json")

    # Now simulate a subsequent run where the energy pipeline/v2 scoring failed.
    lake.gold.remove("country_transition_risk_v2.parquet")
    with pytest.raises(typer.Exit):
        publish()

    second_pointer = lake.gold.read_bytes("latest_successful_run.json")
    assert first_pointer == second_pointer


def test_publish_succeeds_and_declares_v2_active_when_both_present(fake_lake_env: Path) -> None:
    from climate_risk.cli import publish
    from climate_risk.scoring.risk_score_v2_energy import SCORE_VERSION as V2_SCORE_VERSION
    from climate_risk.storage import read_json

    lake = _make_lake(fake_lake_env)
    _write_v2_score(lake)

    publish()

    assert lake.gold.exists("latest_successful_run.json")
    manifest_paths = lake.gold.glob("manifests/*.json")
    assert manifest_paths
    latest_manifest_path = max(manifest_paths, key=lake.gold.modified_at)
    manifest = read_json(lake.gold, latest_manifest_path)
    assert isinstance(manifest, dict)
    assert manifest["score_version"] == V2_SCORE_VERSION
    assert manifest["comparison_score_version"] == "v1"
    assert manifest["v1_artifact"] == "country_transition_risk.parquet"
    assert manifest["v2_artifact"] == "country_transition_risk_v2.parquet"

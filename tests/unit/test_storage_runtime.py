from __future__ import annotations

from pathlib import Path

import pytest

from climate_risk.storage import LakeStorage, LocalStorageBackend, write_json, write_text
from climate_risk.storage.azure import AzureStorageBackend
from climate_risk.storage.runtime import (
    StorageRuntimeError,
    log_backend_diagnostics,
    validate_cloud_storage_invariant,
    verify_durable_success,
)


class RecordingLogger:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def info(self, event: str, **kwargs: object) -> None:
        self.events.append({"event": event, **kwargs})


@pytest.fixture
def memory_fs():
    import fsspec

    fs = fsspec.filesystem("memory")
    fs.store.clear()
    return fs


def azure_lake(memory_fs) -> LakeStorage:
    return LakeStorage(
        raw=AzureStorageBackend("abfss://raw@acct.dfs.core.windows.net/", fs=memory_fs),
        bronze=AzureStorageBackend("abfss://bronze@acct.dfs.core.windows.net/", fs=memory_fs),
        silver=AzureStorageBackend("abfss://silver@acct.dfs.core.windows.net/", fs=memory_fs),
        gold=AzureStorageBackend("abfss://gold@acct.dfs.core.windows.net/", fs=memory_fs),
    )


def lake_with_local_zone(tmp_path: Path, memory_fs, local_zone: str) -> LakeStorage:
    zones = {
        "raw": AzureStorageBackend("abfss://raw@acct.dfs.core.windows.net/", fs=memory_fs),
        "bronze": AzureStorageBackend("abfss://bronze@acct.dfs.core.windows.net/", fs=memory_fs),
        "silver": AzureStorageBackend("abfss://silver@acct.dfs.core.windows.net/", fs=memory_fs),
        "gold": AzureStorageBackend("abfss://gold@acct.dfs.core.windows.net/", fs=memory_fs),
    }
    zones[local_zone] = LocalStorageBackend(tmp_path / local_zone)
    return LakeStorage(**zones)


@pytest.mark.parametrize("zone", ["raw", "bronze", "silver", "gold"])
def test_azure_runtime_with_any_local_zone_fails(tmp_path: Path, memory_fs, zone: str) -> None:
    lake = lake_with_local_zone(tmp_path, memory_fs, zone)
    env = {"CONTAINER_APP_JOB_EXECUTION_NAME": "job-run-1"}

    with pytest.raises(StorageRuntimeError, match=f"local_zones=\\['{zone}'\\]"):
        validate_cloud_storage_invariant(lake, env)


def test_azure_runtime_with_all_azure_roots_allowed(memory_fs) -> None:
    validate_cloud_storage_invariant(
        azure_lake(memory_fs), {"CONTAINER_APP_JOB_EXECUTION_NAME": "job-run-1"}
    )


def test_local_runtime_with_local_roots_allowed(tmp_path: Path) -> None:
    lake = LakeStorage.from_env({"CLIMATE_RISK_LAKE_ROOT": str(tmp_path)})
    validate_cloud_storage_invariant(lake, {})


def test_ephemeral_only_cloud_run_fails(tmp_path: Path) -> None:
    lake = LakeStorage.from_env({"CLIMATE_RISK_LAKE_ROOT": str(tmp_path / "ephemeral")})

    with pytest.raises(StorageRuntimeError, match="Azure Container Apps runtime requires"):
        validate_cloud_storage_invariant(
            lake, {"CONTAINER_APP_JOB_EXECUTION_NAME": "job-run-ephemeral"}
        )


def populate_successful_lake(lake: LakeStorage, *, run_id: str = "run-1") -> None:
    lake.raw.write_bytes(
        f"source=owid_co2/ingest_date=2026-08-22/run_id={run_id}/payload.bin", b"x"
    )
    lake.raw.write_bytes(
        f"source=owid_co2/ingest_date=2026-08-22/run_id={run_id}/manifest.json", b"{}"
    )
    lake.bronze.write_bytes("source=owid_co2/snapshot_id=abc/data.parquet", b"x")
    lake.silver.write_bytes("fact_country_year_transition/snapshot_set_id=s1/data.parquet", b"x")
    lake.silver.write_bytes("fact_country_year_energy/snapshot_set_id=e1/data.parquet", b"x")
    lake.gold.write_bytes("backtest_summary.parquet", b"x")
    lake.gold.write_bytes("country_transition_risk.parquet", b"x")
    lake.gold.write_bytes("country_transition_risk_v2.parquet", b"x")
    write_json(
        lake.gold,
        f"manifests/{run_id}.json",
        {
            "run_id": run_id,
            "score_version": "v2_energy",
            "v2_artifact": "country_transition_risk_v2.parquet",
        },
    )
    write_json(lake.gold, "latest_successful_run.json", {"run_id": run_id})


def test_required_raw_object_missing_fails(memory_fs) -> None:
    lake = azure_lake(memory_fs)
    populate_successful_lake(lake)
    for path in lake.raw.glob("source=*/ingest_date=*/run_id=*/payload.bin"):
        lake.raw.remove(path)

    with pytest.raises(StorageRuntimeError, match="raw_snapshots"):
        verify_durable_success(lake, expected_run_id="run-1")


def test_required_silver_artifact_missing_fails(memory_fs) -> None:
    lake = azure_lake(memory_fs)
    populate_successful_lake(lake)
    lake.silver.remove("fact_country_year_transition/snapshot_set_id=s1/data.parquet")

    with pytest.raises(StorageRuntimeError, match="silver_transition"):
        verify_durable_success(lake, expected_run_id="run-1")


def test_required_gold_artifact_missing_fails(memory_fs) -> None:
    lake = azure_lake(memory_fs)
    populate_successful_lake(lake)
    lake.gold.remove("country_transition_risk_v2.parquet")

    with pytest.raises(StorageRuntimeError, match="country_transition_risk_v2.parquet"):
        verify_durable_success(lake, expected_run_id="run-1")


def test_latest_pointer_absent_fails(memory_fs) -> None:
    lake = azure_lake(memory_fs)
    populate_successful_lake(lake)
    lake.gold.remove("latest_successful_run.json")

    with pytest.raises(StorageRuntimeError, match="latest_successful_run.json"):
        verify_durable_success(lake, expected_run_id="run-1")


def test_pointer_references_wrong_run_fails(memory_fs) -> None:
    lake = azure_lake(memory_fs)
    populate_successful_lake(lake, run_id="old-run")

    with pytest.raises(StorageRuntimeError, match="wrong_run_id"):
        verify_durable_success(lake, expected_run_id="new-run")


def test_referenced_manifest_unreadable_fails(memory_fs) -> None:
    lake = azure_lake(memory_fs)
    populate_successful_lake(lake)
    write_text(lake.gold, "manifests/run-1.json", "{not json")

    with pytest.raises(StorageRuntimeError, match="unreadable"):
        verify_durable_success(lake, expected_run_id="run-1")


def test_full_durable_verification_succeeds(memory_fs) -> None:
    lake = azure_lake(memory_fs)
    populate_successful_lake(lake)

    result = verify_durable_success(lake, expected_run_id="run-1")

    assert result["pointer_run_id"] == "run-1"
    assert result["score_version"] == "v2_energy"
    assert result["counts"]["raw_snapshots"] == 1


def test_backend_diagnostic_logs_contain_no_secrets(tmp_path: Path, memory_fs) -> None:
    lake = lake_with_local_zone(tmp_path, memory_fs, "gold")
    logger = RecordingLogger()

    log_backend_diagnostics(
        logger,
        lake,
        {
            "AZURE_CLIENT_ID": "client-id-secret-like",
            "AZURE_STORAGE_KEY": "storage-key-secret",
            "CLIMATE_RISK_GOLD_ROOT": str(tmp_path / "gold"),
        },
    )

    rendered = repr(logger.events)
    assert "client-id-secret-like" not in rendered
    assert "storage-key-secret" not in rendered
    assert all(event["event"] == "storage backend selected" for event in logger.events)

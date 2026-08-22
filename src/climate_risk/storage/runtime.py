"""Runtime storage invariants and durable-output verification."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

from climate_risk.storage.azure import AzureStorageBackend
from climate_risk.storage.base import StorageBackend, read_json
from climate_risk.storage.lake import ZONES, LakeStorage, _zone_uri
from climate_risk.storage.local import LocalStorageBackend


class StorageRuntimeError(RuntimeError):
    """Raised when runtime storage configuration or durability is unsafe."""


class DiagnosticLogger(Protocol):
    def info(self, event: str, **kwargs: object) -> None: ...


@dataclass(frozen=True, slots=True)
class BackendDiagnostic:
    zone: str
    backend: str
    location: str


def is_azure_container_apps_job(env: dict[str, str] | None = None) -> bool:
    """True when running inside Azure Container Apps Jobs.

    `CLIMATE_RISK_REQUIRE_AZURE_STORAGE` is a test/manual override that
    intentionally makes the production invariant explicit.
    """
    env = env if env is not None else dict(os.environ)
    return any(
        env.get(key)
        for key in (
            "CONTAINER_APP_JOB_EXECUTION_NAME",
            "CONTAINER_APP_JOB_NAME",
            "CONTAINER_APP_NAME",
            "CLIMATE_RISK_REQUIRE_AZURE_STORAGE",
        )
    )


def backend_diagnostics(
    lake: LakeStorage, env: dict[str, str] | None = None
) -> list[BackendDiagnostic]:
    env = env if env is not None else dict(os.environ)
    diagnostics: list[BackendDiagnostic] = []
    for zone in ZONES:
        backend = getattr(lake, zone)
        diagnostics.append(
            BackendDiagnostic(
                zone=zone,
                backend=type(backend).__name__,
                location=_sanitized_location(zone, backend, env),
            )
        )
    return diagnostics


def log_backend_diagnostics(
    logger: DiagnosticLogger,
    lake: LakeStorage,
    env: dict[str, str] | None = None,
) -> None:
    for diagnostic in backend_diagnostics(lake, env):
        logger.info(
            "storage backend selected",
            zone=diagnostic.zone,
            backend=diagnostic.backend,
            location=diagnostic.location,
        )


def validate_cloud_storage_invariant(lake: LakeStorage, env: dict[str, str] | None = None) -> None:
    env = env if env is not None else dict(os.environ)
    if not is_azure_container_apps_job(env):
        return

    local_zones = [zone for zone in ZONES if isinstance(getattr(lake, zone), LocalStorageBackend)]
    non_azure_zones = [
        zone for zone in ZONES if not isinstance(getattr(lake, zone), AzureStorageBackend)
    ]
    if local_zones or non_azure_zones:
        details = ", ".join(
            f"{d.zone}={d.backend}({d.location})" for d in backend_diagnostics(lake, env)
        )
        raise StorageRuntimeError(
            "Azure Container Apps runtime requires all lake zones to use ADLS/abfss "
            f"storage; local_zones={local_zones}, non_azure_zones={non_azure_zones}; {details}"
        )


def prepare_lake_from_env(
    logger: DiagnosticLogger,
    env: dict[str, str] | None = None,
    *,
    ensure_zones: bool = False,
) -> LakeStorage:
    env = env if env is not None else dict(os.environ)
    lake = LakeStorage.from_env(env)
    log_backend_diagnostics(logger, lake, env)
    validate_cloud_storage_invariant(lake, env)
    if ensure_zones:
        lake.ensure_zones()
    return lake


def verify_durable_success(
    lake: LakeStorage, *, require_energy: bool = True, expected_run_id: str | None = None
) -> dict[str, object]:
    """Verify durable artifacts after publish, using storage reads/exists.

    This check is intentionally independent of in-process stage success:
    a cloud run is successful only when the backend can re-read the objects
    that downstream consumers need.
    """
    required_globs = {
        "raw_snapshots": "source=*/ingest_date=*/run_id=*/payload.bin",
        "raw_manifests": "source=*/ingest_date=*/run_id=*/manifest.json",
        "bronze_artifacts": "source=*/snapshot_id=*/data.parquet",
        "silver_transition": "fact_country_year_transition/snapshot_set_id=*/data.parquet",
        "silver_energy": "fact_country_year_energy/snapshot_set_id=*/data.parquet",
    }
    counts = {
        name: len(getattr(lake, _zone_for_glob(name)).glob(pattern))
        for name, pattern in required_globs.items()
    }

    missing: list[str] = []
    for name, count in counts.items():
        if name == "silver_energy" and not require_energy:
            continue
        if count <= 0:
            missing.append(name)

    required_gold = [
        "backtest_summary.parquet",
        "country_transition_risk.parquet",
        "country_transition_risk_v2.parquet",
        "latest_successful_run.json",
    ]
    for path in required_gold:
        if not lake.gold.exists(path):
            missing.append(f"gold:{path}")

    pointer: dict[str, object] | None = None
    manifest: dict[str, object] | None = None
    manifest_path: str | None = None
    if lake.gold.exists("latest_successful_run.json"):
        pointer_obj = read_json(lake.gold, "latest_successful_run.json")
        if not isinstance(pointer_obj, dict):
            missing.append("gold:latest_successful_run.json:not_object")
        else:
            pointer = pointer_obj
            run_id = pointer.get("run_id")
            if isinstance(run_id, str) and run_id:
                if expected_run_id is not None and run_id != expected_run_id:
                    missing.append("gold:latest_successful_run.json:wrong_run_id")
                manifest_path = f"manifests/{run_id}.json"
                if not lake.gold.exists(manifest_path):
                    missing.append(f"gold:{manifest_path}")
                else:
                    manifest_obj = None
                    try:
                        manifest_obj = read_json(lake.gold, manifest_path)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        missing.append(f"gold:{manifest_path}:unreadable")
                    else:
                        if not isinstance(manifest_obj, dict):
                            missing.append(f"gold:{manifest_path}:not_object")
                            manifest_obj = None
                    if isinstance(manifest_obj, dict):
                        manifest = manifest_obj
                        if manifest.get("run_id") != run_id:
                            missing.append("gold:manifest_run_id_mismatch")
                        active_artifact = manifest.get("v2_artifact") or manifest.get(
                            "active_score_artifact"
                        )
                        if isinstance(active_artifact, str):
                            if not lake.gold.exists(active_artifact):
                                missing.append(f"gold:{active_artifact}")
                        else:
                            missing.append("gold:active_score_artifact_missing")
            else:
                missing.append("gold:latest_successful_run.json:run_id_missing")

    if missing:
        raise StorageRuntimeError(
            "durable success verification failed; missing or unreadable artifacts: "
            + ", ".join(missing)
        )

    return {
        "counts": counts,
        "pointer_run_id": pointer.get("run_id") if pointer else None,
        "manifest_path": manifest_path,
        "score_version": manifest.get("score_version") if manifest else None,
    }


def _zone_for_glob(name: str) -> str:
    if name.startswith("raw_"):
        return "raw"
    if name.startswith("bronze_"):
        return "bronze"
    if name.startswith("silver_"):
        return "silver"
    raise ValueError(name)


def _sanitized_location(zone: str, backend: StorageBackend, env: dict[str, str]) -> str:
    if isinstance(backend, AzureStorageBackend):
        return f"abfss://{backend.container}@{backend.account_name}.dfs.core.windows.net/"
    if isinstance(backend, LocalStorageBackend):
        return str(backend.root)
    return _zone_uri(zone, env)

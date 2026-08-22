"""Zone-aware lake storage: the `RunPaths` replacement.

Each zone (raw, bronze, silver, gold) gets its own `StorageBackend`,
independently rooted -- this matches the Azure design's four separate
ADLS Gen2 filesystems, which have no shared account-level parent path
(there is no valid `abfss://<account>/..` above them). A single
`CLIMATE_RISK_LAKE_ROOT` env var is still honoured as a local-dev
convenience default (each zone becomes `<lake_root>/<zone>`); explicit
per-zone env vars (`CLIMATE_RISK_RAW_ROOT` etc.) always take precedence
and are how Azure wires in four distinct `abfss://` URIs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from climate_risk.config.loader import REPO_ROOT
from climate_risk.storage.azure import AzureStorageBackend
from climate_risk.storage.base import StorageBackend
from climate_risk.storage.local import LocalStorageBackend

ZONES = ("raw", "bronze", "silver", "gold")


def backend_for_uri(uri: str) -> StorageBackend:
    """The one place this codebase branches on storage scheme.

    Everywhere else talks only to the `StorageBackend` protocol.
    """
    if uri.startswith("abfss://"):
        return AzureStorageBackend(uri)
    return LocalStorageBackend(Path(uri))


def _zone_uri(zone: str, env: dict[str, str]) -> str:
    explicit = env.get(f"CLIMATE_RISK_{zone.upper()}_ROOT")
    if explicit:
        return explicit
    lake_root = env.get("CLIMATE_RISK_LAKE_ROOT", str(REPO_ROOT / "data" / "lake"))
    return f"{lake_root.rstrip('/')}/{zone}"


@dataclass(frozen=True, slots=True)
class LakeStorage:
    """The four zone backends a pipeline run reads/writes."""

    raw: StorageBackend
    bronze: StorageBackend
    silver: StorageBackend
    gold: StorageBackend

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> LakeStorage:
        env = env if env is not None else dict(os.environ)
        return cls(**{zone: backend_for_uri(_zone_uri(zone, env)) for zone in ZONES})

    def ensure_zones(self) -> None:
        for zone in ZONES:
            getattr(self, zone).makedirs("")

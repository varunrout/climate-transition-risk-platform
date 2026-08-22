"""Configuration and path loading.

Environment variables carry only deployment-specific values (lake root,
storage account). Analytical configuration (sources, countries, features,
quality rules) is versioned YAML under config/, loaded here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from climate_risk.config.models import CountryConfig, SourceConfig

REPO_ROOT = Path(__file__).resolve().parents[3]
# In a repo checkout (editable install) config/ sits 3 levels above this file.
# In the production container the package is installed non-editable into a
# venv's site-packages, so that relationship no longer holds -- the
# Dockerfile copies config/ to /app/config and sets CLIMATE_RISK_CONFIG_DIR
# accordingly. Read once at import time: it must be set before the process
# starts, which is how container ENV and shell exports both work.
CONFIG_DIR = Path(os.environ.get("CLIMATE_RISK_CONFIG_DIR", str(REPO_ROOT / "config")))


@dataclass(frozen=True, slots=True)
class RunPaths:
    """Filesystem lake root and derived zone paths.

    Local-first: the same logical zone layout (raw/bronze/silver/gold) maps
    to ADLS Gen2 containers in the Azure target state without code changes —
    only this root changes.
    """

    lake_root: Path

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> RunPaths:
        env = env if env is not None else dict(os.environ)
        root = env.get("CLIMATE_RISK_LAKE_ROOT", str(REPO_ROOT / "data" / "lake"))
        return cls(lake_root=Path(root))

    @property
    def raw(self) -> Path:
        return self.lake_root / "raw"

    @property
    def bronze(self) -> Path:
        return self.lake_root / "bronze"

    @property
    def silver(self) -> Path:
        return self.lake_root / "silver"

    @property
    def gold(self) -> Path:
        return self.lake_root / "gold"

    def ensure_zones(self) -> None:
        for zone in (self.raw, self.bronze, self.silver, self.gold):
            zone.mkdir(parents=True, exist_ok=True)


def load_source_registry(path: Path | None = None) -> dict[str, SourceConfig]:
    path = path or (CONFIG_DIR / "sources.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    sources: dict[str, SourceConfig] = {}
    for key, entry in raw["sources"].items():
        sources[key] = SourceConfig(key=key, **entry)
    return sources


def load_countries(path: Path | None = None) -> dict[str, CountryConfig]:
    path = path or (CONFIG_DIR / "countries.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    countries: dict[str, CountryConfig] = {}
    for entry in raw["countries"]:
        country = CountryConfig(**entry)
        countries[country.country_iso3] = country
    return countries

"""Configuration and path loading.

Environment variables carry only deployment-specific values (lake root,
storage account). Analytical configuration (sources, countries, features,
quality rules) is versioned YAML under config/, loaded here.
"""

from __future__ import annotations

import os
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

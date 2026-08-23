"""Loads the published gold/web bundle once at process startup and serves
typed, validated in-memory lookups.

This is a read-only cache over already-published artifacts -- it never
recomputes risk scores, scenarios, or diagnostics, and never re-reads
storage per request. Deliberately plain Python (list[dict]), not pandas:
the bundle is already JSON-safe (no NaN, see `climate_risk.bi.web_publish`)
and round-tripping it through a DataFrame would silently reintroduce NaN
for missing values, which is exactly the bug that module exists to avoid.
See docs/api/contracts.md.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from climate_risk.bi.web_publish import (
    RUN_METADATA_SAFE_FIELDS,
    WEB_PREFIX,
    WEB_SCHEMA_VERSION,
)
from climate_risk.scoring.risk_score_v2_energy import SCORE_VERSION
from climate_risk.storage import LakeStorage, read_text

EXPECTED_ACTIVE_SCORE_VERSION = SCORE_VERSION  # "v2_energy"
EXPECTED_PRODUCTION_SCENARIO_METHOD = "empirical_bootstrap_v1"
SUPPORTED_DATA_SCHEMA_VERSIONS = {WEB_SCHEMA_VERSION}

WEB_FILES = [
    "manifest",
    "countries",
    "country-overview",
    "country-timeseries",
    "risk-components",
    "scenario-quantiles",
    "backtest-metrics",
    "energy-indicators",
    "regime-diagnostics",
    "run-metadata",
]


class StartupValidationError(RuntimeError):
    """Raised when the published bundle is missing, corrupt, or unexpected.

    The API fails to start rather than serve partially invalid analytics
    -- see spec section 11 / docs/api/contracts.md.
    """


Record = dict[str, Any]


@dataclass(frozen=True)
class Bundle:
    manifest: Record
    countries: list[Record]
    country_overview: list[Record]
    country_timeseries: list[Record]
    risk_components: list[Record]
    scenario_quantiles: list[Record]
    backtest_metrics: list[Record]
    energy_indicators: list[Record]
    regime_diagnostics: list[Record]
    run_metadata: Record

    def country(self, iso3: str) -> Record | None:
        return next((r for r in self.country_overview if r["country_iso3"] == iso3), None)

    def country_exists(self, iso3: str) -> bool:
        return self.country(iso3) is not None


def _sha256_of(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_bundle(lake: LakeStorage) -> Bundle:
    """Read every gold/web/*.json file, verify integrity against the
    manifest, and parse into in-memory tables. Raises
    StartupValidationError on any inconsistency."""
    missing = [name for name in WEB_FILES if not lake.gold.exists(f"{WEB_PREFIX}/{name}.json")]
    if missing:
        raise StartupValidationError(
            f"gold/web bundle is missing required file(s): {missing}. "
            "Run `climate-risk build-web` before starting the API."
        )

    raw: dict[str, str] = {
        name: read_text(lake.gold, f"{WEB_PREFIX}/{name}.json") for name in WEB_FILES
    }

    try:
        manifest = json.loads(raw["manifest"])
    except json.JSONDecodeError as exc:
        raise StartupValidationError(f"gold/web/manifest.json is not valid JSON: {exc}") from exc

    schema_version = manifest.get("schema_version")
    if schema_version not in SUPPORTED_DATA_SCHEMA_VERSIONS:
        raise StartupValidationError(
            f"gold/web bundle schema version {schema_version!r} is not supported by this "
            f"API build (supports {sorted(SUPPORTED_DATA_SCHEMA_VERSIONS)}). Rebuild the "
            "bundle or upgrade the API."
        )

    active_score_version = manifest.get("active_score_version")
    if active_score_version != EXPECTED_ACTIVE_SCORE_VERSION:
        raise StartupValidationError(
            f"gold/web bundle declares active_score_version={active_score_version!r}, "
            f"expected {EXPECTED_ACTIVE_SCORE_VERSION!r}. Refusing to serve a bundle whose "
            "production score has drifted from what this API build expects."
        )

    production_scenario_method = manifest.get("active_scenario_method")
    if production_scenario_method != EXPECTED_PRODUCTION_SCENARIO_METHOD:
        raise StartupValidationError(
            f"gold/web bundle declares active_scenario_method={production_scenario_method!r}, "
            f"expected {EXPECTED_PRODUCTION_SCENARIO_METHOD!r}."
        )

    file_entries = {f["name"]: f for f in manifest.get("files", [])}
    parsed: dict[str, Any] = {}
    for name in WEB_FILES:
        if name == "manifest":
            continue
        entry = file_entries.get(f"{name}.json")
        if entry is None:
            raise StartupValidationError(f"manifest.json has no entry for {name}.json.")
        records = json.loads(raw[name])
        actual_hash = _sha256_of(json.dumps(records, sort_keys=True, separators=(",", ":")))
        if actual_hash != entry.get("sha256"):
            raise StartupValidationError(
                f"{name}.json content does not match its manifest SHA-256 -- the bundle may "
                "be corrupted or the manifest is stale."
            )
        if len(records) != entry.get("row_count"):
            raise StartupValidationError(
                f"{name}.json row count ({len(records)}) does not match the manifest "
                f"({entry.get('row_count')})."
            )
        parsed[name] = records

    seen_iso3: set[str] = set()
    for row in parsed["country-overview"]:
        iso3 = row["country_iso3"]
        if iso3 in seen_iso3:
            raise StartupValidationError(
                f"country-overview.json has duplicate country_iso3={iso3!r}."
            )
        seen_iso3.add(iso3)

    run_metadata_rows = parsed["run-metadata"]
    if not run_metadata_rows:
        raise StartupValidationError("run-metadata.json contained no rows.")
    run_metadata = run_metadata_rows[0]
    unsafe_fields = set(run_metadata.keys()) - set(RUN_METADATA_SAFE_FIELDS)
    if unsafe_fields:
        raise StartupValidationError(
            f"run-metadata.json contains fields outside the public safelist: {unsafe_fields}."
        )

    return Bundle(
        manifest=manifest,
        countries=parsed["countries"],
        country_overview=parsed["country-overview"],
        country_timeseries=parsed["country-timeseries"],
        risk_components=parsed["risk-components"],
        scenario_quantiles=parsed["scenario-quantiles"],
        backtest_metrics=parsed["backtest-metrics"],
        energy_indicators=parsed["energy-indicators"],
        regime_diagnostics=parsed["regime-diagnostics"],
        run_metadata=run_metadata,
    )


def normalize_iso3(iso3: str) -> str:
    return iso3.strip().upper()

"""Deterministic web publication layer, downstream of gold/bi.

Browsers should not consume Parquet directly. This module selects,
serializes, and validates the already-computed `gold/bi/*.parquet` tables
into browser-safe JSON under `gold/web/`. It does not recompute risk
scoring, scenario generation, backtesting, or structural-break logic --
that logic lives upstream in `climate_risk.bi.publish` and the modules it
reads from.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from climate_risk.bi.publish import BI_PREFIX
from climate_risk.storage import LakeStorage, read_parquet, write_text

WEB_PREFIX = "web"
WEB_SCHEMA_VERSION = "1.0.0"

# gold/bi table name -> web file stem
TABLE_TO_WEB_FILE = {
    "country_overview": "country-overview",
    "country_timeseries": "country-timeseries",
    "risk_components": "risk-components",
    "scenario_quantiles": "scenario-quantiles",
    "backtest_metrics": "backtest-metrics",
    "energy_indicators": "energy-indicators",
    "regime_diagnostics": "regime-diagnostics",
    "run_metadata": "run-metadata",
}

# run_metadata fields that are safe to publish to a public static frontend.
# Deliberately excludes local/lake-relative source paths and the Azure job
# execution id -- not needed by the product and not worth publishing.
RUN_METADATA_SAFE_FIELDS = [
    "run_id",
    "started_at",
    "completed_at",
    "generated_at",
    "publish_status",
    "active_score_version",
    "component_version",
    "weights_version",
    "production_scenario_method",
    "git_sha",
    "image_ref",
    "image_digest",
    "config_hash",
    "transition_snapshot_id",
    "owid_co2_snapshot_id",
    "world_bank_wdi_snapshot_id",
    "owid_energy_snapshot_id",
    "latest_model_eligible_year",
    "latest_model_eligible_year_completeness",
    "bi_version",
]


def json_safe(value: Any) -> Any:
    """Convert a single scalar value into something `json.dumps` can handle.

    Handles NaN/Infinity/-Infinity (-> None), numpy scalar types (-> native
    Python), pandas NA/NaT (-> None), and pandas/py Timestamps (-> ISO 8601).
    """
    if value is None:
        return None
    if isinstance(value, bool | np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, float | np.floating):
        f = float(value)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, np.datetime64):
        ts = pd.Timestamp(value)
        return None if pd.isna(ts) else ts.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, np.ndarray):
        return [json_safe(v) for v in value.tolist()]
    return value


def dataframe_to_records(
    frame: pd.DataFrame, *, fields: list[str] | None = None
) -> list[dict[str, Any]]:
    """Convert a DataFrame into a list of JSON-safe row dicts.

    `fields`, when given, both selects and orders the output columns --
    used to keep an explicit safelist (e.g. run_metadata) rather than
    forwarding every column verbatim.
    """
    columns = fields if fields is not None else list(frame.columns)
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        records.append({col: json_safe(row.get(col)) for col in columns})
    return records


def _sha256_of(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_web_bundle(lake: LakeStorage) -> dict[str, list[dict[str, Any]]]:
    """Read every gold/bi table and return web-file-stem -> JSON-safe records."""
    bundle: dict[str, list[dict[str, Any]]] = {}
    for table_name, file_stem in TABLE_TO_WEB_FILE.items():
        frame = read_parquet(lake.gold, f"{BI_PREFIX}/{table_name}.parquet")
        fields = RUN_METADATA_SAFE_FIELDS if table_name == "run_metadata" else None
        bundle[file_stem] = dataframe_to_records(frame, fields=fields)

    # A small navigation/search index -- avoids the frontend loading the full
    # country-overview payload just to populate a selector or search box.
    overview = bundle["country-overview"]
    bundle["countries"] = [
        {
            "country_iso3": row.get("country_iso3"),
            "country_name": row.get("country_name"),
            "region": row.get("region"),
            "income_group": row.get("income_group"),
        }
        for row in overview
    ]
    return bundle


def build_manifest(
    bundle: dict[str, list[dict[str, Any]]], *, generated_at: str | None = None
) -> dict[str, Any]:
    """Build manifest.json content: bundle-level provenance plus a per-file
    integrity/row-count listing, and a bundle-wide hash for cheap client-side
    staleness/corruption detection.
    """
    run_metadata_rows = bundle.get("run-metadata", [])
    run_metadata = run_metadata_rows[0] if run_metadata_rows else {}
    country_overview = bundle.get("country-overview", [])

    files: list[dict[str, Any]] = []
    file_hashes: list[str] = []
    for file_stem in sorted(bundle):
        payload = json.dumps(bundle[file_stem], sort_keys=True, separators=(",", ":"))
        digest = _sha256_of(payload)
        file_hashes.append(digest)
        files.append(
            {
                "name": f"{file_stem}.json",
                "row_count": len(bundle[file_stem]),
                "sha256": digest,
                "schema_version": WEB_SCHEMA_VERSION,
            }
        )

    manifest = {
        "schema_version": WEB_SCHEMA_VERSION,
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "source_run_id": run_metadata.get("run_id"),
        "source_git_sha": run_metadata.get("git_sha"),
        "active_score_version": run_metadata.get("active_score_version"),
        "active_component_version": run_metadata.get("component_version"),
        "active_scenario_method": run_metadata.get("production_scenario_method"),
        "model_eligible_year": run_metadata.get("latest_model_eligible_year"),
        "country_count": len(country_overview),
        "source_snapshot_ids": {
            "owid_co2": run_metadata.get("owid_co2_snapshot_id"),
            "world_bank_wdi": run_metadata.get("world_bank_wdi_snapshot_id"),
            "owid_energy": run_metadata.get("owid_energy_snapshot_id"),
        },
        "config_hash": run_metadata.get("config_hash"),
        "web_bundle_hash": _sha256_of("".join(file_hashes)),
        "files": files,
    }
    return manifest


def write_web_bundle(
    lake: LakeStorage,
    bundle: dict[str, list[dict[str, Any]]],
    manifest: dict[str, Any],
) -> None:
    for file_stem, records in bundle.items():
        write_text(lake.gold, f"{WEB_PREFIX}/{file_stem}.json", json.dumps(records, indent=2))
    write_text(lake.gold, f"{WEB_PREFIX}/manifest.json", json.dumps(manifest, indent=2))

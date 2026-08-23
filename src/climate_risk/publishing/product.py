"""Downstream product publication: gold/bi + gold/web, verified.

This is deliberately separate from `climate_risk.publishing.barrier`, which
gates the core analytical release (`gold/latest_successful_run.json`). That
barrier must stay exactly as strict as it is today -- a failed or missing
core stage must block the whole release.

gold/bi and gold/web are downstream *product* publication: they reshape an
already-published core release for BI/web consumption and never recompute
scoring, scenarios, or diagnostics (see `climate_risk.bi.publish` and
`climate_risk.bi.web_publish`). A failure here must never roll back or
corrupt a valid core analytical publication -- but it must be loud, not
silent, so operational monitoring (e.g. Azure Container Apps Job exit code)
sees the product layer went stale.

`publish_product()` requires a core publish to have already happened
(`gold/latest_successful_run.json` must exist), builds gold/bi then gold/web
from it, and then re-reads everything back from storage to verify the
result is complete and internally consistent before declaring success --
the same "trust the backend read, not just the in-process write" pattern
used by `climate_risk.storage.runtime.verify_durable_success` for the core
release.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from climate_risk.bi.publish import (
    PRODUCTION_SCENARIO_METHOD,
    build_bi_artifacts,
    write_bi_artifacts,
)
from climate_risk.bi.web_publish import (
    RUN_METADATA_SAFE_FIELDS,
    TABLE_TO_WEB_FILE,
    WEB_PREFIX,
    WEB_SCHEMA_VERSION,
    build_manifest,
    build_web_bundle,
    write_web_bundle,
)
from climate_risk.publishing.barrier import POINTER_PATH
from climate_risk.scoring.risk_score_v2_energy import SCORE_VERSION as ACTIVE_SCORE_VERSION
from climate_risk.storage import LakeStorage, read_json, read_text

BI_PREFIX = "bi"


class ProductPublicationError(RuntimeError):
    """Raised when downstream BI/web product publication fails or cannot be verified.

    Never raised in a way that touches `gold/latest_successful_run.json` or
    any core-release artifact -- only gold/bi/* and gold/web/* are written
    or checked here.
    """


class DiagnosticLogger(Protocol):
    def info(self, event: str, **kwargs: object) -> None: ...


@dataclass(frozen=True, slots=True)
class ProductPublicationResult:
    run_id: str
    bi_table_count: int
    web_file_count: int
    web_bundle_hash: str


def publish_product(
    lake: LakeStorage, logger: DiagnosticLogger, *, scenario_target_year: int = 2030
) -> ProductPublicationResult:
    """Build and verify gold/bi + gold/web for the current core release.

    Raises `ProductPublicationError` (never a bare exception from a deeper
    module) on any failure -- missing core release, a build error, or a
    post-write verification mismatch.
    """
    expected_run_id = _require_core_release(lake)

    try:
        bi_artifacts = build_bi_artifacts(lake, scenario_target_year=scenario_target_year)
        write_bi_artifacts(lake, bi_artifacts)

        bundle = build_web_bundle(lake)
        manifest = build_manifest(bundle)
        write_web_bundle(lake, bundle, manifest)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: any build/write
        # failure here must surface as a ProductPublicationError, never as an
        # uncaught exception that could be mistaken for a core-publish failure.
        raise ProductPublicationError(
            f"product publication build failed (core release {expected_run_id!r} is "
            f"untouched and remains the latest valid release): {exc}"
        ) from exc

    verification = verify_product_publication(lake, expected_run_id=expected_run_id)
    logger.info("product publication verified", **verification)

    return ProductPublicationResult(
        run_id=expected_run_id,
        bi_table_count=len(bi_artifacts.as_dict()),
        web_file_count=len(bundle) + 1,
        web_bundle_hash=manifest["web_bundle_hash"],
    )


def verify_product_publication(lake: LakeStorage, *, expected_run_id: str) -> dict[str, object]:
    """Re-read gold/bi and gold/web from storage and verify completeness,
    per-file integrity, and correspondence to `expected_run_id`.

    Deliberately independent of `climate_risk.api.repository` (which
    performs an equivalent check at API startup): the core pipeline must
    not depend on the read-only serving layer, or vice versa become
    entangled beyond the shared gold/bi + gold/web contract.
    """
    missing: list[str] = []

    for table_name in TABLE_TO_WEB_FILE:
        path = f"{BI_PREFIX}/{table_name}.parquet"
        if not lake.gold.exists(path):
            missing.append(f"gold:{path}")

    manifest_path = f"{WEB_PREFIX}/manifest.json"
    if not lake.gold.exists(manifest_path):
        missing.append(f"gold:{manifest_path}")
        raise ProductPublicationError(
            "product publication verification failed; missing: " + ", ".join(missing)
        )

    manifest_text = read_text(lake.gold, manifest_path)
    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        raise ProductPublicationError(
            f"gold:{manifest_path} is not valid JSON after write: {exc}"
        ) from exc
    if not isinstance(manifest, dict):
        missing.append(f"gold:{manifest_path}:not_object")

    if isinstance(manifest, dict):
        if manifest.get("schema_version") != WEB_SCHEMA_VERSION:
            missing.append("gold:manifest:schema_version_mismatch")
        if manifest.get("source_run_id") != expected_run_id:
            missing.append(
                f"gold:manifest:source_run_id_mismatch "
                f"(expected={expected_run_id!r}, actual={manifest.get('source_run_id')!r})"
            )
        if manifest.get("active_score_version") != ACTIVE_SCORE_VERSION:
            missing.append("gold:manifest:active_score_version_mismatch")
        if manifest.get("active_scenario_method") != PRODUCTION_SCENARIO_METHOD:
            missing.append("gold:manifest:active_scenario_method_mismatch")

        files_by_name = {f["name"]: f for f in manifest.get("files", []) if isinstance(f, dict)}
        expected_stems = set(TABLE_TO_WEB_FILE.values()) | {"countries"}
        for stem in expected_stems:
            name = f"{stem}.json"
            path = f"{WEB_PREFIX}/{name}"
            if name not in files_by_name:
                missing.append(f"gold:manifest:missing_file_entry:{name}")
                continue
            if not lake.gold.exists(path):
                missing.append(f"gold:{path}")
                continue
            text = read_text(lake.gold, path)
            if "NaN" in text or "Infinity" in text:
                missing.append(f"gold:{path}:non_finite_literal_present")
            try:
                records = json.loads(text)
            except json.JSONDecodeError as exc:
                missing.append(f"gold:{path}:invalid_json:{exc}")
                continue
            # Matches climate_risk.bi.web_publish.build_manifest's hashing:
            # the manifest hashes a canonical compact/sorted re-serialization
            # of the records, not the on-disk indented bytes -- so
            # verification must hash the same canonical form (also how
            # climate_risk.api.repository re-verifies this at API startup).
            canonical_payload = json.dumps(records, sort_keys=True, separators=(",", ":"))
            actual_sha256 = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
            expected_entry = files_by_name[name]
            if actual_sha256 != expected_entry.get("sha256"):
                missing.append(f"gold:{path}:sha256_mismatch")
            if len(records) != expected_entry.get("row_count"):
                missing.append(f"gold:{path}:row_count_mismatch")

        run_metadata_path = f"{WEB_PREFIX}/run-metadata.json"
        if lake.gold.exists(run_metadata_path):
            run_metadata_rows = json.loads(read_text(lake.gold, run_metadata_path))
            if run_metadata_rows:
                unexpected_fields = set(run_metadata_rows[0]) - set(RUN_METADATA_SAFE_FIELDS)
                if unexpected_fields:
                    missing.append(f"gold:{run_metadata_path}:unsafe_fields:{unexpected_fields}")

    if missing:
        raise ProductPublicationError(
            "product publication verification failed; missing or inconsistent: "
            + ", ".join(missing)
        )

    return {
        "source_run_id": manifest.get("source_run_id") if isinstance(manifest, dict) else None,
        "web_bundle_hash": manifest.get("web_bundle_hash") if isinstance(manifest, dict) else None,
        "country_count": manifest.get("country_count") if isinstance(manifest, dict) else None,
        "file_count": len(files_by_name) if isinstance(manifest, dict) else 0,
    }


def _require_core_release(lake: LakeStorage) -> str:
    if not lake.gold.exists(POINTER_PATH):
        raise ProductPublicationError(
            "no core analytical publication found (gold/latest_successful_run.json is "
            "missing); run `climate-risk publish` (or `climate-risk run`) first -- product "
            "publication reshapes an already-published core release and never runs standalone"
        )
    pointer = read_json(lake.gold, POINTER_PATH)
    if not isinstance(pointer, dict) or not pointer.get("run_id"):
        raise ProductPublicationError("gold/latest_successful_run.json has no run_id")
    return str(pointer["run_id"])

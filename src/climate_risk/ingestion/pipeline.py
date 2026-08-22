"""Source-agnostic ingestion orchestration (01_data_ingestion.md sections 3-6, 11).

Zone layout mirrors the target ADLS Gen2 filesystems:

    raw/source=<source>/ingest_date=YYYY-MM-DD/run_id=<uuid>/payload.bin
                                                              manifest.json
    bronze/source=<source>/snapshot_id=<sha256-prefix>/data.parquet

Raw payload bytes are never overwritten (each run_id gets its own
directory); a repeated identical payload still records a manifest but bronze
promotion only happens when validation contains no FATAL event ("fail
closed" — a rejected snapshot stays quarantined under raw/ and never
reaches bronze, so the previously accepted bronze snapshot for this source
is left untouched).

Adapters only fetch and parse bytes in memory (climate_risk.ingestion.base);
this module is the only place that writes to storage, via the
backend-neutral `StorageBackend` protocol -- see ADR 0003 for why that
separation matters.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from climate_risk.contracts.models import (
    IngestManifest,
    IngestStatus,
    QualitySeverity,
)
from climate_risk.contracts.run import resolve_git_sha
from climate_risk.ingestion.base import SourceAdapter
from climate_risk.observability.logging import get_logger
from climate_risk.storage import LakeStorage, write_parquet, write_text


def run_ingest(adapter: SourceAdapter, *, lake: LakeStorage, run_id: str) -> IngestManifest:
    log = get_logger(stage="ingest", source=adapter.source_name, run_id=run_id)
    start = datetime.now(UTC)

    artifact, raw_bytes = adapter.fetch()

    transport_report = adapter.validate_transport(artifact)
    row_count: int | None = None
    schema_fingerprint = ""
    quality_report = transport_report
    frame: pd.DataFrame | None = None

    if not transport_report.has_fatal:
        schema_fingerprint = adapter.fingerprint_schema(artifact, raw_bytes)
        frame = adapter.standardise(artifact, raw_bytes)
        row_count = len(frame)
        dataset_report = adapter.quality_checks(frame)
        quality_report = quality_report.model_copy(
            update={"events": [*transport_report.events, *dataset_report.events]}
        )

    status = _resolve_status(quality_report.has_fatal)

    manifest = IngestManifest(
        run_id=run_id,
        source_name=adapter.source_name,
        source_url=artifact.source_url,
        retrieved_at_utc=artifact.retrieved_at_utc,
        http_status=artifact.http_status,
        etag=artifact.etag,
        last_modified=artifact.last_modified,
        content_length=artifact.content_length,
        sha256=artifact.sha256,
        schema_fingerprint=schema_fingerprint,
        parser_version=adapter.parser_version,
        git_commit=resolve_git_sha(),
        status=status,
        row_count=row_count,
        validation=quality_report,
    )

    ingest_date = start.date().isoformat()
    raw_prefix = f"source={adapter.source_name}/ingest_date={ingest_date}/run_id={run_id}"
    lake.raw.write_bytes(f"{raw_prefix}/payload.bin", raw_bytes)
    write_text(lake.raw, f"{raw_prefix}/manifest.json", manifest.model_dump_json(indent=2))

    for event in quality_report.events:
        level = {
            QualitySeverity.INFO: "info",
            QualitySeverity.WARN: "warning",
            QualitySeverity.ERROR: "error",
            QualitySeverity.FATAL: "error",
        }[event.severity]
        getattr(log, level)("quality event", rule_id=event.rule_id, message=event.message)

    if status == IngestStatus.ACCEPTED and frame is not None:
        snapshot_id = artifact.sha256[:16]
        bronze_path = f"source={adapter.source_name}/snapshot_id={snapshot_id}/data.parquet"
        write_parquet(lake.bronze, bronze_path, frame)
    else:
        log.warning(
            "snapshot quarantined, not promoted to bronze",
            status=status.value,
            fatal_events=len(quality_report.by_severity(QualitySeverity.FATAL)),
        )

    duration_s = (datetime.now(UTC) - start).total_seconds()
    log.info("ingest run finished", status=status.value, duration_s=duration_s, row_count=row_count)
    return manifest


def _resolve_status(has_fatal: bool) -> IngestStatus:
    return IngestStatus.REJECTED if has_fatal else IngestStatus.ACCEPTED

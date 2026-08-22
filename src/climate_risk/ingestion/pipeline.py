"""Source-agnostic ingestion orchestration (01_data_ingestion.md sections 3-6, 11).

Layout on disk mirrors the target ADLS Gen2 layout:

    raw/source=<source>/ingest_date=YYYY-MM-DD/run_id=<uuid>/payload.*
                                                              manifest.json
    bronze/source=<source>/snapshot_id=<sha256-prefix>/data.parquet

Raw payload bytes are never overwritten (each run_id gets its own
directory); a repeated identical payload still records a manifest but bronze
promotion only happens when validation contains no FATAL event ("fail
closed" — a rejected snapshot stays quarantined under raw/ and never
reaches bronze, so the previously accepted bronze snapshot for this source
is left untouched).
"""

from __future__ import annotations

from datetime import UTC, datetime

from climate_risk.config.loader import RunPaths
from climate_risk.contracts.models import (
    IngestManifest,
    IngestStatus,
    QualitySeverity,
    RawArtifact,
)
from climate_risk.contracts.run import current_git_commit
from climate_risk.ingestion.base import SourceAdapter
from climate_risk.observability.logging import get_logger


def run_ingest(adapter: SourceAdapter, *, paths: RunPaths, run_id: str) -> IngestManifest:
    log = get_logger(stage="ingest", source=adapter.source_name, run_id=run_id)
    start = datetime.now(UTC)

    ingest_date = start.date().isoformat()
    raw_dir = (
        paths.raw
        / f"source={adapter.source_name}"
        / f"ingest_date={ingest_date}"
        / f"run_id={run_id}"
    )
    artifact = adapter.fetch(dest_dir=raw_dir)

    transport_report = adapter.validate_transport(artifact)
    row_count: int | None = None
    schema_fingerprint = ""
    quality_report = transport_report

    if not transport_report.has_fatal:
        schema_fingerprint = adapter.fingerprint_schema(artifact)
        frame = adapter.standardise(artifact)
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
        git_commit=current_git_commit(),
        status=status,
        row_count=row_count,
        validation=quality_report,
    )
    (raw_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    for event in quality_report.events:
        level = {
            QualitySeverity.INFO: "info",
            QualitySeverity.WARN: "warning",
            QualitySeverity.ERROR: "error",
            QualitySeverity.FATAL: "error",
        }[event.severity]
        getattr(log, level)("quality event", rule_id=event.rule_id, message=event.message)

    if status == IngestStatus.ACCEPTED:
        _promote_to_bronze(adapter, artifact, paths=paths)
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


def _promote_to_bronze(adapter: SourceAdapter, artifact: RawArtifact, *, paths: RunPaths) -> None:
    frame = adapter.standardise(artifact)
    snapshot_id = artifact.sha256[:16]
    bronze_dir = paths.bronze / f"source={adapter.source_name}" / f"snapshot_id={snapshot_id}"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = bronze_dir / ".data.parquet.tmp"
    final_path = bronze_dir / "data.parquet"
    frame.to_parquet(tmp_path, index=False)
    tmp_path.replace(final_path)  # atomic promote per idempotency requirement

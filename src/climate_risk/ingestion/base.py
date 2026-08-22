"""Source adapter interface (01_data_ingestion.md section 10).

Pipeline orchestration is source-agnostic; source-specific assumptions
(column names, units, quirks) live inside concrete adapters. Adapters fetch
and parse only -- they never touch storage. `fetch()` returns raw bytes in
memory; the orchestrator (`climate_risk.ingestion.pipeline.run_ingest`)
decides where those bytes get persisted via a `StorageBackend`. This split
is what makes an adapter backend-agnostic: nothing here can accidentally
run a local filesystem operation against a remote URI (ADR 0003).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Protocol

import httpx
import pandas as pd

from climate_risk.contracts.models import RawArtifact, ValidationReport


class SourceAdapter(Protocol):
    """Protocol every concrete source adapter implements."""

    source_name: str
    parser_version: str

    def fetch(self) -> tuple[RawArtifact, bytes]: ...

    def validate_transport(self, artifact: RawArtifact) -> ValidationReport: ...

    def fingerprint_schema(self, artifact: RawArtifact, raw_bytes: bytes) -> str: ...

    def standardise(self, artifact: RawArtifact, raw_bytes: bytes) -> pd.DataFrame: ...

    def quality_checks(self, frame: pd.DataFrame) -> ValidationReport: ...


class HttpSourceAdapter(ABC):
    """Shared plumbing for adapters that fetch a single HTTP payload.

    Concrete adapters implement `_download`, `standardise`, and
    `quality_checks`; this base class handles checksum computation, schema
    fingerprinting and generic transport validation so those rules are
    applied identically across sources.
    """

    source_name: str
    parser_version: str
    source_url: str

    def fetch(self) -> tuple[RawArtifact, bytes]:
        response = self._download()
        content = response.content
        sha256 = hashlib.sha256(content).hexdigest()
        artifact = RawArtifact(
            source_name=self.source_name,
            source_url=self.source_url,
            retrieved_at_utc=datetime.now(UTC),
            http_status=response.status_code,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            content_length=len(content),
            sha256=sha256,
            content_type=response.headers.get("content-type"),
        )
        return artifact, content

    @abstractmethod
    def _download(self) -> httpx.Response:
        """Perform the actual HTTP fetch with retry/timeout handling."""
        raise NotImplementedError

    def validate_transport(self, artifact: RawArtifact) -> ValidationReport:
        from climate_risk.contracts.models import QualitySeverity, ValidationEvent

        events: list[ValidationEvent] = []
        if artifact.http_status != 200:
            events.append(
                ValidationEvent(
                    rule_id="DQ-TRANSPORT-001",
                    severity=QualitySeverity.FATAL,
                    message=f"Non-200 HTTP status: {artifact.http_status}",
                )
            )
        if artifact.content_length == 0:
            events.append(
                ValidationEvent(
                    rule_id="DQ-TRANSPORT-002",
                    severity=QualitySeverity.FATAL,
                    message="Zero-byte payload",
                )
            )
        content_type = (artifact.content_type or "").lower()
        if "text/html" in content_type:
            events.append(
                ValidationEvent(
                    rule_id="DQ-TRANSPORT-003",
                    severity=QualitySeverity.FATAL,
                    message="Upstream returned an HTML page instead of the expected payload",
                )
            )
        return ValidationReport(events=events)

    def fingerprint_schema(self, artifact: RawArtifact, raw_bytes: bytes) -> str:
        frame = self.standardise(artifact, raw_bytes)
        column_signature = "|".join(f"{c}:{frame[c].dtype}" for c in sorted(frame.columns))
        return hashlib.sha256(column_signature.encode("utf-8")).hexdigest()

    @abstractmethod
    def standardise(self, artifact: RawArtifact, raw_bytes: bytes) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def quality_checks(self, frame: pd.DataFrame) -> ValidationReport:
        raise NotImplementedError

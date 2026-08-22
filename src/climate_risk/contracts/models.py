"""Domain models for the ingestion/provenance contract.

Mirrors 01_data_ingestion.md (manifest contract, raw invariants) and
08_data_quality_and_validation.md (severity model). These are the types
every pipeline stage exchanges, so a malformed manifest fails a pydantic
validation instead of silently propagating.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class IngestStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    NO_CHANGE = "NO_CHANGE"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class QualitySeverity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


class RawArtifact(BaseModel):
    """The result of a single source fetch, before validation/promotion."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    source_url: str
    retrieved_at_utc: datetime
    http_status: int
    etag: str | None = None
    last_modified: str | None = None
    content_length: int
    sha256: str
    content_type: str | None = None
    payload_path: str  # path to the immutable raw payload on disk / in the lake


class ValidationEvent(BaseModel):
    """One row of the data_quality_events contract (08_data_quality_and_validation.md)."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    severity: QualitySeverity
    message: str
    country_iso3: str | None = None
    year: int | None = None
    observed_value: str | None = None
    expected: str | None = None


class ValidationReport(BaseModel):
    """Aggregate outcome of running a rule set against one dataset."""

    model_config = ConfigDict(frozen=True)

    events: list[ValidationEvent] = Field(default_factory=list)

    @property
    def has_fatal(self) -> bool:
        return any(e.severity == QualitySeverity.FATAL for e in self.events)

    @property
    def has_error(self) -> bool:
        return any(
            e.severity in (QualitySeverity.ERROR, QualitySeverity.FATAL) for e in self.events
        )

    def by_severity(self, severity: QualitySeverity) -> list[ValidationEvent]:
        return [e for e in self.events if e.severity == severity]


class IngestManifest(BaseModel):
    """manifest.json contract — the provenance anchor for reproducibility.

    Field set matches 01_data_ingestion.md section 5 exactly.
    """

    model_config = ConfigDict(frozen=True)

    run_id: str
    source_name: str
    source_url: str
    retrieved_at_utc: datetime
    http_status: int
    etag: str | None = None
    last_modified: str | None = None
    content_length: int
    sha256: str
    schema_fingerprint: str
    parser_version: str
    ingestion_image_digest: str | None = None
    git_commit: str | None = None
    status: IngestStatus
    row_count: int | None = None
    validation: ValidationReport = Field(default_factory=ValidationReport)

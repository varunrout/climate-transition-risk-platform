from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from climate_risk.contracts.models import RawArtifact

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def make_raw_artifact(
    payload_path: Path, *, source_name: str, content_type: str
) -> tuple[RawArtifact, bytes]:
    content = payload_path.read_bytes()
    artifact = RawArtifact(
        source_name=source_name,
        source_url="https://example.invalid/fixture",
        retrieved_at_utc=datetime.now(UTC),
        http_status=200,
        content_length=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        content_type=content_type,
    )
    return artifact, content


@pytest.fixture
def owid_artifact() -> tuple[RawArtifact, bytes]:
    return make_raw_artifact(
        FIXTURES_DIR / "owid_sample.csv", source_name="owid_co2", content_type="text/csv"
    )


@pytest.fixture
def world_bank_artifact() -> tuple[RawArtifact, bytes]:
    return make_raw_artifact(
        FIXTURES_DIR / "world_bank_sample.json",
        source_name="world_bank_wdi",
        content_type="application/json",
    )

"""End-to-end ingest pipeline against fixtures only — no network access required."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from climate_risk.contracts.models import IngestStatus, RawArtifact
from climate_risk.ingestion.owid import OwidCo2Adapter
from climate_risk.ingestion.pipeline import run_ingest
from climate_risk.storage import LakeStorage, backend_for_uri

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class FixtureOwidAdapter(OwidCo2Adapter):
    """Same standardisation/quality logic as OwidCo2Adapter, but fetch() reads
    a local fixture instead of making an HTTP request, so this test is
    deterministic and runs with no internet access."""

    def fetch(self) -> tuple[RawArtifact, bytes]:
        content = (FIXTURES_DIR / "owid_sample.csv").read_bytes()
        artifact = RawArtifact(
            source_name=self.source_name,
            source_url=self.source_url,
            retrieved_at_utc=datetime.now(UTC),
            http_status=200,
            content_length=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            content_type="text/csv",
        )
        return artifact, content


@pytest.fixture
def lake(tmp_path: Path) -> LakeStorage:
    root = tmp_path / "lake"
    storage = LakeStorage(
        raw=backend_for_uri(str(root / "raw")),
        bronze=backend_for_uri(str(root / "bronze")),
        silver=backend_for_uri(str(root / "silver")),
        gold=backend_for_uri(str(root / "gold")),
    )
    storage.ensure_zones()
    return storage


def test_accepted_run_promotes_to_bronze(lake: LakeStorage) -> None:
    manifest = run_ingest(FixtureOwidAdapter(), lake=lake, run_id="test-run-1")

    assert manifest.status == IngestStatus.ACCEPTED
    # 2 years x USA/CHN/DEU after filtering the World aggregate out of the fixture
    assert manifest.row_count == 6

    raw_manifest_path = (
        "source=owid_co2/"
        f"ingest_date={manifest.retrieved_at_utc.date().isoformat()}/"
        "run_id=test-run-1/manifest.json"
    )
    assert lake.raw.exists(raw_manifest_path)

    bronze_files = lake.bronze.glob("source=owid_co2/snapshot_id=*/data.parquet")
    assert len(bronze_files) == 1


def test_raw_snapshot_is_immutable_across_runs(lake: LakeStorage) -> None:
    run_ingest(FixtureOwidAdapter(), lake=lake, run_id="run-a")
    run_ingest(FixtureOwidAdapter(), lake=lake, run_id="run-b")

    run_dirs = lake.raw.glob("source=owid_co2/ingest_date=*/run_id=*/manifest.json")
    assert len(run_dirs) == 2  # each run gets its own immutable directory

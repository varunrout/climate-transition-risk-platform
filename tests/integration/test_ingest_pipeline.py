"""End-to-end ingest pipeline against fixtures only — no network access required."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from climate_risk.config.loader import RunPaths
from climate_risk.contracts.models import IngestStatus, RawArtifact
from climate_risk.ingestion.owid import OwidCo2Adapter
from climate_risk.ingestion.pipeline import run_ingest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class FixtureOwidAdapter(OwidCo2Adapter):
    """Same standardisation/quality logic as OwidCo2Adapter, but fetch() copies
    a local fixture instead of making an HTTP request, so this test is
    deterministic and runs with no internet access."""

    def fetch(self, *, dest_dir: Path) -> RawArtifact:
        import hashlib
        from datetime import UTC, datetime

        dest_dir.mkdir(parents=True, exist_ok=True)
        payload_path = dest_dir / f"{self.source_name}.payload"
        shutil.copyfile(FIXTURES_DIR / "owid_sample.csv", payload_path)
        content = payload_path.read_bytes()
        return RawArtifact(
            source_name=self.source_name,
            source_url=self.source_url,
            retrieved_at_utc=datetime.now(UTC),
            http_status=200,
            content_length=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            content_type="text/csv",
            payload_path=str(payload_path),
        )


@pytest.fixture
def lake_paths(tmp_path: Path) -> RunPaths:
    paths = RunPaths(lake_root=tmp_path / "lake")
    paths.ensure_zones()
    return paths


def test_accepted_run_promotes_to_bronze(lake_paths: RunPaths) -> None:
    manifest = run_ingest(FixtureOwidAdapter(), paths=lake_paths, run_id="test-run-1")

    assert manifest.status == IngestStatus.ACCEPTED
    # 2 years x USA/CHN/DEU after filtering the World aggregate out of the fixture
    assert manifest.row_count == 6

    raw_manifest = (
        lake_paths.raw
        / "source=owid_co2"
        / f"ingest_date={manifest.retrieved_at_utc.date().isoformat()}"
        / "run_id=test-run-1"
        / "manifest.json"
    )
    assert raw_manifest.exists()

    bronze_files = list((lake_paths.bronze / "source=owid_co2").rglob("data.parquet"))
    assert len(bronze_files) == 1


def test_raw_snapshot_is_immutable_across_runs(lake_paths: RunPaths) -> None:
    run_ingest(FixtureOwidAdapter(), paths=lake_paths, run_id="run-a")
    run_ingest(FixtureOwidAdapter(), paths=lake_paths, run_id="run-b")

    run_dirs = list((lake_paths.raw / "source=owid_co2").rglob("run_id=*"))
    assert len(run_dirs) == 2  # each run gets its own immutable directory

from __future__ import annotations

from climate_risk.contracts.run import PipelineRun, RunStatus


def test_run_lifecycle_success() -> None:
    run = PipelineRun.start()
    assert run.status == RunStatus.RUNNING
    assert run.completed_at is None

    run.succeed(release_id="rel-1")
    assert run.status == RunStatus.SUCCEEDED
    assert run.completed_at is not None
    assert run.release_id == "rel-1"


def test_run_lifecycle_failure_records_stage_and_message() -> None:
    run = PipelineRun.start()
    run.fail(stage="ingest", message="checksum mismatch")
    assert run.status == RunStatus.FAILED
    assert run.failure_stage == "ingest"
    assert run.failure_message == "checksum mismatch"
    assert run.release_id is None


def test_run_ids_are_unique() -> None:
    a, b = PipelineRun.start(), PipelineRun.start()
    assert a.run_id != b.run_id

"""Automated tests for the fail-closed publishing barrier (spec section 11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from climate_risk.contracts.run import PipelineRun
from climate_risk.publishing.barrier import PublishBlockedError, publish, read_latest_run
from climate_risk.storage import LocalStorageBackend, write_text


@pytest.fixture
def gold(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(tmp_path / "gold")


def test_failed_run_never_becomes_latest(gold: LocalStorageBackend) -> None:
    good_run = PipelineRun.start()
    good_run.succeed(release_id="release-1")
    publish(good_run, gold=gold)

    before = read_latest_run(gold)
    assert before is not None
    assert before["release_id"] == "release-1"

    failed_run = PipelineRun.start()
    failed_run.fail(stage="model", message="boom")
    with pytest.raises(PublishBlockedError):
        publish(failed_run, gold=gold)

    after = read_latest_run(gold)
    assert after == before  # previous successful release left completely intact


def test_running_run_cannot_publish(gold: LocalStorageBackend) -> None:
    in_progress = PipelineRun.start()
    with pytest.raises(PublishBlockedError):
        publish(in_progress, gold=gold)
    assert read_latest_run(gold) is None


def test_publish_is_atomic_write(gold: LocalStorageBackend) -> None:
    run = PipelineRun.start()
    run.succeed(release_id="release-2")
    publish(run, gold=gold)

    data = read_latest_run(gold)
    assert data is not None
    assert data["run_id"] == run.run_id
    assert data["status"] == "SUCCEEDED"
    # no leftover local temp files from the atomic write
    assert list((gold.root).glob(".latest_successful_run.json.tmp")) == []


def test_publish_blocked_when_required_artifact_missing(gold: LocalStorageBackend) -> None:
    """The object-store-safe sequence: publish() verifies every required
    artifact actually exists before ever touching the pointer -- it doesn't
    just trust that the caller wrote them."""
    run = PipelineRun.start()
    run.succeed(release_id="release-3")

    with pytest.raises(PublishBlockedError, match="missing"):
        publish(run, gold=gold, required_artifacts=["backtest_summary.parquet"])

    assert read_latest_run(gold) is None  # nothing was written


def test_publish_succeeds_once_required_artifacts_exist(gold: LocalStorageBackend) -> None:
    write_text(gold, "backtest_summary.parquet", "not-really-parquet-but-exists")
    write_text(gold, "manifests/run-x.json", "{}")

    run = PipelineRun.start()
    run.succeed(release_id="release-4")
    publish(run, gold=gold, required_artifacts=["backtest_summary.parquet", "manifests/run-x.json"])

    data = read_latest_run(gold)
    assert data is not None
    assert data["release_id"] == "release-4"


def test_missing_required_artifact_leaves_previous_pointer_untouched(
    gold: LocalStorageBackend,
) -> None:
    """A second run that's missing an artifact must not disturb a prior
    successful publish -- the core fail-closed guarantee under a
    remote-object-store-style precondition failure, not just a status check."""
    write_text(gold, "backtest_summary.parquet", "v1")
    first = PipelineRun.start()
    first.succeed(release_id="release-5")
    publish(first, gold=gold, required_artifacts=["backtest_summary.parquet"])
    before = read_latest_run(gold)

    second = PipelineRun.start()
    second.succeed(release_id="release-6")
    with pytest.raises(PublishBlockedError):
        publish(second, gold=gold, required_artifacts=["backtest_summary.parquet", "score.parquet"])

    assert read_latest_run(gold) == before


def test_simulated_pointer_write_failure_leaves_previous_pointer_intact(
    gold: LocalStorageBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even if the final pointer write itself fails partway (disk full,
    network blip against a remote backend, etc.), the previous pointer must
    not end up corrupted or partially written."""
    first = PipelineRun.start()
    first.succeed(release_id="release-7")
    publish(first, gold=gold)
    before_raw = (gold.root / "latest_successful_run.json").read_bytes()

    def _boom(path: str, data: bytes) -> None:
        raise OSError("simulated storage failure mid-write")

    monkeypatch.setattr(gold, "write_bytes", _boom)

    second = PipelineRun.start()
    second.succeed(release_id="release-8")
    with pytest.raises(OSError, match="simulated storage failure"):
        publish(second, gold=gold)

    monkeypatch.undo()
    after_raw = (gold.root / "latest_successful_run.json").read_bytes()
    assert after_raw == before_raw  # byte-for-byte unchanged, no partial/torn write

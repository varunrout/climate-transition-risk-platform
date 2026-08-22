"""Automated test for the fail-closed publishing barrier (spec section 11)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from climate_risk.contracts.run import PipelineRun
from climate_risk.publishing.barrier import PublishBlockedError, publish, read_latest_run


def test_failed_run_never_becomes_latest(tmp_path: Path) -> None:
    gold_root = tmp_path / "gold"

    good_run = PipelineRun.start()
    good_run.succeed(release_id="release-1")
    publish(good_run, gold_root=gold_root)

    before = read_latest_run(gold_root)
    assert before is not None
    assert before["release_id"] == "release-1"

    failed_run = PipelineRun.start()
    failed_run.fail(stage="model", message="boom")
    with pytest.raises(PublishBlockedError):
        publish(failed_run, gold_root=gold_root)

    after = read_latest_run(gold_root)
    assert after == before  # previous successful release left completely intact


def test_running_run_cannot_publish(tmp_path: Path) -> None:
    gold_root = tmp_path / "gold"
    in_progress = PipelineRun.start()
    with pytest.raises(PublishBlockedError):
        publish(in_progress, gold_root=gold_root)
    assert read_latest_run(gold_root) is None


def test_publish_is_atomic_write(tmp_path: Path) -> None:
    gold_root = tmp_path / "gold"
    run = PipelineRun.start()
    run.succeed(release_id="release-2")
    publish(run, gold_root=gold_root)

    pointer = gold_root / "latest_successful_run.json"
    data = json.loads(pointer.read_text(encoding="utf-8"))
    assert data["run_id"] == run.run_id
    assert data["status"] == "SUCCEEDED"
    # no leftover temp files from the atomic rename
    assert list(gold_root.glob(".latest_run_*")) == []

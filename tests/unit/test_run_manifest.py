from __future__ import annotations

import subprocess

import pytest

from climate_risk.contracts.run import PipelineRun, RunStatus, resolve_git_sha


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


# ---------------------------------------------------------------------------
# resolve_git_sha: CLIMATE_RISK_GIT_SHA -> git rev-parse HEAD -> None
# ---------------------------------------------------------------------------


def test_explicit_env_sha_takes_precedence_over_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even inside a real git checkout, an explicit CLIMATE_RISK_GIT_SHA wins --
    this is what makes the resolver correct *inside a container*, where the
    local checkout's own HEAD (if `git` even exists in the image) has no
    relationship to the commit the image was actually built from."""
    sha = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    result = resolve_git_sha({"CLIMATE_RISK_GIT_SHA": sha})
    assert result == sha


def test_falls_back_to_local_git_when_env_unset() -> None:
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    result = resolve_git_sha({})
    assert result == expected


def test_none_when_git_genuinely_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulates the real container situation: no CLIMATE_RISK_GIT_SHA set
    and no usable `git` (no .git directory, or no git binary) -- must
    return None, never fabricate a value."""

    def _raise(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git: not found")

    monkeypatch.setattr(subprocess, "run", _raise)
    assert resolve_git_sha({}) is None


def test_empty_string_env_value_is_treated_as_unset() -> None:
    """The Dockerfile's ARG GIT_SHA defaults to "" when not passed at build
    time -- that must not be mistaken for a real (if empty) SHA."""
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    result = resolve_git_sha({"CLIMATE_RISK_GIT_SHA": ""})
    assert result == expected  # falls through to git, doesn't return ""


def test_manifest_receives_the_resolved_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    """PipelineRun.start() -- the real call site the publish manifest's
    git_sha field is populated from -- must carry the resolved value
    through, not just resolve_git_sha() in isolation."""
    sha = "cafef00dcafef00dcafef00dcafef00dcafef00d"
    monkeypatch.setenv("CLIMATE_RISK_GIT_SHA", sha)
    run = PipelineRun.start()
    assert run.git_commit == sha
    assert run.model_dump()["git_commit"] == sha

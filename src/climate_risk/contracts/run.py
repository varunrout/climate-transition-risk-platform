"""Run manifest contract (07_data_model_and_contracts.md section 11).

Every pipeline invocation gets one run_id and, at the end, one manifest
recording exactly what code/config/data produced its output — the
audit trail the honesty rule in the spec depends on.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


def new_run_id() -> str:
    return str(uuid.uuid4())


def resolve_git_sha(env: dict[str, str] | None = None) -> str | None:
    """Provenance resolver, in order:

    1. CLIMATE_RISK_GIT_SHA -- set at image build time (Dockerfile ARG/ENV,
       baked in from the actual `git rev-parse HEAD` used for that build).
       This is the only reliable source once the container is running: the
       production image deliberately does not contain `.git` (bloat, and
       no reason to ship repo history), so a runtime `git` subprocess call
       inside the container can never see one.
    2. `git rev-parse HEAD` -- works when running from a local checkout
       (dev machine, CI without the container, `uv run climate-risk ...`).
    3. `None` -- genuinely unavailable; the manifest field stays null
       rather than fabricating a value.

    Never inferred by parsing the GHCR image tag: the tag is a *label* a
    deploy step chooses to apply (defensibly a git SHA today, but the code
    has no way to prove that without trusting an external convention), not
    provenance the running process itself can attest to.
    """
    env = env if env is not None else dict(os.environ)
    explicit = env.get("CLIMATE_RISK_GIT_SHA")
    if explicit:
        return explicit

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


class PipelineRun(BaseModel):
    model_config = ConfigDict(frozen=False)

    run_id: str
    started_at: datetime
    completed_at: datetime | None = None
    status: RunStatus = RunStatus.RUNNING
    git_commit: str | None = None
    config_hash: str | None = None
    snapshot_set_id: str | None = None
    feature_set_version: str | None = None
    model_version: str | None = None
    release_id: str | None = None
    failure_stage: str | None = None
    failure_message: str | None = None

    @classmethod
    def start(cls) -> PipelineRun:
        return cls(
            run_id=new_run_id(),
            started_at=datetime.now(UTC),
            git_commit=resolve_git_sha(),
        )

    def succeed(self, *, release_id: str | None = None) -> None:
        self.status = RunStatus.SUCCEEDED
        self.completed_at = datetime.now(UTC)
        self.release_id = release_id

    def fail(self, *, stage: str, message: str) -> None:
        self.status = RunStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.failure_stage = stage
        self.failure_message = message

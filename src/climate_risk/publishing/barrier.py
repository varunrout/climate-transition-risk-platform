"""Fail-closed publishing barrier (03_architecture.md section 7).

`latest_successful_run.json` under the gold zone is the pointer every
downstream consumer (Power BI, API) resolves. It is updated only via
`publish()`, and only for a RunStatus.SUCCEEDED run — a failed or
in-progress run can never become the latest pointer, so the previous
successful release stays intact.

This does NOT claim POSIX atomic-rename semantics against a remote object
store, because ADLS Gen2/Azure Blob Storage doesn't give you that for an
arbitrary multi-step publication (write several files, then swap a
pointer) the way a same-filesystem `os.replace` does locally. Instead the
sequence itself is what's safe:

  1. caller writes every run-scoped gold output (backtest, score, manifest)
  2. caller passes their paths as `required_artifacts`
  3. `publish()` verifies every one of them actually exists in the backend
  4. only if all of that succeeds does it write the pointer -- last, and
     it alone

If step 3 finds anything missing, or the run wasn't SUCCEEDED to begin
with, nothing is written and `PublishBlockedError` is raised. The
previous pointer, if any, is completely untouched in every failure path --
there is no window where it's read back partially updated, because it is
never touched until every precondition already passed.

Per-backend note on the pointer write itself: `StorageBackend.write_bytes`
is atomic at the single-object level for both backends this project uses
(temp-file+rename locally; a single blob PUT on Azure, which Azure
guarantees is atomic -- a reader never observes a half-written blob), so
even the final pointer swap doesn't leave a torn/partial file visible.
"""

from __future__ import annotations

import json

from climate_risk.contracts.run import PipelineRun, RunStatus
from climate_risk.storage import StorageBackend, read_json, write_text

POINTER_PATH = "latest_successful_run.json"


class PublishBlockedError(RuntimeError):
    """Raised when publish() is called for a run that must not become latest."""


def read_latest_run(gold: StorageBackend) -> dict[str, object] | None:
    if not gold.exists(POINTER_PATH):
        return None
    result = read_json(gold, POINTER_PATH)
    assert isinstance(result, dict)
    return result


def publish(
    run: PipelineRun, *, gold: StorageBackend, required_artifacts: list[str] | None = None
) -> None:
    """Promote `run` to latest_successful_run, or refuse and change nothing.

    `required_artifacts` are gold-zone-relative paths that must already
    exist (written by the caller before calling this) -- e.g. the run
    manifest, backtest summary, and score outputs. Missing any of them
    blocks publication exactly like a non-SUCCEEDED run does.
    """
    if run.status is not RunStatus.SUCCEEDED:
        raise PublishBlockedError(
            f"refusing to publish run {run.run_id!r} with status {run.status!r}; "
            "the previous latest_successful_run pointer is left untouched"
        )

    missing = [a for a in (required_artifacts or []) if not gold.exists(a)]
    if missing:
        raise PublishBlockedError(
            f"refusing to publish run {run.run_id!r}: required gold artifact(s) missing "
            f"before publish: {missing}; the previous latest_successful_run pointer is left untouched"
        )

    write_text(gold, POINTER_PATH, run.model_dump_json(indent=2))


def validate_manifest_json(gold: StorageBackend, manifest_path: str) -> bool:
    """True if `manifest_path` exists and parses as JSON. Used by callers as
    part of assembling `required_artifacts` -- a manifest that fails to
    parse is treated the same as a missing one."""
    if not gold.exists(manifest_path):
        return False
    try:
        json.loads(gold.read_bytes(manifest_path).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    return True

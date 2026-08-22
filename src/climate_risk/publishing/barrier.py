"""Fail-closed publishing barrier (03_architecture.md section 7).

`latest_successful_run.json` under the gold zone is the pointer every
downstream consumer (Power BI, API) resolves. It is updated only via
`publish()`, and only for a RunStatus.SUCCEEDED run — a failed or
in-progress run can never become the latest pointer, so the previous
successful release stays intact.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from climate_risk.contracts.run import PipelineRun, RunStatus


class PublishBlockedError(RuntimeError):
    """Raised when publish() is called for a run that must not become latest."""


def latest_pointer_path(gold_root: Path) -> Path:
    return gold_root / "latest_successful_run.json"


def read_latest_run(gold_root: Path) -> dict[str, object] | None:
    path = latest_pointer_path(gold_root)
    if not path.exists():
        return None
    result: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return result


def publish(run: PipelineRun, *, gold_root: Path) -> None:
    """Atomically promote `run` to latest_successful_run, or refuse.

    Raises PublishBlockedError for any non-SUCCEEDED run instead of writing
    anything, so a partially-failed run can never overwrite the previous
    published release.
    """
    if run.status is not RunStatus.SUCCEEDED:
        raise PublishBlockedError(
            f"refusing to publish run {run.run_id!r} with status {run.status!r}; "
            "the previous latest_successful_run pointer is left untouched"
        )

    gold_root.mkdir(parents=True, exist_ok=True)
    target = latest_pointer_path(gold_root)

    fd, tmp_name = tempfile.mkstemp(dir=gold_root, prefix=".latest_run_", suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(run.model_dump_json(indent=2))
        os.replace(tmp_name, target)  # atomic on POSIX and NTFS
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise

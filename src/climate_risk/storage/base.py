"""Backend-neutral storage contract.

Every pipeline stage (ingestion, silver build, backtest, score, publish)
talks to storage only through this `StorageBackend` protocol -- never
through `pathlib.Path` operations on a possibly-remote URI. This is the
fix for the confirmed bug in ADR 0003: `RunPaths` used to be a thin
`pathlib.Path` wrapper, so pointing it at an `abfss://` URL made
`Path("abfss://...").mkdir()` try to create a literal local directory
named "abfss:" and crash.

A `StorageBackend` is rooted at exactly one zone (raw, bronze, silver, or
gold) -- this matches the Azure design's four separate ADLS Gen2
filesystems, which have no shared account-level parent path. Concrete
backends (`storage.local.LocalStorageBackend`, `storage.azure.AzureStorageBackend`)
implement only the primitive byte/text operations; `write_parquet`,
`read_parquet`, `write_json`, `read_json` are free functions here built on
top of those primitives, so no logic is duplicated between backends and
no `if path.startswith("abfss://")` branching is scattered through the
pipeline -- the one branch point is `storage.lake.backend_for_uri`.
"""

from __future__ import annotations

import io
import json
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class StorageBackend(Protocol):
    """Primitive operations every concrete backend must implement.

    All paths are zone-relative POSIX-style strings (forward slashes,
    no leading slash), e.g. "source=owid_co2/snapshot_id=abc123/data.parquet"
    -- never an absolute local path and never a full abfss:// URL. The
    backend already knows its own root; callers only ever supply the part
    of the path below that root.
    """

    def exists(self, path: str) -> bool: ...

    def makedirs(self, path: str = "") -> None:
        """Ensure `path` (a directory/prefix, possibly "" for the zone root) exists.

        For object-store backends without real directories this is a
        best-effort no-op -- writing a blob at a "nested" key does not
        require a directory to pre-exist.
        """
        ...

    def write_bytes(self, path: str, data: bytes) -> None:
        """Write `data` to `path`.

        Must not leave a partially-written object visible to a reader
        that concurrently calls `read_bytes`/`exists` on the same path --
        see each backend's docstring for how it achieves that (temp+rename
        locally; a single atomic blob PUT on Azure).
        """
        ...

    def read_bytes(self, path: str) -> bytes: ...

    def glob(self, pattern: str) -> list[str]:
        """Return zone-relative paths matching `pattern` (e.g. "source=*/snapshot_id=*/data.parquet")."""
        ...

    def remove(self, path: str) -> None:
        """Delete `path` if it exists; no error if it doesn't."""
        ...

    def modified_at(self, path: str) -> float:
        """Last-modified time of `path` as a Unix timestamp (seconds).

        Used to pick the most-recently-written snapshot among several
        content-addressed candidates (e.g. bronze snapshot_id=* dirs) --
        real backend metadata (mtime locally, blob last-modified on Azure),
        not an assumption about path ordering.
        """
        ...


def write_text(backend: StorageBackend, path: str, text: str) -> None:
    backend.write_bytes(path, text.encode("utf-8"))


def read_text(backend: StorageBackend, path: str) -> str:
    return backend.read_bytes(path).decode("utf-8")


def write_json(backend: StorageBackend, path: str, obj: object) -> None:
    write_text(backend, path, json.dumps(obj, indent=2))


def read_json(backend: StorageBackend, path: str) -> object:
    return json.loads(read_text(backend, path))


def write_parquet(backend: StorageBackend, path: str, frame: pd.DataFrame) -> None:
    buffer = io.BytesIO()
    frame.to_parquet(buffer, index=False)
    backend.write_bytes(path, buffer.getvalue())


def read_parquet(backend: StorageBackend, path: str) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(backend.read_bytes(path)))

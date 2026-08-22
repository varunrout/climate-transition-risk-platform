"""Local filesystem storage backend -- the default for `data/lake/<zone>`."""

from __future__ import annotations

from pathlib import Path


class LocalStorageBackend:
    """One zone rooted at a local directory. `write_bytes` is atomic via a
    same-directory temp file + `Path.replace`, which is an atomic rename on
    both POSIX and NTFS -- a reader never observes a partially-written file.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def _resolve(self, path: str) -> Path:
        return self.root / path if path else self.root

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def makedirs(self, path: str = "") -> None:
        self._resolve(path).mkdir(parents=True, exist_ok=True)

    def write_bytes(self, path: str, data: bytes) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.tmp")
        tmp.write_bytes(data)
        tmp.replace(target)

    def read_bytes(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def glob(self, pattern: str) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(
            str(p.relative_to(self.root)).replace("\\", "/") for p in self.root.glob(pattern)
        )

    def remove(self, path: str) -> None:
        self._resolve(path).unlink(missing_ok=True)

    def modified_at(self, path: str) -> float:
        return self._resolve(path).stat().st_mtime

"""Azure Data Lake Storage Gen2 backend, via fsspec/adlfs.

Authentication is managed-identity only -- no account keys, SAS tokens, or
connection strings anywhere in this module or in the Terraform/Container
Apps configuration that sets it up (infra/modules/container_apps).

Because the Container Apps Job runs under a *user-assigned* managed
identity (`id-climate-risk-job`), the identity is ambiguous unless a
client ID is supplied -- `DefaultAzureCredential()` with no arguments can
fall through to other credential sources or fail to pick the right
identity. `AZURE_CLIENT_ID` (a non-secret identifier, safe to pass as a
plain env var) selects `ManagedIdentityCredential(client_id=...)`
directly and deterministically: no credential-chain fallback, no
ambiguity about which auth path was used, provable by construction rather
than by inspecting logs. Local/dev use (no AZURE_CLIENT_ID set) falls back
to `DefaultAzureCredential()`, which picks up `az login` locally.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from adlfs import AzureBlobFileSystem
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

if TYPE_CHECKING:
    from fsspec import AbstractFileSystem


def resolve_credential() -> DefaultAzureCredential | ManagedIdentityCredential:
    """The credential this process will use for ADLS access.

    Never a storage account key. `client_id` set means a user-assigned
    managed identity is being addressed explicitly and unambiguously.
    """
    client_id = os.environ.get("AZURE_CLIENT_ID")
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)
    return DefaultAzureCredential()


@lru_cache(maxsize=8)
def _filesystem(account_name: str) -> AzureBlobFileSystem:
    """One AzureBlobFileSystem per storage account, reused across zones/backends
    (all four zones in this project's design live in the same storage account)."""
    return AzureBlobFileSystem(account_name=account_name, credential=resolve_credential())


class AzureStorageBackend:
    """One zone == one ADLS Gen2 filesystem (container), e.g. `abfss://raw@<account>.dfs.core.windows.net/`.

    `write_bytes` is a single blob PUT, which Azure Blob Storage guarantees
    is atomic at the object level -- a reader never observes a partially
    written blob, even without a temp-file+rename dance. This is a real,
    documented property of the Blob/DFS PUT operation, not an assumption;
    it does *not* give POSIX rename semantics across paths, which this
    backend does not claim to have.
    """

    def __init__(self, uri: str, *, fs: AbstractFileSystem | None = None) -> None:
        parsed = urlparse(uri)
        if parsed.scheme != "abfss" or not parsed.username or not parsed.hostname:
            raise ValueError(
                f"expected abfss://<container>@<account>.dfs.core.windows.net/, got {uri!r}"
            )
        self.container = parsed.username
        self.account_name = parsed.hostname.split(".")[0]
        # `fs` injection exists for tests: swap in an in-memory fsspec
        # filesystem to exercise this class's path/glob/read/write logic
        # without real Azure credentials. Production code never passes it --
        # `_filesystem()` resolves the real managed-identity-backed
        # AzureBlobFileSystem, cached per account.
        self.fs = fs if fs is not None else _filesystem(self.account_name)

    def _resolve(self, path: str) -> str:
        return f"{self.container}/{path}" if path else self.container

    def exists(self, path: str) -> bool:
        return bool(self.fs.exists(self._resolve(path)))

    def makedirs(self, path: str = "") -> None:
        # The filesystem (container) itself is provisioned by Terraform
        # (azurerm_storage_data_lake_gen2_filesystem); nested prefixes on
        # ADLS Gen2 with hierarchical namespace are real directories and
        # adlfs creates them on demand when a blob is written under them,
        # so this only needs to handle the explicit-directory case.
        if path:
            self.fs.makedirs(self._resolve(path), exist_ok=True)

    def write_bytes(self, path: str, data: bytes) -> None:
        with self.fs.open(self._resolve(path), "wb") as handle:
            handle.write(data)

    def read_bytes(self, path: str) -> bytes:
        with self.fs.open(self._resolve(path), "rb") as handle:
            result: bytes = handle.read()
            return result

    def glob(self, pattern: str) -> list[str]:
        prefix = f"{self.container}/"
        matches = self.fs.glob(self._resolve(pattern))
        # Different fsspec filesystem implementations disagree on whether a
        # returned path carries a leading "/" (adlfs: no; fsspec's in-memory
        # filesystem, used in tests: yes) -- normalise before stripping the
        # container prefix so this doesn't silently return container-
        # qualified paths on one backend and zone-relative ones on another.
        results = []
        for match in matches:
            normalised = match.lstrip("/")
            results.append(
                normalised[len(prefix) :] if normalised.startswith(prefix) else normalised
            )
        return sorted(results)

    def remove(self, path: str) -> None:
        if self.fs.exists(self._resolve(path)):
            self.fs.rm(self._resolve(path))

    def modified_at(self, path: str) -> float:
        info = self.fs.info(self._resolve(path))
        last_modified = info.get("last_modified")
        if last_modified is None:
            raise KeyError(f"no last_modified metadata for {path!r}")
        timestamp: float = last_modified.timestamp()
        return timestamp

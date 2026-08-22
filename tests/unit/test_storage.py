"""Storage abstraction tests -- the fix for ADR 0003's confirmed bug.

Covers: local backend primitives, URI/zone configuration, a remote-style
backend exercised against an in-memory fsspec filesystem (no real Azure
credentials needed), Parquet/JSON round trips, zone isolation, identical
logical structure across backends, and that managed-identity configuration
never involves a secret.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from climate_risk.storage import (
    LakeStorage,
    LocalStorageBackend,
    backend_for_uri,
    read_json,
    read_parquet,
    read_text,
    write_json,
    write_parquet,
    write_text,
)
from climate_risk.storage.azure import AzureStorageBackend, resolve_credential

# ---------------------------------------------------------------------------
# backend_for_uri / zone configuration
# ---------------------------------------------------------------------------


def test_backend_for_uri_selects_local_for_plain_path(tmp_path: Path) -> None:
    backend = backend_for_uri(str(tmp_path / "raw"))
    assert isinstance(backend, LocalStorageBackend)


def test_backend_for_uri_selects_azure_for_abfss() -> None:
    backend = backend_for_uri("abfss://raw@stclimateriskdev01.dfs.core.windows.net/")
    assert isinstance(backend, AzureStorageBackend)
    # This is the exact scenario that crashed in ADR 0003: constructing the
    # backend for an abfss:// URI must never touch pathlib at all.
    assert backend.container == "raw"
    assert backend.account_name == "stclimateriskdev01"


def test_lake_storage_from_env_defaults_to_local_data_lake(tmp_path: Path) -> None:
    lake = LakeStorage.from_env({"CLIMATE_RISK_LAKE_ROOT": str(tmp_path)})
    assert isinstance(lake.raw, LocalStorageBackend)
    assert isinstance(lake.bronze, LocalStorageBackend)
    assert lake.raw.root == tmp_path / "raw"
    assert lake.bronze.root == tmp_path / "bronze"
    assert lake.silver.root == tmp_path / "silver"
    assert lake.gold.root == tmp_path / "gold"


def test_lake_storage_from_env_honours_explicit_per_zone_roots(tmp_path: Path) -> None:
    """The corrected design: four independent zone roots, not one shared
    account-level parent -- there is no valid abfss://<account>/.. above
    separate ADLS Gen2 filesystems."""
    lake = LakeStorage.from_env(
        {
            "CLIMATE_RISK_RAW_ROOT": "abfss://raw@stclimateriskdev01.dfs.core.windows.net/",
            "CLIMATE_RISK_BRONZE_ROOT": "abfss://bronze@stclimateriskdev01.dfs.core.windows.net/",
            "CLIMATE_RISK_SILVER_ROOT": "abfss://silver@stclimateriskdev01.dfs.core.windows.net/",
            "CLIMATE_RISK_GOLD_ROOT": "abfss://gold@stclimateriskdev01.dfs.core.windows.net/",
        }
    )
    assert isinstance(lake.raw, AzureStorageBackend)
    assert lake.raw.container == "raw"
    assert isinstance(lake.bronze, AzureStorageBackend)
    assert lake.bronze.container == "bronze"
    assert isinstance(lake.silver, AzureStorageBackend)
    assert lake.silver.container == "silver"
    assert isinstance(lake.gold, AzureStorageBackend)
    assert lake.gold.container == "gold"


def test_per_zone_override_takes_precedence_over_lake_root(tmp_path: Path) -> None:
    lake = LakeStorage.from_env(
        {
            "CLIMATE_RISK_LAKE_ROOT": str(tmp_path / "unused"),
            "CLIMATE_RISK_RAW_ROOT": str(tmp_path / "explicit_raw"),
        }
    )
    assert isinstance(lake.raw, LocalStorageBackend)
    assert lake.raw.root == tmp_path / "explicit_raw"
    assert isinstance(lake.bronze, LocalStorageBackend)
    assert lake.bronze.root == tmp_path / "unused" / "bronze"


# ---------------------------------------------------------------------------
# Local backend primitives
# ---------------------------------------------------------------------------


def test_local_backend_exists_makedirs_write_read(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path / "zone")
    assert not backend.exists("a/b.txt")
    backend.write_bytes("a/b.txt", b"hello")
    assert backend.exists("a/b.txt")
    assert backend.read_bytes("a/b.txt") == b"hello"


def test_local_backend_write_leaves_no_temp_file(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path / "zone")
    backend.write_bytes("data.bin", b"x")
    leftovers = list((tmp_path / "zone").glob(".*.tmp"))
    assert leftovers == []


def test_local_backend_glob_and_remove(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path / "zone")
    backend.write_bytes("source=a/snapshot_id=1/data.parquet", b"x")
    backend.write_bytes("source=a/snapshot_id=2/data.parquet", b"y")
    backend.write_bytes("source=b/snapshot_id=1/data.parquet", b"z")

    matches = backend.glob("source=a/snapshot_id=*/data.parquet")
    assert len(matches) == 2

    backend.remove("source=a/snapshot_id=1/data.parquet")
    assert not backend.exists("source=a/snapshot_id=1/data.parquet")
    backend.remove("does/not/exist")  # no error


def test_local_backend_modified_at_reflects_write_order(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path / "zone")
    backend.write_bytes("snapshot_id=old/data.parquet", b"x")
    time.sleep(0.02)
    backend.write_bytes("snapshot_id=new/data.parquet", b"y")

    candidates = backend.glob("snapshot_id=*/data.parquet")
    latest = max(candidates, key=backend.modified_at)
    assert "new" in latest


# ---------------------------------------------------------------------------
# Parquet / JSON round trips (base.py helpers, backend-agnostic)
# ---------------------------------------------------------------------------


def test_parquet_round_trip_preserves_schema_and_row_count(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path / "zone")
    frame = pd.DataFrame(
        {"country_iso3": ["USA", "CHN"], "year": [2020, 2021], "value": [1.5, 2.5]}
    )
    write_parquet(backend, "data.parquet", frame)
    reread = read_parquet(backend, "data.parquet")

    assert list(reread.columns) == list(frame.columns)
    assert len(reread) == len(frame)
    assert reread["country_iso3"].tolist() == frame["country_iso3"].tolist()
    assert reread["value"].tolist() == frame["value"].tolist()


def test_json_round_trip(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path / "zone")
    obj = {"run_id": "abc", "score": 42, "countries": ["USA", "CHN"]}
    write_json(backend, "manifest.json", obj)
    assert read_json(backend, "manifest.json") == obj


def test_text_round_trip(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path / "zone")
    write_text(backend, "note.txt", "hello world")
    assert read_text(backend, "note.txt") == "hello world"


# ---------------------------------------------------------------------------
# Zone isolation
# ---------------------------------------------------------------------------


def test_zones_are_independently_rooted_and_do_not_leak(tmp_path: Path) -> None:
    lake = LakeStorage.from_env({"CLIMATE_RISK_LAKE_ROOT": str(tmp_path)})
    lake.ensure_zones()

    lake.raw.write_bytes("only_in_raw.txt", b"x")
    assert lake.raw.exists("only_in_raw.txt")
    assert not lake.bronze.exists("only_in_raw.txt")
    assert not lake.silver.exists("only_in_raw.txt")
    assert not lake.gold.exists("only_in_raw.txt")


# ---------------------------------------------------------------------------
# Remote-style backend: in-memory fsspec filesystem, no real Azure needed
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_azure_backend() -> AzureStorageBackend:
    """An AzureStorageBackend wired to fsspec's in-memory filesystem instead
    of a real ADLS account -- exercises the exact same path-joining/glob/
    open logic AzureStorageBackend uses against real Azure, with no
    credentials and no network. A fresh in-memory filesystem per test."""
    import fsspec

    fs = fsspec.filesystem("memory")
    fs.store.clear()  # fsspec memory filesystem is process-global; start clean
    return AzureStorageBackend("abfss://raw@teststorageacct.dfs.core.windows.net/", fs=fs)


def test_remote_style_backend_write_read_exists(memory_azure_backend: AzureStorageBackend) -> None:
    backend = memory_azure_backend
    assert not backend.exists("a/b.txt")
    backend.write_bytes("a/b.txt", b"hello-remote")
    assert backend.exists("a/b.txt")
    assert backend.read_bytes("a/b.txt") == b"hello-remote"


def test_remote_style_backend_glob_strips_container_prefix(
    memory_azure_backend: AzureStorageBackend,
) -> None:
    backend = memory_azure_backend
    backend.write_bytes("source=owid_co2/snapshot_id=abc/data.parquet", b"x")
    backend.write_bytes("source=owid_co2/snapshot_id=def/data.parquet", b"y")

    matches = backend.glob("source=owid_co2/snapshot_id=*/data.parquet")
    assert len(matches) == 2
    # zone-relative, not container-prefixed -- matches LocalStorageBackend's contract
    assert all(not m.startswith("raw/") for m in matches)
    assert all(m.startswith("source=owid_co2/") for m in matches)


def test_remote_style_backend_parquet_round_trip(memory_azure_backend: AzureStorageBackend) -> None:
    frame = pd.DataFrame({"country_iso3": ["USA"], "year": [2020], "value": [1.23]})
    write_parquet(memory_azure_backend, "data.parquet", frame)
    reread = read_parquet(memory_azure_backend, "data.parquet")
    assert reread["country_iso3"].tolist() == ["USA"]
    assert reread["value"].tolist() == [1.23]


def test_remote_style_backend_remove(memory_azure_backend: AzureStorageBackend) -> None:
    backend = memory_azure_backend
    backend.write_bytes("temp.json", b"{}")
    assert backend.exists("temp.json")
    backend.remove("temp.json")
    assert not backend.exists("temp.json")
    backend.remove("never/existed")  # no error


def test_identical_logical_structure_across_local_and_remote_backends(
    tmp_path: Path, memory_azure_backend: AzureStorageBackend
) -> None:
    """The same relative paths and glob patterns behave identically on both
    backends -- pipeline code that only talks to StorageBackend cannot tell
    which one it's using, which is the whole point of the abstraction."""
    local = LocalStorageBackend(tmp_path / "zone")
    remote = memory_azure_backend

    for backend in (local, remote):
        backend.write_bytes("source=x/snapshot_id=1/data.parquet", b"a")
        backend.write_bytes("source=x/snapshot_id=2/data.parquet", b"b")

    local_matches = sorted(local.glob("source=x/snapshot_id=*/data.parquet"))
    remote_matches = sorted(remote.glob("source=x/snapshot_id=*/data.parquet"))
    assert (
        local_matches
        == remote_matches
        == [
            "source=x/snapshot_id=1/data.parquet",
            "source=x/snapshot_id=2/data.parquet",
        ]
    )


# ---------------------------------------------------------------------------
# Managed identity: no secret involved
# ---------------------------------------------------------------------------


def test_resolve_credential_uses_managed_identity_when_client_id_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from azure.identity import ManagedIdentityCredential

    monkeypatch.setenv("AZURE_CLIENT_ID", "11111111-1111-1111-1111-111111111111")
    credential = resolve_credential()
    assert isinstance(credential, ManagedIdentityCredential)


def test_resolve_credential_falls_back_to_default_without_client_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from azure.identity import DefaultAzureCredential

    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    credential = resolve_credential()
    assert isinstance(credential, DefaultAzureCredential)


def test_azure_storage_backend_has_no_key_or_secret_attributes() -> None:
    """No account-key/SAS/connection-string field anywhere on the backend --
    the only credential path is resolve_credential()'s managed identity."""
    backend = AzureStorageBackend("abfss://raw@acct.dfs.core.windows.net/")
    forbidden_attr_substrings = ("key", "secret", "sas", "connection_string", "password")
    attr_names = [a for a in vars(backend) if not a.startswith("_")]
    for name in attr_names:
        lowered = name.lower()
        assert not any(bad in lowered for bad in forbidden_attr_substrings), name


# ---------------------------------------------------------------------------
# Property-based: path-joining invariants
# ---------------------------------------------------------------------------


@given(
    st.text(
        alphabet=st.characters(blacklist_characters="/\\\x00", blacklist_categories=("Cs",)),
        min_size=1,
        max_size=20,
    )
)
def test_local_backend_resolve_stays_within_root(tmp_path_factory, segment: str) -> None:  # noqa: ANN001
    root = tmp_path_factory.mktemp("zone")
    backend = LocalStorageBackend(root)
    resolved = backend._resolve(segment)  # noqa: SLF001 - invariant test on internals
    assert resolved == root / segment

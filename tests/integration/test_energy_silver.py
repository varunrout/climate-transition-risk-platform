"""Energy silver table builder against bronze fixtures written directly to a tmp lake."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from climate_risk.storage import LakeStorage, backend_for_uri, read_parquet, write_parquet
from climate_risk.transforms.silver import build_fact_country_year_energy
from climate_risk.transforms.writer import write_fact_country_year_energy


def _make_lake(root: Path) -> LakeStorage:
    storage = LakeStorage(
        raw=backend_for_uri(str(root / "raw")),
        bronze=backend_for_uri(str(root / "bronze")),
        silver=backend_for_uri(str(root / "silver")),
        gold=backend_for_uri(str(root / "gold")),
    )
    storage.ensure_zones()
    return storage


@pytest.fixture
def lake_with_energy_bronze(tmp_path: Path) -> LakeStorage:
    lake = _make_lake(tmp_path / "lake")
    write_parquet(
        lake.bronze,
        "source=owid_energy/snapshot_id=abc123/data.parquet",
        pd.DataFrame(
            {
                "country_iso3": ["USA", "USA", "CHN", "CHN"],
                "year": [2019, 2020, 2019, 2020],
                "coal_share_elec": [23.5, 19.3, 65.0, 63.0],
                "gas_share_elec": [38.4, 40.3, 3.3, 3.3],
                "oil_share_elec": [0.5, 0.4, 0.2, 0.2],
                "fossil_share_elec": [62.4, 60.0, 68.5, 66.5],
                "renewables_share_elec": [17.6, 19.8, 26.7, 28.0],
                "low_carbon_share_elec": [38.4, 40.1, 32.0, 33.7],
                "nuclear_share_elec": [20.0, 20.3, 4.9, 4.8],
                "solar_share_elec": [1.8, 2.5, 3.0, 3.4],
                "wind_share_elec": [7.3, 8.4, 5.5, 6.1],
                "hydro_share_elec": [6.6, 6.8, 17.2, 17.4],
                "biofuel_share_elec": [1.5, 1.6, 0.9, 0.9],
            }
        ),
    )
    return lake


def test_build_fact_country_year_energy_scopes_and_stamps_snapshot(
    lake_with_energy_bronze: LakeStorage,
) -> None:
    frame, snapshot_set_id, report = build_fact_country_year_energy(lake_with_energy_bronze)

    assert not report.has_fatal
    assert len(snapshot_set_id) == 16
    assert set(frame["country_iso3"].unique()) == {"USA", "CHN"}
    assert (frame["snapshot_set_id"] == snapshot_set_id).all()
    # raw pass-through only -- no derived trend/momentum columns at this layer
    assert "coal_trend_pp_per_year" not in frame.columns


def test_no_duplicate_keys(lake_with_energy_bronze: LakeStorage) -> None:
    frame, _, report = build_fact_country_year_energy(lake_with_energy_bronze)
    assert not frame.duplicated(subset=["country_iso3", "year", "snapshot_set_id"]).any()
    assert not report.has_fatal


def test_write_and_read_back(lake_with_energy_bronze: LakeStorage) -> None:
    frame, snapshot_set_id, _ = build_fact_country_year_energy(lake_with_energy_bronze)
    write_fact_country_year_energy(
        frame, snapshot_set_id=snapshot_set_id, lake=lake_with_energy_bronze
    )

    path = f"fact_country_year_energy/snapshot_set_id={snapshot_set_id}/data.parquet"
    assert lake_with_energy_bronze.silver.exists(path)
    reread = read_parquet(lake_with_energy_bronze.silver, path)
    assert len(reread) == len(frame)


def test_missing_bronze_snapshot_raises_clear_error(tmp_path: Path) -> None:
    lake = _make_lake(tmp_path / "empty_lake")
    with pytest.raises(FileNotFoundError, match="no accepted bronze snapshot"):
        build_fact_country_year_energy(lake)

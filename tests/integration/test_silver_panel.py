"""Silver panel builder against bronze fixtures written directly to a tmp lake."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from climate_risk.config.loader import load_countries
from climate_risk.storage import LakeStorage, backend_for_uri, read_parquet, write_parquet
from climate_risk.transforms.silver import (
    build_dim_country,
    build_silver_panel,
    latest_complete_common_year,
)
from climate_risk.transforms.writer import write_dim_country, write_fact_country_year_transition


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
def lake_with_bronze(tmp_path: Path) -> LakeStorage:
    lake = _make_lake(tmp_path / "lake")

    write_parquet(
        lake.bronze,
        "source=owid_co2/snapshot_id=abc123/data.parquet",
        pd.DataFrame(
            {
                "country_iso3": ["USA", "USA", "CHN", "CHN"],
                "year": [2019, 2020, 2019, 2020],
                "co2": [5144.361, 4712.774, 10707.219, 10914.395],
                "gdp": [23315000000000.0, 22132000000000.0, 14340000000000.0, 14688000000000.0],
                "population": [328239523, 331526933, 1407745000, 1411100000],
                "primary_energy_consumption": [26908.4, 25218.9, 144778.2, 148215.6],
                "co2_per_capita": [15.67, 14.22, 7.61, 7.73],
            }
        ),
    )
    write_parquet(
        lake.bronze,
        "source=world_bank_wdi/snapshot_id=def456/data.parquet",
        pd.DataFrame(
            {
                "country_iso3": ["USA", "USA", "CHN", "CHN"],
                "year": [2019, 2020, 2019, 2020],
                "gdp_constant_2015_usd": [
                    20328833000000.0,
                    19856000000000.0,
                    13894817000000.0,
                    14504927000000.0,
                ],
                "population": [328239523, 331526933, 1407745000, 1411100000],
            }
        ),
    )
    return lake


def test_build_silver_panel_joins_and_computes_intensity(lake_with_bronze: LakeStorage) -> None:
    panel, snapshot_set_id, report = build_silver_panel(lake_with_bronze)

    assert not report.has_fatal
    assert len(snapshot_set_id) == 16
    assert set(panel["country_iso3"].unique()) == {"USA", "CHN"}
    assert panel["is_core_complete"].all()

    usa_2019 = panel[(panel["country_iso3"] == "USA") & (panel["year"] == 2019)].iloc[0]
    expected_intensity = (5144.361 * 1e9) / 20328833000000.0
    assert usa_2019["carbon_intensity_gdp"] == pytest.approx(expected_intensity)
    # World Bank is primary GDP; OWID GDP is kept only as a secondary column, not blended in.
    assert usa_2019["real_gdp"] == 20328833000000.0
    assert usa_2019["secondary_gdp_owid"] == 23315000000000.0


def test_no_duplicate_keys_and_no_aggregate_leakage(lake_with_bronze: LakeStorage) -> None:
    panel, _, report = build_silver_panel(lake_with_bronze)
    assert not panel.duplicated(subset=["country_iso3", "year", "snapshot_set_id"]).any()
    assert not report.has_fatal


def test_latest_complete_common_year_requires_all_countries(lake_with_bronze: LakeStorage) -> None:
    panel, _, _ = build_silver_panel(lake_with_bronze)
    # only USA/CHN present in this fixture, not the full 19-country config -> no common year
    assert latest_complete_common_year(panel, countries=set(load_countries().keys())) is None
    assert latest_complete_common_year(panel, countries={"USA", "CHN"}) == 2020


def test_write_silver_zone_is_readable_back(lake_with_bronze: LakeStorage) -> None:
    panel, snapshot_set_id, _ = build_silver_panel(lake_with_bronze)
    write_dim_country(build_dim_country(), lake=lake_with_bronze)
    write_fact_country_year_transition(
        panel, snapshot_set_id=snapshot_set_id, lake=lake_with_bronze
    )

    dim = read_parquet(lake_with_bronze.silver, "dim_country/data.parquet")
    assert len(dim) == 19  # full G20 sovereign panel, independent of which countries have data

    fact_path = f"fact_country_year_transition/snapshot_set_id={snapshot_set_id}/data.parquet"
    assert lake_with_bronze.silver.exists(fact_path)
    reread = read_parquet(lake_with_bronze.silver, fact_path)
    assert len(reread) == len(panel)


def test_missing_bronze_snapshot_raises_clear_error(tmp_path: Path) -> None:
    lake = _make_lake(tmp_path / "empty_lake")
    with pytest.raises(FileNotFoundError, match="no accepted bronze snapshot"):
        build_silver_panel(lake)

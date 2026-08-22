"""Silver-zone writers."""

from __future__ import annotations

import pandas as pd

from climate_risk.storage import LakeStorage, write_parquet


def write_dim_country(dim_country: pd.DataFrame, *, lake: LakeStorage) -> None:
    write_parquet(lake.silver, "dim_country/data.parquet", dim_country)


def write_fact_country_year_transition(
    panel: pd.DataFrame, *, snapshot_set_id: str, lake: LakeStorage
) -> None:
    write_parquet(
        lake.silver,
        f"fact_country_year_transition/snapshot_set_id={snapshot_set_id}/data.parquet",
        panel,
    )

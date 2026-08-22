"""Atomic silver-zone writers."""

from __future__ import annotations

import pandas as pd

from climate_risk.config.loader import RunPaths


def write_dim_country(dim_country: pd.DataFrame, *, paths: RunPaths) -> None:
    out_dir = paths.silver / "dim_country"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / ".data.parquet.tmp"
    final = out_dir / "data.parquet"
    dim_country.to_parquet(tmp, index=False)
    tmp.replace(final)


def write_fact_country_year_transition(
    panel: pd.DataFrame, *, snapshot_set_id: str, paths: RunPaths
) -> None:
    out_dir = paths.silver / "fact_country_year_transition" / f"snapshot_set_id={snapshot_set_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / ".data.parquet.tmp"
    final = out_dir / "data.parquet"
    panel.to_parquet(tmp, index=False)
    tmp.replace(final)

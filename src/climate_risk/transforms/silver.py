"""Silver country-year panel builder (07_data_model_and_contracts.md sections 4-5).

Builds `dim_country` (from the controlled config/countries.yaml mapping —
no fuzzy matching) and `fact_country_year_transition` by joining the latest
accepted OWID and World Bank bronze snapshots on (country_iso3, year).

GDP handling follows 06_data_sources_and_licensing.md section 8: World Bank
`gdp_constant_2015_usd` is the nominated primary source for `real_gdp`
because it is a constant-price series suitable for intensity ratios; OWID's
`gdp` field uses a different (non-constant-price) definition and is kept
only as `secondary_gdp_owid` for visibility, not blended into `real_gdp` and
not compared against it with a numeric tolerance, since the two are not
unit-comparable levels. No field here is imputed — a missing value stays
missing and is counted in `missing_feature_count` (01_data_ingestion.md
section 9: "a row with missing denominator data is not silently imputed").
"""

from __future__ import annotations

import hashlib

import pandas as pd

from climate_risk.config.loader import load_countries
from climate_risk.contracts.models import QualitySeverity, ValidationEvent, ValidationReport
from climate_risk.storage import LakeStorage, StorageBackend, read_parquet

CORE_FEATURES = ["co2_mt", "real_gdp", "population"]


def latest_bronze_snapshot(bronze: StorageBackend, source_name: str) -> tuple[str, str]:
    """Return (data_path, snapshot_id) for the most recently written bronze
    snapshot of `source_name`. "Latest" is picked by real backend
    last-modified metadata (`StorageBackend.modified_at`), not path
    ordering -- snapshot_id is a content hash, not a timestamp, so multiple
    historical snapshot dirs are not chronologically sortable by name.
    "Latest" here is the promotion barrier from 01_data_ingestion.md section
    8 in its simplest form: a snapshot only exists here if it was accepted
    (zero FATAL events).
    """
    candidates = bronze.glob(f"source={source_name}/snapshot_id=*/data.parquet")
    if not candidates:
        raise FileNotFoundError(
            f"no accepted bronze snapshot for source={source_name!r}; run `climate-risk ingest` first"
        )
    latest = max(candidates, key=bronze.modified_at)
    snapshot_id = latest.split("/")[-2].removeprefix("snapshot_id=")
    return latest, snapshot_id


def build_dim_country() -> pd.DataFrame:
    countries = load_countries()
    rows = [
        {
            "country_iso3": c.country_iso3,
            "country_name": c.country_name,
            "g20_flag": c.g20_flag,
            "region": c.region,
            "income_group": c.income_group,
            "valid_from": "2000-01-01",
            "valid_to": None,
        }
        for c in countries.values()
    ]
    return pd.DataFrame(rows)


def build_silver_panel(lake: LakeStorage) -> tuple[pd.DataFrame, str, ValidationReport]:
    """Join OWID + World Bank bronze into fact_country_year_transition.

    Returns (panel, snapshot_set_id, validation_report). Raises nothing on
    data problems — problems become ValidationEvents so the caller decides
    whether the FATAL-gated promotion to silver/ happens (mirrors the
    ingestion pipeline's fail-closed pattern).
    """
    owid_path, owid_snapshot = latest_bronze_snapshot(lake.bronze, "owid_co2")
    wb_path, wb_snapshot = latest_bronze_snapshot(lake.bronze, "world_bank_wdi")

    owid = read_parquet(lake.bronze, owid_path)
    world_bank = read_parquet(lake.bronze, wb_path)

    countries = load_countries()
    in_scope = set(countries.keys())

    owid_slim = owid[owid["country_iso3"].isin(in_scope)][
        [
            "country_iso3",
            "year",
            "co2",
            "gdp",
            "population",
            "primary_energy_consumption",
            "co2_per_capita",
        ]
    ].rename(
        columns={
            "co2": "co2_mt",
            "gdp": "secondary_gdp_owid",
            "population": "population_owid",
            "primary_energy_consumption": "primary_energy_twh",
        }
    )
    wb_slim = world_bank[world_bank["country_iso3"].isin(in_scope)][
        ["country_iso3", "year", "gdp_constant_2015_usd", "population"]
    ].rename(columns={"gdp_constant_2015_usd": "real_gdp", "population": "population_wb"})

    panel = owid_slim.merge(wb_slim, on=["country_iso3", "year"], how="outer")
    panel["population"] = panel["population_wb"].where(
        panel["population_wb"].notna(), panel["population_owid"]
    )
    panel = panel.drop(columns=["population_owid", "population_wb"])

    panel["carbon_intensity_gdp"] = (panel["co2_mt"] * 1e9) / panel[
        "real_gdp"
    ]  # kg CO2 per real USD
    panel["energy_intensity_gdp"] = panel["primary_energy_twh"] / panel["real_gdp"]

    panel["missing_feature_count"] = panel[CORE_FEATURES].isna().sum(axis=1)
    panel["is_core_complete"] = panel["missing_feature_count"] == 0
    panel["imputation_mask"] = ""  # no imputation is performed anywhere in this stage

    snapshot_set_id = hashlib.sha256(
        f"owid:{owid_snapshot}|world_bank:{wb_snapshot}".encode()
    ).hexdigest()[:16]
    panel["snapshot_set_id"] = snapshot_set_id

    columns = [
        "country_iso3",
        "year",
        "co2_mt",
        "real_gdp",
        "secondary_gdp_owid",
        "population",
        "carbon_intensity_gdp",
        "co2_per_capita",
        "energy_intensity_gdp",
        "primary_energy_twh",
        "is_core_complete",
        "missing_feature_count",
        "imputation_mask",
        "snapshot_set_id",
    ]
    panel = panel[columns].sort_values(["country_iso3", "year"]).reset_index(drop=True)

    report = _quality_checks(panel, countries=set(countries.keys()))
    return panel, snapshot_set_id, report


def _quality_checks(panel: pd.DataFrame, *, countries: set[str]) -> ValidationReport:
    events: list[ValidationEvent] = []

    dupes = panel.duplicated(subset=["country_iso3", "year", "snapshot_set_id"]).sum()
    if dupes:
        events.append(
            ValidationEvent(
                rule_id="DQ-PANEL-010",
                severity=QualitySeverity.FATAL,
                message=f"{dupes} duplicate (country_iso3, year, snapshot_set_id) row(s) in silver panel",
            )
        )

    non_sovereign = set(panel["country_iso3"].unique()) - countries
    if non_sovereign:
        events.append(
            ValidationEvent(
                rule_id="DQ-PANEL-011",
                severity=QualitySeverity.FATAL,
                message=f"Non-sovereign/aggregate rows leaked into the panel: {sorted(non_sovereign)}",
            )
        )

    if len(panel):
        complete_by_country = panel[panel["is_core_complete"]].groupby("country_iso3")["year"].max()
        latest_common_complete_year = (
            int(complete_by_country.min()) if len(complete_by_country) == len(countries) else None
        )
        if latest_common_complete_year is None:
            missing = countries - set(complete_by_country.index)
            events.append(
                ValidationEvent(
                    rule_id="DQ-GDP-020",
                    severity=QualitySeverity.WARN,
                    message=(
                        "No single latest common complete year across all in-scope countries; "
                        f"countries with zero fully-complete years: {sorted(missing)}"
                    ),
                )
            )

    return ValidationReport(events=events)


def latest_complete_common_year(panel: pd.DataFrame, *, countries: set[str]) -> int | None:
    """The latest year where every in-scope country has all core features present.

    01_data_ingestion.md section 9: more recent partial years may exist in
    the panel for exploratory use but must not enter a model requiring
    complete target features.
    """
    complete = panel[panel["is_core_complete"]]
    if complete.empty:
        return None
    years_per_country = complete.groupby("country_iso3")["year"].apply(set)
    if set(years_per_country.index) != countries:
        return None
    common_years = set.intersection(*years_per_country.tolist())
    return max(common_years) if common_years else None

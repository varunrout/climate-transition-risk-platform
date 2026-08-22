"""Our World in Data CO2 & Greenhouse Gas Emissions adapter.

Role and risks documented in 06_data_sources_and_licensing.md section 2.
OWID already publishes an iso_code column, so country identity resolution
here is a direct match against config/countries.yaml rather than fuzzy
name matching (the controlled-mapping requirement in 07_data_model_and_contracts.md
section 4 is satisfied by the config, not by string heuristics in this adapter).
"""

from __future__ import annotations

from io import StringIO

import httpx
import pandas as pd

from climate_risk.config.loader import load_countries, load_source_registry
from climate_risk.contracts.models import (
    QualitySeverity,
    RawArtifact,
    ValidationEvent,
    ValidationReport,
)
from climate_risk.ingestion.base import HttpSourceAdapter
from climate_risk.ingestion.http_utils import get_with_retry

REQUIRED_COLUMNS = {
    "country",
    "iso_code",
    "year",
    "co2",
    "co2_per_gdp",
    "gdp",
    "population",
    "energy_per_gdp",
    "primary_energy_consumption",
    "co2_per_capita",
}


class OwidCo2Adapter(HttpSourceAdapter):
    source_name = "owid_co2"
    parser_version = "1.0.0"

    def __init__(self) -> None:
        self.source_url = load_source_registry()["owid_co2"].url

    def _download(self) -> httpx.Response:
        return get_with_retry(self.source_url, timeout=60.0)

    def standardise(self, artifact: RawArtifact, raw_bytes: bytes) -> pd.DataFrame:
        frame = pd.read_csv(StringIO(raw_bytes.decode("utf-8")))

        countries = load_countries()
        in_scope_iso3 = set(countries.keys())
        frame = frame[frame["iso_code"].isin(in_scope_iso3)].copy()

        keep = [c for c in REQUIRED_COLUMNS if c in frame.columns]
        frame = frame[keep].rename(columns={"iso_code": "country_iso3"})
        frame["source_snapshot_id"] = artifact.sha256[:16]
        frame["parser_version"] = self.parser_version
        return frame.reset_index(drop=True)

    def quality_checks(self, frame: pd.DataFrame) -> ValidationReport:
        events: list[ValidationEvent] = []
        missing_required = REQUIRED_COLUMNS - set(frame.columns) - {"iso_code"}
        # country_iso3 replaces iso_code after standardise(); check on the renamed set.
        missing_required = {c for c in missing_required if c != "iso_code"}
        if "country_iso3" not in frame.columns:
            missing_required.add("country_iso3")
        if missing_required:
            events.append(
                ValidationEvent(
                    rule_id="DQ-OWID-001",
                    severity=QualitySeverity.FATAL,
                    message=f"Missing required columns after standardisation: {sorted(missing_required)}",
                )
            )
            return ValidationReport(events=events)

        dupes = frame.duplicated(subset=["country_iso3", "year"]).sum()
        if dupes:
            events.append(
                ValidationEvent(
                    rule_id="DQ-PANEL-010",
                    severity=QualitySeverity.FATAL,
                    message=f"{dupes} duplicate (country_iso3, year) row(s) in OWID bronze frame",
                )
            )

        countries = load_countries()
        present = set(frame["country_iso3"].unique())
        missing_g20 = set(countries.keys()) - present
        if missing_g20:
            events.append(
                ValidationEvent(
                    rule_id="DQ-COUNTRY-031",
                    severity=QualitySeverity.WARN,
                    message=f"G20 countries absent from OWID snapshot: {sorted(missing_g20)}",
                )
            )

        latest_year = int(frame["year"].max()) if len(frame) else None
        if latest_year is not None:
            missing_gdp_latest = frame[(frame["year"] == latest_year) & frame["gdp"].isna()]
            if len(missing_gdp_latest):
                events.append(
                    ValidationEvent(
                        rule_id="DQ-GDP-020",
                        severity=QualitySeverity.WARN,
                        message=(
                            f"{len(missing_gdp_latest)} countries missing GDP in latest source "
                            f"year {latest_year} (known OWID/GDP reporting lag)"
                        ),
                        year=latest_year,
                    )
                )

        return ValidationReport(events=events)

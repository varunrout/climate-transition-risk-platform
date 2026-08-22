"""Our World in Data energy-mix adapter (M6).

Electricity-generation-mix share columns, re-published by OWID from Ember's
Yearly Electricity Data plus the Energy Institute's Statistical Review of
World Energy. Licence, access path and country/year coverage for this
project's 19-country G20 panel were verified directly (not assumed) --
see docs/m6_source_feasibility.md. Same controlled-mapping country
resolution as OwidCo2Adapter (climate_risk.ingestion.owid): OWID already
publishes iso_code, so no fuzzy name matching is needed.
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

# Raw share-of-electricity-generation columns kept in bronze/silver. Sub-technology
# columns (solar/wind/hydro/biofuel) are carried for transparency/drill-down; the
# v1 derived feature set (climate_risk.features.energy_transition) only consumes
# fossil/coal/renewables/low_carbon.
REQUIRED_COLUMNS = {
    "country",
    "iso_code",
    "year",
    "coal_share_elec",
    "gas_share_elec",
    "oil_share_elec",
    "fossil_share_elec",
    "renewables_share_elec",
    "low_carbon_share_elec",
    "nuclear_share_elec",
    "solar_share_elec",
    "wind_share_elec",
    "hydro_share_elec",
    "biofuel_share_elec",
}


class OwidEnergyAdapter(HttpSourceAdapter):
    source_name = "owid_energy"
    parser_version = "1.0.0"

    def __init__(self) -> None:
        self.source_url = load_source_registry()["owid_energy"].url

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
        missing_required = {c for c in REQUIRED_COLUMNS if c != "iso_code"} - set(frame.columns)
        if "country_iso3" not in frame.columns:
            missing_required.add("country_iso3")
        if missing_required:
            events.append(
                ValidationEvent(
                    rule_id="DQ-OWIDENERGY-001",
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
                    message=f"{dupes} duplicate (country_iso3, year) row(s) in OWID energy bronze frame",
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
                    message=f"G20 countries absent from OWID energy snapshot: {sorted(missing_g20)}",
                )
            )

        latest_year = int(frame["year"].max()) if len(frame) else None
        if latest_year is not None:
            missing_latest = frame[
                (frame["year"] == latest_year) & frame["fossil_share_elec"].isna()
            ]
            if len(missing_latest):
                events.append(
                    ValidationEvent(
                        rule_id="DQ-ENERGY-040",
                        severity=QualitySeverity.WARN,
                        message=(
                            f"{len(missing_latest)} countries missing electricity-mix data in "
                            f"latest source year {latest_year} (known reporting lag)"
                        ),
                        year=latest_year,
                    )
                )

        return ValidationReport(events=events)

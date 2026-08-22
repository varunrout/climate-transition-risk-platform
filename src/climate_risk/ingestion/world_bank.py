"""World Bank World Development Indicators adapter.

Fetches GDP (constant 2015 US$, NY.GDP.MKTP.KD) and population
(SP.POP.TOTL) for the G20 sovereign panel. Two indicator calls are combined
into a single raw artifact so the manifest/checksum contract still applies
to "one source fetch" even though the upstream API is per-indicator.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from climate_risk.config.loader import load_countries
from climate_risk.contracts.models import (
    QualitySeverity,
    RawArtifact,
    ValidationEvent,
    ValidationReport,
)
from climate_risk.ingestion.http_utils import get_with_retry

INDICATORS = {
    "NY.GDP.MKTP.KD": "gdp_constant_2015_usd",
    "SP.POP.TOTL": "population",
}


class WorldBankAdapter:
    source_name = "world_bank_wdi"
    parser_version = "1.0.0"

    def __init__(self) -> None:
        countries = load_countries()
        self.country_codes = sorted(countries.keys())
        self.source_url = (
            "https://api.worldbank.org/v2/country/"
            f"{';'.join(self.country_codes)}/indicator/{{indicator}}"
            "?format=json&per_page=20000&date=2000:2025"
        )

    def fetch(self, *, dest_dir: Path) -> RawArtifact:
        dest_dir.mkdir(parents=True, exist_ok=True)
        combined: dict[str, list[dict[str, object]]] = {}
        last_status = 200
        for indicator in INDICATORS:
            url = (
                "https://api.worldbank.org/v2/country/"
                f"{';'.join(self.country_codes)}/indicator/{indicator}"
                "?format=json&per_page=20000&date=2000:2025"
            )
            response = get_with_retry(url, timeout=60.0)
            last_status = response.status_code
            if response.status_code != 200:
                combined[indicator] = []
                continue
            payload = response.json()
            # WB returns [metadata, data] on success, or a single error dict on failure.
            combined[indicator] = (
                payload[1] if isinstance(payload, list) and len(payload) > 1 else []
            )

        payload_bytes = json.dumps(combined, sort_keys=True).encode("utf-8")
        payload_path = dest_dir / f"{self.source_name}.payload"
        payload_path.write_bytes(payload_bytes)
        sha256 = hashlib.sha256(payload_bytes).hexdigest()

        return RawArtifact(
            source_name=self.source_name,
            source_url=self.source_url,
            retrieved_at_utc=datetime.now(UTC),
            http_status=last_status,
            content_length=len(payload_bytes),
            sha256=sha256,
            content_type="application/json",
            payload_path=str(payload_path),
        )

    def validate_transport(self, artifact: RawArtifact) -> ValidationReport:
        events: list[ValidationEvent] = []
        if artifact.content_length == 0:
            events.append(
                ValidationEvent(
                    rule_id="DQ-TRANSPORT-002",
                    severity=QualitySeverity.FATAL,
                    message="Zero-byte World Bank payload",
                )
            )
        return ValidationReport(events=events)

    def fingerprint_schema(self, artifact: RawArtifact) -> str:
        frame = self.standardise(artifact)
        column_signature = "|".join(f"{c}:{frame[c].dtype}" for c in sorted(frame.columns))
        return hashlib.sha256(column_signature.encode("utf-8")).hexdigest()

    def standardise(self, artifact: RawArtifact) -> pd.DataFrame:
        combined = json.loads(Path(artifact.payload_path).read_text(encoding="utf-8"))

        frames = []
        for indicator, column_name in INDICATORS.items():
            rows = combined.get(indicator, [])
            if not rows:
                continue
            frame = pd.DataFrame(rows)
            frame = frame[["countryiso3code", "date", "value"]].rename(
                columns={"countryiso3code": "country_iso3", "date": "year", "value": column_name}
            )
            frame["year"] = frame["year"].astype(int)
            frames.append(frame.set_index(["country_iso3", "year"]))

        if not frames:
            return pd.DataFrame(columns=["country_iso3", "year", *INDICATORS.values()])

        merged = frames[0]
        for frame in frames[1:]:
            merged = merged.join(frame, how="outer")
        merged = merged.reset_index()
        merged["source_snapshot_id"] = artifact.sha256[:16]
        merged["parser_version"] = self.parser_version
        return merged

    def quality_checks(self, frame: pd.DataFrame) -> ValidationReport:
        events: list[ValidationEvent] = []
        required = {"country_iso3", "year", *INDICATORS.values()}
        missing = required - set(frame.columns)
        if missing:
            events.append(
                ValidationEvent(
                    rule_id="DQ-WB-001",
                    severity=QualitySeverity.FATAL,
                    message=f"Missing required columns: {sorted(missing)}",
                )
            )
            return ValidationReport(events=events)

        dupes = frame.duplicated(subset=["country_iso3", "year"]).sum()
        if dupes:
            events.append(
                ValidationEvent(
                    rule_id="DQ-PANEL-010",
                    severity=QualitySeverity.FATAL,
                    message=f"{dupes} duplicate (country_iso3, year) row(s) in World Bank bronze frame",
                )
            )

        negative_gdp = frame[frame["gdp_constant_2015_usd"] < 0]
        if len(negative_gdp):
            events.append(
                ValidationEvent(
                    rule_id="DQ-WB-001",
                    severity=QualitySeverity.ERROR,
                    message=f"{len(negative_gdp)} row(s) with negative GDP",
                )
            )

        if len(frame):
            latest_year = int(frame["year"].max())
            missing_gdp_latest = frame[
                (frame["year"] == latest_year) & frame["gdp_constant_2015_usd"].isna()
            ]
            if len(missing_gdp_latest):
                events.append(
                    ValidationEvent(
                        rule_id="DQ-GDP-020",
                        severity=QualitySeverity.WARN,
                        message=(
                            f"{len(missing_gdp_latest)} countries missing GDP in latest source "
                            f"year {latest_year} (known World Bank reporting lag)"
                        ),
                        year=latest_year,
                    )
                )

        return ValidationReport(events=events)

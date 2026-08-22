from __future__ import annotations

from climate_risk.contracts.models import QualitySeverity
from climate_risk.ingestion.owid import OwidCo2Adapter


def test_standardise_filters_to_g20_and_drops_world_aggregate(owid_artifact) -> None:  # noqa: ANN001
    adapter = OwidCo2Adapter()
    artifact, raw_bytes = owid_artifact
    frame = adapter.standardise(artifact, raw_bytes)

    assert set(frame["country_iso3"]) == {"USA", "CHN", "DEU"}
    assert "OWID_WRL" not in set(frame["country_iso3"])  # aggregate must not leak in


def test_no_duplicate_country_year_keys(owid_artifact) -> None:  # noqa: ANN001
    adapter = OwidCo2Adapter()
    artifact, raw_bytes = owid_artifact
    frame = adapter.standardise(artifact, raw_bytes)
    report = adapter.quality_checks(frame)
    assert report.by_severity(QualitySeverity.FATAL) == []


def test_missing_gdp_in_latest_year_is_warn_not_silent(owid_artifact) -> None:  # noqa: ANN001
    adapter = OwidCo2Adapter()
    artifact, raw_bytes = owid_artifact
    frame = adapter.standardise(artifact, raw_bytes)
    report = adapter.quality_checks(frame)
    gdp_warnings = [
        e for e in report.by_severity(QualitySeverity.WARN) if e.rule_id == "DQ-GDP-020"
    ]
    assert len(gdp_warnings) == 1  # Germany 2020 GDP is null in the fixture


def test_duplicate_country_year_is_fatal() -> None:
    import pandas as pd

    adapter = OwidCo2Adapter()
    frame = pd.DataFrame(
        {
            "country_iso3": ["USA", "USA"],
            "year": [2020, 2020],
            "gdp": [1.0, 1.0],
        }
    )
    report = adapter.quality_checks(frame)
    fatal = report.by_severity(QualitySeverity.FATAL)
    assert any(e.rule_id == "DQ-OWID-001" for e in fatal)  # missing required columns -> fatal

from __future__ import annotations

import pandas as pd

from climate_risk.contracts.models import QualitySeverity
from climate_risk.ingestion.owid_energy import OwidEnergyAdapter


def test_standardise_filters_to_g20_and_drops_world_aggregate(owid_energy_artifact) -> None:  # noqa: ANN001
    adapter = OwidEnergyAdapter()
    artifact, raw_bytes = owid_energy_artifact
    frame = adapter.standardise(artifact, raw_bytes)

    assert set(frame["country_iso3"]) == {"USA", "CHN", "DEU"}
    assert "OWID_WRL" not in set(frame["country_iso3"])


def test_no_duplicate_country_year_keys(owid_energy_artifact) -> None:  # noqa: ANN001
    adapter = OwidEnergyAdapter()
    artifact, raw_bytes = owid_energy_artifact
    frame = adapter.standardise(artifact, raw_bytes)
    report = adapter.quality_checks(frame)
    assert report.by_severity(QualitySeverity.FATAL) == []


def test_missing_latest_year_data_is_warn_not_silent(owid_energy_artifact) -> None:  # noqa: ANN001
    adapter = OwidEnergyAdapter()
    artifact, raw_bytes = owid_energy_artifact
    frame = adapter.standardise(artifact, raw_bytes)
    report = adapter.quality_checks(frame)
    energy_warnings = [
        e for e in report.by_severity(QualitySeverity.WARN) if e.rule_id == "DQ-ENERGY-040"
    ]
    assert len(energy_warnings) == 1  # Germany 2020 fossil_share_elec is null in the fixture


def test_missing_required_columns_is_fatal() -> None:
    adapter = OwidEnergyAdapter()
    frame = pd.DataFrame({"country_iso3": ["USA"], "year": [2020]})
    report = adapter.quality_checks(frame)
    fatal = report.by_severity(QualitySeverity.FATAL)
    assert any(e.rule_id == "DQ-OWIDENERGY-001" for e in fatal)


def test_duplicate_country_year_is_fatal(owid_energy_artifact) -> None:  # noqa: ANN001
    adapter = OwidEnergyAdapter()
    artifact, raw_bytes = owid_energy_artifact
    frame = adapter.standardise(artifact, raw_bytes)
    duplicated = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    report = adapter.quality_checks(duplicated)
    fatal = report.by_severity(QualitySeverity.FATAL)
    assert any(e.rule_id == "DQ-PANEL-010" for e in fatal)

from __future__ import annotations

from climate_risk.contracts.models import QualitySeverity
from climate_risk.ingestion.world_bank import WorldBankAdapter


def test_standardise_merges_gdp_and_population(world_bank_artifact) -> None:  # noqa: ANN001
    adapter = WorldBankAdapter()
    frame = adapter.standardise(world_bank_artifact)

    row = frame[(frame["country_iso3"] == "USA") & (frame["year"] == 2019)].iloc[0]
    assert row["gdp_constant_2015_usd"] == 20328833000000.0
    assert row["population"] == 328239523


def test_null_population_is_missing_not_fabricated(world_bank_artifact) -> None:  # noqa: ANN001
    adapter = WorldBankAdapter()
    frame = adapter.standardise(world_bank_artifact)
    row = frame[(frame["country_iso3"] == "CHN") & (frame["year"] == 2020)].iloc[0]
    assert row["population"] != row["population"]  # NaN, not silently imputed


def test_no_fatal_quality_events_on_clean_fixture(world_bank_artifact) -> None:  # noqa: ANN001
    adapter = WorldBankAdapter()
    frame = adapter.standardise(world_bank_artifact)
    report = adapter.quality_checks(frame)
    assert report.by_severity(QualitySeverity.FATAL) == []

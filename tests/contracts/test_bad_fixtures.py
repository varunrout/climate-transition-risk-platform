"""Adversarial fixtures per 08_data_quality_and_validation.md section 10."""

from __future__ import annotations

import pandas as pd

from climate_risk.contracts.models import QualitySeverity
from climate_risk.ingestion.owid import OwidCo2Adapter
from climate_risk.ingestion.world_bank import WorldBankAdapter


def test_html_error_page_masquerading_as_csv_is_fatal_transport(owid_artifact) -> None:  # noqa: ANN001
    adapter = OwidCo2Adapter()
    html_artifact = owid_artifact.model_copy(update={"content_type": "text/html; charset=utf-8"})
    report = adapter.validate_transport(html_artifact)
    assert report.has_fatal


def test_zero_byte_payload_is_fatal_transport(owid_artifact) -> None:  # noqa: ANN001
    adapter = OwidCo2Adapter()
    empty_artifact = owid_artifact.model_copy(update={"content_length": 0})
    report = adapter.validate_transport(empty_artifact)
    assert report.has_fatal


def test_non_200_status_is_fatal_transport(owid_artifact) -> None:  # noqa: ANN001
    adapter = OwidCo2Adapter()
    error_artifact = owid_artifact.model_copy(update={"http_status": 503})
    report = adapter.validate_transport(error_artifact)
    assert report.has_fatal


def test_negative_gdp_flagged_error() -> None:
    adapter = WorldBankAdapter()
    frame = pd.DataFrame(
        {
            "country_iso3": ["USA"],
            "year": [2020],
            "gdp_constant_2015_usd": [-1.0],
            "population": [100.0],
        }
    )
    report = adapter.quality_checks(frame)
    assert any(e.severity == QualitySeverity.ERROR for e in report.events)

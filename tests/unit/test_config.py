from __future__ import annotations

from climate_risk.config.loader import load_countries, load_source_registry
from climate_risk.config.models import LicenceReviewStatus


def test_countries_g20_sovereign_count() -> None:
    countries = load_countries()
    assert len(countries) == 19  # 19 sovereign G20 members; EU aggregate excluded
    assert all(len(iso3) == 3 and iso3.isupper() for iso3 in countries)
    assert "USA" in countries
    assert "EU" not in countries


def test_sources_owid_and_world_bank_enabled_and_approved() -> None:
    sources = load_source_registry()
    assert sources["owid_co2"].enabled
    assert sources["owid_co2"].licence_review_status == LicenceReviewStatus.APPROVED
    assert sources["world_bank_wdi"].enabled
    assert sources["world_bank_wdi"].licence_review_status == LicenceReviewStatus.APPROVED


def test_ember_pending_verification_is_disabled() -> None:
    sources = load_source_registry()
    ember = sources["ember_global_electricity"]
    assert ember.licence_review_status == LicenceReviewStatus.PENDING_VERIFICATION
    assert ember.enabled is False

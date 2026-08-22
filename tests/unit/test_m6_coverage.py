from __future__ import annotations

import pandas as pd

from climate_risk.config.loader import load_countries
from climate_risk.research.m6_coverage import (
    MIN_COUNTRY_COVERAGE_PCT,
    evaluate_cross_sectional_coverage,
    evaluate_source_column_coverage,
)

ALL_COUNTRIES = sorted(load_countries().keys())


def test_full_coverage_passes_threshold() -> None:
    latest_year = 2024
    rows = []
    for country in ALL_COUNTRIES:
        for year in range(latest_year - 9, latest_year + 1):
            rows.append({"country_iso3": country, "year": year, "coal_share_elec": 10.0})
    panel = pd.DataFrame(rows)

    result = evaluate_source_column_coverage(panel, column="coal_share_elec")
    assert result.country_coverage_pct == 1.0
    assert result.missing_countries == []
    assert result.meets_minimum_thresholds is True


def test_missing_countries_are_reported_and_fail_threshold() -> None:
    latest_year = 2024
    present = ALL_COUNTRIES[:2]  # far below MIN_COUNTRY_COVERAGE_PCT of the full 19-country panel
    rows = [
        {"country_iso3": country, "year": year, "coal_share_elec": 10.0}
        for country in present
        for year in range(latest_year - 9, latest_year + 1)
    ]
    panel = pd.DataFrame(rows)

    result = evaluate_source_column_coverage(panel, column="coal_share_elec")
    assert result.country_coverage_pct < MIN_COUNTRY_COVERAGE_PCT
    assert set(result.missing_countries) == set(ALL_COUNTRIES) - set(present)
    assert result.meets_minimum_thresholds is False
    assert any("country_coverage_pct" in reason for reason in result.threshold_failure_reasons)


def test_stale_country_detected_when_latest_year_lags() -> None:
    latest_year = 2024
    rows = []
    for country in ALL_COUNTRIES:
        end_year = latest_year - 3 if country == ALL_COUNTRIES[0] else latest_year
        for year in range(latest_year - 9, end_year + 1):
            rows.append({"country_iso3": country, "year": year, "coal_share_elec": 10.0})
    panel = pd.DataFrame(rows)

    result = evaluate_source_column_coverage(panel, column="coal_share_elec")
    assert ALL_COUNTRIES[0] in result.stale_countries


def test_short_history_country_detected() -> None:
    latest_year = 2024
    rows = []
    for country in ALL_COUNTRIES:
        years = (
            [latest_year]
            if country == ALL_COUNTRIES[0]
            else range(latest_year - 9, latest_year + 1)
        )
        for year in years:
            rows.append({"country_iso3": country, "year": year, "coal_share_elec": 10.0})
    panel = pd.DataFrame(rows)

    result = evaluate_source_column_coverage(panel, column="coal_share_elec")
    assert ALL_COUNTRIES[0] in result.short_history_countries


def test_cross_sectional_coverage_on_evaluation_panel() -> None:
    evaluation_panel = pd.DataFrame(
        {
            "country_iso3": ALL_COUNTRIES,
            "some_feature": [1.0] * (len(ALL_COUNTRIES) - 1) + [None],
        }
    )
    result = evaluate_cross_sectional_coverage(evaluation_panel, feature_name="some_feature")
    assert result.countries_present == len(ALL_COUNTRIES) - 1
    assert result.missing_countries == [ALL_COUNTRIES[-1]]

"""M6 coverage analysis.

Thresholds are declared as module-level constants -- fixed before this
module is ever run against real evaluation results, not chosen after
seeing which features would pass. Any future change to a threshold value
is a visible code diff with its own commit message, not a silent tuning
pass.
"""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, ConfigDict

from climate_risk.config.loader import load_countries

# ---------------------------------------------------------------------------
# Minimum inclusion thresholds -- fixed before evaluation, per the M6 brief
# ("Define explicit minimum inclusion thresholds before evaluating the
# score. Do not choose thresholds after seeing favourable results.").
# ---------------------------------------------------------------------------
MIN_COUNTRY_COVERAGE_PCT = 0.90
"""A feature must have a non-null latest value for >=90% of the 19-country
panel (i.e. at least 17/19) to be eligible for score inclusion. Below this,
too many countries would need whole-component weight renormalisation for
the feature to be a credible cross-sectional signal."""

MIN_COUNTRY_YEAR_COVERAGE_PCT_10YR = 0.85
"""Over the trailing 10 years, >=85% of (country, year) cells must be
non-null for a raw source column to be considered reliably measured, not
just spottily available in the latest year."""

MAX_STALE_DATA_RATE = 0.10
"""No more than 10% of countries may be "stale" (their latest available
year for this feature more than 1 year behind the panel's overall latest
year) -- a feature that's systematically a year+ behind for a chunk of the
panel would silently bias the score toward whichever countries report on
time."""

MIN_HISTORY_YEARS_FOR_TREND = 5
"""A trend/momentum feature (OLS slope, YoY mean, residual) needs >=5
distinct non-null years of history for a country to be included -- stricter
than the 3-observation floor in climate_risk.features.energy_transition,
which is a "can we compute at all" floor, not a "is this trustworthy
enough for a sovereign risk score" floor."""


class CoverageResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    feature_name: str
    country_coverage_pct: float
    countries_present: int
    countries_total: int
    missing_countries: list[str]
    short_history_countries: list[str]
    stale_countries: list[str]
    stale_data_rate: float
    country_year_coverage_pct_latest_year: float | None
    country_year_coverage_pct_5yr: float | None
    country_year_coverage_pct_10yr: float | None
    meets_minimum_thresholds: bool
    threshold_failure_reasons: list[str]


def _country_year_coverage(
    raw_panel: pd.DataFrame, *, column: str, countries: list[str], latest_year: int, window: int
) -> float | None:
    years = range(latest_year - window + 1, latest_year + 1)
    cells = raw_panel[raw_panel["year"].isin(years)]
    total_possible = len(countries) * len(list(years))
    if total_possible == 0:
        return None
    present = cells[cells["country_iso3"].isin(countries) & cells[column].notna()]
    return len(present) / total_possible


def evaluate_cross_sectional_coverage(
    evaluation_panel: pd.DataFrame, *, feature_name: str
) -> CoverageResult:
    """Coverage of a feature already reduced to one row per country
    (the m6_panel.build_evaluation_panel output)."""
    countries = sorted(load_countries().keys())
    present_mask = evaluation_panel.set_index("country_iso3")[feature_name].notna()
    present_mask = present_mask.reindex(countries, fill_value=False)
    present = present_mask[present_mask].index.tolist()
    missing = present_mask[~present_mask].index.tolist()

    coverage_pct = len(present) / len(countries)
    failures: list[str] = []
    if coverage_pct < MIN_COUNTRY_COVERAGE_PCT:
        failures.append(
            f"country_coverage_pct {coverage_pct:.2%} < minimum {MIN_COUNTRY_COVERAGE_PCT:.0%}"
        )

    return CoverageResult(
        feature_name=feature_name,
        country_coverage_pct=coverage_pct,
        countries_present=len(present),
        countries_total=len(countries),
        missing_countries=sorted(missing),
        short_history_countries=[],
        stale_countries=[],
        stale_data_rate=0.0,
        country_year_coverage_pct_latest_year=None,
        country_year_coverage_pct_5yr=None,
        country_year_coverage_pct_10yr=None,
        meets_minimum_thresholds=not failures,
        threshold_failure_reasons=failures,
    )


def evaluate_source_column_coverage(
    raw_energy_panel: pd.DataFrame, *, column: str
) -> CoverageResult:
    """Full country-year coverage of a raw source column in
    fact_country_year_energy, over the latest year / trailing 5yr / trailing
    10yr windows -- catches "looks fine in the latest year but sparse
    historically" that a cross-sectional-only check would miss."""
    countries = sorted(load_countries().keys())
    latest_year = int(raw_energy_panel["year"].max())

    by_country = raw_energy_panel[raw_energy_panel["country_iso3"].isin(countries)]
    history_years = by_country.dropna(subset=[column]).groupby("country_iso3")["year"].apply(set)

    present_countries = sorted(history_years.index.tolist())
    missing_countries = sorted(set(countries) - set(present_countries))

    short_history = sorted(
        str(c) for c, years in history_years.items() if len(years) < MIN_HISTORY_YEARS_FOR_TREND
    )

    stale = sorted(
        str(c) for c, years in history_years.items() if years and max(years) < latest_year - 1
    )
    stale_rate = len(stale) / len(countries)

    coverage_latest = _country_year_coverage(
        by_country, column=column, countries=countries, latest_year=latest_year, window=1
    )
    coverage_5yr = _country_year_coverage(
        by_country, column=column, countries=countries, latest_year=latest_year, window=5
    )
    coverage_10yr = _country_year_coverage(
        by_country, column=column, countries=countries, latest_year=latest_year, window=10
    )

    coverage_pct = len(present_countries) / len(countries)
    failures: list[str] = []
    if coverage_pct < MIN_COUNTRY_COVERAGE_PCT:
        failures.append(
            f"country_coverage_pct {coverage_pct:.2%} < minimum {MIN_COUNTRY_COVERAGE_PCT:.0%}"
        )
    if coverage_10yr is not None and coverage_10yr < MIN_COUNTRY_YEAR_COVERAGE_PCT_10YR:
        failures.append(
            f"10yr country-year coverage {coverage_10yr:.2%} < minimum {MIN_COUNTRY_YEAR_COVERAGE_PCT_10YR:.0%}"
        )
    if stale_rate > MAX_STALE_DATA_RATE:
        failures.append(f"stale_data_rate {stale_rate:.2%} > maximum {MAX_STALE_DATA_RATE:.0%}")

    return CoverageResult(
        feature_name=column,
        country_coverage_pct=coverage_pct,
        countries_present=len(present_countries),
        countries_total=len(countries),
        missing_countries=missing_countries,
        short_history_countries=short_history,
        stale_countries=stale,
        stale_data_rate=stale_rate,
        country_year_coverage_pct_latest_year=coverage_latest,
        country_year_coverage_pct_5yr=coverage_5yr,
        country_year_coverage_pct_10yr=coverage_10yr,
        meets_minimum_thresholds=not failures,
        threshold_failure_reasons=failures,
    )


RAW_SOURCE_COLUMNS = [
    "coal_share_elec",
    "fossil_share_elec",
    "renewables_share_elec",
    "low_carbon_share_elec",
]

DERIVED_FEATURE_COLUMNS = [
    "coal_trend_pp_per_year",
    "clean_power_momentum_pp_per_year",
    "renewable_buildout_rate_pp_per_year",
    "fossil_persistence_mean_pct",
    "transition_velocity",
    "stalled_transition_residual_pp",
]


def run_coverage_analysis(
    evaluation_panel: pd.DataFrame, raw_energy_panel: pd.DataFrame
) -> pd.DataFrame:
    """One row per candidate feature: raw source columns get full
    country-year coverage; derived/cross-sectional features get the
    latest-value coverage check (their own trailing-window logic already
    enforces a minimum history internally)."""
    results = [
        evaluate_source_column_coverage(raw_energy_panel, column=c) for c in RAW_SOURCE_COLUMNS
    ]
    results += [
        evaluate_cross_sectional_coverage(evaluation_panel, feature_name=c)
        for c in DERIVED_FEATURE_COLUMNS
    ]
    results += [
        evaluate_cross_sectional_coverage(evaluation_panel, feature_name=c)
        for c in ("carbon_intensity_trend", "coupling_elasticity")
    ]
    return pd.DataFrame([r.model_dump() for r in results])

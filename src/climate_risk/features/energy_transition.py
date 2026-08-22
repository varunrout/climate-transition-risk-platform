"""Energy-system transition features (M6).

Computed only from the verified `fact_country_year_energy` raw silver table
(docs/m6_source_feasibility.md) -- never from a fabricated or unverified
source. Every feature here is diagnostic/exploratory: none of it is wired
into `climate_risk.scoring.risk_score` yet. The M6 brief requires coverage,
collinearity, incremental-information and backtest checks before any energy
feature is allowed to influence the risk score -- those checks have not been
run, so this module intentionally has no call site inside `scoring/`.

Two feature families are explicitly *not* computed here because the
verified source doesn't carry the underlying column, and the project's rule
is to record a gap rather than approximate or fabricate one:
- electricity carbon intensity (gCO2/kWh) -- not present in OWID `energy-data`'s
  currently-ingested columns.
- absolute electricity-demand growth -- `energy-data`'s ingested columns are
  generation-mix shares (%), not absolute generation/demand levels.
"""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, ConfigDict
from scipy import stats

DEFAULT_TRAILING_WINDOW_YEARS = 5
MIN_TRAILING_OBSERVATIONS = 3


class EnergyTransitionFeatures(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_iso3: str
    latest_year: int
    trailing_window_years: int
    sample_size: int

    # Latest-year raw levels (% of electricity generation) -- pass-through from
    # fact_country_year_energy, repeated here only for convenience so this
    # artifact is self-contained; not a second source of truth.
    coal_share_elec: float | None
    fossil_share_elec: float | None
    renewables_share_elec: float | None
    low_carbon_share_elec: float | None

    # Trend/momentum: OLS slope of the named series vs year, in percentage
    # points per year, fit over the trailing window ending at latest_year.
    coal_trend_pp_per_year: float | None
    clean_power_momentum_pp_per_year: float | None

    # Mean year-over-year change in renewables_share_elec over the trailing
    # window (percentage points per year) -- "build-out rate".
    renewable_buildout_rate_pp_per_year: float | None

    # Trailing-window mean fossil share -- reported as a raw, transparent
    # persistence measure (not blended with the trend slope into a single
    # opaque "lock-in score": that composite is exactly the kind of derived
    # judgement call the M6 brief requires to be backtested before use).
    fossil_persistence_mean_pct: float | None

    # clean_power_momentum_pp_per_year normalised by remaining headroom to
    # 100% low-carbon share -- a country at 90% moving +1pp/yr is closer to
    # "done" than one at 20% moving +1pp/yr; None if headroom is ~0.
    transition_velocity: float | None

    # actual latest low_carbon_share_elec minus the value the trailing-window
    # trend would have predicted for latest_year -- negative means the
    # transition has stalled relative to its own recent trend.
    stalled_transition_residual_pp: float | None


def _trailing_slope_pp_per_year(
    frame: pd.DataFrame, *, column: str, window_years: int
) -> tuple[float | None, int]:
    rows = frame.dropna(subset=[column]).sort_values("year")
    if len(rows) < MIN_TRAILING_OBSERVATIONS:
        return None, len(rows)
    latest_year = int(rows["year"].max())
    windowed = rows[rows["year"] > latest_year - window_years]
    if len(windowed) < MIN_TRAILING_OBSERVATIONS:
        return None, len(windowed)
    regression = stats.linregress(windowed["year"].to_numpy(), windowed[column].to_numpy())
    return float(regression.slope), len(windowed)


def compute_energy_features(
    energy_panel: pd.DataFrame,
    *,
    country_iso3: str,
    trailing_window_years: int = DEFAULT_TRAILING_WINDOW_YEARS,
) -> EnergyTransitionFeatures | None:
    """Diagnostic energy-transition features for one country's latest year.

    Returns None (never a fabricated value) if the country has fewer than
    MIN_TRAILING_OBSERVATIONS rows with a non-null fossil/low-carbon share.
    """
    rows = energy_panel[energy_panel["country_iso3"] == country_iso3].sort_values("year")
    if rows.empty:
        return None

    latest = rows.dropna(subset=["fossil_share_elec", "low_carbon_share_elec"], how="all")
    if latest.empty:
        return None
    latest_year = int(latest["year"].max())
    latest_row = latest[latest["year"] == latest_year].iloc[0]

    windowed = rows[rows["year"] > latest_year - trailing_window_years]

    coal_trend, coal_n = _trailing_slope_pp_per_year(
        rows, column="coal_share_elec", window_years=trailing_window_years
    )
    clean_momentum, clean_n = _trailing_slope_pp_per_year(
        rows, column="low_carbon_share_elec", window_years=trailing_window_years
    )
    sample_size = max(coal_n, clean_n)
    if sample_size < MIN_TRAILING_OBSERVATIONS:
        return None

    renewables_series = windowed.dropna(subset=["renewables_share_elec"]).sort_values("year")
    if len(renewables_series) >= 2:
        buildout_rate = float(renewables_series["renewables_share_elec"].diff().dropna().mean())
    else:
        buildout_rate = None

    fossil_series = windowed["fossil_share_elec"].dropna()
    fossil_persistence = float(fossil_series.mean()) if len(fossil_series) else None

    low_carbon_latest = latest_row.get("low_carbon_share_elec")
    low_carbon_latest = float(low_carbon_latest) if pd.notna(low_carbon_latest) else None

    transition_velocity: float | None = None
    if clean_momentum is not None and low_carbon_latest is not None:
        headroom = 100.0 - low_carbon_latest
        if headroom > 1.0:  # avoid dividing by near-zero headroom
            transition_velocity = clean_momentum / headroom

    stalled_residual: float | None = None
    if clean_momentum is not None and low_carbon_latest is not None and len(windowed) >= 2:
        trend_rows = windowed.dropna(subset=["low_carbon_share_elec"]).sort_values("year")
        if len(trend_rows) >= MIN_TRAILING_OBSERVATIONS:
            regression = stats.linregress(
                trend_rows["year"].to_numpy(), trend_rows["low_carbon_share_elec"].to_numpy()
            )
            predicted = float(regression.intercept + regression.slope * latest_year)
            stalled_residual = low_carbon_latest - predicted

    def _val(col: str) -> float | None:
        v = latest_row.get(col)
        return float(v) if pd.notna(v) else None

    return EnergyTransitionFeatures(
        country_iso3=country_iso3,
        latest_year=latest_year,
        trailing_window_years=trailing_window_years,
        sample_size=int(sample_size),
        coal_share_elec=_val("coal_share_elec"),
        fossil_share_elec=_val("fossil_share_elec"),
        renewables_share_elec=_val("renewables_share_elec"),
        low_carbon_share_elec=low_carbon_latest,
        coal_trend_pp_per_year=coal_trend,
        clean_power_momentum_pp_per_year=clean_momentum,
        renewable_buildout_rate_pp_per_year=buildout_rate,
        fossil_persistence_mean_pct=fossil_persistence,
        transition_velocity=transition_velocity,
        stalled_transition_residual_pp=stalled_residual,
    )


def compute_energy_features_for_panel(
    energy_panel: pd.DataFrame,
    *,
    trailing_window_years: int = DEFAULT_TRAILING_WINDOW_YEARS,
) -> pd.DataFrame:
    """Cross-sectional feature table: one row per country with a valid latest
    observation, plus cross-country percentile positioning (computed only
    once every country's latest value is known -- a genuinely cross-sectional
    step, not per-country).
    """
    results = []
    for country_iso3 in sorted(energy_panel["country_iso3"].unique()):
        result = compute_energy_features(
            energy_panel, country_iso3=country_iso3, trailing_window_years=trailing_window_years
        )
        if result is not None:
            results.append(result)

    if not results:
        return pd.DataFrame()

    frame = pd.DataFrame([r.model_dump() for r in results])
    frame["coal_share_elec_percentile"] = frame["coal_share_elec"].rank(pct=True)
    frame["low_carbon_share_elec_percentile"] = frame["low_carbon_share_elec"].rank(pct=True)
    return frame.sort_values("country_iso3").reset_index(drop=True)

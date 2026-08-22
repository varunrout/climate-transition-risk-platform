"""M7 structural-break / regime research framework.

Research-only. Nothing in this module is imported by the production
`run`/`score`/`publish` path. Every detector accepts an optional
`as_of_year` cutoff and filters observations before fitting, so historical
origin evaluation can recompute regime evidence without future leakage.

The default rules are intentionally conservative for annual sovereign
data: one break at most in phase 1, at least five observations per segment,
and at least twelve observations overall.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict
from scipy import stats

BreakMethod = Literal[
    "threshold_baseline",
    "rolling_slope_change",
    "cusum_stability",
    "segmented_regression",
]
Directionality = Literal["higher_is_higher_risk", "higher_is_lower_risk"]
BreakKind = Literal["level", "trend", "volatility"]

BREAK_VERSION = "m7_regime_break_v0.1"
MIN_TOTAL_OBSERVATIONS = 12
MIN_SEGMENT_LENGTH = 5
RECENT_WINDOW_YEARS = 5
MAX_BREAKS_PHASE1 = 1
BREAK_YEAR_TOLERANCE = 1
HISTORICAL_ORIGINS: tuple[int, ...] = (2010, 2012, 2014, 2015, 2016, 2017)


class CandidateSeriesSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    series_name: str
    source_table: str
    source_column: str
    break_kind: BreakKind
    directionality: Directionality
    unit: str
    transformation: str
    minimum_economic_slope_delta: float
    notes: str


class RegimeBreakResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_iso3: str
    series_name: str
    as_of_year: int
    break_method: str
    break_version: str = BREAK_VERSION
    status: str
    latest_regime_start_year: int | None
    years_in_current_regime: int | None
    break_count: int
    strongest_break_year: int | None
    strongest_break_strength: float | None
    pre_break_slope: float | None
    post_break_slope: float | None
    slope_delta: float | None
    fit_improvement_pct: float | None
    regime_direction: str
    regime_confidence: float | None
    current_regime_label: str
    n_observations: int
    min_total_observations: int
    min_segment_length: int
    notes: str


@dataclass(frozen=True)
class _PreparedSeries:
    years: np.ndarray
    values: np.ndarray
    as_of_year: int


def candidate_series_catalog() -> list[CandidateSeriesSpec]:
    return [
        CandidateSeriesSpec(
            series_name="carbon_intensity_gdp",
            source_table="fact_country_year_transition",
            source_column="carbon_intensity_gdp",
            break_kind="trend",
            directionality="higher_is_higher_risk",
            unit="kg CO2 per real USD",
            transformation="log level; breaks evaluated on log(carbon_intensity_gdp)",
            minimum_economic_slope_delta=0.01,
            notes="Primary transition-intensity series used by the scenario engine.",
        ),
        CandidateSeriesSpec(
            series_name="carbon_intensity_log_change",
            source_table="fact_country_year_transition",
            source_column="carbon_intensity_gdp",
            break_kind="level",
            directionality="higher_is_higher_risk",
            unit="annual log change",
            transformation="country-level annual diff(log(carbon_intensity_gdp))",
            minimum_economic_slope_delta=0.005,
            notes="Annual change series, separated from the intensity level trend.",
        ),
        CandidateSeriesSpec(
            series_name="co2_gdp_decoupling_gap",
            source_table="fact_country_year_transition",
            source_column="co2_mt, real_gdp",
            break_kind="level",
            directionality="higher_is_higher_risk",
            unit="annual log CO2 growth minus annual log GDP growth",
            transformation="diff(log(co2_mt)) - diff(log(real_gdp))",
            minimum_economic_slope_delta=0.005,
            notes="Positive means emissions grew faster than GDP; negative means decoupling improved.",
        ),
        CandidateSeriesSpec(
            series_name="low_carbon_share_elec",
            source_table="fact_country_year_energy",
            source_column="low_carbon_share_elec",
            break_kind="trend",
            directionality="higher_is_lower_risk",
            unit="percentage points of electricity generation",
            transformation="raw annual level",
            minimum_economic_slope_delta=0.5,
            notes="M6 frozen energy-component level input.",
        ),
        CandidateSeriesSpec(
            series_name="clean_power_momentum_pp_per_year",
            source_table="fact_country_year_energy",
            source_column="low_carbon_share_elec",
            break_kind="level",
            directionality="higher_is_lower_risk",
            unit="percentage points per year",
            transformation="rolling five-observation OLS slope of low_carbon_share_elec",
            minimum_economic_slope_delta=0.25,
            notes="Year-indexed analogue of the M6 transition-momentum input.",
        ),
        CandidateSeriesSpec(
            series_name="fossil_share_elec",
            source_table="fact_country_year_energy",
            source_column="fossil_share_elec",
            break_kind="trend",
            directionality="higher_is_higher_risk",
            unit="percentage points of electricity generation",
            transformation="raw annual level",
            minimum_economic_slope_delta=0.5,
            notes="Risk-relevant power-system dependence input; kept separate from low-carbon share.",
        ),
        CandidateSeriesSpec(
            series_name="coal_share_elec",
            source_table="fact_country_year_energy",
            source_column="coal_share_elec",
            break_kind="trend",
            directionality="higher_is_higher_risk",
            unit="percentage points of electricity generation",
            transformation="raw annual level",
            minimum_economic_slope_delta=0.5,
            notes="Material coal-dependence series; M6 rejected it as a score level signal, not as diagnostics.",
        ),
    ]


def build_candidate_series_panel(
    transition_panel: pd.DataFrame, energy_panel: pd.DataFrame
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    transition = transition_panel.sort_values(["country_iso3", "year"]).copy()
    energy = energy_panel.sort_values(["country_iso3", "year"]).copy()

    rows.append(
        _long_series(
            transition,
            series_name="carbon_intensity_gdp",
            value=transition["carbon_intensity_gdp"].where(transition["carbon_intensity_gdp"] > 0),
            transform_log=True,
        )
    )

    transition["carbon_intensity_log_change"] = transition.groupby("country_iso3")[
        "carbon_intensity_gdp"
    ].transform(lambda s: np.log(s.where(s > 0)).diff())
    rows.append(
        _long_series(
            transition,
            series_name="carbon_intensity_log_change",
            value=transition["carbon_intensity_log_change"],
        )
    )

    co2_log_change = (
        np.log(transition["co2_mt"].where(transition["co2_mt"] > 0))
        .groupby(transition["country_iso3"])
        .diff()
    )
    gdp_log_change = (
        np.log(transition["real_gdp"].where(transition["real_gdp"] > 0))
        .groupby(transition["country_iso3"])
        .diff()
    )
    transition["co2_gdp_decoupling_gap"] = co2_log_change - gdp_log_change
    rows.append(
        _long_series(
            transition,
            series_name="co2_gdp_decoupling_gap",
            value=transition["co2_gdp_decoupling_gap"],
        )
    )

    for column in ["low_carbon_share_elec", "fossil_share_elec", "coal_share_elec"]:
        rows.append(_long_series(energy, series_name=column, value=energy[column]))

    momentum = pd.Series(np.nan, index=energy.index, dtype=float)
    for _, group in energy.groupby("country_iso3"):
        momentum.loc[group.index] = _rolling_slope(group)
    energy["clean_power_momentum_pp_per_year"] = momentum
    rows.append(
        _long_series(
            energy,
            series_name="clean_power_momentum_pp_per_year",
            value=energy["clean_power_momentum_pp_per_year"],
        )
    )

    out = pd.concat(rows, ignore_index=True)
    catalog = {spec.series_name: spec for spec in candidate_series_catalog()}
    out["directionality"] = out["series_name"].map(
        {name: spec.directionality for name, spec in catalog.items()}
    )
    return out.dropna(subset=["value"]).sort_values(["series_name", "country_iso3", "year"])


def run_phase1_diagnostics(
    transition_panel: pd.DataFrame,
    energy_panel: pd.DataFrame,
    *,
    random_seed: int = 42,
    bootstrap_iterations: int = 100,
    max_bootstrap_profiles: int = 12,
) -> dict[str, object]:
    series_panel = build_candidate_series_panel(transition_panel, energy_panel)
    catalog = pd.DataFrame([spec.model_dump() for spec in candidate_series_catalog()])
    breaks = detect_breaks_for_panel(series_panel)
    method_comparison = compare_methods(breaks)
    agreement = method_agreement(breaks)
    profiles = regime_profiles(breaks)
    bootstrap_keys = _bootstrap_profile_keys(breaks, max_profiles=max_bootstrap_profiles)
    stability = bootstrap_stability_for_panel(
        series_panel,
        method="segmented_regression",
        n_iterations=bootstrap_iterations,
        random_seed=random_seed,
        profile_keys=bootstrap_keys,
    )
    case_studies = select_country_case_studies(breaks, stability)
    decision = {
        "milestone": "M7",
        "phase": "phase1",
        "decision": "PHASE2_JUSTIFIED",
        "decision_is_not_production_promotion": True,
        "reasons": [
            "phase 1 implemented leakage-safe candidate diagnostics and produced method-sensitive results for real data",
            "scenario-engine value has not yet been backtested; production score and Azure pipeline remain unchanged",
        ],
        "minimum_history_rules": {
            "min_total_observations": MIN_TOTAL_OBSERVATIONS,
            "min_segment_length": MIN_SEGMENT_LENGTH,
            "recent_window_years": RECENT_WINDOW_YEARS,
            "max_breaks_phase1": MAX_BREAKS_PHASE1,
            "max_bootstrap_profiles_phase1": max_bootstrap_profiles,
        },
        "candidate_series": catalog.to_dict(orient="records"),
    }
    return {
        "candidate_series": series_panel,
        "feature_catalog": catalog,
        "country_breaks": breaks,
        "method_comparison": method_comparison,
        "method_agreement": agreement,
        "regime_profiles": profiles,
        "break_stability": stability,
        "country_case_studies": case_studies,
        "decision": decision,
    }


def run_phase2_diagnostics(
    transition_panel: pd.DataFrame,
    energy_panel: pd.DataFrame,
    *,
    origins: tuple[int, ...] = HISTORICAL_ORIGINS,
) -> dict[str, object]:
    """Historical-origin M7 diagnostics.

    At each origin, the same detectors are recomputed using only observations
    available at or before that year. This measures whether apparent regimes
    would have been visible through time; it does not alter the scenario engine.
    """
    series_panel = build_candidate_series_panel(transition_panel, energy_panel)
    origin_results = detect_breaks_by_origin(series_panel, origins=origins)
    origin_agreement = method_agreement_by_origin(origin_results)
    temporal_stability = temporal_regime_stability(origin_results)
    decision = {
        "milestone": "M7",
        "phase": "phase2",
        "decision": "PHASE3_JUSTIFIED",
        "decision_is_not_production_promotion": True,
        "reasons": [
            "historical-origin regime recomputation is implemented and leakage-safe",
            "scenario value and interval calibration remain untested until Phase 3",
        ],
        "origins": list(origins),
        "minimum_history_rules": {
            "min_total_observations": MIN_TOTAL_OBSERVATIONS,
            "min_segment_length": MIN_SEGMENT_LENGTH,
            "max_breaks_phase1_and_phase2": MAX_BREAKS_PHASE1,
        },
    }
    return {
        "origin_regime_results": origin_results,
        "origin_method_agreement": origin_agreement,
        "temporal_stability": temporal_stability,
        "decision": decision,
    }


def detect_breaks_for_panel(series_panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    specs = {spec.series_name: spec for spec in candidate_series_catalog()}
    for (country_iso3, series_name), group in series_panel.groupby(["country_iso3", "series_name"]):
        spec = specs[str(series_name)]
        for method in (
            "threshold_baseline",
            "rolling_slope_change",
            "cusum_stability",
            "segmented_regression",
        ):
            result = detect_break(
                group,
                country_iso3=str(country_iso3),
                series_name=str(series_name),
                directionality=spec.directionality,
                method=method,
                minimum_economic_slope_delta=spec.minimum_economic_slope_delta,
            )
            rows.append(result.model_dump())
    return pd.DataFrame(rows)


def detect_breaks_by_origin(
    series_panel: pd.DataFrame, *, origins: tuple[int, ...] = HISTORICAL_ORIGINS
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    specs = {spec.series_name: spec for spec in candidate_series_catalog()}
    for origin_year in origins:
        for (country_iso3, series_name), group in series_panel.groupby(
            ["country_iso3", "series_name"]
        ):
            spec = specs[str(series_name)]
            for method in (
                "threshold_baseline",
                "rolling_slope_change",
                "cusum_stability",
                "segmented_regression",
            ):
                result = detect_break(
                    group,
                    country_iso3=str(country_iso3),
                    series_name=str(series_name),
                    directionality=spec.directionality,
                    method=method,
                    minimum_economic_slope_delta=spec.minimum_economic_slope_delta,
                    as_of_year=origin_year,
                )
                row = result.model_dump()
                row["origin_year"] = origin_year
                rows.append(row)
    return pd.DataFrame(rows)


def detect_break(
    frame: pd.DataFrame,
    *,
    country_iso3: str,
    series_name: str,
    directionality: Directionality,
    method: BreakMethod,
    minimum_economic_slope_delta: float,
    as_of_year: int | None = None,
) -> RegimeBreakResult:
    prepared = _prepare_series(frame, as_of_year=as_of_year)
    if len(prepared.values) < MIN_TOTAL_OBSERVATIONS:
        return _insufficient(country_iso3, series_name, prepared, method)

    if method == "threshold_baseline":
        return _threshold_baseline(
            country_iso3, series_name, prepared, directionality, minimum_economic_slope_delta
        )
    if method == "rolling_slope_change":
        return _rolling_slope_change(
            country_iso3, series_name, prepared, directionality, minimum_economic_slope_delta
        )
    if method == "cusum_stability":
        return _cusum_stability(
            country_iso3, series_name, prepared, directionality, minimum_economic_slope_delta
        )
    return _segmented_regression(
        country_iso3, series_name, prepared, directionality, minimum_economic_slope_delta
    )


def compare_methods(breaks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if breaks.empty:
        return pd.DataFrame()
    for (series_name, method), group in breaks.groupby(["series_name", "break_method"]):
        eligible = group[group["status"] != "INSUFFICIENT_EVIDENCE"]
        detected = eligible[eligible["break_count"] > 0]
        rows.append(
            {
                "series_name": series_name,
                "break_method": method,
                "eligible_country_count": int(eligible["country_iso3"].nunique()),
                "detected_break_count": int(len(detected)),
                "median_break_strength": _maybe_median(detected["strongest_break_strength"]),
                "median_regime_confidence": _maybe_median(detected["regime_confidence"]),
                "accelerating_count": int(
                    (eligible["current_regime_label"] == "ACCELERATING_TRANSITION").sum()
                ),
                "stalled_count": int(
                    (eligible["current_regime_label"] == "STALLED_TRANSITION").sum()
                ),
                "deteriorating_count": int(
                    (eligible["current_regime_label"] == "DETERIORATING_TRANSITION").sum()
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(["series_name", "break_method"])


def method_agreement(breaks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (country_iso3, series_name), group in breaks.groupby(["country_iso3", "series_name"]):
        eligible = group[group["status"] != "INSUFFICIENT_EVIDENCE"]
        if eligible.empty:
            continue
        detected = eligible[eligible["break_count"] > 0]
        years = detected["strongest_break_year"].dropna().astype(int).tolist()
        modal_year = _modal_break_year(years)
        agreeing_years = (
            sum(abs(year - modal_year) <= BREAK_YEAR_TOLERANCE for year in years)
            if modal_year is not None
            else 0
        )
        directions = detected["regime_direction"].dropna().tolist()
        rows.append(
            {
                "country_iso3": country_iso3,
                "series_name": series_name,
                "eligible_methods": int(len(eligible)),
                "methods_detecting_break": int(len(detected)),
                "break_detection_agreement": float(len(detected) / len(eligible)),
                "modal_break_year": modal_year,
                "break_year_agreement_within_1yr": (
                    float(agreeing_years / len(detected)) if len(detected) else np.nan
                ),
                "slope_direction_agreement": _share_modal(directions),
                "mean_regime_confidence": _maybe_mean(detected["regime_confidence"]),
                "method_sensitivity": (
                    "ROBUST_ACROSS_METHODS"
                    if len(detected) >= 3 and agreeing_years >= 3
                    else "METHOD_SENSITIVE"
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(["series_name", "country_iso3"])


def method_agreement_by_origin(origin_results: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for origin_year, group in origin_results.groupby("origin_year"):
        agreement = method_agreement(group)
        if not agreement.empty:
            agreement["origin_year"] = cast(int, origin_year)
            rows.append(agreement)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).sort_values(
        ["origin_year", "series_name", "country_iso3"]
    )


def temporal_regime_stability(origin_results: pd.DataFrame) -> pd.DataFrame:
    segmented = origin_results[origin_results["break_method"] == "segmented_regression"].copy()
    if segmented.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for (country_iso3, series_name), group in segmented.groupby(["country_iso3", "series_name"]):
        eligible = group[group["status"] != "INSUFFICIENT_EVIDENCE"].sort_values("origin_year")
        if eligible.empty:
            rows.append(
                {
                    "country_iso3": country_iso3,
                    "series_name": series_name,
                    "eligible_origins": 0,
                    "break_detection_rate": np.nan,
                    "label_switch_count": np.nan,
                    "modal_break_year": np.nan,
                    "break_year_spread": np.nan,
                    "latest_origin_label": None,
                }
            )
            continue
        detected = eligible[eligible["break_count"] > 0]
        labels = eligible["current_regime_label"].tolist()
        break_years = detected["strongest_break_year"].dropna().astype(int).tolist()
        rows.append(
            {
                "country_iso3": country_iso3,
                "series_name": series_name,
                "eligible_origins": int(len(eligible)),
                "break_detection_rate": float(len(detected) / len(eligible)),
                "label_switch_count": int(
                    sum(a != b for a, b in zip(labels, labels[1:], strict=False))
                ),
                "modal_break_year": _modal_break_year(break_years),
                "break_year_spread": (
                    int(max(break_years) - min(break_years)) if break_years else np.nan
                ),
                "latest_origin_label": labels[-1],
            }
        )
    return pd.DataFrame(rows).sort_values(["series_name", "country_iso3"])


def regime_profiles(breaks: pd.DataFrame) -> pd.DataFrame:
    segmented = breaks[breaks["break_method"] == "segmented_regression"].copy()
    if segmented.empty:
        return segmented
    cols = [
        "country_iso3",
        "series_name",
        "as_of_year",
        "latest_regime_start_year",
        "years_in_current_regime",
        "break_count",
        "strongest_break_year",
        "strongest_break_strength",
        "pre_break_slope",
        "post_break_slope",
        "slope_delta",
        "regime_direction",
        "regime_confidence",
        "current_regime_label",
        "break_method",
        "break_version",
    ]
    return segmented[cols].sort_values(["series_name", "country_iso3"]).reset_index(drop=True)


def bootstrap_stability_for_panel(
    series_panel: pd.DataFrame,
    *,
    method: BreakMethod = "segmented_regression",
    n_iterations: int = 100,
    random_seed: int = 42,
    profile_keys: set[tuple[str, str]] | None = None,
) -> pd.DataFrame:
    specs = {spec.series_name: spec for spec in candidate_series_catalog()}
    rows: list[dict[str, object]] = []
    for (country_iso3, series_name), group in series_panel.groupby(["country_iso3", "series_name"]):
        key = (str(country_iso3), str(series_name))
        if profile_keys is not None and key not in profile_keys:
            continue
        spec = specs[str(series_name)]
        stability = bootstrap_break_stability(
            group,
            country_iso3=str(country_iso3),
            series_name=str(series_name),
            directionality=spec.directionality,
            method=method,
            minimum_economic_slope_delta=spec.minimum_economic_slope_delta,
            n_iterations=n_iterations,
            random_seed=random_seed,
        )
        rows.append(stability)
    return pd.DataFrame(rows).sort_values(["series_name", "country_iso3"])


def _bootstrap_profile_keys(breaks: pd.DataFrame, *, max_profiles: int) -> set[tuple[str, str]]:
    segmented = breaks[breaks["break_method"] == "segmented_regression"].copy()
    if segmented.empty or max_profiles <= 0:
        return set()
    segmented["sort_confidence"] = segmented["regime_confidence"].fillna(0.0)
    segmented["sort_strength"] = segmented["strongest_break_strength"].fillna(0.0)
    selected = segmented.sort_values(
        ["break_count", "sort_confidence", "sort_strength", "series_name", "country_iso3"],
        ascending=[False, False, False, True, True],
    ).head(max_profiles)
    return {(str(row.country_iso3), str(row.series_name)) for row in selected.itertuples()}


def bootstrap_break_stability(
    frame: pd.DataFrame,
    *,
    country_iso3: str,
    series_name: str,
    directionality: Directionality,
    method: BreakMethod,
    minimum_economic_slope_delta: float,
    n_iterations: int = 100,
    random_seed: int = 42,
) -> dict[str, object]:
    prepared = _prepare_series(frame)
    if len(prepared.values) < MIN_TOTAL_OBSERVATIONS:
        return {
            "country_iso3": country_iso3,
            "series_name": series_name,
            "break_method": method,
            "n_iterations": 0,
            "random_seed": random_seed,
            "break_detection_probability": np.nan,
            "median_break_year": np.nan,
            "break_year_p10": np.nan,
            "break_year_p90": np.nan,
            "slope_delta_median": np.nan,
            "notes": "insufficient history",
        }

    base = _segmented_regression(
        country_iso3, series_name, prepared, directionality, minimum_economic_slope_delta
    )
    residuals = _fit_single_residuals(prepared.years, prepared.values)
    rng = np.random.default_rng(random_seed)
    detected_years: list[int] = []
    slope_deltas: list[float] = []
    for _ in range(n_iterations):
        sampled = rng.choice(residuals, size=len(residuals), replace=True)
        synthetic = _linear_prediction(prepared.years, prepared.values) + sampled
        boot = pd.DataFrame({"year": prepared.years, "value": synthetic})
        result = detect_break(
            boot,
            country_iso3=country_iso3,
            series_name=series_name,
            directionality=directionality,
            method=method,
            minimum_economic_slope_delta=minimum_economic_slope_delta,
        )
        if result.break_count and result.strongest_break_year is not None:
            detected_years.append(result.strongest_break_year)
            if result.slope_delta is not None:
                slope_deltas.append(result.slope_delta)

    return {
        "country_iso3": country_iso3,
        "series_name": series_name,
        "break_method": method,
        "base_break_year": base.strongest_break_year,
        "base_break_strength": base.strongest_break_strength,
        "n_iterations": n_iterations,
        "random_seed": random_seed,
        "break_detection_probability": float(len(detected_years) / n_iterations),
        "median_break_year": float(np.median(detected_years)) if detected_years else np.nan,
        "break_year_p10": float(np.percentile(detected_years, 10)) if detected_years else np.nan,
        "break_year_p90": float(np.percentile(detected_years, 90)) if detected_years else np.nan,
        "slope_delta_median": float(np.median(slope_deltas)) if slope_deltas else np.nan,
        "notes": "residual bootstrap around single-trend null; used for timing stability only",
    }


def select_country_case_studies(breaks: pd.DataFrame, stability: pd.DataFrame) -> dict[str, object]:
    segmented = breaks[breaks["break_method"] == "segmented_regression"].copy()
    if segmented.empty:
        return {"selection_note": "no segmented-regression results available", "cases": []}
    merged = segmented.merge(
        stability[["country_iso3", "series_name", "break_detection_probability"]],
        on=["country_iso3", "series_name"],
        how="left",
    )

    cases: list[dict[str, object]] = []
    targets = [
        ("strong_acceleration", "ACCELERATING_TRANSITION", False),
        ("persistent_transition", "STEADY_IMPROVEMENT", False),
        ("apparent_stall", "STALLED_TRANSITION", False),
        ("deterioration", "DETERIORATING_TRANSITION", False),
        ("no_credible_break", "INSUFFICIENT_EVIDENCE", True),
    ]
    used: set[tuple[str, str]] = set()
    for case_type, label, no_break in targets:
        if no_break:
            pool = merged[merged["break_count"] == 0]
        else:
            pool = merged[merged["current_regime_label"] == label]
        pool = pool.sort_values(
            ["regime_confidence", "strongest_break_strength"], ascending=False, na_position="last"
        )
        for _, row in pool.iterrows():
            key = (str(row["country_iso3"]), str(row["series_name"]))
            if key in used:
                continue
            used.add(key)
            case: dict[str, object] = {"case_type": case_type}
            case.update({str(k): v for k, v in row.dropna().to_dict().items()})
            cases.append(case)
            break
    return {
        "selection_note": "selected mechanically from segmented-regression profiles; no policy attribution inferred",
        "cases": cases,
    }


def _threshold_baseline(
    country_iso3: str,
    series_name: str,
    prepared: _PreparedSeries,
    directionality: Directionality,
    minimum_economic_slope_delta: float,
) -> RegimeBreakResult:
    years = prepared.years
    values = prepared.values
    if len(values) < MIN_SEGMENT_LENGTH * 2:
        return _insufficient(country_iso3, series_name, prepared, "threshold_baseline")
    pre_years = years[-(MIN_SEGMENT_LENGTH * 2) : -MIN_SEGMENT_LENGTH]
    post_years = years[-MIN_SEGMENT_LENGTH:]
    pre_values = values[-(MIN_SEGMENT_LENGTH * 2) : -MIN_SEGMENT_LENGTH]
    post_values = values[-MIN_SEGMENT_LENGTH:]
    pre_slope = _ols_slope(pre_years, pre_values)
    post_slope = _ols_slope(post_years, post_values)
    slope_delta = post_slope - pre_slope
    strength = abs(slope_delta) / _robust_scale(np.diff(values))
    break_year = int(post_years[0])
    confidence = _confidence(strength, abs(slope_delta), minimum_economic_slope_delta, 0.0)
    detected = abs(slope_delta) >= minimum_economic_slope_delta and strength >= 1.0
    return _result(
        country_iso3,
        series_name,
        prepared,
        "threshold_baseline",
        detected,
        break_year,
        strength,
        pre_slope,
        post_slope,
        slope_delta,
        0.0,
        confidence,
        directionality,
    )


def _rolling_slope_change(
    country_iso3: str,
    series_name: str,
    prepared: _PreparedSeries,
    directionality: Directionality,
    minimum_economic_slope_delta: float,
) -> RegimeBreakResult:
    best: tuple[float, int, float, float, float] | None = None
    for idx in range(MIN_SEGMENT_LENGTH, len(prepared.values) - MIN_SEGMENT_LENGTH + 1):
        pre = slice(idx - MIN_SEGMENT_LENGTH, idx)
        post = slice(idx, idx + MIN_SEGMENT_LENGTH)
        pre_slope = _ols_slope(prepared.years[pre], prepared.values[pre])
        post_slope = _ols_slope(prepared.years[post], prepared.values[post])
        delta = post_slope - pre_slope
        strength = abs(delta) / _robust_scale(np.diff(prepared.values))
        if best is None or strength > best[0]:
            best = (strength, int(prepared.years[idx]), pre_slope, post_slope, delta)
    assert best is not None
    strength, break_year, pre_slope, post_slope, slope_delta = best
    confidence = _confidence(strength, abs(slope_delta), minimum_economic_slope_delta, 0.0)
    detected = abs(slope_delta) >= minimum_economic_slope_delta and strength >= 1.25
    return _result(
        country_iso3,
        series_name,
        prepared,
        "rolling_slope_change",
        detected,
        break_year,
        strength,
        pre_slope,
        post_slope,
        slope_delta,
        0.0,
        confidence,
        directionality,
    )


def _cusum_stability(
    country_iso3: str,
    series_name: str,
    prepared: _PreparedSeries,
    directionality: Directionality,
    minimum_economic_slope_delta: float,
) -> RegimeBreakResult:
    years = prepared.years
    values = prepared.values
    residuals = _fit_single_residuals(years, values)
    scale = float(np.std(residuals, ddof=1))
    if scale <= 0:
        return _no_break(country_iso3, series_name, prepared, "cusum_stability")
    cumulative = np.cumsum(residuals / scale)
    valid = range(MIN_SEGMENT_LENGTH, len(values) - MIN_SEGMENT_LENGTH + 1)
    idx = max(valid, key=lambda i: abs(cumulative[i - 1]))
    break_year = int(years[idx])
    pre_slope = _ols_slope(years[:idx], values[:idx])
    post_slope = _ols_slope(years[idx:], values[idx:])
    slope_delta = post_slope - pre_slope
    statistic = abs(float(cumulative[idx - 1])) / np.sqrt(len(values))
    confidence = _confidence(statistic, abs(slope_delta), minimum_economic_slope_delta, 0.0)
    detected = statistic >= 1.25 and abs(slope_delta) >= minimum_economic_slope_delta
    return _result(
        country_iso3,
        series_name,
        prepared,
        "cusum_stability",
        detected,
        break_year,
        statistic,
        pre_slope,
        post_slope,
        slope_delta,
        0.0,
        confidence,
        directionality,
    )


def _segmented_regression(
    country_iso3: str,
    series_name: str,
    prepared: _PreparedSeries,
    directionality: Directionality,
    minimum_economic_slope_delta: float,
) -> RegimeBreakResult:
    years = prepared.years
    values = prepared.values
    single_sse = _sse_linear(years, values)
    best: tuple[float, int, float, float, float] | None = None
    for idx in range(MIN_SEGMENT_LENGTH, len(values) - MIN_SEGMENT_LENGTH + 1):
        pre_sse = _sse_linear(years[:idx], values[:idx])
        post_sse = _sse_linear(years[idx:], values[idx:])
        total_sse = pre_sse + post_sse
        fit_improvement = max(0.0, (single_sse - total_sse) / single_sse) if single_sse > 0 else 0.0
        pre_slope = _ols_slope(years[:idx], values[:idx])
        post_slope = _ols_slope(years[idx:], values[idx:])
        delta = post_slope - pre_slope
        strength = abs(delta) / _robust_scale(np.diff(values))
        score = fit_improvement * strength
        if best is None or score > best[0]:
            best = (score, idx, pre_slope, post_slope, delta)
    assert best is not None
    _score, idx, pre_slope, post_slope, slope_delta = best
    break_year = int(years[idx])
    total_sse = _sse_linear(years[:idx], values[:idx]) + _sse_linear(years[idx:], values[idx:])
    fit_improvement = max(0.0, (single_sse - total_sse) / single_sse) if single_sse > 0 else 0.0
    strength = abs(slope_delta) / _robust_scale(np.diff(values))
    confidence = _confidence(
        strength, abs(slope_delta), minimum_economic_slope_delta, fit_improvement
    )
    detected = (
        fit_improvement >= 0.15
        and abs(slope_delta) >= minimum_economic_slope_delta
        and strength >= 1.25
    )
    return _result(
        country_iso3,
        series_name,
        prepared,
        "segmented_regression",
        detected,
        break_year,
        strength,
        pre_slope,
        post_slope,
        slope_delta,
        fit_improvement,
        confidence,
        directionality,
    )


def _result(
    country_iso3: str,
    series_name: str,
    prepared: _PreparedSeries,
    method: str,
    detected: bool,
    break_year: int,
    strength: float,
    pre_slope: float,
    post_slope: float,
    slope_delta: float,
    fit_improvement: float,
    confidence: float,
    directionality: Directionality,
) -> RegimeBreakResult:
    latest_year = prepared.as_of_year
    regime_start = break_year if detected else int(prepared.years[0])
    direction = _direction(post_slope, directionality)
    label = _label(direction, detected, slope_delta, directionality)
    return RegimeBreakResult(
        country_iso3=country_iso3,
        series_name=series_name,
        as_of_year=latest_year,
        break_method=method,
        status="BREAK_DETECTED" if detected else "NO_CREDIBLE_BREAK",
        latest_regime_start_year=regime_start,
        years_in_current_regime=latest_year - regime_start + 1,
        break_count=1 if detected else 0,
        strongest_break_year=break_year if detected else None,
        strongest_break_strength=float(strength) if detected else None,
        pre_break_slope=float(pre_slope) if detected else None,
        post_break_slope=float(post_slope),
        slope_delta=float(slope_delta) if detected else None,
        fit_improvement_pct=float(fit_improvement * 100.0) if detected else None,
        regime_direction=direction,
        regime_confidence=float(confidence) if detected else 0.0,
        current_regime_label=label,
        n_observations=len(prepared.values),
        min_total_observations=MIN_TOTAL_OBSERVATIONS,
        min_segment_length=MIN_SEGMENT_LENGTH,
        notes="phase-1 single-break diagnostic; not a causal attribution",
    )


def _insufficient(
    country_iso3: str, series_name: str, prepared: _PreparedSeries, method: str
) -> RegimeBreakResult:
    return RegimeBreakResult(
        country_iso3=country_iso3,
        series_name=series_name,
        as_of_year=prepared.as_of_year,
        break_method=method,
        status="INSUFFICIENT_EVIDENCE",
        latest_regime_start_year=None,
        years_in_current_regime=None,
        break_count=0,
        strongest_break_year=None,
        strongest_break_strength=None,
        pre_break_slope=None,
        post_break_slope=None,
        slope_delta=None,
        fit_improvement_pct=None,
        regime_direction="INSUFFICIENT_EVIDENCE",
        regime_confidence=None,
        current_regime_label="INSUFFICIENT_EVIDENCE",
        n_observations=len(prepared.values),
        min_total_observations=MIN_TOTAL_OBSERVATIONS,
        min_segment_length=MIN_SEGMENT_LENGTH,
        notes="fewer than the globally pre-registered minimum observations",
    )


def _no_break(
    country_iso3: str, series_name: str, prepared: _PreparedSeries, method: str
) -> RegimeBreakResult:
    slope = _ols_slope(prepared.years, prepared.values)
    return _result(
        country_iso3,
        series_name,
        prepared,
        method,
        False,
        int(prepared.years[0]),
        0.0,
        slope,
        slope,
        0.0,
        0.0,
        0.0,
        "higher_is_higher_risk",
    )


def _prepare_series(frame: pd.DataFrame, *, as_of_year: int | None = None) -> _PreparedSeries:
    rows = frame.copy()
    if as_of_year is not None:
        rows = rows[rows["year"] <= as_of_year]
    rows = rows.dropna(subset=["value"]).sort_values("year")
    if rows.empty:
        cutoff = int(as_of_year) if as_of_year is not None else -1
        return _PreparedSeries(np.array([], dtype=int), np.array([], dtype=float), cutoff)
    return _PreparedSeries(
        rows["year"].to_numpy(dtype=int),
        rows["value"].to_numpy(dtype=float),
        int(rows["year"].max()),
    )


def _long_series(
    frame: pd.DataFrame, *, series_name: str, value: pd.Series, transform_log: bool = False
) -> pd.DataFrame:
    out = frame[["country_iso3", "year"]].copy()
    out["series_name"] = series_name
    out["value"] = np.log(value) if transform_log else value
    return out


def _rolling_slope(group: pd.DataFrame) -> pd.Series:
    ordered = group.sort_values("year")
    values = []
    for _, row in ordered.iterrows():
        history = ordered[ordered["year"] <= row["year"]].dropna(subset=["low_carbon_share_elec"])
        history = history.tail(RECENT_WINDOW_YEARS)
        if len(history) < MIN_SEGMENT_LENGTH:
            values.append(np.nan)
        else:
            values.append(
                _ols_slope(
                    history["year"].to_numpy(),
                    history["low_carbon_share_elec"].to_numpy(),
                )
            )
    return pd.Series(values, index=ordered.index).reindex(group.index).astype(float)


def _ols_slope(years: np.ndarray, values: np.ndarray) -> float:
    if len(values) < 2 or float(np.std(values)) == 0.0:
        return 0.0
    return float(stats.linregress(years, values).slope)


def _sse_linear(years: np.ndarray, values: np.ndarray) -> float:
    prediction = _linear_prediction(years, values)
    return float(np.sum((values - prediction) ** 2))


def _linear_prediction(years: np.ndarray, values: np.ndarray) -> np.ndarray:
    if len(values) < 2:
        return np.asarray(values, dtype=float)
    regression = stats.linregress(years, values)
    return np.asarray(regression.intercept + regression.slope * years, dtype=float)


def _fit_single_residuals(years: np.ndarray, values: np.ndarray) -> np.ndarray:
    residuals = np.asarray(values, dtype=float) - _linear_prediction(years, values)
    return cast(np.ndarray, residuals)


def _robust_scale(values: np.ndarray) -> float:
    valid = values[np.isfinite(values)]
    if len(valid) == 0:
        return 1.0
    mad = float(np.median(np.abs(valid - np.median(valid)))) * 1.4826
    std = float(np.std(valid, ddof=1)) if len(valid) > 1 else 0.0
    scale = max(mad, std * 0.5, 1e-9)
    return scale


def _confidence(
    strength: float,
    slope_effect: float,
    minimum_economic_slope_delta: float,
    fit_improvement: float,
) -> float:
    effect_component = min(1.0, slope_effect / max(minimum_economic_slope_delta * 3.0, 1e-9))
    strength_component = min(1.0, strength / 3.0)
    fit_component = min(1.0, fit_improvement / 0.35) if fit_improvement > 0 else 0.25
    return float(np.mean([effect_component, strength_component, fit_component]))


def _direction(slope: float, directionality: Directionality) -> str:
    tol = 1e-9
    if abs(slope) <= tol:
        return "FLAT"
    improves = slope < 0 if directionality == "higher_is_higher_risk" else slope > 0
    return "IMPROVING" if improves else "DETERIORATING"


def _label(
    direction: str, detected: bool, slope_delta: float, directionality: Directionality
) -> str:
    if direction == "DETERIORATING":
        return "DETERIORATING_TRANSITION"
    if direction == "FLAT":
        return "STALLED_TRANSITION"
    improves_more = (
        slope_delta < 0 if directionality == "higher_is_higher_risk" else slope_delta > 0
    )
    if detected and improves_more:
        return "ACCELERATING_TRANSITION"
    return "STEADY_IMPROVEMENT"


def _maybe_median(series: pd.Series) -> float | None:
    clean = series.dropna()
    return float(clean.median()) if len(clean) else None


def _maybe_mean(series: pd.Series) -> float | None:
    clean = series.dropna()
    return float(clean.mean()) if len(clean) else None


def _modal_break_year(years: list[int]) -> int | None:
    if not years:
        return None
    return int(pd.Series(years).mode().iloc[0])


def _share_modal(values: list[str]) -> float | None:
    if not values:
        return None
    counts = pd.Series(values).value_counts()
    return float(counts.iloc[0] / len(values))

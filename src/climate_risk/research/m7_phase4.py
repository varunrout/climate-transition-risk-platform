"""M7 phase 4 recency-weighted scenario hardening.

Research-only. This module freezes the Phase 3 RECENCY_WEIGHTING_ONLY result,
tests a small pre-declared recency family, and evaluates leakage-safe interval
calibration without changing the production scenario engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

import numpy as np
import pandas as pd

from climate_risk.research.m7_scenarios import (
    BACKTEST_ORIGINS,
    N_SIMULATIONS,
    RECENCY_HALFLIFE_YEARS,
    TARGET_COLUMN,
    forecast_scenario,
    interval_score,
)

PHASE4_VERSION = "m7_recency_scenario_hardening_v0.1"
NOMINAL_COVERAGE = 0.90
EFFECTIVE_TIE_TOLERANCE = 0.001
CALIBRATION_QUANTILE = 0.90
MAX_INTERVAL_SCALE = 1.50
MIN_CALIBRATION_SPLITS = 30
RANDOM_SEED = 42

RecencyScheme = Literal["weak_recency", "canonical_recency", "strong_recency"]
CandidateMethod = Literal[
    "deterministic_trend",
    "empirical_bootstrap",
    "recency_weighted_bootstrap",
    "nested_recency_weighted_bootstrap",
    "recency_weighted_calibrated",
]


@dataclass(frozen=True)
class RecencyCandidate:
    scheme: RecencyScheme
    half_life_years: float


RECENCY_CANDIDATES: tuple[RecencyCandidate, ...] = (
    RecencyCandidate("weak_recency", 10.0),
    RecencyCandidate("canonical_recency", RECENCY_HALFLIFE_YEARS),
    RecencyCandidate("strong_recency", 3.0),
)


def preregistered_phase4_rules() -> dict[str, object]:
    return {
        "phase4_version": PHASE4_VERSION,
        "phase3_decision_frozen": "RECENCY_WEIGHTING_ONLY",
        "structural_break_forecasting_status": "not_promoted",
        "target_column": TARGET_COLUMN,
        "origins": [list(origin) for origin in BACKTEST_ORIGINS],
        "candidate_recency_schemes": [
            {"scheme": candidate.scheme, "half_life_years": candidate.half_life_years}
            for candidate in RECENCY_CANDIDATES
        ],
        "primary_candidate": "canonical_recency",
        "nested_selection": (
            "for an evaluation origin t, select the lowest prior-origin MAE scheme "
            "using only completed origins with target_year < t; use canonical_recency "
            "when fewer than MIN_CALIBRATION_SPLITS prior splits are available"
        ),
        "interval_calibration": {
            "method": "prior-origin residual-to-half-width scaling",
            "quantile": CALIBRATION_QUANTILE,
            "minimum_prior_splits": MIN_CALIBRATION_SPLITS,
            "scale_bounds": [1.0, MAX_INTERVAL_SCALE],
            "leakage_rule": "only forecasts with target_year < evaluation origin may set scale",
        },
        "fallback_method": "empirical_bootstrap when recency bootstrap has insufficient history",
        "decision_categories": [
            "PROMOTE_RECENCY_WEIGHTED_SCENARIO",
            "PROMOTE_RECENCY_WEIGHTED_PLUS_CALIBRATION",
            "KEEP_EXISTING_EMPIRICAL_BOOTSTRAP_IN_PRODUCTION",
        ],
        "decision_rule": {
            "promote_recency_weighted": [
                "MAE improves vs empirical_bootstrap",
                "country and origin robustness are not concentrated",
                "coverage gap is not worse than empirical_bootstrap",
                "calibrated candidate is not materially better on coverage with acceptable sharpness",
            ],
            "promote_recency_weighted_plus_calibration": [
                "calibrated candidate preserves or improves MAE vs empirical_bootstrap",
                "calibration gap improves by at least 0.03 vs empirical_bootstrap",
                f"mean interval width is <= {MAX_INTERVAL_SCALE} times empirical_bootstrap width",
                "country and origin robustness are not concentrated",
            ],
            "keep_empirical": [
                "recency gain is too small, not robust, under-calibrated, or not enough value "
                "relative to the production empirical bootstrap",
            ],
        },
    }


def run_phase4_hardening(
    transition_panel: pd.DataFrame,
    *,
    countries: list[str],
    origins: tuple[tuple[int, int], ...] = BACKTEST_ORIGINS,
    n_simulations: int = N_SIMULATIONS,
    random_seed: int = RANDOM_SEED,
) -> dict[str, object]:
    candidate_results = run_phase4_backtest(
        transition_panel,
        countries=countries,
        origins=origins,
        n_simulations=n_simulations,
        random_seed=random_seed,
    )
    comparison = candidate_comparison(candidate_results)
    country_results = summarise_by(candidate_results, ["model_variant", "country_iso3"])
    origin_results = summarise_by(candidate_results, ["model_variant", "origin_year"])
    calibration = calibration_analysis(candidate_results)
    recency_robustness = robustness_vs_baseline(candidate_results, "recency_weighted_bootstrap")
    nested_analysis = nested_weight_selection_analysis(candidate_results)
    uncertainty = clustered_delta_uncertainty(
        candidate_results,
        experimental="recency_weighted_bootstrap",
        baseline="empirical_bootstrap",
        random_seed=random_seed,
    )
    decision = phase4_decision(candidate_results, comparison, recency_robustness, uncertainty)
    return {
        "candidate_comparison": comparison,
        "country_results": country_results,
        "origin_results": origin_results,
        "calibration_analysis": calibration,
        "recency_robustness": recency_robustness,
        "nested_weight_selection": nested_analysis,
        "performance_uncertainty": uncertainty,
        "decision": decision,
    }


def run_phase4_backtest(
    panel: pd.DataFrame,
    *,
    countries: list[str],
    origins: tuple[tuple[int, int], ...] = BACKTEST_ORIGINS,
    n_simulations: int = N_SIMULATIONS,
    random_seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    selected_by_origin = select_nested_recency_schemes(
        panel,
        countries=countries,
        origins=origins,
        n_simulations=n_simulations,
        random_seed=random_seed,
    )
    scale_by_origin = prior_origin_interval_scales(
        panel,
        countries=countries,
        origins=origins,
        selected_by_origin=selected_by_origin,
        n_simulations=n_simulations,
        random_seed=random_seed,
    )
    for country_iso3 in countries:
        country_rows = panel[panel["country_iso3"] == country_iso3].sort_values("year")
        for origin_year, target_year in origins:
            history = country_rows[country_rows["year"] <= origin_year]
            actual_rows = country_rows[country_rows["year"] == target_year]
            if actual_rows.empty or pd.isna(actual_rows.iloc[0][TARGET_COLUMN]):
                continue
            actual = _to_float(actual_rows.iloc[0][TARGET_COLUMN])
            if actual <= 0:
                continue
            for method in _phase4_methods():
                forecast = _phase4_forecast(
                    history,
                    method=method,
                    target_year=target_year,
                    selected_scheme=selected_by_origin[origin_year],
                    calibration_scale=scale_by_origin[origin_year],
                    n_simulations=n_simulations,
                    random_seed=random_seed,
                )
                if forecast is None:
                    continue
                rows.append(
                    _evaluated_row(forecast, country_iso3, origin_year, target_year, actual)
                )
    return pd.DataFrame(rows)


def select_nested_recency_schemes(
    panel: pd.DataFrame,
    *,
    countries: list[str],
    origins: tuple[tuple[int, int], ...] = BACKTEST_ORIGINS,
    n_simulations: int = N_SIMULATIONS,
    random_seed: int = RANDOM_SEED,
) -> dict[int, RecencyCandidate]:
    selected: dict[int, RecencyCandidate] = {}
    for origin_year, _target_year in origins:
        prior = _candidate_scheme_results(
            panel,
            countries=countries,
            origins=tuple(origin for origin in origins if origin[1] < origin_year),
            n_simulations=n_simulations,
            random_seed=random_seed,
        )
        if len(prior) < MIN_CALIBRATION_SPLITS:
            selected[origin_year] = _candidate("canonical_recency")
            continue
        mae_by_scheme = prior.groupby("recency_scheme")["absolute_error"].mean()
        selected[origin_year] = _candidate(cast(RecencyScheme, str(mae_by_scheme.idxmin())))
    return selected


def prior_origin_interval_scales(
    panel: pd.DataFrame,
    *,
    countries: list[str],
    origins: tuple[tuple[int, int], ...],
    selected_by_origin: dict[int, RecencyCandidate],
    n_simulations: int = N_SIMULATIONS,
    random_seed: int = RANDOM_SEED,
) -> dict[int, float]:
    scales: dict[int, float] = {}
    for origin_year, _target_year in origins:
        prior_origins = tuple(origin for origin in origins if origin[1] < origin_year)
        prior_rows = []
        for prior_origin_year, prior_target_year in prior_origins:
            selected = selected_by_origin[prior_origin_year]
            for country_iso3 in countries:
                country_rows = panel[panel["country_iso3"] == country_iso3].sort_values("year")
                history = country_rows[country_rows["year"] <= prior_origin_year]
                actual_rows = country_rows[country_rows["year"] == prior_target_year]
                if actual_rows.empty:
                    continue
                forecast = _recency_forecast(
                    history,
                    target_year=prior_target_year,
                    candidate=selected,
                    n_simulations=n_simulations,
                    random_seed=random_seed,
                )
                if forecast is None:
                    continue
                actual = _to_float(actual_rows.iloc[0][TARGET_COLUMN])
                half_width = (
                    _to_float(forecast["forecast_p95"]) - _to_float(forecast["forecast_p05"])
                ) / 2.0
                if half_width <= 0:
                    continue
                prior_rows.append(abs(actual - _to_float(forecast["forecast_p50"])) / half_width)
        if len(prior_rows) < MIN_CALIBRATION_SPLITS:
            scales[origin_year] = 1.0
            continue
        scale = float(np.quantile(np.array(prior_rows, dtype=float), CALIBRATION_QUANTILE))
        scales[origin_year] = min(MAX_INTERVAL_SCALE, max(1.0, scale))
    return scales


def recency_weights(years: pd.Series, *, half_life_years: float) -> np.ndarray:
    ordered = np.sort(years.to_numpy(dtype=float))
    latest = float(ordered[-1])
    ages = latest - ordered
    return np.power(0.5, ages / half_life_years)


def apply_interval_scale(forecast: dict[str, object], *, scale: float) -> dict[str, object]:
    scaled = dict(forecast)
    p50 = _to_float(scaled["forecast_p50"])
    lower_width = p50 - _to_float(scaled["forecast_p05"])
    upper_width = _to_float(scaled["forecast_p95"]) - p50
    scaled["forecast_p05"] = max(0.0, p50 - lower_width * scale)
    scaled["forecast_p95"] = p50 + upper_width * scale
    scaled["calibration_scale"] = scale
    return scaled


def coverage_rate(rows: pd.DataFrame) -> float:
    return float(rows["covered_90"].mean()) if len(rows) else float("nan")


def mean_interval_width(rows: pd.DataFrame) -> float:
    return float(rows["interval_width_90"].mean()) if len(rows) else float("nan")


def candidate_comparison(results: pd.DataFrame) -> pd.DataFrame:
    return summarise_by(results, ["model_variant"])


def calibration_analysis(results: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for method, group in results.groupby("model_variant"):
        rows.append(
            {
                **_metric_summary(group),
                "model_variant": method,
                "nominal_coverage_90": NOMINAL_COVERAGE,
                "calibration_gap_90": abs(coverage_rate(group) - NOMINAL_COVERAGE),
                "lower_tail_miss_rate": float((group["actual"] < group["forecast_p05"]).mean()),
                "upper_tail_miss_rate": float((group["actual"] > group["forecast_p95"]).mean()),
                "mean_calibration_scale": float(group["calibration_scale"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("model_variant")


def robustness_vs_baseline(
    results: pd.DataFrame, experimental: str, baseline: str = "empirical_bootstrap"
) -> pd.DataFrame:
    paired = _paired_results(results, experimental, baseline)
    paired["error_delta"] = (
        paired["absolute_error_experimental"] - paired["absolute_error_baseline"]
    )
    paired["outcome"] = np.where(
        paired["error_delta"] < -EFFECTIVE_TIE_TOLERANCE,
        "improved",
        np.where(paired["error_delta"] > EFFECTIVE_TIE_TOLERANCE, "degraded", "tied"),
    )
    country = paired.groupby("country_iso3")["error_delta"].mean()
    origin = paired.groupby("origin_year")["error_delta"].mean()
    return pd.DataFrame(
        [
            {
                "experimental_variant": experimental,
                "baseline_variant": baseline,
                "n_splits": len(paired),
                "splits_improved": int((paired["outcome"] == "improved").sum()),
                "splits_degraded": int((paired["outcome"] == "degraded").sum()),
                "splits_tied": int((paired["outcome"] == "tied").sum()),
                "countries_improved": int((country < -EFFECTIVE_TIE_TOLERANCE).sum()),
                "countries_degraded": int((country > EFFECTIVE_TIE_TOLERANCE).sum()),
                "countries_tied": int(country.abs().le(EFFECTIVE_TIE_TOLERANCE).sum()),
                "origins_improved": int((origin < -EFFECTIVE_TIE_TOLERANCE).sum()),
                "origins_degraded": int((origin > EFFECTIVE_TIE_TOLERANCE).sum()),
                "origins_tied": int(origin.abs().le(EFFECTIVE_TIE_TOLERANCE).sum()),
                "median_error_delta": float(paired["error_delta"].median()),
                "mean_error_delta": float(paired["error_delta"].mean()),
                "worst_degradation": float(paired["error_delta"].max()),
                "largest_improvement": float(-paired["error_delta"].min()),
            }
        ]
    )


def nested_weight_selection_analysis(results: pd.DataFrame) -> pd.DataFrame:
    nested = results[results["model_variant"] == "nested_recency_weighted_bootstrap"]
    return (
        nested.groupby(["origin_year", "recency_scheme", "recency_half_life_years"], dropna=False)
        .size()
        .reset_index(name="selected_country_splits")
        .sort_values("origin_year")
    )


def clustered_delta_uncertainty(
    results: pd.DataFrame,
    *,
    experimental: str,
    baseline: str,
    n_iterations: int = 2_000,
    random_seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    paired = _paired_results(results, experimental, baseline)
    if paired.empty:
        return pd.DataFrame()
    paired["delta"] = paired["absolute_error_experimental"] - paired["absolute_error_baseline"]
    clusters = [
        group["delta"].to_numpy(dtype=float)
        for _country, group in paired.sort_values(["country_iso3", "origin_year"]).groupby(
            "country_iso3"
        )
    ]
    rng = np.random.default_rng(random_seed)
    draws = []
    for _ in range(n_iterations):
        sampled = rng.integers(0, len(clusters), size=len(clusters))
        values = np.concatenate([clusters[index] for index in sampled])
        draws.append(float(values.mean()))
    return pd.DataFrame(
        [
            {
                "experimental_variant": experimental,
                "baseline_variant": baseline,
                "cluster_unit": "country_iso3",
                "n_clusters": len(clusters),
                "n_splits": len(paired),
                "n_iterations": n_iterations,
                "random_seed": random_seed,
                "observed_delta_mae": float(paired["delta"].mean()),
                "delta_mae_p05": float(np.percentile(draws, 5)),
                "delta_mae_p50": float(np.percentile(draws, 50)),
                "delta_mae_p95": float(np.percentile(draws, 95)),
                "probability_improves_mae": float(np.mean(np.array(draws) < 0.0)),
            }
        ]
    )


def phase4_decision(
    results: pd.DataFrame,
    comparison: pd.DataFrame,
    recency_robustness: pd.DataFrame,
    uncertainty: pd.DataFrame,
) -> dict[str, object]:
    metrics = comparison.set_index("model_variant")
    empirical = metrics.loc["empirical_bootstrap"]
    recency = metrics.loc["recency_weighted_bootstrap"]
    calibrated = metrics.loc["recency_weighted_calibrated"]
    robust = recency_robustness.iloc[0]
    empirical_width = _to_float(empirical["mean_interval_width_90"])
    recency_beats_empirical = _to_float(recency["mae"]) < _to_float(empirical["mae"])
    calibrated_beats_empirical = _to_float(calibrated["mae"]) <= _to_float(empirical["mae"])
    recency_gap = abs(_to_float(recency["coverage_90"]) - NOMINAL_COVERAGE)
    empirical_gap = abs(_to_float(empirical["coverage_90"]) - NOMINAL_COVERAGE)
    calibrated_gap = abs(_to_float(calibrated["coverage_90"]) - NOMINAL_COVERAGE)
    calibrated_width_ok = (
        _to_float(calibrated["mean_interval_width_90"]) <= empirical_width * MAX_INTERVAL_SCALE
    )
    country_robust = int(robust["countries_improved"]) >= int(robust["countries_degraded"])
    origin_robust = int(robust["origins_improved"]) >= int(robust["origins_degraded"])
    uncertainty_supports_gain = (
        bool(len(uncertainty))
        and _to_float(uncertainty.iloc[0]["probability_improves_mae"]) >= 0.60
    )
    gates = {
        "recency_beats_empirical_mae": recency_beats_empirical,
        "recency_coverage_gap_not_worse": recency_gap <= empirical_gap,
        "country_robustness_not_concentrated": country_robust,
        "origin_robustness_not_concentrated": origin_robust,
        "clustered_uncertainty_supports_gain": uncertainty_supports_gain,
        "calibrated_preserves_or_improves_empirical_mae": calibrated_beats_empirical,
        "calibrated_improves_gap_by_0_03": calibrated_gap <= empirical_gap - 0.03,
        "calibrated_width_ok": calibrated_width_ok,
    }
    if (
        gates["calibrated_preserves_or_improves_empirical_mae"]
        and gates["calibrated_improves_gap_by_0_03"]
        and gates["calibrated_width_ok"]
        and gates["country_robustness_not_concentrated"]
        and gates["origin_robustness_not_concentrated"]
    ):
        production_decision = "PROMOTE_RECENCY_WEIGHTED_PLUS_CALIBRATION"
        production_promotion_justified = True
    elif (
        gates["recency_beats_empirical_mae"]
        and gates["recency_coverage_gap_not_worse"]
        and gates["country_robustness_not_concentrated"]
        and gates["origin_robustness_not_concentrated"]
        and gates["clustered_uncertainty_supports_gain"]
    ):
        production_decision = "PROMOTE_RECENCY_WEIGHTED_SCENARIO"
        production_promotion_justified = True
    else:
        production_decision = "KEEP_EXISTING_EMPIRICAL_BOOTSTRAP_IN_PRODUCTION"
        production_promotion_justified = False
    return {
        "milestone": "M7",
        "phase": "phase4",
        "phase4_version": PHASE4_VERSION,
        "phase3_decision_frozen": "RECENCY_WEIGHTING_ONLY",
        "production_decision": production_decision,
        "production_promotion_justified": production_promotion_justified,
        "m7_status": "COMPLETE",
        "structural_break_diagnostic_status": "retained_as_research_diagnostics",
        "risk_score_v2_energy_changed": False,
        "azure_changed": False,
        "pre_registered_rules": preregistered_phase4_rules(),
        "gates": gates,
    }


def summarise_by(results: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    rows = []
    for values, group in results.groupby(keys):
        value_tuple = values if isinstance(values, tuple) else (values,)
        rows.append({**dict(zip(keys, value_tuple, strict=True)), **_metric_summary(group)})
    return pd.DataFrame(rows).sort_values(keys)


def _phase4_forecast(
    history: pd.DataFrame,
    *,
    method: CandidateMethod,
    target_year: int,
    selected_scheme: RecencyCandidate,
    calibration_scale: float,
    n_simulations: int,
    random_seed: int,
) -> dict[str, object] | None:
    if method in ("deterministic_trend", "empirical_bootstrap"):
        forecast = forecast_scenario(
            history,
            method=method,
            target_year=target_year,
            regime={},
            n_simulations=n_simulations,
            random_seed=random_seed,
        )
        if forecast is None:
            return None
        forecast["recency_scheme"] = None
        forecast["recency_half_life_years"] = np.nan
        forecast["calibration_scale"] = 1.0
        return forecast
    candidate = (
        _candidate("canonical_recency")
        if method == "recency_weighted_bootstrap"
        else selected_scheme
    )
    forecast = _recency_forecast(
        history,
        target_year=target_year,
        candidate=candidate,
        n_simulations=n_simulations,
        random_seed=random_seed,
    )
    if forecast is None:
        fallback = forecast_scenario(
            history,
            method="empirical_bootstrap",
            target_year=target_year,
            regime={},
            n_simulations=n_simulations,
            random_seed=random_seed,
        )
        if fallback is None:
            return None
        fallback["model_variant"] = method
        fallback["fallback_used"] = True
        fallback["recency_scheme"] = candidate.scheme
        fallback["recency_half_life_years"] = candidate.half_life_years
        fallback["calibration_scale"] = 1.0
        return fallback
    forecast["model_variant"] = method
    if method == "recency_weighted_calibrated":
        forecast = apply_interval_scale(forecast, scale=calibration_scale)
    return forecast


def _recency_forecast(
    history: pd.DataFrame,
    *,
    target_year: int,
    candidate: RecencyCandidate,
    n_simulations: int,
    random_seed: int,
) -> dict[str, object] | None:
    series = history[TARGET_COLUMN]
    years = history["year"]
    changes = _log_changes(series, years)
    if changes is None:
        return None
    ordered_years, ordered_values, log_changes = changes
    horizon = target_year - int(ordered_years[-1])
    if horizon <= 0:
        return None
    weights = recency_weights(pd.Series(ordered_years), half_life_years=candidate.half_life_years)
    change_weights = weights[-len(log_changes) :]
    change_weights = change_weights / change_weights.sum()
    rng = np.random.default_rng(random_seed)
    draws = rng.choice(log_changes, size=(n_simulations, horizon), replace=True, p=change_weights)
    simulated = float(ordered_values[-1]) * np.exp(draws.sum(axis=1))
    p05, p50, p95 = np.percentile(simulated, [5, 50, 95])
    return {
        "model_variant": "recency_weighted_bootstrap",
        "forecast_p50": float(p50),
        "forecast_p05": float(p05),
        "forecast_p95": float(p95),
        "simulation_count": n_simulations,
        "random_seed": random_seed,
        "regime_activated": False,
        "fallback_used": False,
        "recency_scheme": candidate.scheme,
        "recency_half_life_years": candidate.half_life_years,
        "calibration_scale": 1.0,
    }


def _candidate_scheme_results(
    panel: pd.DataFrame,
    *,
    countries: list[str],
    origins: tuple[tuple[int, int], ...],
    n_simulations: int,
    random_seed: int,
) -> pd.DataFrame:
    rows = []
    for candidate in RECENCY_CANDIDATES:
        for country_iso3 in countries:
            country_rows = panel[panel["country_iso3"] == country_iso3].sort_values("year")
            for origin_year, target_year in origins:
                history = country_rows[country_rows["year"] <= origin_year]
                actual_rows = country_rows[country_rows["year"] == target_year]
                if actual_rows.empty:
                    continue
                forecast = _recency_forecast(
                    history,
                    target_year=target_year,
                    candidate=candidate,
                    n_simulations=n_simulations,
                    random_seed=random_seed,
                )
                if forecast is None:
                    continue
                actual = _to_float(actual_rows.iloc[0][TARGET_COLUMN])
                rows.append(
                    {
                        "recency_scheme": candidate.scheme,
                        "origin_year": origin_year,
                        "target_year": target_year,
                        "country_iso3": country_iso3,
                        "absolute_error": abs(_to_float(forecast["forecast_p50"]) - actual),
                    }
                )
    return pd.DataFrame(rows)


def _evaluated_row(
    forecast: dict[str, object],
    country_iso3: str,
    origin_year: int,
    target_year: int,
    actual: float,
) -> dict[str, object]:
    p50 = _to_float(forecast["forecast_p50"])
    p05 = _to_float(forecast["forecast_p05"])
    p95 = _to_float(forecast["forecast_p95"])
    return {
        **forecast,
        "country_iso3": country_iso3,
        "origin_year": origin_year,
        "target_year": target_year,
        "horizon_years": target_year - origin_year,
        "actual": actual,
        "absolute_error": abs(p50 - actual),
        "covered_90": p05 <= actual <= p95,
        "interval_width_90": p95 - p05,
        "interval_score_90": interval_score(actual, p05, p95, alpha=0.10),
        "phase4_version": PHASE4_VERSION,
    }


def _metric_summary(group: pd.DataFrame) -> dict[str, object]:
    errors = group["absolute_error"].to_numpy(dtype=float)
    return {
        "n_splits": len(group),
        "mae": float(np.mean(errors)),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "median_ae": float(np.median(errors)),
        "coverage_90": coverage_rate(group),
        "calibration_gap_90": abs(coverage_rate(group) - NOMINAL_COVERAGE),
        "mean_interval_width_90": mean_interval_width(group),
        "mean_interval_score_90": float(group["interval_score_90"].mean()),
    }


def _paired_results(results: pd.DataFrame, experimental: str, baseline: str) -> pd.DataFrame:
    keys = ["country_iso3", "origin_year", "target_year"]
    exp = results[results["model_variant"] == experimental][[*keys, "absolute_error"]].rename(
        columns={"absolute_error": "absolute_error_experimental"}
    )
    base = results[results["model_variant"] == baseline][[*keys, "absolute_error"]].rename(
        columns={"absolute_error": "absolute_error_baseline"}
    )
    return exp.merge(base, on=keys, how="inner")


def _log_changes(
    series: pd.Series, years: pd.Series
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    mask = series.notna() & (series > 0)
    if mask.sum() < 6:
        return None
    ordered_years = years[mask].to_numpy()
    ordered_values = series[mask].to_numpy(dtype=float)
    order = np.argsort(ordered_years)
    ordered_years = ordered_years[order]
    ordered_values = ordered_values[order]
    log_changes = np.diff(np.log(ordered_values))
    if len(log_changes) < 5:
        return None
    return ordered_years, ordered_values, log_changes


def _phase4_methods() -> tuple[CandidateMethod, ...]:
    return (
        "deterministic_trend",
        "empirical_bootstrap",
        "recency_weighted_bootstrap",
        "nested_recency_weighted_bootstrap",
        "recency_weighted_calibrated",
    )


def _candidate(scheme: RecencyScheme) -> RecencyCandidate:
    for candidate in RECENCY_CANDIDATES:
        if candidate.scheme == scheme:
            return candidate
    raise ValueError(f"unknown recency scheme: {scheme}")


def _to_float(value: object) -> float:
    return float(cast(float | int | str, value))

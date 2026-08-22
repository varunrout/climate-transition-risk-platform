"""M7 phase 3 regime-aware scenario experiments.

Research-only. This module evaluates experimental scenario variants against
the existing production baselines without modifying `climate_risk.scenarios`.
All historical-origin evaluation filters to observations <= origin_year.
"""

from __future__ import annotations

from typing import Literal, cast

import numpy as np
import pandas as pd

from climate_risk.research.m7_regimes import (
    detect_break,
    detect_breaks_by_origin,
    method_agreement,
)
from climate_risk.scenarios.engine import bootstrap_monte_carlo, deterministic_trend_baseline

ScenarioMethod = Literal[
    "deterministic_trend",
    "empirical_bootstrap",
    "recency_weighted_bootstrap",
    "current_regime_only",
    "regime_weighted_bootstrap",
    "break_confidence_weighted_bootstrap",
    "conditional_regime_weighted_bootstrap",
]

PHASE3_VERSION = "m7_regime_scenario_v0.1"
BACKTEST_ORIGINS: tuple[tuple[int, int], ...] = (
    (2010, 2015),
    (2012, 2017),
    (2014, 2019),
    (2015, 2020),
    (2016, 2021),
    (2017, 2022),
)
MIN_POST_BREAK_OBSERVATIONS = 5
BREAK_CONFIDENCE_THRESHOLD = 0.70
MIN_BREAK_STRENGTH = 1.25
RECENCY_HALFLIFE_YEARS = 5.0
REGIME_WEIGHT_MULTIPLIER = 3.0
MAX_CONFIDENCE_WEIGHT_MULTIPLIER = 5.0
N_SIMULATIONS = 5_000
TARGET_COLUMN = "carbon_intensity_gdp"


def preregistered_phase3_rules() -> dict[str, object]:
    return {
        "phase3_version": PHASE3_VERSION,
        "target_column": TARGET_COLUMN,
        "origins": [list(origin) for origin in BACKTEST_ORIGINS],
        "min_post_break_observations": MIN_POST_BREAK_OBSERVATIONS,
        "break_confidence_threshold": BREAK_CONFIDENCE_THRESHOLD,
        "min_break_strength": MIN_BREAK_STRENGTH,
        "recency_halflife_years": RECENCY_HALFLIFE_YEARS,
        "regime_weight_multiplier": REGIME_WEIGHT_MULTIPLIER,
        "max_confidence_weight_multiplier": MAX_CONFIDENCE_WEIGHT_MULTIPLIER,
        "fallback_method": "empirical_bootstrap",
        "decision_rule": {
            "accept_regime_aware_scenarios": [
                "best regime method improves MAE vs empirical_bootstrap and recency_weighted_bootstrap",
                "coverage gap is no worse than empirical_bootstrap by more than 0.05",
                "at least half of eligible origins improve vs empirical_bootstrap",
                "at least half of eligible countries improve vs empirical_bootstrap",
                "break-year sensitivity median absolute p50 shift <= 10% of empirical_bootstrap MAE",
            ],
            "recency_weighting_only": [
                "recency_weighted_bootstrap beats empirical_bootstrap and regime methods do not beat recency",
            ],
            "diagnostics_only": [
                "regime methods are interpretable but fail point, calibration, robustness, or recency-control gates",
            ],
        },
    }


def run_phase3_experiment(
    transition_panel: pd.DataFrame,
    *,
    countries: list[str],
    origins: tuple[tuple[int, int], ...] = BACKTEST_ORIGINS,
    n_simulations: int = N_SIMULATIONS,
    random_seed: int = 42,
) -> dict[str, object]:
    results = run_regime_scenario_backtest(
        transition_panel,
        countries=countries,
        origins=origins,
        n_simulations=n_simulations,
        random_seed=random_seed,
    )
    origin_metrics = summarise_by(results, ["model_variant", "origin_year"])
    country_metrics = summarise_by(results, ["model_variant", "country_iso3"])
    calibration = calibration_metrics(results)
    break_sensitivity = break_year_sensitivity(
        transition_panel,
        countries=countries,
        origins=origins,
        n_simulations=max(1_000, n_simulations // 5),
        random_seed=random_seed,
    )
    recency_vs_regime = compare_against_baselines(results)
    conditional = conditional_policy_summary(results)
    uncertainty = performance_delta_uncertainty(results, random_seed=random_seed)
    cases = select_phase3_case_studies(results, break_sensitivity)
    decision = phase3_decision(results, calibration, break_sensitivity, recency_vs_regime)
    return {
        "scenario_method_results": results,
        "origin_metrics": origin_metrics,
        "country_metrics": country_metrics,
        "calibration_metrics": calibration,
        "break_sensitivity": break_sensitivity,
        "recency_vs_regime": recency_vs_regime,
        "conditional_policy": conditional,
        "performance_uncertainty": uncertainty,
        "case_studies": cases,
        "decision": decision,
    }


def run_regime_scenario_backtest(
    panel: pd.DataFrame,
    *,
    countries: list[str],
    origins: tuple[tuple[int, int], ...] = BACKTEST_ORIGINS,
    n_simulations: int = N_SIMULATIONS,
    random_seed: int = 42,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for country_iso3 in countries:
        country_rows = panel[panel["country_iso3"] == country_iso3].sort_values("year")
        for origin_year, target_year in origins:
            history = country_rows[country_rows["year"] <= origin_year]
            actual_rows = country_rows[country_rows["year"] == target_year]
            if actual_rows.empty or pd.isna(actual_rows.iloc[0][TARGET_COLUMN]):
                continue
            actual = float(actual_rows.iloc[0][TARGET_COLUMN])
            if actual <= 0:
                continue
            regime = _regime_evidence(history, origin_year=origin_year)
            agreement = _agreement_evidence(history, origin_year=origin_year)
            for method in _methods():
                forecast = forecast_scenario(
                    history,
                    method=method,
                    target_year=target_year,
                    regime=regime,
                    n_simulations=n_simulations,
                    random_seed=random_seed,
                )
                if forecast is None:
                    continue
                p50 = _as_float(forecast["forecast_p50"])
                p05 = _as_float(forecast["forecast_p05"])
                p95 = _as_float(forecast["forecast_p95"])
                rows.append(
                    {
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
                        "regime_break_year": regime.get("strongest_break_year"),
                        "regime_confidence": regime.get("regime_confidence"),
                        "regime_break_strength": regime.get("strongest_break_strength"),
                        "regime_activated": bool(forecast["regime_activated"]),
                        "methods_detecting_break": agreement.get("methods_detecting_break"),
                        "method_sensitivity": agreement.get("method_sensitivity"),
                        "phase3_version": PHASE3_VERSION,
                    }
                )
    return pd.DataFrame(rows)


def forecast_scenario(
    history: pd.DataFrame,
    *,
    method: ScenarioMethod,
    target_year: int,
    regime: dict[str, object],
    n_simulations: int = N_SIMULATIONS,
    random_seed: int = 42,
) -> dict[str, object] | None:
    series = history[TARGET_COLUMN]
    years = history["year"]
    if method == "deterministic_trend":
        deterministic = deterministic_trend_baseline(series, years=years, target_year=target_year)
        if deterministic is None:
            return None
        return {
            "model_variant": method,
            "forecast_p50": deterministic.forecast_value,
            "forecast_p05": deterministic.forecast_value,
            "forecast_p95": deterministic.forecast_value,
            "simulation_count": 0,
            "random_seed": random_seed,
            "regime_activated": False,
            "fallback_used": False,
        }

    if method == "empirical_bootstrap":
        return _production_bootstrap_result(
            series,
            years=years,
            target_year=target_year,
            n_simulations=n_simulations,
            random_seed=random_seed,
        )

    if method == "recency_weighted_bootstrap":
        return _weighted_bootstrap_result(
            series,
            years=years,
            target_year=target_year,
            weights=_recency_weights(years),
            model_variant=method,
            n_simulations=n_simulations,
            random_seed=random_seed,
            regime_activated=False,
            fallback_used=False,
        )

    active = regime_activation(regime, len(history))
    if method == "current_regime_only":
        if active and regime.get("strongest_break_year") is not None:
            start = _as_int(regime["strongest_break_year"])
            regime_history = history[history["year"] >= start]
            result = _production_bootstrap_result(
                regime_history[TARGET_COLUMN],
                years=regime_history["year"],
                target_year=target_year,
                n_simulations=n_simulations,
                random_seed=random_seed,
            )
            if result is not None:
                result["model_variant"] = method
                result["regime_activated"] = True
                result["fallback_used"] = False
                return result
        result = forecast_scenario(
            history,
            method="empirical_bootstrap",
            target_year=target_year,
            regime=regime,
            n_simulations=n_simulations,
            random_seed=random_seed,
        )
        if result is not None:
            result["model_variant"] = method
            result["fallback_used"] = True
        return result

    if method == "regime_weighted_bootstrap":
        weights = _regime_weights(years, regime=regime, multiplier=REGIME_WEIGHT_MULTIPLIER)
        return _weighted_bootstrap_result(
            series,
            years=years,
            target_year=target_year,
            weights=weights,
            model_variant=method,
            n_simulations=n_simulations,
            random_seed=random_seed,
            regime_activated=active,
            fallback_used=False,
        )

    multiplier = confidence_weight_multiplier(regime)
    result = _weighted_bootstrap_result(
        series,
        years=years,
        target_year=target_year,
        weights=_regime_weights(years, regime=regime, multiplier=multiplier),
        model_variant=method,
        n_simulations=n_simulations,
        random_seed=random_seed,
        regime_activated=active,
        fallback_used=False,
    )
    if method == "conditional_regime_weighted_bootstrap" and not active:
        fallback = forecast_scenario(
            history,
            method="empirical_bootstrap",
            target_year=target_year,
            regime=regime,
            n_simulations=n_simulations,
            random_seed=random_seed,
        )
        if fallback is not None:
            fallback["model_variant"] = method
            fallback["fallback_used"] = True
        return fallback
    return result


def regime_activation(regime: dict[str, object], history_rows: int) -> bool:
    break_year = regime.get("strongest_break_year")
    confidence = regime.get("regime_confidence")
    strength = regime.get("strongest_break_strength")
    if break_year is None or confidence is None or strength is None:
        return False
    post_break_rows = history_rows - _as_int(regime.get("break_index", history_rows))
    return (
        _as_float(confidence) >= BREAK_CONFIDENCE_THRESHOLD
        and _as_float(strength) >= MIN_BREAK_STRENGTH
        and post_break_rows >= MIN_POST_BREAK_OBSERVATIONS
    )


def confidence_weight_multiplier(regime: dict[str, object]) -> float:
    confidence = regime.get("regime_confidence")
    if confidence is None:
        return 1.0
    clipped = min(1.0, max(0.0, _as_float(confidence)))
    return 1.0 + clipped * (MAX_CONFIDENCE_WEIGHT_MULTIPLIER - 1.0)


def interval_score(actual: float, lower: float, upper: float, *, alpha: float) -> float:
    width = upper - lower
    lower_penalty = (2.0 / alpha) * (lower - actual) if actual < lower else 0.0
    upper_penalty = (2.0 / alpha) * (actual - upper) if actual > upper else 0.0
    return float(width + lower_penalty + upper_penalty)


def summarise_by(results: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    rows = []
    for values, group in results.groupby(keys):
        value_tuple = values if isinstance(values, tuple) else (values,)
        row = dict(zip(keys, value_tuple, strict=True))
        row.update(_metric_summary(group))
        rows.append(row)
    return pd.DataFrame(rows).sort_values(keys)


def calibration_metrics(results: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for method, group in results.groupby("model_variant"):
        summary = _metric_summary(group)
        rows.append(
            {
                "model_variant": method,
                **summary,
                "calibration_gap_90": abs(_as_float(summary["coverage_90"]) - 0.90),
                "lower_tail_miss_rate": float((group["actual"] < group["forecast_p05"]).mean()),
                "upper_tail_miss_rate": float((group["actual"] > group["forecast_p95"]).mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("model_variant")


def compare_against_baselines(results: pd.DataFrame) -> pd.DataFrame:
    overall = calibration_metrics(results).set_index("model_variant")
    baseline = _row(overall, "empirical_bootstrap")
    recency = _row(overall, "recency_weighted_bootstrap")
    rows = []
    for method, row in overall.iterrows():
        rows.append(
            {
                "model_variant": method,
                "mae": _series_float(row, "mae"),
                "delta_mae_vs_empirical_bootstrap": _series_float(row, "mae")
                - _series_float(baseline, "mae"),
                "delta_mae_vs_recency_weighted": _series_float(row, "mae")
                - _series_float(recency, "mae"),
                "coverage_90": _series_float(row, "coverage_90"),
                "delta_coverage_gap_vs_empirical_bootstrap": _series_float(
                    row, "calibration_gap_90"
                )
                - _series_float(baseline, "calibration_gap_90"),
                "mean_interval_width_90": _series_float(row, "mean_interval_width_90"),
            }
        )
    return pd.DataFrame(rows).sort_values("delta_mae_vs_empirical_bootstrap")


def conditional_policy_summary(results: pd.DataFrame) -> pd.DataFrame:
    baseline = results[results["model_variant"] == "empirical_bootstrap"]
    conditional = results[results["model_variant"] == "conditional_regime_weighted_bootstrap"]
    joined = conditional.merge(
        baseline[
            ["country_iso3", "origin_year", "target_year", "absolute_error", "covered_90"]
        ].rename(
            columns={
                "absolute_error": "baseline_absolute_error",
                "covered_90": "baseline_covered_90",
            }
        ),
        on=["country_iso3", "origin_year", "target_year"],
        how="inner",
    )
    joined["improved"] = joined["absolute_error"] < joined["baseline_absolute_error"]
    return pd.DataFrame(
        [
            {
                "policy": "conditional_regime_weighted_bootstrap",
                "n_splits": len(joined),
                "activated_splits": int(joined["regime_activated"].sum()),
                "fallback_splits": int(joined["fallback_used"].sum()),
                "countries_improved": int(
                    joined.groupby("country_iso3")["improved"].mean().gt(0.5).sum()
                ),
                "origins_improved": int(
                    joined.groupby("origin_year")["improved"].mean().gt(0.5).sum()
                ),
                "worst_error_delta": float(
                    (joined["absolute_error"] - joined["baseline_absolute_error"]).max()
                ),
                "largest_error_improvement": float(
                    (joined["baseline_absolute_error"] - joined["absolute_error"]).max()
                ),
            }
        ]
    )


def performance_delta_uncertainty(
    results: pd.DataFrame,
    *,
    baseline: str = "empirical_bootstrap",
    n_iterations: int = 1_000,
    random_seed: int = 42,
) -> pd.DataFrame:
    keys = ["country_iso3", "origin_year", "target_year"]
    wide = results.pivot_table(index=keys, columns="model_variant", values="absolute_error")
    if baseline not in wide:
        return pd.DataFrame()
    rng = np.random.default_rng(random_seed)
    rows = []
    for method in sorted(c for c in wide.columns if c != baseline):
        complete = wide[[baseline, method]].dropna()
        if complete.empty:
            continue
        deltas = []
        values = complete.to_numpy(dtype=float)
        for _ in range(n_iterations):
            idx = rng.integers(0, len(values), size=len(values))
            sample = values[idx]
            deltas.append(float(sample[:, 1].mean() - sample[:, 0].mean()))
        rows.append(
            {
                "model_variant": method,
                "baseline_variant": baseline,
                "n_splits": len(complete),
                "n_iterations": n_iterations,
                "random_seed": random_seed,
                "observed_delta_mae": float(values[:, 1].mean() - values[:, 0].mean()),
                "delta_mae_p05": float(np.percentile(deltas, 5)),
                "delta_mae_p50": float(np.percentile(deltas, 50)),
                "delta_mae_p95": float(np.percentile(deltas, 95)),
                "probability_improves_mae": float(np.mean(np.array(deltas) < 0.0)),
            }
        )
    return pd.DataFrame(rows).sort_values("observed_delta_mae")


def break_year_sensitivity(
    panel: pd.DataFrame,
    *,
    countries: list[str],
    origins: tuple[tuple[int, int], ...] = BACKTEST_ORIGINS,
    n_simulations: int = 1_000,
    random_seed: int = 42,
) -> pd.DataFrame:
    rows = []
    for country_iso3 in countries:
        country_rows = panel[panel["country_iso3"] == country_iso3].sort_values("year")
        for origin_year, target_year in origins:
            history = country_rows[country_rows["year"] <= origin_year]
            regime = _regime_evidence(history, origin_year=origin_year)
            if (
                not regime_activation(regime, len(history))
                or regime.get("strongest_break_year") is None
            ):
                continue
            base = forecast_scenario(
                history,
                method="regime_weighted_bootstrap",
                target_year=target_year,
                regime=regime,
                n_simulations=n_simulations,
                random_seed=random_seed,
            )
            if base is None:
                continue
            for offset in (-2, -1, 1, 2):
                perturbed = dict(regime)
                perturbed["strongest_break_year"] = _as_int(regime["strongest_break_year"]) + offset
                shifted = forecast_scenario(
                    history,
                    method="regime_weighted_bootstrap",
                    target_year=target_year,
                    regime=perturbed,
                    n_simulations=n_simulations,
                    random_seed=random_seed,
                )
                if shifted is None:
                    continue
                rows.append(
                    {
                        "country_iso3": country_iso3,
                        "origin_year": origin_year,
                        "target_year": target_year,
                        "offset_years": offset,
                        "base_break_year": regime["strongest_break_year"],
                        "perturbed_break_year": perturbed["strongest_break_year"],
                        "base_forecast_p50": base["forecast_p50"],
                        "perturbed_forecast_p50": shifted["forecast_p50"],
                        "abs_p50_delta": abs(
                            _as_float(base["forecast_p50"]) - _as_float(shifted["forecast_p50"])
                        ),
                    }
                )
    return pd.DataFrame(rows)


def phase3_decision(
    results: pd.DataFrame,
    calibration: pd.DataFrame,
    break_sensitivity: pd.DataFrame,
    recency_vs_regime: pd.DataFrame,
) -> dict[str, object]:
    metrics = calibration.set_index("model_variant")
    baseline = _row(metrics, "empirical_bootstrap")
    recency = _row(metrics, "recency_weighted_bootstrap")
    regime_candidates = [
        "current_regime_only",
        "regime_weighted_bootstrap",
        "break_confidence_weighted_bootstrap",
        "conditional_regime_weighted_bootstrap",
    ]
    best_regime = min(regime_candidates, key=lambda m: _cell_float(metrics, m, "mae"))
    best = _row(metrics, best_regime)
    baseline_mae = _series_float(baseline, "mae")
    sensitivity_median = (
        _as_float(break_sensitivity["abs_p50_delta"].median()) if len(break_sensitivity) else np.inf
    )
    paired = _paired_improvement(results, best_regime, "empirical_bootstrap")
    gates = {
        "beats_empirical_mae": _series_float(best, "mae") < baseline_mae,
        "beats_recency_mae": _series_float(best, "mae") < _series_float(recency, "mae"),
        "coverage_not_materially_worse": abs(_series_float(best, "coverage_90") - 0.90)
        <= abs(_series_float(baseline, "coverage_90") - 0.90) + 0.05,
        "origin_robust": _as_int(paired["origins_improved"]) >= _as_int(paired["origin_count"]) / 2,
        "country_robust": _as_int(paired["countries_improved"])
        >= _as_int(paired["country_count"]) / 2,
        "break_year_sensitivity_ok": sensitivity_median <= baseline_mae * 0.10,
    }
    if all(gates.values()):
        decision = (
            "ACCEPT_CONDITIONAL_REGIME_AWARE_SCENARIOS"
            if best_regime == "conditional_regime_weighted_bootstrap"
            else "ACCEPT_REGIME_AWARE_SCENARIOS"
        )
    elif _series_float(recency, "mae") < baseline_mae and _series_float(
        best, "mae"
    ) >= _series_float(recency, "mae"):
        decision = "RECENCY_WEIGHTING_ONLY"
    elif any(_cell_float(metrics, m, "mae") < baseline_mae for m in regime_candidates):
        decision = "DIAGNOSTICS_ONLY"
    else:
        decision = "REJECT_OR_REVISE"
    return {
        "milestone": "M7",
        "phase": "phase3",
        "phase3_version": PHASE3_VERSION,
        "decision": decision,
        "decision_is_not_production_promotion": True,
        "best_regime_method": best_regime,
        "pre_registered_rules": preregistered_phase3_rules(),
        "gates": gates,
        "paired_robustness": paired,
        "break_sensitivity_median_abs_p50_delta": sensitivity_median,
        "recency_vs_regime": recency_vs_regime.to_dict(orient="records"),
    }


def select_phase3_case_studies(
    results: pd.DataFrame, break_sensitivity: pd.DataFrame
) -> dict[str, object]:
    paired = _paired_rows(results, "conditional_regime_weighted_bootstrap", "empirical_bootstrap")
    paired["error_delta"] = (
        paired["absolute_error_experimental"] - paired["absolute_error_baseline"]
    )
    cases = []
    if len(paired):
        helped = paired.sort_values("error_delta").iloc[0]
        hurt = paired.sort_values("error_delta", ascending=False).iloc[0]
        cases.append({"case_type": "regime_aware_clearly_helps", **helped.to_dict()})
        cases.append({"case_type": "regime_aware_clearly_hurts", **hurt.to_dict()})
    if len(break_sensitivity):
        robust = break_sensitivity.sort_values("abs_p50_delta").iloc[0]
        cases.append({"case_type": "break_uncertain_forecast_robust", **robust.to_dict()})
    disagreement = results[
        (results["model_variant"] == "conditional_regime_weighted_bootstrap")
        & (results["method_sensitivity"] == "METHOD_SENSITIVE")
    ]
    if len(disagreement):
        cases.append({"case_type": "detector_disagreement", **disagreement.iloc[0].to_dict()})
    fallback = results[
        (results["model_variant"] == "conditional_regime_weighted_bootstrap")
        & (results["fallback_used"])
    ]
    if len(fallback):
        cases.append({"case_type": "no_break_or_weak_break_fallback", **fallback.iloc[0].to_dict()})
    return {"selection_note": "mechanically selected from Phase 3 backtest rows", "cases": cases}


def _production_bootstrap_result(
    series: pd.Series,
    *,
    years: pd.Series,
    target_year: int,
    n_simulations: int,
    random_seed: int,
) -> dict[str, object] | None:
    result = bootstrap_monte_carlo(
        series,
        years=years,
        target_year=target_year,
        n_simulations=n_simulations,
        random_seed=random_seed,
    )
    if result is None:
        return None
    quantiles, _paths = result
    return {
        "model_variant": "empirical_bootstrap",
        "forecast_p50": quantiles.p50,
        "forecast_p05": quantiles.p05,
        "forecast_p95": quantiles.p95,
        "simulation_count": n_simulations,
        "random_seed": random_seed,
        "regime_activated": False,
        "fallback_used": False,
    }


def _weighted_bootstrap_result(
    series: pd.Series,
    *,
    years: pd.Series,
    target_year: int,
    weights: np.ndarray,
    model_variant: str,
    n_simulations: int,
    random_seed: int,
    regime_activated: bool,
    fallback_used: bool,
) -> dict[str, object] | None:
    changes = _log_changes(series, years)
    if changes is None:
        return None
    ordered_years, ordered_values, log_changes = changes
    horizon = target_year - int(ordered_years[-1])
    if horizon <= 0:
        return None
    change_weights = weights[-len(log_changes) :]
    change_weights = change_weights / change_weights.sum()
    rng = np.random.default_rng(random_seed)
    draws = rng.choice(log_changes, size=(n_simulations, horizon), replace=True, p=change_weights)
    simulated = float(ordered_values[-1]) * np.exp(draws.sum(axis=1))
    p05, p50, p95 = np.percentile(simulated, [5, 50, 95])
    return {
        "model_variant": model_variant,
        "forecast_p50": float(p50),
        "forecast_p05": float(p05),
        "forecast_p95": float(p95),
        "simulation_count": n_simulations,
        "random_seed": random_seed,
        "regime_activated": regime_activated,
        "fallback_used": fallback_used,
    }


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


def _recency_weights(years: pd.Series) -> np.ndarray:
    ordered = np.sort(years.to_numpy(dtype=float))
    latest = float(ordered[-1])
    ages = latest - ordered
    return np.power(0.5, ages / RECENCY_HALFLIFE_YEARS)


def _regime_weights(
    years: pd.Series, *, regime: dict[str, object], multiplier: float
) -> np.ndarray:
    weights = np.ones(len(years), dtype=float)
    break_year = regime.get("strongest_break_year")
    if break_year is None:
        return weights
    ordered_years = years.to_numpy(dtype=int)
    weights[ordered_years >= _as_int(break_year)] = multiplier
    return weights


def _regime_evidence(history: pd.DataFrame, *, origin_year: int) -> dict[str, object]:
    frame = pd.DataFrame(
        {
            "country_iso3": history["country_iso3"],
            "year": history["year"],
            "series_name": "carbon_intensity_gdp",
            "value": np.log(history[TARGET_COLUMN].where(history[TARGET_COLUMN] > 0)),
        }
    ).dropna(subset=["value"])
    country = str(history["country_iso3"].iloc[0]) if len(history) else ""
    result = detect_break(
        frame,
        country_iso3=country,
        series_name="carbon_intensity_gdp",
        directionality="higher_is_higher_risk",
        method="segmented_regression",
        minimum_economic_slope_delta=0.01,
        as_of_year=origin_year,
    )
    out = result.model_dump()
    if result.strongest_break_year is not None:
        ordered = frame[frame["year"] <= origin_year].sort_values("year").reset_index(drop=True)
        matches = ordered.index[ordered["year"] >= result.strongest_break_year]
        out["break_index"] = int(matches[0]) if len(matches) else len(ordered)
    else:
        out["break_index"] = len(frame)
    return out


def _agreement_evidence(history: pd.DataFrame, *, origin_year: int) -> dict[str, object]:
    frame = pd.DataFrame(
        {
            "country_iso3": history["country_iso3"],
            "year": history["year"],
            "series_name": "carbon_intensity_gdp",
            "value": np.log(history[TARGET_COLUMN].where(history[TARGET_COLUMN] > 0)),
        }
    ).dropna(subset=["value"])
    results = detect_breaks_by_origin(frame, origins=(origin_year,))
    agreement = method_agreement(results)
    return {str(k): v for k, v in agreement.iloc[0].to_dict().items()} if len(agreement) else {}


def _metric_summary(group: pd.DataFrame) -> dict[str, object]:
    errors = group["absolute_error"].to_numpy(dtype=float)
    return {
        "n_splits": len(group),
        "mae": float(np.mean(errors)),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "median_ae": float(np.median(errors)),
        "coverage_90": float(group["covered_90"].mean()),
        "mean_interval_width_90": float(group["interval_width_90"].mean()),
        "mean_interval_score_90": float(group["interval_score_90"].mean()),
    }


def _paired_rows(results: pd.DataFrame, experimental: str, baseline: str) -> pd.DataFrame:
    keys = ["country_iso3", "origin_year", "target_year"]
    exp = results[results["model_variant"] == experimental][[*keys, "absolute_error"]].rename(
        columns={"absolute_error": "absolute_error_experimental"}
    )
    base = results[results["model_variant"] == baseline][[*keys, "absolute_error"]].rename(
        columns={"absolute_error": "absolute_error_baseline"}
    )
    return exp.merge(base, on=keys, how="inner")


def _paired_improvement(
    results: pd.DataFrame, experimental: str, baseline: str
) -> dict[str, object]:
    paired = _paired_rows(results, experimental, baseline)
    if paired.empty:
        return {
            "country_count": 0,
            "origin_count": 0,
            "countries_improved": 0,
            "origins_improved": 0,
        }
    paired["improved"] = paired["absolute_error_experimental"] < paired["absolute_error_baseline"]
    country_means = paired.groupby("country_iso3")["improved"].mean()
    origin_means = paired.groupby("origin_year")["improved"].mean()
    return {
        "country_count": int(len(country_means)),
        "origin_count": int(len(origin_means)),
        "countries_improved": int(country_means.gt(0.5).sum()),
        "origins_improved": int(origin_means.gt(0.5).sum()),
    }


def _row(frame: pd.DataFrame, index: str) -> pd.Series:
    return cast(pd.Series, frame.loc[index])


def _as_float(value: object) -> float:
    return float(cast(float | int | str, value))


def _as_int(value: object) -> int:
    return int(cast(int | float | str, value))


def _series_float(series: pd.Series, key: str) -> float:
    return _as_float(series[key])


def _cell_float(frame: pd.DataFrame, index: str, column: str) -> float:
    return _as_float(frame.loc[index, column])


def _methods() -> tuple[ScenarioMethod, ...]:
    return (
        "deterministic_trend",
        "empirical_bootstrap",
        "recency_weighted_bootstrap",
        "current_regime_only",
        "regime_weighted_bootstrap",
        "break_confidence_weighted_bootstrap",
        "conditional_regime_weighted_bootstrap",
    )

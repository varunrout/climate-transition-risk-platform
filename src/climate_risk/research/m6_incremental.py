"""M6 incremental-information test -- the core score-integration gate.

Question: do energy-system features add forecasting information beyond
what the existing baseline (deterministic log-linear trend on
carbon_intensity_gdp, `climate_risk.scenarios.engine`) already captures?

Target/proxy, stated explicitly (there is no ground-truth "transition risk"
label anywhere in this project, and none is invented here): the actually
observed carbon_intensity_gdp at each rolling-origin backtest's target
year, using the SAME origins as `climate_risk.backtesting.rolling_origin`
so this result is directly comparable to the existing v1 backtest.

Method: at each (country, origin_year, target_year) split, take the
existing deterministic-trend forecast as the baseline. Fit a linear
correction from energy features (observed only at-or-before origin_year --
computed via the same production `compute_energy_features` function used
for real inference, given a panel truncated to that origin, so there is
exactly one implementation of "derive without future leakage") to the
baseline's log-residual, evaluated via leave-one-country-out
cross-validation (n=19 makes this the only honest form of "out-of-sample"
available -- a random train/test split would let the same country's other
years leak across the split). A permutation test supplies a null
distribution given how small n is.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from climate_risk.features.energy_transition import compute_energy_features
from climate_risk.scenarios.engine import deterministic_trend_baseline

# Same rolling origins as climate_risk.backtesting.rolling_origin's default
# CLI call -- this result is a direct, comparable extension of the existing
# v1 backtest, not a separately-chosen evaluation window.
BACKTEST_ORIGINS: list[tuple[int, int]] = [
    (2010, 2015),
    (2012, 2017),
    (2014, 2019),
    (2015, 2020),
    (2016, 2021),
    (2017, 2022),
]

# The compact set this test evaluates -- matches the eventual candidate
# energy component design (power-system dependence + momentum + fossil
# persistence) rather than an arbitrary feature soup, so a pass/fail here
# answers the actual question being gated.
ENERGY_CANDIDATE_FEATURES: list[str] = [
    "low_carbon_share_elec",
    "clean_power_momentum_pp_per_year",
    "fossil_persistence_mean_pct",
]

# Carried alongside ENERGY_CANDIDATE_FEATURES purely so alternative
# (redundancy-reduced) component formulations can be compared in
# `compare_feature_sets` without a second dataset build -- see
# `climate_risk.research.m6_component_alternatives` (M6 phase 3, section 2).
# coal_share_elec is its own redundancy cluster in ADR 0008's clustering
# (unlike low_carbon_share_elec/fossil_persistence_mean_pct, which are
# near-mechanical mirrors of each other), making it a candidate
# less-redundant "level" signal.
EXTRA_DATASET_COLUMNS: list[str] = ["coal_share_elec"]


def build_incremental_dataset(
    transition_panel: pd.DataFrame,
    energy_panel: pd.DataFrame,
    *,
    countries: list[str],
    origins: list[tuple[int, int]] = BACKTEST_ORIGINS,
    trailing_window_years: int = 5,
) -> pd.DataFrame:
    """One row per (country, origin_year, target_year) split with a valid
    baseline forecast, a valid observed target actual, and computable
    energy features as of origin_year. Rows failing any of those
    eligibility checks are dropped, not imputed."""
    rows: list[dict[str, object]] = []
    for country_iso3 in countries:
        history_full = transition_panel[transition_panel["country_iso3"] == country_iso3]
        for origin_year, target_year in origins:
            history = history_full[history_full["year"] <= origin_year].sort_values("year")
            series = history["carbon_intensity_gdp"]
            years = history["year"]
            baseline = deterministic_trend_baseline(series, years=years, target_year=target_year)
            if baseline is None or baseline.forecast_value <= 0:
                continue

            actual_rows = history_full[history_full["year"] == target_year]
            if actual_rows.empty or pd.isna(actual_rows.iloc[0]["carbon_intensity_gdp"]):
                continue
            actual = float(actual_rows.iloc[0]["carbon_intensity_gdp"])
            if actual <= 0:
                continue

            energy_history = energy_panel[energy_panel["year"] <= origin_year]
            features = compute_energy_features(
                energy_history,
                country_iso3=country_iso3,
                trailing_window_years=trailing_window_years,
            )
            if features is None:
                continue

            row: dict[str, object] = {
                "country_iso3": country_iso3,
                "origin_year": origin_year,
                "target_year": target_year,
                "actual": actual,
                "baseline_forecast": baseline.forecast_value,
                "log_actual": float(np.log(actual)),
                "log_baseline_forecast": float(np.log(baseline.forecast_value)),
            }
            row["residual"] = row["log_actual"] - row["log_baseline_forecast"]  # type: ignore[operator]
            for feature_name in [*ENERGY_CANDIDATE_FEATURES, *EXTRA_DATASET_COLUMNS]:
                row[feature_name] = getattr(features, feature_name)
            rows.append(row)
    return pd.DataFrame(rows)


def leave_one_country_out_comparison(
    dataset: pd.DataFrame, *, feature_columns: list[str] = ENERGY_CANDIDATE_FEATURES
) -> dict[str, object]:
    """Baseline-only MAE vs baseline+energy-corrected MAE, both out-of-sample
    via leave-one-country-out. Returns an `error` key instead of a result
    when there isn't enough complete-case data to fit honestly."""
    complete = dataset.dropna(subset=[*feature_columns, "residual"])
    countries = sorted(complete["country_iso3"].unique())
    min_countries_for_cv = len(feature_columns) + 3
    if len(countries) < min_countries_for_cv:
        return {
            "error": (
                f"only {len(countries)} countries have complete data for "
                f"{feature_columns}; need >= {min_countries_for_cv} for honest leave-one-country-out CV"
            ),
            "n_countries_with_complete_data": len(countries),
        }

    baseline_abs_errors: list[float] = []
    augmented_abs_errors: list[float] = []
    n_splits_evaluated = 0
    for held_out in countries:
        train = complete[complete["country_iso3"] != held_out]
        test = complete[complete["country_iso3"] == held_out]
        if len(train) < len(feature_columns) + 2:
            continue

        x_train = sm.add_constant(train[feature_columns], has_constant="add")
        model = sm.OLS(train["residual"].to_numpy(dtype=float), x_train.to_numpy(dtype=float)).fit()

        x_test = sm.add_constant(test[feature_columns], has_constant="add")
        predicted_residual = model.predict(x_test.to_numpy(dtype=float))

        baseline_forecast = np.exp(test["log_baseline_forecast"].to_numpy(dtype=float))
        augmented_forecast = np.exp(
            test["log_baseline_forecast"].to_numpy(dtype=float) + predicted_residual
        )
        actual = test["actual"].to_numpy(dtype=float)

        baseline_abs_errors.extend(np.abs(baseline_forecast - actual).tolist())
        augmented_abs_errors.extend(np.abs(augmented_forecast - actual).tolist())
        n_splits_evaluated += len(test)

    if not baseline_abs_errors:
        return {
            "error": "no held-out fold had enough training rows to fit",
            "n_countries_with_complete_data": len(countries),
        }

    baseline_mae = float(np.mean(baseline_abs_errors))
    augmented_mae = float(np.mean(augmented_abs_errors))
    return {
        "feature_columns": feature_columns,
        "n_splits": n_splits_evaluated,
        "n_countries_in_cv": len(countries),
        "baseline_mae": baseline_mae,
        "augmented_mae": augmented_mae,
        "mae_improvement": baseline_mae - augmented_mae,
        "mae_improvement_pct": (
            (baseline_mae - augmented_mae) / baseline_mae if baseline_mae else None
        ),
    }


def permutation_test(
    dataset: pd.DataFrame,
    *,
    feature_columns: list[str] = ENERGY_CANDIDATE_FEATURES,
    n_permutations: int = 200,
    random_seed: int = 42,
) -> dict[str, object]:
    """Null distribution for the leave-one-country-out MAE improvement:
    shuffle the energy feature rows relative to (residual, baseline_forecast,
    actual) `n_permutations` times, breaking any true relationship, and see
    how often a shuffled ("fake") model achieves an improvement at least as
    large as the real one. At n=19 this is more honest than trusting a
    single point-estimate R^2/MAE difference.
    """
    complete = dataset.dropna(subset=[*feature_columns, "residual"]).reset_index(drop=True)
    observed = leave_one_country_out_comparison(dataset, feature_columns=feature_columns)
    if "error" in observed:
        return {"error": observed["error"], "observed": observed}

    rng = np.random.default_rng(random_seed)
    improvements: list[float] = []
    feature_matrix = complete[feature_columns].to_numpy(dtype=float)
    for _ in range(n_permutations):
        shuffled = complete.copy()
        permuted_idx = rng.permutation(len(complete))
        shuffled[feature_columns] = feature_matrix[permuted_idx]
        result = leave_one_country_out_comparison(shuffled, feature_columns=feature_columns)
        if "error" not in result:
            improvement = result["mae_improvement"]
            assert isinstance(improvement, float)
            improvements.append(improvement)

    observed_improvement = observed["mae_improvement"]
    assert isinstance(observed_improvement, float)
    null_array = np.array(improvements)
    p_value = float(np.mean(null_array >= observed_improvement)) if improvements else None
    # "percentile of observed improvement within the null" -- what fraction
    # of the null (fake-relationship) improvements fall AT OR BELOW the
    # real, observed improvement. High (e.g. >95) means the observed result
    # sits at the extreme upper tail of what pure chance produces here.
    percentile_within_null = (
        float(np.mean(null_array <= observed_improvement) * 100.0) if improvements else None
    )
    return {
        "observed_mae_improvement": observed_improvement,
        "n_permutations_requested": n_permutations,
        "n_permutations_run": len(improvements),
        "random_seed": random_seed,
        "permutation_p_value": p_value,
        "observed_improvement_percentile_within_null": percentile_within_null,
        "null_improvement_mean": float(np.mean(improvements)) if improvements else None,
        "null_improvement_std": float(np.std(improvements, ddof=1))
        if len(improvements) > 1
        else None,
    }


def leave_one_country_out_comparison_by_origin(
    dataset: pd.DataFrame, *, feature_columns: list[str] = ENERGY_CANDIDATE_FEATURES
) -> pd.DataFrame:
    """The same leave-one-country-out comparison, computed separately per
    origin_year rather than pooled -- reveals whether an apparent
    improvement is broad-based across the backtest's historical windows or
    concentrated in one favourable period (M6 phase 3, section 4)."""
    rows = []
    for origin_year in sorted(dataset["origin_year"].unique()):
        subset = dataset[dataset["origin_year"] == origin_year]
        target_years = subset["target_year"].unique()
        target_year = int(target_years[0]) if len(target_years) == 1 else None
        result = leave_one_country_out_comparison(subset, feature_columns=feature_columns)
        rows.append({"origin_year": int(origin_year), "target_year": target_year, **result})
    return pd.DataFrame(rows)


def leave_one_origin_out_comparison(
    dataset: pd.DataFrame, *, feature_columns: list[str] = ENERGY_CANDIDATE_FEATURES
) -> dict[str, object]:
    """Held-out unit is an entire origin_year (all countries at once) rather
    than a country -- tests whether the fitted correction generalises across
    time, not just across countries. With only 6 origins this is a coarser,
    lower-power test than the country-wise CV and is reported alongside it,
    not instead of it."""
    complete = dataset.dropna(subset=[*feature_columns, "residual"])
    origins = sorted(complete["origin_year"].unique())
    if len(origins) < 3:
        return {
            "error": f"only {len(origins)} distinct origins available; need >= 3 for leave-one-origin-out CV",
            "n_origins": len(origins),
        }

    baseline_abs_errors: list[float] = []
    augmented_abs_errors: list[float] = []
    n_splits_evaluated = 0
    for held_out_origin in origins:
        train = complete[complete["origin_year"] != held_out_origin]
        test = complete[complete["origin_year"] == held_out_origin]
        if len(train) < len(feature_columns) + 2 or test.empty:
            continue

        x_train = sm.add_constant(train[feature_columns], has_constant="add")
        model = sm.OLS(train["residual"].to_numpy(dtype=float), x_train.to_numpy(dtype=float)).fit()

        x_test = sm.add_constant(test[feature_columns], has_constant="add")
        predicted_residual = model.predict(x_test.to_numpy(dtype=float))

        baseline_forecast = np.exp(test["log_baseline_forecast"].to_numpy(dtype=float))
        augmented_forecast = np.exp(
            test["log_baseline_forecast"].to_numpy(dtype=float) + predicted_residual
        )
        actual = test["actual"].to_numpy(dtype=float)

        baseline_abs_errors.extend(np.abs(baseline_forecast - actual).tolist())
        augmented_abs_errors.extend(np.abs(augmented_forecast - actual).tolist())
        n_splits_evaluated += len(test)

    if not baseline_abs_errors:
        return {
            "error": "no held-out origin had enough training rows to fit",
            "n_origins": len(origins),
        }

    baseline_mae = float(np.mean(baseline_abs_errors))
    augmented_mae = float(np.mean(augmented_abs_errors))
    return {
        "feature_columns": feature_columns,
        "n_splits": n_splits_evaluated,
        "n_origins_in_cv": len(origins),
        "baseline_mae": baseline_mae,
        "augmented_mae": augmented_mae,
        "mae_improvement": baseline_mae - augmented_mae,
        "mae_improvement_pct": (
            (baseline_mae - augmented_mae) / baseline_mae if baseline_mae else None
        ),
    }


def compare_feature_sets(dataset: pd.DataFrame, feature_sets: dict[str, list[str]]) -> pd.DataFrame:
    """Run leave-one-country-out comparison for each named candidate
    component formulation (M6 phase 3, section 2: 3-signal vs 2-signal vs
    alternatives) so they can be compared on equal footing."""
    rows = []
    for name, columns in feature_sets.items():
        result = leave_one_country_out_comparison(dataset, feature_columns=columns)
        rows.append({"formulation": name, "n_features": len(columns), **result})
    return pd.DataFrame(rows)


def ablation_comparison(dataset: pd.DataFrame) -> pd.DataFrame:
    """Each candidate feature alone vs the full compact set -- shows whether
    the improvement (if any) is driven by one signal or genuinely needs the
    combination."""
    rows = []
    for feature_name in ENERGY_CANDIDATE_FEATURES:
        result = leave_one_country_out_comparison(dataset, feature_columns=[feature_name])
        rows.append({"feature_set": feature_name, **result})
    full_result = leave_one_country_out_comparison(
        dataset, feature_columns=ENERGY_CANDIDATE_FEATURES
    )
    rows.append({"feature_set": "all_three_combined", **full_result})
    return pd.DataFrame(rows)

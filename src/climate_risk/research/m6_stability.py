"""M6 feature stability: is a derived indicator stable enough to use in a
sovereign risk score, or does it swing on one noisy annual observation?

Three independent probes, each returning a small DataFrame/dict so the
result is auditable rather than a single opaque "stability score":
1. year-to-year volatility of the raw source series (per country).
2. sensitivity of the derived trend/momentum features to the trailing
   window length (3 vs 5 vs 7 years).
3. sensitivity to a one-year data revision (drop the latest observed year
   and recompute -- the same shape of test as a genuine late-reported or
   later-revised annual figure would produce).
"""

from __future__ import annotations

import pandas as pd
from scipy import stats

from climate_risk.features.energy_transition import compute_energy_features_for_panel

LOOKBACK_WINDOWS_TESTED = (3, 5, 7)


def yoy_volatility(raw_energy_panel: pd.DataFrame, *, column: str) -> pd.DataFrame:
    """Per-country std-dev of year-over-year change in `column` (percentage
    points), plus the number of YoY changes it's based on. NaN (not 0) when
    a country has fewer than 2 YoY changes -- insufficient history is not
    the same as zero volatility."""
    rows = []
    for country_iso3, group in raw_energy_panel.groupby("country_iso3"):
        series = group.dropna(subset=[column]).sort_values("year")[column]
        diffs = series.diff().dropna()
        rows.append(
            {
                "country_iso3": country_iso3,
                "n_yoy_changes": len(diffs),
                "yoy_std_pp": float(diffs.std(ddof=1)) if len(diffs) >= 2 else None,
                "yoy_mean_abs_pp": float(diffs.abs().mean()) if len(diffs) >= 1 else None,
            }
        )
    return pd.DataFrame(rows).sort_values("country_iso3").reset_index(drop=True)


def lookback_window_sensitivity(
    energy_panel: pd.DataFrame, *, windows: tuple[int, ...] = LOOKBACK_WINDOWS_TESTED
) -> dict[str, object]:
    """Recompute the derived features under each window in `windows` and
    compare. A feature whose cross-country rank order flips substantially
    between a 3yr and 7yr trailing window is telling you the trailing
    window choice -- not the underlying signal -- is driving the score.
    """
    per_window = {
        w: compute_energy_features_for_panel(energy_panel, trailing_window_years=w) for w in windows
    }
    target_columns = [
        "coal_trend_pp_per_year",
        "clean_power_momentum_pp_per_year",
        "renewable_buildout_rate_pp_per_year",
    ]

    pairwise_rows = []
    for column in target_columns:
        for i, w1 in enumerate(windows):
            for w2 in windows[i + 1 :]:
                f1 = per_window[w1].set_index("country_iso3")[column]
                f2 = per_window[w2].set_index("country_iso3")[column]
                common = f1.dropna().index.intersection(f2.dropna().index)
                if len(common) < 3:
                    spearman = None
                    mean_abs_diff = None
                else:
                    spearman = float(stats.spearmanr(f1[common], f2[common]).correlation)
                    mean_abs_diff = float((f1[common] - f2[common]).abs().mean())
                pairwise_rows.append(
                    {
                        "feature": column,
                        "window_a": w1,
                        "window_b": w2,
                        "n_common_countries": len(common),
                        "spearman_rank_correlation": spearman,
                        "mean_abs_value_difference_pp_per_year": mean_abs_diff,
                    }
                )
    return {
        "windows_tested": list(windows),
        "pairwise_comparisons": pd.DataFrame(pairwise_rows),
    }


def one_year_revision_sensitivity(
    energy_panel: pd.DataFrame, *, trailing_window_years: int = 5
) -> pd.DataFrame:
    """Drop each country's single latest observed year and recompute its
    features -- proxies for "what if this year's figure hadn't landed yet /
    gets revised". Reports both the raw value shift and whether the
    cross-country percentile rank would have crossed a full decile.
    """
    full = compute_energy_features_for_panel(
        energy_panel, trailing_window_years=trailing_window_years
    )
    if full.empty:
        return pd.DataFrame()

    latest_year_by_country = energy_panel.groupby("country_iso3")["year"].max()
    # Each country's own latest year is pulled independently (not a single
    # shared cutoff), since the point is "what if this one country's most
    # recent figure hadn't landed / gets revised", not a global truncation.
    rows = []
    for country_iso3 in full["country_iso3"]:
        truncated_panel = energy_panel[
            ~(
                (energy_panel["country_iso3"] == country_iso3)
                & (energy_panel["year"] == latest_year_by_country[country_iso3])
            )
        ]
        truncated_features = compute_energy_features_for_panel(
            truncated_panel, trailing_window_years=trailing_window_years
        )
        before = full[full["country_iso3"] == country_iso3].iloc[0]
        after_rows = truncated_features[truncated_features["country_iso3"] == country_iso3]
        if after_rows.empty:
            rows.append(
                {
                    "country_iso3": country_iso3,
                    "dropped_year": int(latest_year_by_country[country_iso3]),
                    "low_carbon_share_elec_before": before["low_carbon_share_elec"],
                    "low_carbon_share_elec_after": None,
                    "low_carbon_percentile_before": before["low_carbon_share_elec_percentile"],
                    "low_carbon_percentile_after": None,
                    "percentile_shift_deciles": None,
                    "dropped_from_panel_when_year_removed": True,
                }
            )
            continue
        after = after_rows.iloc[0]
        before_pctl = before["low_carbon_share_elec_percentile"]
        after_pctl = after["low_carbon_share_elec_percentile"]
        shift_deciles = (
            abs(before_pctl - after_pctl) * 10.0
            if pd.notna(before_pctl) and pd.notna(after_pctl)
            else None
        )
        rows.append(
            {
                "country_iso3": country_iso3,
                "dropped_year": int(latest_year_by_country[country_iso3]),
                "low_carbon_share_elec_before": before["low_carbon_share_elec"],
                "low_carbon_share_elec_after": after["low_carbon_share_elec"],
                "low_carbon_percentile_before": before_pctl,
                "low_carbon_percentile_after": after_pctl,
                "percentile_shift_deciles": shift_deciles,
                "dropped_from_panel_when_year_removed": False,
            }
        )
    return pd.DataFrame(rows).sort_values("country_iso3").reset_index(drop=True)


def summarise_stability(
    lookback_sensitivity: dict[str, object], revision_sensitivity: pd.DataFrame
) -> dict[str, float | int | None]:
    pairwise = lookback_sensitivity["pairwise_comparisons"]
    assert isinstance(pairwise, pd.DataFrame)
    valid = pairwise.dropna(subset=["spearman_rank_correlation"])

    revision_valid = revision_sensitivity.dropna(subset=["percentile_shift_deciles"])
    return {
        "mean_lookback_spearman_correlation": (
            float(valid["spearman_rank_correlation"].mean()) if len(valid) else None
        ),
        "min_lookback_spearman_correlation": (
            float(valid["spearman_rank_correlation"].min()) if len(valid) else None
        ),
        "mean_one_year_revision_percentile_shift_deciles": (
            float(revision_valid["percentile_shift_deciles"].mean())
            if len(revision_valid)
            else None
        ),
        "max_one_year_revision_percentile_shift_deciles": (
            float(revision_valid["percentile_shift_deciles"].max()) if len(revision_valid) else None
        ),
        "countries_dropped_from_panel_by_one_year_revision": int(
            revision_sensitivity["dropped_from_panel_when_year_removed"].sum()
        )
        if len(revision_sensitivity)
        else 0,
    }

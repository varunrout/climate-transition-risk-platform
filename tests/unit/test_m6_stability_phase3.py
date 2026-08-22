from __future__ import annotations

import pandas as pd

from climate_risk.research.m6_stability import (
    lookback_instability_by_feature,
    lookback_window_country_deltas,
    lookback_window_sensitivity,
    theil_sen_vs_ols_lookback_stability,
)

YEARS = list(range(2010, 2021))  # 11 years


def _energy_panel(countries: list[str], *, noisy: set[str] | None = None) -> pd.DataFrame:
    noisy = noisy or set()
    rows = []
    for idx, country in enumerate(countries):
        base = 20.0 + idx * 5.0
        growth = 1.0 + idx * 0.3
        for i, year in enumerate(YEARS):
            noise = 15.0 if (country in noisy and i == len(YEARS) - 1) else 0.0
            low_carbon = base + growth * i + noise
            rows.append(
                {
                    "country_iso3": country,
                    "year": year,
                    "low_carbon_share_elec": low_carbon,
                    "fossil_share_elec": 100.0 - low_carbon,
                    "coal_share_elec": (100.0 - low_carbon) * 0.6,
                    "renewables_share_elec": low_carbon * 0.8,
                    "fossil_persistence_mean_pct": 100.0 - low_carbon,
                }
            )
    return pd.DataFrame(rows)


def test_lookback_instability_by_feature_ranks_features() -> None:
    countries = ["AAA", "BBB", "CCC", "DDD"]
    panel = _energy_panel(countries, noisy={"AAA"})
    lookback = lookback_window_sensitivity(panel)
    pairwise = lookback["pairwise_comparisons"]
    assert isinstance(pairwise, pd.DataFrame)
    summary = lookback_instability_by_feature(pairwise)
    assert set(summary.columns) >= {
        "feature",
        "mean_spearman_correlation",
        "min_spearman_correlation",
    }
    assert len(summary) > 0


def test_lookback_instability_by_feature_empty_input() -> None:
    empty = pd.DataFrame(columns=["feature", "window_a", "window_b", "spearman_rank_correlation"])
    summary = lookback_instability_by_feature(empty)
    assert summary.empty


def test_lookback_window_country_deltas_identifies_noisy_country() -> None:
    countries = ["AAA", "BBB", "CCC", "DDD"]
    panel = _energy_panel(countries, noisy={"AAA"})
    deltas = lookback_window_country_deltas(panel)
    assert not deltas.empty
    # the country with an injected one-year noise spike should show up among
    # the largest deltas for low_carbon-derived features.
    top_countries = set(deltas.head(5)["country_iso3"])
    assert "AAA" in top_countries


def test_theil_sen_vs_ols_returns_both_estimators() -> None:
    countries = ["AAA", "BBB", "CCC", "DDD"]
    panel = _energy_panel(countries, noisy={"AAA"})
    result = theil_sen_vs_ols_lookback_stability(panel, column="low_carbon_share_elec")
    assert "ols_mean_pairwise_spearman" in result
    assert "theil_sen_mean_pairwise_spearman" in result

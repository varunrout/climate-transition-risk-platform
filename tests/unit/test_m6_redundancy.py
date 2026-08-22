from __future__ import annotations

import numpy as np
import pandas as pd

from climate_risk.research.m6_redundancy import (
    correlation_matrices,
    redundancy_groups,
    variance_inflation_factors,
)

COLUMNS = ["a", "b", "c"]


def _panel(n: int = 19, *, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    a = rng.normal(0, 1, n)
    b = a * 0.98 + rng.normal(0, 0.05, n)  # near-duplicate of a
    c = rng.normal(0, 1, n)  # independent
    return pd.DataFrame({"country_iso3": [f"C{i}" for i in range(n)], "a": a, "b": b, "c": c})


def test_correlation_matrices_returns_pearson_and_spearman() -> None:
    panel = _panel()
    result = correlation_matrices(panel, columns=COLUMNS)
    assert set(result.keys()) == {"pearson", "spearman"}
    assert result["pearson"].loc["a", "b"] > 0.9


def test_redundant_features_grouped_together() -> None:
    panel = _panel()
    groups = redundancy_groups(panel, columns=COLUMNS, threshold=0.7)
    group_by_feature = groups.set_index("feature")["redundancy_group"]
    assert group_by_feature["a"] == group_by_feature["b"]
    assert group_by_feature["c"] != group_by_feature["a"]


def test_vif_reports_note_when_insufficient_rows() -> None:
    tiny_panel = _panel(n=3)
    result = variance_inflation_factors(tiny_panel, columns=COLUMNS)
    assert result["vif"].isna().all()
    assert (result["note"] != "").all()


def test_vif_computed_when_enough_rows() -> None:
    panel = _panel(n=30)
    result = variance_inflation_factors(panel, columns=COLUMNS)
    assert result["vif"].notna().any()
    # a and b are near-duplicates -> high VIF for both
    a_vif = result.set_index("feature").loc["a", "vif"]
    c_vif = result.set_index("feature").loc["c", "vif"]
    assert a_vif > c_vif
